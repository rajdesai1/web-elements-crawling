#!/usr/bin/env python3
"""
Domain Storage Manager for Extension Crawler
Handles structured storage of viewports and interactions with robust organization
"""

import hashlib
import json
import logging
import os
import re
import shutil
import time
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from patchright.async_api import Browser

logger = logging.getLogger(__name__)

class DomainStorageManager:
    """
    Advanced storage manager with domain-based organization that supports both viewport captures
    and element interactions.
    
    Storage structure:
    base_dir/
      domain1.com/
        url1/
          viewport_TIMESTAMP_ID/
            viewport_TIMESTAMP_ID.png
            viewport_TIMESTAMP_ID.json
          interaction_TIMESTAMP_ID/
            interaction_TIMESTAMP_ID.png
            interaction_TIMESTAMP_ID.json
          session_metadata.json
        url2/
          ...
      domain2.com/
        ...
    """
    
    def __init__(self, 
                base_dir: str,
                screenshot_quality: int = 100,
                max_retries: int = 3,
                retry_delay: float = 1.0):
        """
        Initialize the domain storage manager
        
        Args:
            base_dir: Base directory for storing all crawled data
            screenshot_quality: Quality of screenshots (1-100)
            max_retries: Maximum number of retries for storage operations
            retry_delay: Delay between retries in seconds
        """
        self.base_dir = Path(base_dir).resolve()
        self.screenshot_quality = max(1, min(100, screenshot_quality))
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Create base directory if it doesn't exist
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Domain storage manager initialized with base directory: %s", self.base_dir)
        logger.info("Screenshot quality set to: %d", self.screenshot_quality)
    
    def sanitize_filename(self, name: str) -> str:
        """
        Sanitize a string to be used as a valid filename
        
        Args:
            name: String to sanitize
            
        Returns:
            Sanitized string valid for use as a filename
        """
        # Remove URL scheme and parameters
        name = re.sub(r'^https?://', '', name)
        name = re.sub(r'[?#].*$', '', name)
        
        # Replace invalid characters with underscores
        name = re.sub(r'[\\/*?:"<>|]', '_', name)
        
        # Limit length to avoid path too long errors
        if len(name) > 200:
            # Keep the first 100 and last 100 chars with a hash in between
            hash_part = hashlib.md5(name.encode()).hexdigest()[:8]
            name = f"{name[:96]}_{hash_part}_{name[-96:]}"
            
        return name
    
    def get_domain_from_url(self, url: str) -> str:
        """
        Extract the domain from a URL
        
        Args:
            url: Full URL
            
        Returns:
            Domain name
        """
        # Parse the URL
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc
        
        # Remove www. prefix if present
        domain = re.sub(r'^www\.', '', domain)
        
        # Handle empty domain
        if not domain:
            domain = "unknown_domain"
            
        return domain
    
    def get_url_path(self, url: str) -> str:
        """
        Extract a sanitized path from a URL for folder naming
        
        Args:
            url: Full URL
            
        Returns:
            Sanitized URL path for folder structure
        """
        # Parse the URL
        parsed_url = urllib.parse.urlparse(url)
        
        # Create a path-friendly version of the URL
        path = parsed_url.path
        
        # Handle empty paths and paths that are just a slash - treat them the same
        if not path or path == '/':
            return "root"
            
        # Remove leading and trailing slashes
        path = path.strip('/')
        # Replace slashes with underscores
        path = path.replace('/', '_')
        
        # Add query parameters as a hash if present
        if parsed_url.query:
            query_hash = hashlib.md5(parsed_url.query.encode()).hexdigest()[:8]
            path = f"{path}_q{query_hash}"
            
        # Sanitize and limit length
        return self.sanitize_filename(path)
    
    def create_capture_id(self, prefix: str = "capture") -> str:
        """
        Create a unique ID for a capture folder
        
        Args:
            prefix: Prefix for the capture ID (viewport, interaction, error)
            
        Returns:
            Unique capture ID
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        # Sanitize prefix
        prefix = self.sanitize_filename(prefix)
        return f"{prefix}_{timestamp}_{unique_id}"
    
    def get_storage_paths(self, 
                         url: str, 
                         capture_id: Optional[str] = None,
                         prefix: str = "capture") -> Tuple[Path, Path, Path]:
        """
        Get paths for storing data for a URL
        
        Args:
            url: URL being processed
            capture_id: Optional custom capture ID
            prefix: Type of capture (viewport, interaction, error)
            
        Returns:
            Tuple of (domain_dir, url_dir, capture_dir)
        """
        domain = self.get_domain_from_url(url)
        url_path = self.get_url_path(url)
        
        domain_dir = self.base_dir / domain
        url_dir = domain_dir / url_path
        
        if not capture_id:
            capture_id = self.create_capture_id(prefix)
            
        capture_dir = url_dir / capture_id
        
        return domain_dir, url_dir, capture_dir
    
    def create_directory_structure(self, url: str, capture_id: Optional[str] = None, prefix: str = "capture") -> Path:
        """
        Create the directory structure for storing data
        
        Args:
            url: URL being processed
            capture_id: Optional custom capture ID
            prefix: Type of capture (viewport, interaction, error)
            
        Returns:
            Path to the capture directory
        """
        domain_dir, url_dir, capture_dir = self.get_storage_paths(url, capture_id, prefix)
        
        # Create directories with retries
        for i in range(self.max_retries):
            try:
                domain_dir.mkdir(parents=True, exist_ok=True)
                url_dir.mkdir(parents=True, exist_ok=True)
                capture_dir.mkdir(parents=True, exist_ok=True)
                return capture_dir
            except Exception as e:
                if i < self.max_retries - 1:
                    logger.warning("Retry %d/%d: Error creating directory: %s", i+1, self.max_retries, e)
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Failed to create directory structure after %d attempts: %s", self.max_retries, e)
                    raise
    
    def save_screenshot(self, 
                       screenshot_path: Union[str, Path], 
                       screenshot_data: bytes) -> bool:
        """
        Save a screenshot to the specified path
        
        Args:
            screenshot_path: Path to save the screenshot
            screenshot_data: Binary screenshot data
            
        Returns:
            True if successful, False otherwise
        """
        screenshot_path = Path(screenshot_path)
        
        for i in range(self.max_retries):
            try:
                with open(screenshot_path, 'wb') as f:
                    f.write(screenshot_data)
                logger.info("Screenshot saved to: %s", screenshot_path)
                return True
            except Exception as e:
                if i < self.max_retries - 1:
                    logger.warning("Retry %d/%d: Error saving screenshot: %s", i+1, self.max_retries, e)
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Failed to save screenshot after %d attempts: %s", self.max_retries, e)
                    return False
    
    def save_json_data(self, json_path: Union[str, Path], data: Dict) -> bool:
        """
        Save JSON data to the specified path
        
        Args:
            json_path: Path to save the JSON data
            data: Dictionary to save
            
        Returns:
            True if successful, False otherwise
        """
        json_path = Path(json_path)
        
        for i in range(self.max_retries):
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info("JSON data saved to: %s", json_path)
                return True
            except Exception as e:
                if i < self.max_retries - 1:
                    logger.warning("Retry %d/%d: Error saving JSON data: %s", i+1, self.max_retries, e)
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Failed to save JSON data after %d attempts: %s", self.max_retries, e)
                    return False
    
    def store_viewport(self, 
                     url: str, 
                     screenshot_data: bytes, 
                     metadata: Dict,
                     viewport_name: Optional[str] = None,
                     viewport_index: Optional[int] = None,
                     scrollability_data: Optional[Dict] = None) -> Dict[str, Union[str, Path, bool]]:
        """
        Store a viewport screenshot and metadata for a URL
        
        Args:
            url: URL being processed
            screenshot_data: Binary screenshot data
            metadata: Dictionary with viewport metadata
            viewport_name: Optional custom name for the viewport
            viewport_index: Optional viewport index (e.g., 1, 2, 3...)
            scrollability_data: Optional scrollability information from calculate_scrollability
            
        Returns:
            Dictionary with storage information
        """
        # Create a viewport ID with the appropriate prefix
        prefix = "viewport"
        if viewport_index is not None:
            prefix = f"viewport{viewport_index:02d}"
            
        # Use custom viewport name if provided
        viewport_id = viewport_name if viewport_name else self.create_capture_id(prefix)
        
        # Create directory structure
        viewport_dir = self.create_directory_structure(url, viewport_id, prefix)
        
        # Define paths for screenshot and JSON
        screenshot_path = viewport_dir / f"{viewport_id}.png"
        json_path = viewport_dir / f"{viewport_id}.json"
        
        # Add metadata to the JSON
        viewport_metadata = {
            "url": url,
            "domain": self.get_domain_from_url(url),
            "timestamp": datetime.now().isoformat(),
            "viewport_id": viewport_id,
            "type": "viewport",
            "viewport_index": viewport_index
        }
        
        if isinstance(metadata, dict):
            metadata["_metadata"] = viewport_metadata
        else:
            metadata = {"data": metadata, "_metadata": viewport_metadata}
        
        # Save the screenshot and JSON data
        screenshot_success = self.save_screenshot(screenshot_path, screenshot_data)
        json_success = self.save_json_data(json_path, metadata)
        
        # Update the session metadata file with scrollability data if provided
        self.update_session_metadata(url, viewport_id, "viewport", viewport_index, scrollability_data=scrollability_data)
        
        if screenshot_success and json_success:
            logger.info("Viewport %s stored successfully for URL: %s", viewport_id, url)
            return {
                "viewport_id": viewport_id,
                "viewport_dir": viewport_dir,
                "screenshot_path": screenshot_path,
                "json_path": json_path,
                "success": True
            }
        else:
            logger.error("Failed to store viewport %s for URL: %s", viewport_id, url)
            return {
                "viewport_id": viewport_id,
                "viewport_dir": viewport_dir,
                "screenshot_path": screenshot_path if screenshot_success else None,
                "json_path": json_path if json_success else None,
                "success": False
            }
    
    def store_interaction(self, 
                        url: str, 
                        screenshot_data: bytes, 
                        data: Dict,
                        interaction_name: Optional[str] = None,
                        element_id: Optional[str] = None) -> Dict[str, Union[str, Path, bool]]:
        """
        Store an interaction screenshot and data for a URL
        
        Args:
            url: URL being processed
            screenshot_data: Binary screenshot data
            data: Dictionary with interaction data
            interaction_name: Optional custom name for the interaction
            element_id: Optional element identifier
            
        Returns:
            Dictionary with storage information
        """
        # Create an interaction ID with the appropriate prefix
        prefix = "interaction"
        if element_id:
            # Create a shortened, sanitized element ID
            short_element_id = self.sanitize_filename(element_id)[:20]
            prefix = f"interaction_{short_element_id}"
            
        # Use custom interaction name if provided
        interaction_id = interaction_name if interaction_name else self.create_capture_id(prefix)
        
        # Create directory structure - USING THE SAME PATTERN AS STORE_VIEWPORT
        interaction_dir = self.create_directory_structure(url, interaction_id, prefix)
        
        # Define paths for screenshot and JSON
        screenshot_path = interaction_dir / f"{interaction_id}.png"
        json_path = interaction_dir / f"{interaction_id}.json"
        
        # Add metadata to the JSON
        interaction_metadata = {
            "url": url,
            "domain": self.get_domain_from_url(url),
            "timestamp": datetime.now().isoformat(),
            "interaction_id": interaction_id,
            "element_id": element_id,
            "type": "interaction"
        }
        
        if isinstance(data, dict):
            data["_metadata"] = interaction_metadata
        else:
            data = {"data": data, "_metadata": interaction_metadata}
        
        # Save the screenshot and JSON data
        screenshot_success = self.save_screenshot(screenshot_path, screenshot_data)
        json_success = self.save_json_data(json_path, data)
        
        # Update the session metadata file
        self.update_session_metadata(url, interaction_id, "interaction", element_id=element_id)
        
        if screenshot_success and json_success:
            logger.info("Interaction %s stored successfully for URL: %s", interaction_id, url)
            return {
                "interaction_id": interaction_id,
                "interaction_dir": interaction_dir,
                "screenshot_path": screenshot_path,
                "json_path": json_path,
                "success": True
            }
        else:
            logger.error("Failed to store interaction %s for URL: %s", interaction_id, url)
            return {
                "interaction_id": interaction_id,
                "interaction_dir": interaction_dir,
                "screenshot_path": screenshot_path if screenshot_success else None,
                "json_path": json_path if json_success else None,
                "success": False
            }
    
    def store_error(self, 
                  url: str, 
                  error_data: Dict,
                  screenshot_data: Optional[bytes] = None,
                  error_name: Optional[str] = None) -> Dict[str, Union[str, Path, bool]]:
        """
        Store error information for a URL
        
        Args:
            url: URL that encountered an error
            error_data: Dictionary with error details
            screenshot_data: Optional screenshot showing the error
            error_name: Optional custom name for the error
            
        Returns:
            Dictionary with storage information
        """
        # Create an error ID with the appropriate prefix
        prefix = "error"
        
        # Use custom error name if provided
        error_id = error_name if error_name else self.create_capture_id(prefix)
        
        # Create directory structure
        error_dir = self.create_directory_structure(url, error_id, prefix)
        
        # Define paths for screenshot and JSON
        json_path = error_dir / f"{error_id}.json"
        screenshot_path = error_dir / f"{error_id}.png" if screenshot_data else None
        
        # Add metadata to the JSON
        error_metadata = {
            "url": url,
            "domain": self.get_domain_from_url(url),
            "timestamp": datetime.now().isoformat(),
            "error_id": error_id,
            "type": "error"
        }
        
        if isinstance(error_data, dict):
            error_data["_metadata"] = error_metadata
        else:
            error_data = {"error": error_data, "_metadata": error_metadata}
        
        # Save the JSON data
        json_success = self.save_json_data(json_path, error_data)
        
        # Save the screenshot if provided
        screenshot_success = False
        if screenshot_data and screenshot_path:
            screenshot_success = self.save_screenshot(screenshot_path, screenshot_data)
        
        # Update the session metadata file
        self.update_session_metadata(url, error_id, "error")
        
        result = {
            "error_id": error_id,
            "error_dir": error_dir,
            "json_path": json_path,
            "success": json_success
        }
        
        if screenshot_path:
            result["screenshot_path"] = screenshot_path if screenshot_success else None
        
        if json_success:
            logger.info(f"Error {error_id} stored successfully for URL: {url}")
        else:
            logger.error(f"Failed to store error {error_id} for URL: {url}")
        
        return result
    
    def update_session_metadata(self, url: str, capture_id: str, capture_type: str, 
                             viewport_index: Optional[int] = None, 
                             element_id: Optional[str] = None,
                             scrollability_data: Optional[Dict] = None) -> None:
        """
        Update session metadata for a URL
        
        Args:
            url: URL to update metadata for
            capture_id: ID of the capture (viewport, interaction, error)
            capture_type: Type of capture (viewport, interaction, error)
            viewport_index: Optional viewport index for viewport captures
            element_id: Optional element ID for interaction captures
            scrollability_data: Optional dictionary containing scrollability data
        """
        domain = self.get_domain_from_url(url)
        url_path = self.get_url_path(url)
        
        domain_dir = self.base_dir / domain
        url_dir = domain_dir / url_path
        metadata_path = url_dir / "session_metadata.json"
        
        # Initialize or load existing metadata
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in metadata file %s, initializing new metadata", metadata_path)
                metadata = {"sessions": []}
        else:
            metadata = {"sessions": []}
            
        # Ensure sessions list exists
        if "sessions" not in metadata:
            metadata["sessions"] = []
            
        # Create capture info
        capture_info = {
            "id": capture_id,
            "type": capture_type,
            "timestamp": datetime.now().isoformat()
        }
        
        # Add viewport index if provided
        if viewport_index is not None:
            capture_info["viewport_index"] = viewport_index
            
        # Add element ID if provided
        if element_id:
            capture_info["element_id"] = element_id
            
        # Find or create current session
        current_session = None
        for session in metadata["sessions"]:
            if session.get("captures") and session["captures"][-1]["id"] == capture_id:
                current_session = session
                break
                
        if not current_session:
            current_session = {
                "start_time": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "captures": [],
                "scrollability": {}
            }
            metadata["sessions"].append(current_session)
        
        # Update session data
        current_session["last_updated"] = datetime.now().isoformat()
        current_session["captures"].append(capture_info)
        
        # Update scrollability data if provided
        if scrollability_data:
            current_session["scrollability"] = scrollability_data
            
        # Save metadata with retry logic
        max_retries = 3
        retry_delay = 1.0
        
        for i in range(max_retries):
            try:
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)
                logger.debug("Updated session metadata for URL: %s", url)
                break
            except Exception as e:
                if i < max_retries - 1:
                    logger.warning("Retry %d/%d: Error updating metadata: %s", i+1, max_retries, e)
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to update metadata after %d attempts: %s", max_retries, e)
                    raise
    
    def get_url_captures(self, url: str) -> Dict[str, List[Dict]]:
        """
        Get all captures for a URL
        
        Args:
            url: URL to get captures for
            
        Returns:
            Dictionary with lists of captures by type
        """
        # Get the URL directory
        domain = self.get_domain_from_url(url)
        url_path = self.get_url_path(url)
        
        domain_dir = self.base_dir / domain
        url_dir = domain_dir / url_path
        
        metadata_path = url_dir / "session_metadata.json"
        
        if not metadata_path.exists():
            logger.warning(f"No session metadata found for URL: {url}")
            return {
                "viewports": [],
                "interactions": [],
                "errors": []
            }
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            logger.error(f"Error loading session metadata file: {e}")
            return {
                "viewports": [],
                "interactions": [],
                "errors": []
            }
        
        # Organize captures by type
        viewports = []
        interactions = []
        errors = []
        
        for capture in metadata.get("captures", []):
            capture_type = capture.get("type")
            
            if capture_type == "viewport":
                viewports.append(capture)
            elif capture_type == "interaction":
                interactions.append(capture)
            elif capture_type == "error":
                errors.append(capture)
        
        return {
            "viewports": viewports,
            "interactions": interactions,
            "errors": errors
        }
    
    def get_domain_statistics(self, domain: str) -> Dict[str, Any]:
        """
        Get statistics for a domain
        
        Args:
            domain: Domain to get statistics for
            
        Returns:
            Dictionary with domain statistics
        """
        domain_dir = self.base_dir / domain
        
        if not domain_dir.exists():
            logger.warning(f"No data found for domain: {domain}")
            return {
                "domain": domain,
                "url_count": 0,
                "captures": {
                    "viewports": 0,
                    "interactions": 0,
                    "errors": 0
                },
                "storage_size_mb": 0
            }
        
        # Count URLs
        url_count = 0
        viewport_count = 0
        interaction_count = 0
        error_count = 0
        storage_size = 0
        
        # Walk through the domain directory
        for root, dirs, files in os.walk(domain_dir):
            root_path = Path(root)
            
            # Count URLs directly under the domain directory
            if root_path.parent == domain_dir:
                url_count += 1
            
            # Count captures by type
            for capture_dir in dirs:
                if capture_dir.startswith("viewport"):
                    viewport_count += 1
                elif capture_dir.startswith("interaction"):
                    interaction_count += 1
                elif capture_dir.startswith("error"):
                    error_count += 1
            
            # Calculate storage size
            for file in files:
                file_path = root_path / file
                storage_size += file_path.stat().st_size
        
        return {
            "domain": domain,
            "url_count": url_count,
            "captures": {
                "viewports": viewport_count,
                "interactions": interaction_count,
                "errors": error_count
            },
            "storage_size_mb": storage_size / (1024 * 1024)
        }
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """
        Get overall storage statistics
        
        Returns:
            Dictionary with storage statistics
        """
        if not self.base_dir.exists():
            logger.warning(f"Base directory does not exist: {self.base_dir}")
            return {
                "domain_count": 0,
                "url_count": 0,
                "captures": {
                    "viewports": 0,
                    "interactions": 0,
                    "errors": 0
                },
                "storage_size_mb": 0
            }
        
        # List all domains
        domains = [d.name for d in self.base_dir.iterdir() if d.is_dir()]
        
        # Get statistics for each domain
        domain_stats = [self.get_domain_statistics(domain) for domain in domains]
        
        # Aggregate statistics
        url_count = sum(stats["url_count"] for stats in domain_stats)
        viewport_count = sum(stats["captures"]["viewports"] for stats in domain_stats)
        interaction_count = sum(stats["captures"]["interactions"] for stats in domain_stats)
        error_count = sum(stats["captures"]["errors"] for stats in domain_stats)
        storage_size = sum(stats["storage_size_mb"] for stats in domain_stats)
        
        return {
            "domain_count": len(domains),
            "url_count": url_count,
            "captures": {
                "viewports": viewport_count,
                "interactions": interaction_count,
                "errors": error_count
            },
            "storage_size_mb": storage_size
        }
    
    def cleanup_old_data(self, keep_days: int = 30) -> Dict[str, int]:
        """
        Remove old data that's older than the specified number of days
        
        Args:
            keep_days: Number of days to keep data for
            
        Returns:
            Dictionary with counts of removed items
        """
        if keep_days <= 0:
            logger.warning("Invalid keep_days value. Must be greater than 0.")
            return {
                "domains_removed": 0,
                "urls_removed": 0,
                "captures_removed": 0
            }
        
        # Calculate cutoff date
        cutoff_date = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)
        
        domains_removed = 0
        urls_removed = 0
        captures_removed = 0
        
        for domain_dir in self.base_dir.iterdir():
            if not domain_dir.is_dir():
                continue
                
            # Check URL directories
            for url_dir in domain_dir.iterdir():
                if not url_dir.is_dir():
                    continue
                    
                # Check captures
                captures_to_remove = []
                for capture_dir in url_dir.iterdir():
                    if not capture_dir.is_dir():
                        continue
                        
                    # Get the modification time of the capture directory
                    mod_time = capture_dir.stat().st_mtime
                    
                    if mod_time < cutoff_date:
                        captures_to_remove.append(capture_dir)
                
                # Remove old captures
                for capture_dir in captures_to_remove:
                    try:
                        shutil.rmtree(capture_dir)
                        captures_removed += 1
                    except Exception as e:
                        logger.error(f"Error removing capture directory {capture_dir}: {e}")
                
                # Check if URL directory is empty after removing captures
                remaining_items = list(url_dir.iterdir())
                if not remaining_items or (len(remaining_items) == 1 and remaining_items[0].name == "session_metadata.json"):
                    try:
                        shutil.rmtree(url_dir)
                        urls_removed += 1
                    except Exception as e:
                        logger.error("Error removing URL directory %s: %s", url_dir, e)
            
            # Check if domain directory is empty after removing URLs
            if not list(domain_dir.iterdir()):
                try:
                    shutil.rmtree(domain_dir)
                    domains_removed += 1
                except Exception as e:
                    logger.error("Error removing domain directory %s: %s", domain_dir, e)
        
        logger.info("Cleanup complete: removed %d domains, %d URLs, %d captures", domains_removed, urls_removed, captures_removed)
        return {
            "domains_removed": domains_removed,
            "urls_removed": urls_removed,
            "captures_removed": captures_removed
        }
    
    def get_session_history(self, url: str) -> Optional[Dict]:
        """
        Get the session history for a URL
        
        Args:
            url: URL to get session history for
            
        Returns:
            Dictionary containing session metadata if found, None otherwise
        """
        try:
            domain = self.get_domain_from_url(url)
            url_path = self.get_url_path(url)
            
            domain_dir = self.base_dir / domain
            url_dir = domain_dir / url_path
            metadata_path = url_dir / "session_metadata.json"
            
            if not metadata_path.exists():
                logger.debug("No session history found for URL %s", url)
                return None
                
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                
            # Sort sessions by start_time in descending order
            if "sessions" in metadata:
                metadata["sessions"].sort(key=lambda x: x.get("start_time", ""), reverse=True)
                
            return metadata
            
        except Exception as e:
            logger.error("Error retrieving session history for URL %s: %s", url, e)
            return None


# def capture_high_quality_screenshot(browser, quality: int = 100) -> bytes:
#     """
#     Capture a high-quality screenshot from a browser instance
    
#     Args:
#         browser: Browser instance
#         quality: JPEG quality (1-100)
        
#     Returns:
#         Binary screenshot data
#     """
#     try:
#         # Use the highest quality setting
#         screenshot_data = browser.screenshot(quality=quality)
#         return screenshot_data
#     except Exception as e:
#         logger.error("Error capturing high-quality screenshot: %s", e)
#         # Fallback to default quality
#         try:
#             screenshot_data = browser.screenshot()
#             return screenshot_data
#         except Exception as e:
#             logger.error("Error capturing fallback screenshot: %s", e)
#             raise 



# Helper function to get a screenshot in high quality
def capture_high_quality_screenshot(browser: Browser, quality: int = 100) -> bytes:
    """
    Capture a high-quality screenshot from a browser
    
    Args:
        browser: Browser object (Selenium or Playwright)
        quality: JPEG quality (1-100)
        
    Returns:
        Binary screenshot data
    """
    if hasattr(browser, 'get_screenshot_as_png'):
        # Selenium webdriver
        return browser.get_screenshot_as_png()
    elif hasattr(browser, 'screenshot'):
        # Playwright browser page
        try:
            # Try to get full page screenshot with high quality
            return browser.screenshot(
                type='jpeg',
                quality=quality
            )
        except:
            # Fallback to default screenshot
            return browser.screenshot()
    else:
        raise TypeError("Unsupported browser type for screenshots") 
