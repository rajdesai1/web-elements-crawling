#!/usr/bin/env python3
"""
Extension-based web crawler that uses a Chrome extension to detect interactive elements.
This crawler loads pages, scrolls through them, detects interactive elements, and interacts
with them to create a rich dataset for element detection.
"""

import asyncio
import random
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Union
from urllib.parse import urljoin, urlparse, urlunparse

# Add new import for asyncio timeout
from asyncio import TimeoutError as AsyncioTimeoutError

from patchright.async_api import Page

from src.config.settings import (BROWSER_SETTINGS, CONCURRENT_DOMAINS,
                                 DATA_DIR, DEFAULT_WORKER_ID,
                                 DOMAIN_MAX_CONCURRENT_URLS,
                                 DOMAIN_MAX_URLS_PER_SESSION, EXTENSION_PATH,
                                 FORM_DATA_REGION, FORM_DATA_VARIETY,
                                 PROFILES_FILE, URL_BATCH_SIZE,
                                 VIEWPORT_SCREENSHOT_QUALITY,
                                 MAX_CLICK_INTERACTIONS_PER_URL,
                                 MAX_FORM_INTERACTIONS_PER_URL,
                                 MAX_INTERACTIONS_PER_URL,
                                 MAX_REDIRECTS_PER_INTERACTION,
                                 REDIRECT_TIMEOUT_MS,
                                 RETURN_TO_ORIGINAL_URL,
                                 URL_PROCESSING_TIMEOUT_SECONDS,
                                 DOMAIN_TIME_LIMIT_SECONDS,
                                 MAX_VIEWPORTS_PER_URL)
from src.crawler.browser_manager import BrowserManager
from src.crawler.form_data_manager import FormDataManager
from src.storage.domain_storage_manager import (
    DomainStorageManager, capture_high_quality_screenshot)
from src.utils.logger import setup_logger
from src.utils.mongodb_queue import domain_manager

# Add parent directory to path for imports
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


logger = setup_logger(__name__)


class ExtensionCrawler:
    """
    Extension-based crawler that uses a Chrome extension to detect interactive elements.
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        max_urls_per_domain: int = DOMAIN_MAX_URLS_PER_SESSION,
        headless: bool = BROWSER_SETTINGS["headless"],
        extension_path: str = None,
        data_dir: Union[str, Path] = DATA_DIR,
        form_data_variety: int = FORM_DATA_VARIETY,
        form_data_region: str = FORM_DATA_REGION,
        profiles_file: Optional[str] = PROFILES_FILE,
        url_batch_size: int = URL_BATCH_SIZE,
        max_viewports_per_url: int = MAX_VIEWPORTS_PER_URL,
        domain_time_limit_seconds: int = DOMAIN_TIME_LIMIT_SECONDS,
    ):
        """
        Initialize the extension crawler.

        Args:
            worker_id: Unique identifier for this worker instance
            max_urls_per_domain: Maximum number of URLs to process per domain
            headless: Whether to run browser in headless mode (default from BROWSER_SETTINGS)
            extension_path: Path to the Chrome extension directory
            data_dir: Directory to store crawl data
            form_data_variety: Level of variety in form data (1=minimal, 2=medium, 3=extensive)
            form_data_region: Region to use for form data (india, usa, global)
            profiles_file: Path to JSON file with form filling profiles
            url_batch_size: Number of URLs to process in a batch for each domain
            max_viewports_per_url: Maximum number of viewport sizes to test for each URL
            domain_time_limit_seconds: Maximum time in seconds to spend crawling a single domain
        """
        self.worker_id = worker_id or DEFAULT_WORKER_ID
        self.max_urls_per_domain = max_urls_per_domain
        self.headless = headless 
        self.extension_path = extension_path or EXTENSION_PATH
        self.data_dir = Path(data_dir)
        self.form_data_variety = form_data_variety
        self.form_data_region = form_data_region
        self.url_batch_size = url_batch_size
        self.max_viewports_per_url = max_viewports_per_url
        self.domain_time_limit_seconds = domain_time_limit_seconds

        # Create data directory if it doesn't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.browser_manager = None
        self.visited_urls = set()
        self.discovered_urls = set()

        logger.info("Initialized ExtensionCrawler with worker ID: %s", self.worker_id)
        logger.info("Extension path: %s", self.extension_path)

        # Initialize form data manager for smart form filling
        self.form_data_manager = FormDataManager(
            region=form_data_region,
            variety_level=form_data_variety,
            profiles_file=profiles_file,
        )

        # Initialize domain storage manager
        self.storage_manager = DomainStorageManager(
            base_dir=os.path.join(self.data_dir, "crawl_data"),
            screenshot_quality=VIEWPORT_SCREENSHOT_QUALITY,
            max_retries=3,
        )

    async def start(self, num_concurrent_domains: int = CONCURRENT_DOMAINS):
        """
        Start the crawler with support for processing multiple domains concurrently.

        Args:
            num_concurrent_domains: Number of domains to process concurrently
        """
        logger.info(
            "Starting ExtensionCrawler with %d concurrent domains",
            num_concurrent_domains,
        )

        try:
            # Initialize browser manager
            logger.debug("Initializing BrowserManager with headless=%s", self.headless)
            self.browser_manager = BrowserManager(headless=self.headless)
            await self.browser_manager.init()

            # Create and run tasks for each concurrent domain
            tasks = []
            for i in range(num_concurrent_domains):
                task_id = f"{self.worker_id}-task-{i}"
                tasks.append(self.process_domains(task_id))

            # Run all domain tasks concurrently with proper error handling
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                logger.warning("Tasks cancelled, cleaning up...")
                raise
            except Exception as e:
                logger.error("Error in domain processing tasks: %s", str(e))
                raise

        except Exception as e:
            logger.error("Fatal error in crawler: %s", str(e))
            raise
        finally:
            # Ensure browser resources are cleaned up
            if self.browser_manager:
                try:
                    await asyncio.wait_for(
                        self.browser_manager.close(),
                        timeout=30.0
                    )
                except Exception as e:
                    logger.error("Error closing browser manager: %s", str(e))
            logger.info("ExtensionCrawler finished")

    async def process_domains(self, task_id: str):
        """
        Process domains continuously, claiming one domain at a time.

        Args:
            task_id: Unique identifier for this task
        """
        logger.info("Starting domain processing task: %s", task_id)

        try:
            while True:
                # Claim a domain
                domain = domain_manager.claim_domain(task_id)

                if not domain:
                    logger.info("No domains available for %s, waiting...", task_id)
                    await asyncio.sleep(10)
                    continue

                logger.info("Processing domain: %s", domain)

                try:
                    # Process the domain
                    await self.process_domain(domain, task_id)

                    # Mark domain as completed
                    domain_manager.mark_domain_completed(
                        domain,
                        {
                            "processed_by": task_id,
                            "completed_at": datetime.now().isoformat(),
                        },
                    )

                except Exception as e:
                    logger.error("Error processing domain %s: %s", domain, e)
                    # Release the domain so it can be claimed again
                    domain_manager.release_domain(domain, task_id)

                # Prevent claiming domains too quickly
                await asyncio.sleep(random.uniform(1, 3))

        except Exception as e:
            logger.error("Task %s encountered an error: %s", task_id, e)

    async def process_domain(
        self, domain: str, task_id: str = None, max_urls: int = None
    ) -> Dict:
        """
        Process a domain by crawling multiple URLs.

        Args:
            domain: Domain to process
            task_id: Task ID for tracking
            max_urls: Maximum number of URLs to process (None for unlimited)

        Returns:
            Dictionary containing processing statistics
        """
        if max_urls is None:
            max_urls = self.max_urls_per_domain

        processed_urls = set()
        failed_urls = []
        discovered_urls_count = 0
        start_time = time.time()

        # Track visited and discovered URLs to avoid duplicates
        visited_urls = set()
        # Create a set to track all known URLs for this domain (both processed and queued)
        known_urls = set()
        
        # Define batch size for URL retrieval
        batch_size = self.url_batch_size

        logger.info("Starting to process domain: %s (max URLs: %s)", domain, max_urls)
        logger.info("Worker ID: %s, Task ID: %s", self.worker_id, task_id or "none")
        logger.info("Processing URLs in batches of %d (max concurrent: %d)", batch_size, DOMAIN_MAX_CONCURRENT_URLS)
        logger.info("Domain time limit: %d seconds", self.domain_time_limit_seconds)

        # Get the initial set of URLs that are already in the queue
        try:
            # Get counts of URLs to estimate the size
            url_counts = domain_manager.get_domain_urls_count(domain)
            total_urls = url_counts.get('total', 0)
            logger.info("Domain has %d total URLs in the queue", total_urls)
            
            # If there are URLs, we should pre-populate the known_urls set
            # Use a larger batch size to efficiently get all URLs
            if total_urls > 0:
                # Get URL data in batches to avoid memory issues
                initial_batch_size = min(500, total_urls)
                for offset in range(0, total_urls, initial_batch_size):
                    initial_urls = domain_manager.get_all_domain_urls(domain, limit=initial_batch_size, offset=offset)
                    for url_data in initial_urls:
                        url = url_data.get("url")
                        if url:
                            known_urls.add(url)
                logger.info("Pre-populated known_urls with %d URLs from the queue", len(known_urls))
        except Exception as e:
            logger.warning("Error pre-populating known_urls set: %s", str(e))

        while len(processed_urls) < max_urls:
            # Check if we've reached the domain time limit
            elapsed_time = time.time() - start_time
            if elapsed_time > self.domain_time_limit_seconds:
                logger.info("Domain time limit reached after %.2f seconds, stopping processing", elapsed_time)
                break
                
            # Get batch of URLs to process
            url_batch = domain_manager.get_domain_urls_batch(domain, batch_size=min(batch_size, max_urls - len(processed_urls)))
            if not url_batch:
                logger.info("No more URLs to process for domain: %s", domain)
                break

            # Process URLs in the batch with concurrency control
            for i in range(0, len(url_batch), DOMAIN_MAX_CONCURRENT_URLS):
                # Check time limit again before processing each batch
                if (time.time() - start_time) > self.domain_time_limit_seconds:
                    logger.info("Domain time limit reached during batch processing, stopping")
                    break
                    
                # Take a slice of URLs up to max concurrent limit
                current_batch = url_batch[i:i + DOMAIN_MAX_CONCURRENT_URLS]
                batch_tasks = []
                
                for url_data in current_batch:
                    url = url_data.get("url")
                    
                    # Check if this URL has "is_discovered" flag to determine if it can discover new URLs
                    # Default to False if not specified (meaning original queue URLs can discover)
                    is_discovered = url_data.get("is_discovered", False)
                    
                    if not url or url in visited_urls:
                        continue
                    
                    # Add to tracking sets
                    visited_urls.add(url)
                    known_urls.add(url)
                    
                    # Create task for processing the URL
                    batch_tasks.append(self.process_url(
                        url=url, 
                        domain=domain,
                        task_id=task_id,
                        processed_urls=processed_urls,
                        visited_urls=visited_urls,
                        known_urls=known_urls,
                        is_discovered=is_discovered  # Pass the flag to process_url
                    ))
                
                # Wait for current batch of URLs to complete before processing next batch
                if batch_tasks:
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                    
                    # Process results
                    for i, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            # Handle exceptions
                            url = current_batch[i].get("url")
                            logger.error("Error processing URL %s: %s", url, str(result))
                            failed_urls.append(url)
                            domain_manager.mark_url_failed(domain, url, str(result))
                            continue
                            
                        url = result["url"]
                        if result["success"]:
                            # Check if any interactive elements were found
                            elements_count = len(result.get("elements", []))
                            processed_urls.add(url)
                            
                            if elements_count > 0:
                                logger.info("✅ Successfully processed URL with %d elements: %s", 
                                            elements_count, url)

                                # Mark URL as completed in MongoDB
                                domain_manager.mark_url_completed(
                                    domain,
                                    url,
                                    {
                                        "processed_by": task_id or self.worker_id,
                                        "completed_at": datetime.now().isoformat(),
                                        "elements_count": elements_count,
                                        "discovered_urls_count": len(result.get("discovered_urls", [])),
                                        "interaction_results_count": result.get("interactions_count", 0),
                                        "status_details": "completed_with_elements"
                                    }
                                )
                            else:
                                # Handle case where no elements were found
                                logger.warning("⚠️ URL processed successfully but no interactive elements found: %s", url)
                                domain_manager.mark_url_failed(
                                    domain,
                                    url,
                                    "No interactive elements found on the page"
                                )

                            # Handle discovered URLs from original queue URLs only
                            is_discovered = result.get("is_discovered", False)
                            if is_discovered:
                                logger.info("Skipping URL discovery for %s as it was discovered during crawling", url)
                            else:
                                # Only process discovered URLs if this was an original (non-discovered) URL
                                new_urls = []
                                unique_urls_count = 0
                                
                                for discovered_url in result.get("discovered_urls", []):
                                    # Clean URL before adding
                                    clean_url = self._clean_url(discovered_url)
                                    if not clean_url:
                                        continue

                                    # Skip if URL is already known (visited, processed, or queued)
                                    if clean_url in known_urls:
                                        continue
                                    
                                    # Add to known URLs set to prevent duplicates
                                    known_urls.add(clean_url)
                                    unique_urls_count += 1

                                    # Mark the URL as discovered so it won't add more URLs to the queue
                                    new_urls.append({"url": clean_url, "is_discovered": True})

                                logger.info("Found %d unique new URLs from %d discovered URLs", 
                                           unique_urls_count, len(result.get("discovered_urls", [])))
                                
                                # limit new urls to 10
                                # random shuffle the new urls
                                random.shuffle(new_urls)
                                new_urls = new_urls[:10]

                                # Add new URLs with the is_discovered flag
                                if new_urls:
                                    batch_size = 10  # Process URLs in batches for better performance
                                    for i in range(0, len(new_urls), batch_size):
                                        batch = new_urls[i : i + batch_size]
                                        added_count = self._add_urls_to_domain(domain, batch)

                                    discovered_urls_count += len(new_urls)
                                    logger.info(
                                        "Added %d new URLs to domain %s (total discovered: %d)",
                                        len(new_urls),
                                        domain,
                                        discovered_urls_count,
                                    )
                        else:
                            failed_urls.append(url)
                            logger.warning("❌ Failed to process URL: %s", url)

                            # Mark URL as failed in MongoDB
                            domain_manager.mark_url_failed(
                                domain, url, result.get("error", "Unknown error")
                            )
                
                # Respect rate limits between concurrent batches
                await asyncio.sleep(random.uniform(1, 3))
            
            # Respect rate limits between main batches
            await asyncio.sleep(random.uniform(1, 3))

        # Calculate statistics
        end_time = time.time()
        processing_time = end_time - start_time

        statistics = {
            "domain": domain,
            "processed_urls_count": len(processed_urls),
            "failed_urls_count": len(failed_urls),
            "discovered_urls_count": discovered_urls_count,
            "processing_time_seconds": processing_time,
            "urls_per_second": (
                len(processed_urls) / processing_time if processing_time > 0 else 0
            ),
            "time_limit_reached": processing_time >= self.domain_time_limit_seconds,
            "unique_urls_tracked": len(known_urls)
        }

        logger.info("📊 Completed processing domain: %s", domain)
        logger.info("Statistics: %s", statistics)

        return statistics

    def _add_urls_to_domain(self, domain: str, urls: List[Union[str, Dict]]) -> int:
        """
        Add URLs to a domain's queue.

        Args:
            domain: Domain to add URLs to
            urls: List of URLs to add (either string URLs or dicts with 'url' and 'is_discovered' keys)

        Returns:
            Number of URLs added
        """
        try:
            return domain_manager.add_urls_to_domain(domain, urls)
        except Exception as e:
            logger.error("Error adding URLs to domain %s: %s", domain, e)
            return 0

    async def process_url(self, url: str, domain: str, 
                     task_id: Optional[str] = None,
                     processed_urls: Optional[Set[str]] = None,
                     visited_urls: Optional[Set[str]] = None,
                     known_urls: Optional[Set[str]] = None,
                     is_discovered: bool = False) -> Dict:
        """
        Process a single URL for interactive elements and collect discovered URLs.

        Args:
            url: URL to process
            domain: Domain of the URL
            task_id: Optional task ID for tracking
            processed_urls: Optional set of processed URLs for tracking
            visited_urls: Optional set of visited URLs for tracking
            known_urls: Optional set of known URLs for tracking
            is_discovered: Flag indicating if this URL was discovered during crawling

        Returns:
            Dictionary containing processed elements and discovered URLs
        """
        logger.info("Processing URL: %s", url)
        result = {
            "url": url,
            "domain": domain,
            "success": False,
            "error": None,
            "elements": [],
            "discovered_urls": [],
            "is_discovered": is_discovered
        }

        # Initialize tracking sets if not provided
        if processed_urls is None:
            processed_urls = set()
        if visited_urls is None:
            visited_urls = set()
        if known_urls is None:
            known_urls = set()
            
        # Initialize discovered URLs counter
        discovered_urls_count = 0

        page = None
        processing_task = None
        
        try:
            page = await self.browser_manager.new_page()
            
            # Create a task for the actual processing with timeout
            async def _process_with_timeout():
                nonlocal result

            # Add error handling for navigation
            try:
                # Navigate to the URL using browser_manager's navigate method
                logger.info("Navigating to %s", url)
                navigation_success = await self.browser_manager.navigate(url, {
                    "wait_until": "domcontentloaded", 
                    "timeout": 60000
                })
                
                if not navigation_success:
                    raise Exception(f"Failed to navigate to {url}")
            except Exception as nav_error:
                logger.error("Navigation error for %s: %s", url, str(nav_error))
                result["error"] = f"Navigation error: {str(nav_error)}"
                return result
            
            # Store all discovered interactive elements
            all_viewport_elements = {}  # Using dict with xpath as key for O(1) lookup
            discovered_urls = set()
            
            # Process first viewport (already visible)
            viewport_count = 1
            current_position = 0
            
            # Calculate scrollability once at the beginning
            try:
                scrollability = await asyncio.wait_for(
                    self.browser_manager.calculate_scrollability(page),
                    timeout=30.0
                )
                logger.info("Page scrollability check: can_scroll=%s, total_viewports=%d", 
                            scrollability.get('vertical', {}).get('canScroll', False),
                            scrollability.get('vertical', {}).get('totalViewports', 1))
            except asyncio.TimeoutError:
                logger.warning("Scrollability check timed out for %s, assuming non-scrollable", url)
                scrollability = {'vertical': {'canScroll': False, 'totalViewports': 1}}
            except Exception as e:
                logger.error("Error checking scrollability for %s: %s", url, str(e))
                scrollability = {'vertical': {'canScroll': False, 'totalViewports': 1}}
            
            # Process viewports and collect elements
            async def process_viewport(viewport_index: int, scroll_position: int = 0):
                try:
                    logger.info("Processing viewport %d at position %dpx", viewport_index, scroll_position)
                
                    # Detect interactive elements in current viewport with timeout
                    interactive_elements = await asyncio.wait_for(
                        self.browser_manager.detect_interactive_elements(page),
                        timeout=30.0
                    )
                    
                    screenshot_data = await asyncio.wait_for(
                        capture_high_quality_screenshot(page, self.storage_manager.screenshot_quality),
                        timeout=30.0
                    )
                    
                    # Store viewport data using DomainStorageManager with scrollability info
                    storage_result = self.storage_manager.store_viewport(
                        url=url,
                        screenshot_data=screenshot_data,
                        metadata=interactive_elements,
                        viewport_index=viewport_index,
                        scrollability_data=scrollability if viewport_index == 1 else None  # Only store on first viewport
                    )
                    
                    # Extract URLs from the current viewport's interactive elements
                    viewport_urls = await self.extract_urls_from_elements(
                        interactive_elements.get("interactiveElements", []), 
                        url
                    )
                    discovered_urls.update(viewport_urls)
                    
                    # Store elements by their Playwright interaction type
                    if interactive_elements and interactive_elements.get('interactiveElements'):
                        for element in interactive_elements.get('interactiveElements', []):
                            element_path = element.get('elementPath')
                            if element_path:
                                # Only update if element doesn't exist or current one is "better"
                                if element_path not in all_viewport_elements or (
                                    len(element.get('attributes', {})) > len(all_viewport_elements[element_path].get('attributes', {}))
                                ):
                                    all_viewport_elements[element_path] = element
                    
                    return storage_result["viewport_dir"]
                except asyncio.TimeoutError:
                    logger.warning("Viewport processing timed out for viewport %d at %dpx", viewport_index, scroll_position)
                    return None
                except Exception as e:
                    logger.error("Error processing viewport %d at %dpx: %s", viewport_index, scroll_position, str(e))
                    return None

            # Process first viewport
            viewport_path = await process_viewport(viewport_count)
            
            # Process remaining viewports if page is scrollable
            if scrollability.get('vertical', {}).get('canScroll', False):
                vertical_scroll = scrollability.get('vertical', {})
                viewport_steps = scrollability.get('viewportSteps', [])
                total_viewports = vertical_scroll.get('totalViewports', 1)
                
                # Apply max_viewports_per_url limit
                max_viewports = min(self.max_viewports_per_url, total_viewports)
                if max_viewports < total_viewports:
                    logger.info("Limiting viewports to %d (of %d possible viewports) based on max_viewports_per_url setting", 
                              max_viewports, total_viewports)
                
                for step_index in range(1, min(len(viewport_steps), max_viewports)):
                    viewport_count += 1
                    step = viewport_steps[step_index]
                    scroll_position = step.get('scrollTop', 0)
                    
                    try:
                        # Scroll to exact position from viewportSteps with timeout
                        await asyncio.wait_for(
                            self.browser_manager.scroll_to(page, {'y': scroll_position, 'behavior': 'smooth'}),
                            timeout=10.0
                        )
                        await asyncio.sleep(1.0)  # Wait for scroll to complete and content to load
                        
                        await process_viewport(viewport_count, scroll_position)
                    except asyncio.TimeoutError:
                        logger.warning("Scroll operation timed out at viewport %d", viewport_count)
                        continue
                    except Exception as e:
                        logger.error("Error scrolling to viewport %d: %s", viewport_count, str(e))
                        continue
            
            # scroll to the top of the page just for better view :)
            await asyncio.wait_for(
                self.browser_manager.scroll_to(page, {'y': 0}),
                timeout=10.0
            )

            # Group elements by their Playwright interaction type
            interaction_groups = {}
            for element in all_viewport_elements.values():
                interaction = element.get('playwrightInteraction', {}).get('action', 'click')
                if interaction not in interaction_groups:
                    interaction_groups[interaction] = []
                interaction_groups[interaction].append(element)

            logger.info("Found elements by interaction type: %s", 
                       {k: len(v) for k, v in interaction_groups.items()})

            # Process elements by interaction type
            interacted_elements = set()
            interaction_results = []
            
            # Process fill interactions first (text inputs, textareas, etc)
            if 'fill' in interaction_groups:
                fill_results = await self.interact_with_form_elements(
                    page, interaction_groups['fill'], interacted_elements
                )
                interaction_results.extend(fill_results)

            # Process check/uncheck interactions (checkboxes, radio buttons)
            for action in ['check', 'uncheck']:
                if action in interaction_groups:
                    check_results = await self.interact_with_form_elements(
                        page, interaction_groups[action], interacted_elements
                    )
                    interaction_results.extend(check_results)

            # Process select interactions (dropdowns)
            if 'selectOption' in interaction_groups:
                select_results = await self.interact_with_form_elements(
                    page, interaction_groups['selectOption'], interacted_elements
                )
                interaction_results.extend(select_results)

            # Process click interactions last
            if 'click' in interaction_groups:
                click_results = await self.interact_with_clickable_elements(
                    page, interaction_groups['click'], interacted_elements
                )
                interaction_results.extend(click_results)

            # Process any remaining interactions
            for interaction_type, elements in interaction_groups.items():
                if interaction_type not in ['fill', 'check', 'uncheck', 'selectOption', 'click']:
                    logger.info("Processing %d elements with interaction type: %s", 
                              len(elements), interaction_type)
                    # Use appropriate interaction method based on type
                    if interaction_type in ['hover', 'drag']:
                        results = await self.interact_with_clickable_elements(
                            page, elements, interacted_elements
                        )
                        interaction_results.extend(results)

            # Store result
            result["success"] = True
            result["elements"] = list(all_viewport_elements.values())
            result["discovered_urls"] = list(discovered_urls)
            result["timestamp"] = datetime.now().isoformat()
            result["viewport_count"] = viewport_count
            result["interactions_count"] = len(interaction_results)

            logger.info(
                "Successfully processed %s - found %d elements and discovered %d URLs",
                url,
                len(result["elements"]),
                len(result["discovered_urls"]),
            )

            return result

            # Execute the processing with a timeout
            try:
                processing_task = asyncio.create_task(_process_with_timeout())
                result = await asyncio.wait_for(
                    processing_task,
                    timeout=URL_PROCESSING_TIMEOUT_SECONDS
                )
            except AsyncioTimeoutError:
                error_msg = f"URL processing timed out after {URL_PROCESSING_TIMEOUT_SECONDS} seconds: {url}"
                logger.error(error_msg)
                result["error"] = error_msg
                
                # Store timeout error information
                try:
                    if page:
                        screenshot_data = await capture_high_quality_screenshot(
                            page, self.storage_manager.screenshot_quality
                        )
                        
                        error_data = {
                            "url": url,
                            "domain": domain,
                            "error": error_msg,
                            "error_type": "timeout",
                            "timestamp": datetime.now().isoformat(),
                            "timeout_seconds": URL_PROCESSING_TIMEOUT_SECONDS
                        }
                        
                        storage_result = self.storage_manager.store_error(
                            url=url,
                            error_data=error_data,
                            screenshot_data=screenshot_data
                        )
                        
                        logger.warning("Saved timeout error for URL %s: %s", url, storage_result["error_id"])
                except Exception as storage_error:
                    logger.error("Error storing timeout failure data: %s", str(storage_error))
                    
                # Cancel the processing task if it's still running
                if processing_task and not processing_task.done():
                    processing_task.cancel()
                    try:
                        await processing_task
                    except asyncio.CancelledError:
                        logger.info("Successfully cancelled the processing task for URL: %s", url)
                    
        except Exception as e:
            error_msg = f"Error processing {url}: {str(e)}"
            logger.error("Error processing %s: %s", url, str(e))
            result["error"] = error_msg
            
            # Store error information if possible
            try:
                if page:
                    screenshot_data = await capture_high_quality_screenshot(
                        page, self.storage_manager.screenshot_quality
                    )
                    
                    error_data = {
                        "url": url,
                        "domain": domain,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    storage_result = self.storage_manager.store_error(
                        url=url,
                        error_data=error_data,
                        screenshot_data=screenshot_data
                    )
                    
                    logger.warning("Saved error for URL %s: %s", url, storage_result["error_id"])
            except Exception as storage_error:
                logger.error(f"Error storing failure data: {storage_error}")

        finally:
            if page:
                await page.close()

        # Process results after all page operations (whether successful, timed out, or failed)
        if result["success"]:
            # Check if any interactive elements were found
            elements_count = len(result.get("elements", []))
            
            # Track processed and visited URLs if sets were provided
            if processed_urls is not None:
                processed_urls.add(url)
            if visited_urls is not None:
                visited_urls.add(url)
            
            if elements_count > 0:
                logger.info("✅ Successfully processed URL with %d elements: %s", 
                          elements_count, url)

                # Mark URL as completed in MongoDB
                domain_manager.mark_url_completed(
                    domain,
                    url,
                    {
                        "processed_by": task_id or self.worker_id,
                        "completed_at": datetime.now().isoformat(),
                        "elements_count": elements_count,
                        "discovered_urls_count": len(result.get("discovered_urls", [])),
                        "interaction_results_count": result.get("interactions_count", 0),
                        "status_details": "completed_with_elements"
                    }
                )
            else:
                # Handle case where no elements were found
                logger.warning("⚠️ URL processed successfully but no interactive elements found: %s", url)
                domain_manager.mark_url_failed(
                    domain,
                    url,
                    "No interactive elements found on the page"
                )

            # Handle discovered URLs from original queue URLs only
            is_discovered = result.get("is_discovered", False)
            if is_discovered:
                logger.info("Skipping URL discovery for %s as it was discovered during crawling", url)
            else:
                # Only process discovered URLs if this was an original (non-discovered) URL
                new_urls = []
                for discovered_url in result.get("discovered_urls", []):
                    # Clean URL before adding
                    clean_url = self._clean_url(discovered_url)
                    if not clean_url:
                        continue

                    # Skip if URL is already known (visited, processed, or queued)
                    if clean_url in known_urls:
                        continue
                    
                    # Add to known URLs set to prevent duplicates
                    known_urls.add(clean_url)

                    # Mark the URL as discovered so it won't add more URLs to the queue
                    new_urls.append({"url": clean_url, "is_discovered": True})

                logger.info("Found %d unique new URLs from %d discovered URLs", 
                           len(new_urls), len(result.get("discovered_urls", [])))
                
                # limit new urls to 10
                # random shuffle the new urls
                random.shuffle(new_urls)
                new_urls = new_urls[:10]

                # Add new URLs with the is_discovered flag
                if new_urls:
                    batch_size = 10  # Process URLs in batches for better performance
                    for i in range(0, len(new_urls), batch_size):
                        batch = new_urls[i : i + batch_size]
                        added_count = self._add_urls_to_domain(domain, batch)

                    discovered_urls_count += len(new_urls)
                    logger.info(
                        "Added %d new URLs to domain %s (total discovered: %d)",
                        len(new_urls),
                        domain,
                        discovered_urls_count,
                    )
        else:
            # Handle failed URL processing (including timeouts)
            logger.warning("❌ Failed to process URL: %s - %s", url, result.get("error", "Unknown error"))
            domain_manager.mark_url_failed(domain, url, result.get("error", "Unknown error"))

        return result

    async def extract_urls_from_elements(
        self, elements: List[Dict], base_url: str
    ) -> List[str]:
        """
        Extract URLs from interactive elements.

        Args:
            elements: List of interactive elements
            base_url: Base URL to resolve relative URLs

        Returns:
            List of discovered URLs
        """
        logger.info("Extracting URLs from %d elements", len(elements))
        urls = []

        for element in elements:
            element_type = element.get("type", "")
            attributes = element.get("attributes", {})

            # Extract from href attribute
            if "href" in attributes:
                href = attributes["href"]
                if href and not href.startswith(
                    ("javascript:", "mailto:", "tel:", "#")
                ):
                    absolute_url = urljoin(base_url, href)
                    urls.append(absolute_url)

            # Extract from form action
            if element_type == "form" and "action" in attributes:
                action = attributes["action"]
                if action and not action.startswith("javascript:"):
                    absolute_url = urljoin(base_url, action)
                    urls.append(absolute_url)

            # Extract from onclick attribute if it contains a URL
            if "onclick" in attributes:
                onclick = attributes["onclick"]
                # Look for common URL patterns in onclick attributes
                url_matches = re.findall(r'(\'|")(https?://[^\'"]+)(\'|")', onclick)
                for match in url_matches:
                    if match and len(match) >= 2:
                        urls.append(match[1])

        # Filter duplicates and return
        unique_urls = list(set(urls))
        logger.info("Extracted %d URLs from elements", len(unique_urls))
        return unique_urls

    def _clean_url(self, url: str) -> Optional[str]:
        """
        Clean a URL by:
        - Removing fragments
        - Ensuring it starts with http:// or https://
        - Normalizing the URL

        Args:
            url: URL to clean

        Returns:
            Cleaned URL or None if invalid
        """
        if not url:
            return None

        try:
            # Parse the URL
            parsed = urlparse(url)

            # Skip invalid URLs
            if not parsed.netloc:
                return None

            # Skip specific schemes
            if parsed.scheme not in ("http", "https", ""):
                return None

            # Ensure scheme is present
            scheme = parsed.scheme if parsed.scheme else "http"

            # Rebuild URL without fragment
            clean_url = urlunparse(
                (
                    scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    "",  # No fragment
                )
            )

            return clean_url
        except Exception as e:
            logger.debug("Error cleaning URL %s: %s", url, str(e))
            return None

    def _is_same_domain(self, url: str, base_domain: str) -> bool:
        """
        Check if a URL belongs to the same domain as the base domain.

        Args:
            url: URL to check
            base_domain: Base domain to compare against

        Returns:
            True if the URL is from the same domain, False otherwise
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if domain.startswith("www."):
                domain = domain[4:]

            return domain == base_domain or domain.endswith("." + base_domain)
        except Exception:
            return False

    async def interact_with_form_elements(self, page: Page, elements: List[Dict], 
                                    interacted_elements: Set[str]) -> List[Dict]:
        """
        Interact with form elements (inputs, textareas, selects) using Playwright's locators.
        
        Args:
            page: Page containing the elements
            elements: List of elements to interact with
            interacted_elements: Set of element IDs that have already been interacted with
            
        Returns:
            List of interaction results
        """
        interaction_results = []
        if not elements:
            return interaction_results
        
        logger.info("Interacting with %d form elements", len(elements))
        
        # Track interaction counts and page state
        form_interactions = 0
        total_interactions = len(interacted_elements)  # Track total interactions across all types
        successful_interactions = 0
        original_url = page.url
        page_changed = False
        redirect_count = 0
        
        # Process elements until we hit the interaction limits
        for element in elements:
            # Check total interaction limit first
            if total_interactions >= MAX_INTERACTIONS_PER_URL:
                logger.info("Reached maximum total interactions limit (%d)", MAX_INTERACTIONS_PER_URL)
                break
                
            # Then check form-specific limit
            if form_interactions >= MAX_FORM_INTERACTIONS_PER_URL:
                logger.info("Reached maximum form interactions limit (%d)", MAX_FORM_INTERACTIONS_PER_URL)
                break
                
            # Reset redirect count for new element
            redirect_count = 0
            
            try:
                # Skip elements we've already interacted with
                element_path = element.get('elementPath')
                if not element_path or element_path in interacted_elements:
                    continue
                    
                # Create a unique ID for this element
                element_id = element_path.split('/')[-1]
                if not element_id:
                    element_id = f"form_{len(interacted_elements)}"
                
                # Get element tag and attributes
                tag_name = element.get('tagName', '').lower()
                attributes = element.get('attributes', {})
                element_type = attributes.get('type', '').lower()
                interaction_type = element.get('playwrightInteraction', {}).get('action')
                
                logger.info("Processing form element: %s (type: %s, interaction: %s)", 
                           element_id, element_type or tag_name, interaction_type)
                
                # Skip if element doesn't have a valid interaction type
                if not interaction_type:
                    logger.warning("Element has no interaction type, skipping: %s", element_id)
                    continue
                
                # First scroll element into view
                scroll_success = await self.browser_manager.scroll_element_into_view(page, element)
                if not scroll_success:
                    logger.warning("Could not scroll element into view, skipping: %s", element_id)
                    continue
                
                # Create the XPath locator
                locator = page.locator(f"xpath={element_path}")
                
                # Check if element exists and is visible
                if not locator:
                    logger.warning("Element not found with XPath: %s", element_path)
                    continue
                    
                # Wait to ensure element is visible and stable
                try:
                    await locator.wait_for(state="visible", timeout=5000)
                except Exception as e:
                    logger.warning("Element not visible after waiting: %s - %s", element_id, str(e))
                    continue
                
                # Create the result data structure
                interaction_data = {
                    "element_id": element_id,
                    "element_path": element_path,
                    "tag_name": tag_name,
                    "element_type": element_type,
                    "interaction_type": interaction_type,
                    "timestamp": datetime.now().isoformat(),
                    "success": False,
                    "redirects": []
                }
                
                # Handle the interaction with navigation tracking
                async def handle_navigation(interaction_func):
                    nonlocal redirect_count, page_changed
                    try:
                        async with page.expect_navigation(timeout=REDIRECT_TIMEOUT_MS) as navigation_info:
                            await interaction_func()
                            result = await navigation_info.value
                            
                            if result:
                                redirect_count += 1
                                logger.info("Navigation occurred (%d/%d): %s -> %s", 
                                          redirect_count, MAX_REDIRECTS_PER_INTERACTION,
                                          original_url, result.url)
                                
                                interaction_data["redirects"].append({
                                    "from_url": original_url,
                                    "to_url": result.url,
                                    "redirect_number": redirect_count
                                })
                                
                                page_changed = True
                                
                                # Check redirect limit
                                if redirect_count >= MAX_REDIRECTS_PER_INTERACTION:
                                    logger.info("Reached maximum redirects limit (%d)", MAX_REDIRECTS_PER_INTERACTION)
                                    return False
                                    
                                # Wait for the page to stabilize
                                await page.wait_for_load_state("domcontentloaded")
                                return True
                            
                    except Exception as navigation_error:
                        # Log exception but don't treat it as a failure
                        logger.warning("Navigation exception during form interaction: %s", str(navigation_error))
                        # Even if navigation failed, page might have changed - set flag cautiously
                        if page.url != original_url:
                            page_changed = True
                            logger.info("Page URL changed despite navigation exception: %s -> %s", 
                                      original_url, page.url)
                        return False
                    return True
                
                # Capture state before interaction
                before_interaction = await self._capture_interaction_state(
                    page=page,
                    element_id=element_id,
                    element_path=element_path,
                    tag_name=tag_name,
                    element_type=element_type,
                        interaction_type=f"{interaction_type}_before"
                )
                
                interaction_success = False
                
                if interaction_type == "fill":
                    # Get appropriate form value
                    form_value = self.form_data_manager.determine_input_value(element)
                        
                    # Fill the form field
                    try:
                        await handle_navigation(lambda: locator.fill(form_value))
                        interaction_success = True
                    except Exception as e:
                        logger.warning("Fill interaction failed: %s - %s", element_id, str(e))
                        interaction_data["error"] = str(e)
                        
                    # Capture state after fill
                    after_interaction = await self._capture_interaction_state(
                        page=page,
                        element_id=element_id,
                        element_path=element_path,
                        tag_name=tag_name,
                        element_type=element_type,
                        interaction_type=f"{interaction_type}_after",
                        extra_data={
                            "form_value": form_value,
                            "before_storage_path": before_interaction["storage_path"]
                        }
                    )
                    
                    interaction_data = after_interaction
                    successful_interactions += 1
                    form_interactions += 1
                    total_interactions += 1
                    
                    # Handle return to original page if needed
                    if page_changed and RETURN_TO_ORIGINAL_URL:
                        try:
                            await page.goto(original_url, timeout=REDIRECT_TIMEOUT_MS)
                            await page.wait_for_load_state("domcontentloaded")
                            page_changed = False
                        except Exception as e:
                            logger.error("Failed to return to original URL: %s", str(e))
                            break
                
                elif interaction_type == "selectOption":
                    # Get appropriate select option value
                    select_value = self.form_data_manager.determine_input_value(element)
                        
                    # Select the option
                    try:
                        await handle_navigation(lambda: locator.select_option(select_value))
                        interaction_success = True
                    except Exception as e:
                        logger.warning("Select interaction failed: %s - %s", element_id, str(e))
                        interaction_data["error"] = str(e)
                    
                    # Capture state after select
                    after_interaction = await self._capture_interaction_state(
                        page=page,
                        element_id=element_id,
                        element_path=element_path,
                        tag_name=tag_name,
                        element_type=element_type,
                        interaction_type=f"{interaction_type}_after",
                        extra_data={
                            "select_value": select_value,
                            "before_storage_path": before_interaction["storage_path"]
                        }
                    )
                    
                    interaction_data = after_interaction
                    successful_interactions += 1
                    form_interactions += 1
                    total_interactions += 1
                    
                    # Handle return to original page if needed
                    if page_changed and RETURN_TO_ORIGINAL_URL:
                        try:
                            await page.goto(original_url, timeout=REDIRECT_TIMEOUT_MS)
                            await page.wait_for_load_state("domcontentloaded")
                            page_changed = False
                        except Exception as e:
                            logger.error("Failed to return to original URL: %s", str(e))
                            break
                
                elif interaction_type in ["check", "uncheck"]:
                    # Handle checkbox/radio interaction
                    try:
                        await handle_navigation(lambda: locator.check() if interaction_type == "check" else locator.uncheck())
                        interaction_success = True
                    except Exception as e:
                        logger.warning("%s interaction failed: %s - %s", interaction_type, element_id, str(e))
                        interaction_data["error"] = str(e)
                        
                    
                    # Capture state after check/uncheck
                    after_interaction = await self._capture_interaction_state(
                        page=page,
                        element_id=element_id,
                        element_path=element_path,
                        tag_name=tag_name,
                        element_type=element_type,
                        interaction_type=f"{interaction_type}_after",
                        extra_data={
                            "before_storage_path": before_interaction["storage_path"]
                        }
                    )
                    
                    interaction_data = after_interaction
                    successful_interactions += 1
                    form_interactions += 1
                    total_interactions += 1
                    
                    # Handle return to original page if needed
                    if page_changed and RETURN_TO_ORIGINAL_URL:
                        try:
                            await page.goto(original_url, timeout=REDIRECT_TIMEOUT_MS)
                            await page.wait_for_load_state("domcontentloaded")
                            page_changed = False
                        except Exception as e:
                            logger.error("Failed to return to original URL: %s", str(e))
                            break
                
                # Store the interaction result
                interaction_results.append(interaction_data)
                interacted_elements.add(element_path)
                
                # Pause between interactions
                await page.wait_for_timeout(random.randint(500, 1000))
                    
            except Exception as e:
                logger.error("Error interacting with form element: %s", str(e))
                
                # Always try to return to original URL if page changed during interaction
                if page_changed and RETURN_TO_ORIGINAL_URL:
                    try:
                        logger.info("Returning to original URL after form interaction failure: %s", original_url)
                        await page.goto(original_url, timeout=REDIRECT_TIMEOUT_MS)
                        await page.wait_for_load_state("domcontentloaded")
                        page_changed = False
                    except Exception as nav_error:
                        logger.error("Failed to return to original URL after form interaction error: %s", str(nav_error))
        
        logger.info("Successfully interacted with %d/%d form elements", 
                   successful_interactions, len(elements))
        
        return interaction_results

    async def interact_with_clickable_elements(self, page: Page, elements: List[Dict], 
                                     interacted_elements: Set[str]) -> List[Dict]:
        """
        Interact with clickable elements (buttons, links, etc.) using Playwright's locators.
        
        Args:
            page: Page containing the elements
            elements: List of elements to interact with
            interacted_elements: Set of element IDs that have already been interacted with
            
        Returns:
            List of interaction results
        """
        interaction_results = []
        if not elements:
            return interaction_results
            
        logger.info("Interacting with %d clickable elements", len(elements))
        
        # Track interaction counts and page state
        click_interactions = 0
        total_interactions = len(interacted_elements)  # Track total interactions across all types
        successful_interactions = 0
        original_url = page.url
        page_changed = False
        redirect_count = 0
        
        # Process elements until we hit the interaction limits
        for element in elements:
            # Check total interaction limit first
            if total_interactions >= MAX_INTERACTIONS_PER_URL:
                logger.info("Reached maximum total interactions limit (%d)", MAX_INTERACTIONS_PER_URL)
                break
                
            # Then check click-specific limit
            if click_interactions >= MAX_CLICK_INTERACTIONS_PER_URL:
                logger.info("Reached maximum click interactions limit (%d)", MAX_CLICK_INTERACTIONS_PER_URL)
                break
                
            # Reset redirect count for new element
            redirect_count = 0
            
            try:
                # Skip elements we've already interacted with
                element_path = element.get('elementPath')
                if not element_path or element_path in interacted_elements:
                    continue
                    
                # Create a unique ID for this element
                element_id = element_path.split('/')[-1]
                if not element_id:
                    element_id = f"click_{len(interacted_elements)}"
                
                # Get element tag and attributes
                tag_name = element.get('tagName', '').lower()
                attributes = element.get('attributes', {})
                element_type = attributes.get('type', '').lower()
                role = attributes.get('role', '').lower()
                
                logger.info("Processing clickable element: %s (type: %s, role: %s)", 
                           element_id, element_type or tag_name, role)
                
                # First scroll element into view
                scroll_success = await self.browser_manager.scroll_element_into_view(page, element)
                if not scroll_success:
                    logger.warning("Could not scroll element into view, skipping: %s", element_id)
                    continue
                
                # Create the XPath locator
                locator = page.locator(f"xpath={element_path}")
                
                # Check if element exists and is visible
                if not locator:
                    logger.warning("Element not found with XPath: %s", element_path)
                    continue
                    
                # Wait to ensure element is visible and stable
                try:
                    await locator.wait_for(state="visible", timeout=5000)
                except Exception as e:
                    logger.warning("Element not visible after waiting: %s - %s", element_id, str(e))
                    continue
                
                # Create the result data structure
                interaction_data = {
                    "element_id": element_id,
                    "element_path": element_path,
                    "tag_name": tag_name,
                    "element_type": element_type,
                    "role": role,
                    "interaction_type": "click",
                    "timestamp": datetime.now().isoformat(),
                    "success": False,
                    "redirects": []
                }
                
                # Capture state before interaction
                before_interaction = await self._capture_interaction_state(
                    page=page,
                    element_id=element_id,
                    element_path=element_path,
                    tag_name=tag_name,
                    element_type=element_type,
                    interaction_type="click_before"
                )
                
                # Initialize after_interaction to avoid "referenced before assignment" error
                after_interaction = None
                interaction_success = False
                
                try:
                    # Get the current number of pages in the context before clicking
                    pre_click_pages = page.context.pages
                    pre_click_page_count = len(pre_click_pages)
                    pre_click_page_urls = {p.url for p in pre_click_pages}
                    
                    # Set up a promise for navigation in current page
                    navigation_promise = None
                    try:
                        navigation_promise = page.wait_for_navigation(timeout=REDIRECT_TIMEOUT_MS)
                    except Exception:
                        pass
                    
                    # DUAL APPROACH: Use both event-based and page comparison methods
                    # 1. Event-based approach for immediate detection
                    popup_future = asyncio.get_event_loop().create_future()
                    
                    # Define a handler that will be called when a popup is created
                    def on_popup(popup_page):
                        logger.info("Popup event detected for element: %s", element_id)
                        if not popup_future.done():
                            popup_future.set_result(popup_page)
                    
                    # Register the popup event handler on this specific page
                    page.on("popup", on_popup)
                    
                    # Click the element
                    await locator.click(delay=random.randint(50, 150))
                    
                    # Wait a short time for any new page or navigation to occur
                    await asyncio.sleep(0.5)
                    
                    # Check for popup using the event handler
                    popup = None
                    try:
                        # Wait for up to 2 seconds for popup event
                        popup = await asyncio.wait_for(popup_future, timeout=2)
                        logger.info("Popup detected via event after clicking: %s", element_id)
                    except asyncio.TimeoutError:
                        logger.debug("No popup detected via event after clicking: %s", element_id)
                    except Exception as e:
                        logger.warning("Error checking for popup via event: %s", str(e))
                    finally:
                        # Always remove the listener to avoid memory leaks
                        try:
                            page.remove_listener("popup", on_popup)
                        except Exception as e:
                            logger.warning("Error removing popup listener: %s", str(e))
                            
                    # If no popup was detected via event, use page comparison as backup
                    if not popup:
                        # 2. Page comparison approach as fallback
                        try:
                            # Get current pages after click
                            post_click_pages = page.context.pages
                            
                            # Check if we have new pages
                            if len(post_click_pages) > pre_click_page_count:
                                # Find new pages that weren't there before
                                for new_p in post_click_pages:
                                    if new_p not in pre_click_pages:
                                        logger.info("New page detected via comparison after clicking: %s", element_id)
                                        popup = new_p
                                        break
                        except Exception as e:
                            logger.warning("Error in page comparison method: %s", str(e))
                    
                    # Process the popup if detected (by either method)
                    if popup:
                        try:
                            # Wait for the popup to load
                            await popup.wait_for_load_state("domcontentloaded", timeout=REDIRECT_TIMEOUT_MS)
                            
                            # Now we can safely access the URL
                            popup_url = popup.url
                            logger.info("Popup URL: %s", popup_url)
                            
                            # Take screenshot of the popup
                            popup_screenshot = await capture_high_quality_screenshot(
                                popup, self.storage_manager.screenshot_quality
                            )
                            
                            # Collect interactive elements data from popup
                            popup_elements = await self.browser_manager.detect_interactive_elements(popup)
                            
                            # Store information about popup
                            interaction_data["new_tab"] = {
                                "url": popup_url,
                                "title": await popup.title(),
                                "element_count": len(popup_elements.get("interactiveElements", [])),
                                "screenshot_taken": bool(popup_screenshot)
                            }
                            
                            # Also collect any URLs from this popup
                            if hasattr(self, 'extract_urls_from_elements'):
                                try:
                                    popup_urls = await self.extract_urls_from_elements(
                                        popup_elements.get("interactiveElements", []), 
                                        popup_url
                                    )
                                    interaction_data["new_tab"]["discovered_urls"] = popup_urls
                                except Exception as e:
                                    logger.warning("Failed to extract URLs from popup: %s", str(e))
                            
                            # Save the screenshot to storage
                            if popup_screenshot:
                                # Create a popup screenshot directory
                                popup_id = f"popup_{self._generate_unique_element_id(element_id, tag_name, element_type, 'popup')}"
                                popup_dir = self.storage_manager.create_directory_structure(popup_url, popup_id, "popup")
                                popup_screenshot_path = popup_dir / f"{popup_id}.png"
                                
                                # Save screenshot directly
                                screenshot_saved = self.storage_manager.save_screenshot(popup_screenshot_path, popup_screenshot)
                                if screenshot_saved:
                                    interaction_data["new_tab"]["screenshot_path"] = str(popup_screenshot_path)
                                else:
                                    logger.warning("Failed to save popup screenshot")


                                
                            # For popups, we still need to capture after interaction state of the original page
                            after_interaction = await self._capture_interaction_state(
                                page=page,
                                element_id=element_id,
                                element_path=element_path,
                                tag_name=tag_name,
                                element_type=element_type,
                                interaction_type="click_after_popup",
                                extra_data={
                                    "before_storage_path": before_interaction["storage_path"],
                                    "popup_processed": True
                                }
                            )
                            
                            # Close the popup after processing it
                            await popup.close()
                            logger.info("Closed popup after capturing data")
                            
                            interaction_success = True
                            click_interactions += 1
                            total_interactions += 1
                            successful_interactions += 1
                            interaction_data = after_interaction
                            
                        except Exception as e:
                            logger.error("Error processing popup: %s", str(e))
                            # Still try to close the popup to avoid resource leaks
                            try:
                                if popup:
                                    await popup.close()
                            except Exception:
                                pass
                    else:
                        # If no popup was processed, check if navigation occurred in current page
                        try:
                            # Check if the navigation promise was fulfilled
                            if navigation_promise:
                                result = await navigation_promise
                                if result:
                                    redirect_count += 1
                                    logger.info("Navigation occurred (%d/%d): %s -> %s", 
                                            redirect_count, MAX_REDIRECTS_PER_INTERACTION,
                                            original_url, result.url)
                                    
                                    interaction_data["redirects"].append({
                                        "from_url": original_url,
                                        "to_url": result.url,
                                        "redirect_number": redirect_count
                                    })
                                    
                                    page_changed = True
                                    
                                    # Check redirect limit
                                    if redirect_count >= MAX_REDIRECTS_PER_INTERACTION:
                                        logger.info("Reached maximum redirects limit (%d)", MAX_REDIRECTS_PER_INTERACTION)
                                        break
                                    
                                    # Wait for the page to stabilize
                                    await page.wait_for_load_state("domcontentloaded")
                            
                                    # Capture state after navigation
                                    after_interaction = await self._capture_interaction_state(
                                        page=page,
                                        element_id=element_id,
                                        element_path=element_path,
                                        tag_name=tag_name,
                                        element_type=element_type,
                                        interaction_type="click_after_navigation",
                                        extra_data={
                                            "navigation": {
                                                "from_url": original_url,
                                                "to_url": result.url,
                                                "redirect_number": redirect_count
                                            },
                                            "before_storage_path": before_interaction["storage_path"]
                                        }
                                    )
                                    
                                    # If using original page and it changed, return to original URL if needed
                                    if page_changed and RETURN_TO_ORIGINAL_URL:
                                        try:
                                            await page.goto(original_url, timeout=REDIRECT_TIMEOUT_MS)
                                            await page.wait_for_load_state("domcontentloaded")
                                            page_changed = False  # Reset flag since we're back
                                        except Exception as e:
                                            logger.error("Failed to return to original URL: %s", str(e))
                                            break
                                else:
                                    # Check if URL changed without navigation promise being fulfilled
                                    current_url = page.url
                                    if current_url != original_url:
                                        redirect_count += 1
                                        logger.info("URL changed without navigation event (%d/%d): %s -> %s", 
                                                redirect_count, MAX_REDIRECTS_PER_INTERACTION,
                                                original_url, current_url)
                                        
                                        page_changed = True
                                        
                                        # Capture state after URL change
                                        after_interaction = await self._capture_interaction_state(
                                            page=page,
                                            element_id=element_id,
                                            element_path=element_path,
                                            tag_name=tag_name,
                                            element_type=element_type,
                                            interaction_type="click_after_url_change",
                                            extra_data={
                                                "navigation": {
                                                    "from_url": original_url,
                                                    "to_url": current_url,
                                                    "redirect_number": redirect_count
                                                },
                                                "before_storage_path": before_interaction["storage_path"]
                                            }
                                        )
                                        
                                        # Return to original URL if needed
                                        if RETURN_TO_ORIGINAL_URL:
                                            try:
                                                await page.goto(original_url, timeout=REDIRECT_TIMEOUT_MS)
                                                await page.wait_for_load_state("domcontentloaded")
                                                page_changed = False  # Reset flag since we're back
                                            except Exception as e:
                                                logger.error("Failed to return to original URL: %s", str(e))
                                            break
                                    else:
                                        # No navigation or URL change, just capture current state
                                        await page.wait_for_timeout(random.randint(500, 1000))
                                        after_interaction = await self._capture_interaction_state(
                                            page=page,
                                            element_id=element_id,
                                            element_path=element_path,
                                            tag_name=tag_name,
                                            element_type=element_type,
                                            interaction_type="click_after",
                                            extra_data={
                                                "before_storage_path": before_interaction["storage_path"]
                                            }
                                        )
                        except Exception as e:
                            logger.warning("Error checking navigation: %s", str(e))
                            # No navigation occurred or error checking it, capture normal after state
                            await page.wait_for_timeout(random.randint(500, 1000))
                            after_interaction = await self._capture_interaction_state(
                                page=page,
                                element_id=element_id,
                                element_path=element_path,
                                tag_name=tag_name,
                                element_type=element_type,
                                interaction_type="click_after",
                                extra_data={
                                    "before_storage_path": before_interaction["storage_path"]
                                }
                            )
                        
                        if after_interaction is not None:  # Only update if we have a valid result
                            interaction_success = True
                            click_interactions += 1
                            total_interactions += 1
                            successful_interactions += 1
                            interaction_data = after_interaction
                
                except Exception as e:
                    logger.warning("Click interaction failed: %s - %s", element_id, str(e))
                    interaction_data["error"] = str(e)
                    
                    # Always try to return to original URL even if the interaction fails
                    if page_changed and RETURN_TO_ORIGINAL_URL:
                        try:
                            logger.info("Returning to original URL after interaction failure: %s", original_url)
                            await page.goto(original_url, timeout=REDIRECT_TIMEOUT_MS)
                            await page.wait_for_load_state("domcontentloaded")
                            page_changed = False
                        except Exception as nav_error:
                            logger.error("Failed to return to original URL after interaction error: %s", str(nav_error))
                    
                    if not interaction_success:
                        total_interactions += 1  # Count failed interactions too
                
                # Store the interaction result regardless of success
                interaction_results.append(interaction_data)
                
                # Mark this element as interacted with to avoid duplicates
                interacted_elements.add(element_path)
                
                # Pause between interactions
                await page.wait_for_timeout(random.randint(500, 1000))
                    
            except Exception as e:
                logger.error("Error interacting with clickable element: %s", str(e))
        
        logger.info("Successfully interacted with %d/%d clickable elements", 
                   successful_interactions, len(elements))
        
        return interaction_results

    def _generate_unique_element_id(self, element_id: str, tag_name: str, element_type: str, interaction_type: str) -> str:
        """
        Generate a unique element ID for storage purposes
        
        Args:
            element_id: Original element ID
            tag_name: HTML tag name
            element_type: Type of element (input, button, etc)
            interaction_type: Type of interaction being performed
            
        Returns:
            Unique element ID string
        """
        timestamp = datetime.now().strftime("%H%M%S")
        # Use original element_id if available, otherwise create from other attributes
        base_id = element_id if element_id else f"{tag_name}_{element_type}"
        return f"interaction_{interaction_type}_{base_id}_{timestamp}"

    async def _capture_interaction_state(self, page, element_id: str, element_path: str, 
                                      tag_name: str, element_type: str, interaction_type: str,
                                      extra_data: dict = None) -> dict:
        """
        Capture the state before/after an interaction including screenshot and interactive elements
        
        Args:
            page: Playwright page object
            element_id: Element identifier
            element_path: Element selector path
            tag_name: HTML tag name
            element_type: Type of element
            interaction_type: Type of interaction (before/after)
            extra_data: Additional data to include in the interaction data
            
        Returns:
            Dictionary containing the interaction data and storage information
        """
        # Wait for page to be fully loaded - important for after-click states
        if interaction_type == "click_after":
            try:
                # Wait for network to be idle (no new requests for at least 500ms)
                await page.wait_for_load_state("networkidle", timeout=15000)
                
                # Wait for dom content to be loaded
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                
                # Enhanced animation settling approach
                await page.wait_for_timeout(random.randint(1500, 2000))
                
                # await self._wait_for_animations_to_settle(page)
                
                # Check if page is still loading by looking at navigation progress
                is_loading = await page.evaluate("() => document.readyState !== 'complete'")
                if is_loading:
                    logger.info("Page still loading after waiting, allowing additional time")
                    await page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning("Error while waiting for page to load: %s", str(e))
        
        # Take screenshot
        screenshot = await capture_high_quality_screenshot(page, self.storage_manager.screenshot_quality)
        
        # Collect interactive elements
        elements_data = await self.browser_manager.detect_interactive_elements(page)
        
        # Generate unique ID for storage
        unique_id = self._generate_unique_element_id(element_id, tag_name, element_type, interaction_type)
        
        # Create interaction data
        interaction_data = {
                        "element_id": element_id,
            "unique_id": unique_id,
                        "element_path": element_path,
                        "tag_name": tag_name,
                        "element_type": element_type,
            "interaction_type": interaction_type,
                        "timestamp": datetime.now().isoformat(),
            "interactiveElements": elements_data.get("interactiveElements", []),
            "websiteInfo": elements_data.get("websiteInfo", {}),
            "viewportSize": elements_data.get("viewportSize", {}),
            "scrollPosition": elements_data.get("scrollPosition", {}),
                        "success": True
                    }
        
        # Add any extra data
        if extra_data:
            interaction_data.update(extra_data)
            
        # Store the interaction
        storage_result = self.storage_manager.store_interaction(
                        url=page.url,
            screenshot_data=screenshot,
            data=interaction_data,
            interaction_name=unique_id,  # Already prefixed with interaction_ in _generate_unique_element_id
            element_id=unique_id
        )
        
        # Add storage path to interaction data
        interaction_data["storage_path"] = str(storage_result["interaction_dir"])
        
        return interaction_data

    async def _wait_for_animations_to_settle(self, page, max_wait_time=5000):
        """
        Wait for animations to settle on a page using heuristics to detect when animations are complete.
        
        This uses multiple techniques:
        1. Initial fixed wait for short animations
        2. Monitoring DOM changes
        3. Checking animation and transition properties
        4. Adaptive waiting based on activity

        Args:
            page: The Playwright page object
            max_wait_time: Maximum time to wait in milliseconds
            
        Returns:
            None
        """
        try:
            logger.info("Waiting for animations to settle...")
            
            # First, a short initial wait for any immediate animations
            await page.wait_for_timeout(1000)
            
            # Set a hard timeout
            start_time = time.time()
            max_wait_seconds = max_wait_time / 1000
            
            # Execute the animation detection script
            animation_status = await page.evaluate("""
                () => {
                    // Function to get all elements with animations/transitions
                    function getAnimatedElements() {
                        const elements = Array.from(document.querySelectorAll('*'));
                        return elements.filter(el => {
                            if (!el || !el.style) return false;
                            
                            const style = window.getComputedStyle(el);
                            const hasAnimation = style.animation !== 'none' && style.animation !== '';
                            const hasTransition = style.transition !== 'none' && style.transition !== '';
                            const hasTransform = style.transform !== 'none';
                            const isAnimating = hasAnimation || hasTransition || hasTransform;
                            
                            // Check for ongoing CSS animations
                            const animations = el.getAnimations ? el.getAnimations() : [];
                            const hasRunningAnimation = animations.some(a => a.playState === 'running');
                            
                            return isAnimating || hasRunningAnimation;
                        });
                    }
                    
                    // Get initial state
                    const initialAnimatedCount = getAnimatedElements().length;
                    
                    // Return initial status
                    return {
                        animatedElementsCount: initialAnimatedCount,
                        hasAnimations: initialAnimatedCount > 0
                    };
                }
            """)
            
            # If no animations detected initially, just return early
            if not animation_status.get('hasAnimations', False):
                logger.info("No animations detected, continuing")
                return
                
            # For pages with animations, perform adaptive waiting
            await page.wait_for_timeout(500)  # Wait a bit more
            
            # Check again after initial wait to see if animations are still running
            animation_settled = False
            check_count = 0
            
            while not animation_settled and (time.time() - start_time) < max_wait_seconds:
                # Limit the number of checks to avoid excessive evaluation
                if check_count >= 5:
                    logger.info("Maximum animation checks reached, continuing")
                    break
                    
                animation_check = await page.evaluate("""
                    () => {
                        // Same function as above
                        function getAnimatedElements() {
                            const elements = Array.from(document.querySelectorAll('*'));
                            return elements.filter(el => {
                                if (!el || !el.style) return false;
                                
                                const style = window.getComputedStyle(el);
                                const hasAnimation = style.animation !== 'none' && style.animation !== '';
                                const hasTransition = style.transition !== 'none' && style.transition !== '';
                                const hasTransform = style.transform !== 'none';
                                const isAnimating = hasAnimation || hasTransition || hasTransform;
                                
                                // Check for ongoing CSS animations
                                const animations = el.getAnimations ? el.getAnimations() : [];
                                const hasRunningAnimation = animations.some(a => a.playState === 'running');
                                
                                return isAnimating || hasRunningAnimation;
                            });
                        }
                        
                        // Check current state
                        const currentAnimatedElements = getAnimatedElements();
                        return {
                            animatedElementsCount: currentAnimatedElements.length,
                            hasAnimations: currentAnimatedElements.length > 0,
                            animationIds: currentAnimatedElements.map(el => {
                                try {
                                    // Create a simple identifier
                                    return `${el.tagName}[${el.className}]`;
                                } catch (e) {
                                    return null;
                                }
                            }).filter(Boolean)
                        };
                    }
                """)
                
                if not animation_check.get('hasAnimations', False):
                    logger.info("Animations have settled")
                    animation_settled = True
                    break
                    
                # Wait a bit longer before checking again
                wait_time = min(500, (max_wait_time - (time.time() - start_time) * 1000))
                if wait_time > 0:
                    await page.wait_for_timeout(wait_time)
                
                check_count += 1
                
            # Final wait to ensure stability
            elapsed = time.time() - start_time
            remaining_wait = max(0, min(1000, max_wait_time - elapsed * 1000))
            
            if remaining_wait > 0:
                logger.info("Final animation settling wait: %dms", remaining_wait)
                await page.wait_for_timeout(remaining_wait)
                
            logger.info("Animation settling complete (elapsed: %.1fs)", time.time() - start_time)
            
        except Exception as e:
            logger.warning("Error while waiting for animations: %s", str(e))
            # Fall back to a simple timeout
            await page.wait_for_timeout(2000)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extension-based web crawler for interactive element detection"
    )
    parser.add_argument("--worker-id", help="Unique identifier for this worker")
    parser.add_argument(
        "--concurrent-domains",
        type=int,
        default=1,
        help="Number of domains to process concurrently",
    )
    parser.add_argument(
        "--url-batch-size",
        type=int,
        default=10,
        help="Number of URLs to process in a batch for each domain",
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )
    parser.add_argument(
        "--extension-path", help="Path to the Chrome extension directory"
    )
    parser.add_argument(
        "--data-dir", default=str(DATA_DIR), help="Directory to store crawl data"
    )
    parser.add_argument(
        "--form-data-variety",
        type=int,
        default=FORM_DATA_VARIETY,
        choices=[1, 2, 3],
        help="Level of variety in form data (1=minimal, 2=medium, 3=extensive)",
    )
    parser.add_argument(
        "--form-data-region",
        default="india",
        help="Region to use for form data (india, global)",
    )
    parser.add_argument(
        "--profiles-file", help="Path to JSON file with form filling profiles"
    )

    args = parser.parse_args()

    # Check Redis connection
    if not domain_manager.healthcheck():
        logger.error("Redis connection failed. Please check your connection settings.")
        return

    logger.info("Redis connection successful!")

    # Create and start the crawler
    crawler = ExtensionCrawler(
        worker_id=args.worker_id,
        headless=args.headless,
        extension_path=args.extension_path,
        data_dir=args.data_dir,
        form_data_variety=args.form_data_variety,
        form_data_region=args.form_data_region,
        profiles_file=args.profiles_file,
        url_batch_size=args.url_batch_size,
    )
    
    await crawler.start(num_concurrent_domains=args.concurrent_domains)


if __name__ == "__main__":
    asyncio.run(main())
