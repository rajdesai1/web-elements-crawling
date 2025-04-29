#!/usr/bin/env python3
"""
Fast and robust sitemap parser for extracting URLs from websites at scale.
Supports various sitemap formats and handles errors gracefully.
"""

import gzip
import io
import json
import os
import random
import re  # Global import for regex operations
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Set, TextIO, Tuple, Union
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config.settings import SITEMAP_SETTINGS, SITEMAPS_DIR
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# XML Namespaces for sitemap parsing
NAMESPACES = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
    "video": "http://www.google.com/schemas/sitemap-video/1.1",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "mobile": "http://www.google.com/schemas/sitemap-mobile/1.0"
}

class SitemapParser:
    """Fast and robust sitemap parser for various formats."""
    
    def __init__(
        self,
        base_url: str,
        max_retries: int = 3,
        max_urls: int = 10000,
        max_workers: int = 5,
        timeout: int = 30,
        user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        rate_limit_delay: float = 0.5,
        output_file: Optional[str] = None,
        max_sitemaps_per_level: Optional[int] = None,
        urls_per_sitemap: Optional[int] = None,
        dynamic_sampling: bool = False,
        sampling_factor: float = 0.1,  # 10% by default
        dual_mode: bool = False,  # Run both sample and full modes simultaneously
        base_output_dir: str = "sitemap_results"  # Base directory for output files
    ):
        """
        Initialize the sitemap parser.
        
        Args:
            base_url: Base URL for the website
            max_retries: Maximum number of retries for failed requests
            max_urls: Maximum number of URLs to extract
            max_workers: Maximum number of concurrent workers
            timeout: Request timeout in seconds
            user_agent: User agent to use for requests
            rate_limit_delay: Delay between requests to prevent rate limiting (in seconds)
            output_file: Path to file where URLs should be saved (optional)
            max_sitemaps_per_level: Maximum number of sitemaps to process at each level of nesting
                                   (if None, will be determined dynamically when dynamic_sampling=True)
            urls_per_sitemap: Number of URLs to extract from each final sitemap
                             (if None, will be determined dynamically when dynamic_sampling=True)
            dynamic_sampling: Whether to use dynamic sampling instead of fixed limits
            sampling_factor: Percentage (0.0-1.0) of items to sample when using dynamic sampling
            dual_mode: Run both sample and full modes simultaneously
            base_output_dir: Base directory for output files when using dual mode
        """
        self.base_url = base_url.rstrip('/')
        self.domain = self._extract_domain(base_url)
        self.max_retries = max_retries
        self.max_urls = max_urls
        self.max_workers = max_workers
        self.timeout = timeout
        self.user_agent = user_agent
        self.rate_limit_delay = rate_limit_delay
        self.max_sitemaps_per_level = max_sitemaps_per_level
        self.urls_per_sitemap = urls_per_sitemap
        self.dynamic_sampling = dynamic_sampling
        self.sampling_factor = max(0.01, min(1.0, sampling_factor))  # Ensure between 1% and 100%
        self.dual_mode = dual_mode
        self.base_output_dir = base_output_dir
        
        self.visited_sitemaps: Set[str] = set()
        self.sitemap_urls: List[str] = []
        
        # Initialize session
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        
        # For rate limit handling
        self.last_request_time = 0
        self.current_delay = rate_limit_delay
        
        if self.dual_mode:
            # Setup for dual mode (both sample and full simultaneously)
            logger.info(f"Running in dual mode (processing both sample and full modes)")
            
            # Create output directories
            os.makedirs(f"{self.base_output_dir}/sample", exist_ok=True)
            os.makedirs(f"{self.base_output_dir}/full", exist_ok=True)
            
            # Prepare output file names
            if output_file:
                file_name = os.path.basename(output_file)
            else:
                file_name = f"{self.domain}_urls.txt"
                
            self.sample_output_file = f"{self.base_output_dir}/sample/{file_name}"
            self.full_output_file = f"{self.base_output_dir}/full/{file_name}"
            
            logger.info(f"Sample mode results will be saved to: {self.sample_output_file}")
            logger.info(f"Full mode results will be saved to: {self.full_output_file}")
            
            # Initialize URL collections for both modes
            self.sample_urls: Set[str] = set()
            self.full_urls: Set[str] = set()
            
            # Initialize output file handles
            self.sample_output_handle = None
            self.full_output_handle = None
            
            # Setup sample output file
            self._setup_output_file(self.sample_output_file, 'sample')
            
            # Setup full output file
            self._setup_output_file(self.full_output_file, 'full')
        else:
            # Single mode operation
            self.output_file = output_file
            self.urls: Set[str] = set()
            self.output_file_handle = None
            self._setup_output_file(output_file)
    
    def _setup_output_file(self, file_path: Optional[str], mode: str = None) -> None:
        """
        Initialize an output file in text mode.
        
        Args:
            file_path: Path to the output file
            mode: 'sample' or 'full' when in dual mode, None for single mode
        """
        if not file_path:
            return
            
        try:
            if self.dual_mode and mode:
                file_handle_attr = f"{mode}_output_handle"
            else:
                file_handle_attr = "output_file_handle"
            
            # Open file in text mode
            file_handle = open(file_path, 'w', encoding='utf-8')
            setattr(self, file_handle_attr, file_handle)
            logger.debug(f"Initialized output file: {file_path}")
        except Exception as e:
            logger.error(f"Error setting up output file {file_path}: {e}")
    
    def _write_url_to_output(self, url: str, mode: str = None) -> None:
        """
        Write a URL to the output file in text mode.
        
        Args:
            url: URL to write
            mode: 'sample' or 'full' when in dual mode, None for single mode
        """
        if self.dual_mode and mode:
            file_handle = getattr(self, f"{mode}_output_handle", None)
        else:
            file_handle = self.output_file_handle
        
        if not file_handle:
            return
            
        try:
            # Write URL to file (text mode only)
            file_handle.write(f"{url}\n")
        except Exception as e:
            logger.error(f"Error writing URL to output file: {e}")
    
    def close(self) -> None:
        """Close resources."""
        if self.dual_mode:
            # Close sample mode file
            if hasattr(self, 'sample_output_handle') and self.sample_output_handle:
                try:
                    self.sample_output_handle.close()
                    logger.debug(f"Closed sample output file")
                except Exception as e:
                    logger.error(f"Error closing sample output file: {e}")
            
            # Close full mode file
            if hasattr(self, 'full_output_handle') and self.full_output_handle:
                try:
                    self.full_output_handle.close()
                    logger.debug(f"Closed full output file")
                except Exception as e:
                    logger.error(f"Error closing full output file: {e}")
        else:
            # Regular close
            if self.output_file_handle:
                try:
                    self.output_file_handle.close()
                except Exception as e:
                    logger.error(f"Error closing output file: {e}")
        
        self.session.close()
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lstrip('www.')
    
    def _wait_before_request(self) -> None:
        """Wait between requests to respect rate limits."""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.current_delay:
            # Calculate how much more we need to wait
            wait_time = self.current_delay - elapsed
            # Add a small random delay to avoid synchronization
            wait_time += random.uniform(0, 0.5)
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def _fetch_sitemap(self, url: str) -> Optional[bytes]:
        """Fetch sitemap content - tries only once with no retries."""
        try:
            # Wait before making the request
            self._wait_before_request()
            
            # Make the request
            logger.debug(f"Fetching sitemap: {url}")
            response = self.session.get(url, timeout=self.timeout, stream=True)
            
            # If request wasn't successful, just return None
            if not response.ok:
                logger.warning(f"Failed to fetch sitemap (status code {response.status_code}): {url}")
                return None
            
            # Determine the content type
            content_type = response.headers.get('Content-Type', '').lower()
            content_disposition = response.headers.get('Content-Disposition', '').lower()
            
            # Handle different content types
            if 'gzip' in content_type or 'gzip' in content_disposition or url.endswith('.gz'):
                try:
                    return gzip.decompress(response.content)
                except Exception as e:
                    logger.warning(f"File has .gz extension but isn't gzipped: {url}. Using as regular content.")
                    return response.content
            elif 'zip' in content_type or 'zip' in content_disposition or url.endswith('.zip'):
                # Handle ZIP archives
                try:
                    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
                        # Find the main sitemap file in the archive
                        sitemap_files = [f for f in zip_file.namelist() if f.endswith('.xml')]
                        if sitemap_files:
                            # Use the first XML file in the archive
                            return zip_file.read(sitemap_files[0])
                        else:
                            logger.warning(f"No XML files found in ZIP archive: {url}")
                            return None
                except Exception as e:
                    logger.warning(f"File has .zip extension but isn't a valid ZIP: {url}. Using as regular content.")
                    return response.content
            else:
                # Regular content
                return response.content
                
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching sitemap: {url}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error fetching sitemap {url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching sitemap {url}: {e}")
            
        return None
    
    def _parse_xml_sitemap(self, content: bytes) -> Tuple[List[str], List[str]]:
        """Parse XML sitemap content."""
        urls = []
        nested_sitemaps = []
        
        try:
            # Remove any BOM and decode to string
            content_str = content.decode('utf-8-sig')
            root = ET.fromstring(content_str)
            
            # Handle both sitemap index and URL set
            # Find the namespace
            ns_match = re.search(r'\{([^}]+)\}', root.tag) if '}' in root.tag else None
            namespace = ns_match.group(1) if ns_match else ''
            ns = {'ns': namespace} if namespace else {}
            
            # Check if it's a sitemap index
            if root.tag.endswith('sitemapindex'):
                for sitemap in root.findall('.//ns:sitemap/ns:loc', ns) or root.findall('.//sitemap/loc'):
                    if sitemap.text:
                        nested_sitemaps.append(sitemap.text.strip())
            # Check if it's a urlset
            elif root.tag.endswith('urlset'):
                for url in root.findall('.//ns:url/ns:loc', ns) or root.findall('.//url/loc'):
                    if url.text:
                        urls.append(url.text.strip())
            
        except Exception as e:
            logger.error(f"Error parsing XML sitemap: {e}")
        
        return urls, nested_sitemaps
    
    def _parse_plain_text_sitemap(self, content: bytes) -> Tuple[List[str], List[str]]:
        """Parse plain text sitemap."""
        urls = []
        try:
            content_str = content.decode('utf-8', errors='ignore')
            lines = content_str.splitlines()
            
            for line in lines:
                line = line.strip()
                if line and line.startswith(('http://', 'https://')):
                    urls.append(line)
        except Exception as e:
            logger.error(f"Error parsing plain text sitemap: {e}")
        
        return urls, []
    
    def _parse_rss_feed(self, content: bytes) -> Tuple[List[str], List[str]]:
        """Parse RSS or Atom feed."""
        urls = []
        
        try:
            soup = BeautifulSoup(content, 'xml')
            
            # Check for RSS feed
            rss_items = soup.find_all('item')
            for item in rss_items:
                link = item.find('link')
                if link and link.text:
                    urls.append(link.text.strip())
            
            # Check for Atom feed
            atom_entries = soup.find_all('entry')
            for entry in atom_entries:
                link = entry.find('link')
                if link and link.get('href'):
                    urls.append(link.get('href').strip())
        except Exception as e:
            logger.error(f"Error parsing RSS/Atom feed: {e}")
        
        return urls, []
    
    def _parse_json_sitemap(self, content: bytes) -> Tuple[List[str], List[str]]:
        """Parse JSON sitemap."""
        urls = []
        nested_sitemaps = []
        
        try:
            content_str = content.decode('utf-8', errors='ignore')
            data = json.loads(content_str)
            
            # Case 1: Array of URLs
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str) and item.startswith(('http://', 'https://')):
                        urls.append(item)
                    elif isinstance(item, dict):
                        # Check for URL in common fields
                        for field in ['url', 'loc', 'link', 'href']:
                            if field in item and isinstance(item[field], str) and item[field].startswith(('http://', 'https://')):
                                urls.append(item[field])
                                break
            
            # Case 2: Object with URLs array
            elif isinstance(data, dict):
                # Check for URLs array
                for field in ['urls', 'urlset', 'items', 'entries']:
                    if field in data and isinstance(data[field], list):
                        items = data[field]
                        for item in items:
                            if isinstance(item, str) and item.startswith(('http://', 'https://')):
                                urls.append(item)
                            elif isinstance(item, dict):
                                for url_field in ['url', 'loc', 'link', 'href']:
                                    if url_field in item and isinstance(item[url_field], str) and item[url_field].startswith(('http://', 'https://')):
                                        urls.append(item[url_field])
                                        break
                
                # Check for sitemaps array
                for field in ['sitemaps', 'sitemapindex']:
                    if field in data and isinstance(data[field], list):
                        items = data[field]
                        for item in items:
                            if isinstance(item, str) and item.startswith(('http://', 'https://')):
                                nested_sitemaps.append(item)
                            elif isinstance(item, dict) and 'loc' in item and isinstance(item['loc'], str) and item['loc'].startswith(('http://', 'https://')):
                                nested_sitemaps.append(item['loc'])
        except Exception as e:
            logger.error(f"Error parsing JSON sitemap: {e}")
        
        return urls, nested_sitemaps
    
    def _parse_html_sitemap(self, content: bytes) -> Tuple[List[str], List[str]]:
        """Parse HTML sitemap by extracting links."""
        urls = []
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            base_url = self.base_url
            
            # Find all links
            for link in soup.find_all('a', href=True):
                href = link['href'].strip()
                # Handle relative URLs
                if href.startswith('/'):
                    href = f"{base_url}{href}"
                elif not href.startswith(('http://', 'https://')):
                    href = f"{base_url}/{href}"
                
                # Skip anchors, javascript, mailto, etc.
                if href.startswith(('http://', 'https://')) and not href.startswith(('javascript:', 'mailto:', 'tel:')):
                    # Only include URLs from the same domain
                    if self.domain in self._extract_domain(href):
                        urls.append(href)
        except Exception as e:
            logger.error(f"Error parsing HTML sitemap: {e}")
        
        return urls, []
    
    def _parse_sitemap(self, content: bytes) -> Tuple[List[str], List[str]]:
        """Parse sitemap content in various formats."""
        # Try parsing as XML first
        try:
            # Check if it looks like XML
            if content.startswith(b'<?xml') or b'<urlset' in content or b'<sitemapindex' in content:
                return self._parse_xml_sitemap(content)
        except Exception:
            pass

        # Try JSON
        try:
            if content.startswith(b'{') or content.startswith(b'['):
                return self._parse_json_sitemap(content)
        except Exception:
            pass

        # Check if it's HTML
        try:
            if b'<!DOCTYPE html>' in content or b'<html' in content:
                return self._parse_html_sitemap(content)
        except Exception:
            pass

        # Check if it's RSS/Atom
        try:
            if b'<rss' in content or b'<feed' in content:
                return self._parse_rss_feed(content)
        except Exception:
            pass

        # Fall back to plain text
        return self._parse_plain_text_sitemap(content)
    
    def _calculate_dynamic_limit(self, total_items: int, level: int = 0) -> int:
        """
        Calculate a dynamic limit based on the total number of items.
        
        Args:
            total_items: Total number of items (URLs or sitemaps)
            level: Current depth level (used to adjust sampling for deeper levels)
            
        Returns:
            Number of items to process
        """
        if not self.dynamic_sampling:
            # If not using dynamic sampling, use the fixed limits
            if level == 0 and self.max_sitemaps_per_level is not None:
                return self.max_sitemaps_per_level
            elif level > 0 and self.urls_per_sitemap is not None:
                return self.urls_per_sitemap
                
        # Base factor adjusts depending on depth
        factor = self.sampling_factor / (level + 1)
        
        # Calculate number of items to sample
        num_items = max(1, int(total_items * factor))
        
        # Apply reasonable limits based on total items
        if total_items <= 5:
            # For very small sets, take all items
            return total_items
        elif total_items <= 20:
            # For small sets, take at least 3 or 30%, whichever is greater
            return max(3, num_items)
        elif total_items <= 100:
            # For medium sets, take at least 5 or calculated amount
            return max(5, num_items)
        else:
            # For large sets, use the factor but ensure we take at least 10
            return max(10, num_items)
    
    def discover_sitemaps(self) -> List[str]:
        """Discover sitemaps from robots.txt and common locations."""
        sitemap_urls = []
        
        # Check robots.txt first
        robots_url = f"{self.base_url}/robots.txt"
        try:
            self._wait_before_request()
            logger.info(f"Checking {robots_url} for sitemaps")
            response = self.session.get(robots_url, timeout=self.timeout)
            if response.ok:
                content = response.text
                # Find all sitemap directives
                for line in content.splitlines():
                    if line.lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        sitemap_urls.append(sitemap_url)
                        logger.info(f"Found sitemap in robots.txt: {sitemap_url}")
        except Exception as e:
            logger.warning(f"Error checking robots.txt: {e}")
        
        # Try common sitemap locations if none found in robots.txt
        if not sitemap_urls:
            common_paths = [
                '/sitemap.xml',
                '/sitemap_index.xml',
                '/sitemap.txt',
                '/sitemap.json',
                '/sitemap_index.xml.gz',
                '/sitemap.xml.gz',
                '/sitemap/sitemap.xml'
            ]
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                def check_path(path):
                    url = f"{self.base_url}{path}"
                    try:
                        self._wait_before_request()
                        logger.debug(f"Checking common sitemap location: {url}")
                        response = self.session.head(url, timeout=self.timeout)
                        if response.status_code == 200:
                            logger.info(f"Found sitemap at common location: {url}")
                            return url
                    except Exception:
                        pass
                    return None
                
                results = list(executor.map(check_path, common_paths))
                sitemap_urls.extend([r for r in results if r])
        
        # Apply dynamic or fixed limit to the number of sitemaps to process
        if len(sitemap_urls) > 1:
            if self.dynamic_sampling:
                limit = self._calculate_dynamic_limit(len(sitemap_urls), 0)
                if len(sitemap_urls) > limit:
                    logger.info(f"Dynamically limiting to {limit} sitemaps from robots.txt (out of {len(sitemap_urls)})")
                    sitemap_urls = sitemap_urls[:limit]
            elif self.max_sitemaps_per_level is not None and len(sitemap_urls) > self.max_sitemaps_per_level:
                logger.info(f"Limiting to {self.max_sitemaps_per_level} sitemaps from robots.txt")
                sitemap_urls = sitemap_urls[:self.max_sitemaps_per_level]
        
        # Save the discovered sitemaps
        self.sitemap_urls = sitemap_urls
        logger.info(f"Found {len(sitemap_urls)} sitemaps for {self.domain}")
        
        return sitemap_urls
    
    def _process_sitemap(self, sitemap_url: str, depth: int = 0) -> None:
        """
        Process a single sitemap.
        For final sitemaps (those containing actual URLs, not other sitemaps),
        extract URLs based on mode (dual or single).
        
        Args:
            sitemap_url: URL of the sitemap to process
            depth: Current depth level of sitemap nesting
        """
        # Skip if already visited
        if sitemap_url in self.visited_sitemaps:
            return
        
        # Check if we've reached the maximum number of URLs already
        if self.dual_mode:
            if len(self.full_urls) >= self.max_urls:
                return
        else:
            if len(self.urls) >= self.max_urls:
                return
        
        self.visited_sitemaps.add(sitemap_url)
        logger.info(f"Processing sitemap: {sitemap_url}")
        
        # Fetch sitemap content
        content = self._fetch_sitemap(sitemap_url)
        if not content:
            logger.warning(f"Failed to fetch sitemap: {sitemap_url}")
            return
        
        # Parse sitemap
        urls, nested_sitemaps = self._parse_sitemap(content)
        
        # Process URLs based on mode
        if urls and (not nested_sitemaps or depth > 5):  # Limit on depth to prevent infinite recursion
            if self.dual_mode:
                # Dual mode - handle both sample and full modes
                
                # Take a random URL instead of the first one for sample mode
                if urls:
                    sample_url = random.choice(urls)
                    sample_urls = [sample_url]
                    logger.info(f"Taking 1 RANDOM URL for sample mode from sitemap: {sitemap_url} (out of {len(urls)})")
                else:
                    sample_urls = []
                
                # Add sample URLs to the set
                for url in sample_urls:
                    if len(self.sample_urls) >= self.max_urls:
                        break
                    if url not in self.sample_urls:
                        self.sample_urls.add(url)
                        self._write_url_to_output(url, 'sample')
                
                # Full mode: take all URLs or up to urls_per_sitemap
                full_urls = urls
                if self.urls_per_sitemap is not None and len(urls) > self.urls_per_sitemap:
                    logger.info(f"Limiting to {self.urls_per_sitemap} URLs for full mode from sitemap: {sitemap_url}")
                    full_urls = urls[:self.urls_per_sitemap]
                else:
                    logger.info(f"Taking all {len(urls)} URLs for full mode from sitemap: {sitemap_url}")
                
                # Add full mode URLs to the set
                for url in full_urls:
                    if len(self.full_urls) >= self.max_urls:
                        break
                    if url not in self.full_urls:
                        self.full_urls.add(url)
                        self._write_url_to_output(url, 'full')
            else:
                # Single mode based on self.mode
                if getattr(self, 'mode', 'full') == 'sample':
                    # Sample mode: take a random URL from final sitemap
                    if len(urls) > 1:
                        random_url = random.choice(urls)
                        logger.info(f"Taking 1 RANDOM URL from final sitemap: {sitemap_url} (out of {len(urls)})")
                        urls = [random_url]
                else:  # Full mode
                    if self.urls_per_sitemap is not None and len(urls) > self.urls_per_sitemap:
                        logger.info(f"Limiting to {self.urls_per_sitemap} URLs from final sitemap: {sitemap_url}")
                        urls = urls[:self.urls_per_sitemap]
                    else:
                        logger.info(f"Taking all {len(urls)} URLs from final sitemap: {sitemap_url}")
                
                # Add URLs to the set for single mode
                for url in urls:
                    if len(self.urls) >= self.max_urls:
                        return
                        
                    if url not in self.urls:
                        self.urls.add(url)
                        # Write to output file if specified
                        self._write_url_to_output(url)
        
        # If we have nested sitemaps and haven't exceeded depth limit
        if nested_sitemaps and depth < 10:  # Reasonable depth limit
            # Apply dynamic or fixed limit to nested sitemaps
            if len(nested_sitemaps) > 1:
                if self.dynamic_sampling:
                    limit = self._calculate_dynamic_limit(len(nested_sitemaps), depth)
                    if len(nested_sitemaps) > limit:
                        logger.info(f"Dynamically limiting to {limit} nested sitemaps at depth {depth} (out of {len(nested_sitemaps)})")
                        nested_sitemaps = nested_sitemaps[:limit]
                elif self.max_sitemaps_per_level is not None and len(nested_sitemaps) > self.max_sitemaps_per_level:
                    logger.info(f"Limiting to {self.max_sitemaps_per_level} nested sitemaps at depth {depth}")
                    nested_sitemaps = nested_sitemaps[:self.max_sitemaps_per_level]
            
            # Process nested sitemaps
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                list(executor.map(lambda url: self._process_sitemap(url, depth + 1), nested_sitemaps))
    
    def get_all_urls(self) -> Generator[str, None, None]:
        """Get all URLs from sitemaps."""
        # Process discovered sitemaps
        if not self.sitemap_urls:
            self.discover_sitemaps()
        
        # Process sitemaps one by one
        for sitemap_url in self.sitemap_urls:
            self._process_sitemap(sitemap_url, depth=0)
        
        if self.dual_mode:
            # Log results for dual mode
            sample_count = len(self.sample_urls)
            full_count = len(self.full_urls)
            logger.info(f"Finished processing in dual mode: found {sample_count} sample URLs and {full_count} full URLs")
            
            # Return all URLs (first sample, then remaining full)
            yielded_urls = set()
            
            # First yield sample URLs
            for url in self.sample_urls:
                yielded_urls.add(url)
                yield url
                if len(yielded_urls) >= self.max_urls:
                    return
            
            # Then yield full URLs that weren't in sample
            for url in self.full_urls:
                if url not in yielded_urls:
                    yielded_urls.add(url)
                    yield url
                    if len(yielded_urls) >= self.max_urls:
                        return
        else:
            # Single mode - yield URLs as before
            urls_yielded = 0
            for url in self.urls:
                yield url
                urls_yielded += 1
                if urls_yielded >= self.max_urls:
                    return
            
            logger.info(f"Finished processing {len(self.sitemap_urls)} sitemaps, found {urls_yielded} URLs")
    
    def get_urls(self) -> List[str]:
        """Get all URLs from discovered sitemaps (non-generator version)."""
        return list(self.get_all_urls())
    
    def get_sample_urls(self) -> List[str]:
        """Get sample URLs when in dual mode."""
        if not self.dual_mode:
            logger.warning("get_sample_urls() called but not in dual mode")
            return []
        return list(self.sample_urls)
    
    def get_full_urls(self) -> List[str]:
        """Get full URLs when in dual mode."""
        if not self.dual_mode:
            logger.warning("get_full_urls() called but not in dual mode")
            return []
        return list(self.full_urls) 
