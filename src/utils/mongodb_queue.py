"""
MongoDB-based distributed queue for URL crawling tasks.
Allows multiple instances to pull URLs without duplication.
Also manages domain-level operations for distributed crawlers.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Union
from urllib.parse import urlparse

import pymongo
from pymongo import MongoClient

from src.config.settings import (MAX_RETRIES, MONGODB_DB_NAME,
                                 MONGODB_DOMAINS_COLLECTION, MONGODB_URI,
                                 MONGODB_URLS_COLLECTION, STATUS_COMPLETED,
                                 STATUS_FAILED, STATUS_PENDING,
                                 STATUS_PROCESSING)
from src.utils.logger import setup_logger

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = setup_logger(__name__)

# Initialize MongoDB connection
try:
    mongo_client = MongoClient(MONGODB_URI)
    db = mongo_client[MONGODB_DB_NAME]
    domains_collection = db[MONGODB_DOMAINS_COLLECTION]
    urls_collection = db[MONGODB_URLS_COLLECTION]
    
    # Create indexes for performance
    domains_collection.create_index("domain", unique=True)
    urls_collection.create_index([("domain", pymongo.ASCENDING), ("url", pymongo.ASCENDING)], unique=True)
    urls_collection.create_index([("domain", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])
    
    logger.info("MongoDB connection initialized successfully")
except Exception as e:
    logger.error("Error initializing MongoDB connection: %s", str(e))


class DomainUrlManager:
    """
    Manages URLs organized by domain for distributed crawling using MongoDB.
    Handles domain claiming, URL assignment, and status tracking.
    """
    
    def __init__(self, mongo_client=None):
        """
        Initialize the domain URL manager.
        
        Args:
            mongo_client: MongoDB client to use (creates one if not provided)
        """
        if mongo_client:
            self.mongo_client = mongo_client
        else:
            self.mongo_client = MongoClient(MONGODB_URI)
            
        self.db = self.mongo_client[MONGODB_DB_NAME]
        self.domains_collection = self.db[MONGODB_DOMAINS_COLLECTION]
        self.urls_collection = self.db[MONGODB_URLS_COLLECTION]
        
    def healthcheck(self) -> bool:
        """Check if MongoDB connection is working."""
        try:
            # Ping the database
            return self.mongo_client.admin.command('ping')['ok'] == 1.0
        except Exception as e:
            logger.error("MongoDB connection error: %s", str(e))
            return False

    def extract_domain_from_url(self, url: str) -> Optional[str]:
        """
        Extract domain from URL.
    
        Args:
            url: URL to extract domain from
    
        Returns:
            Domain name or None if URL is invalid
        """
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return None
            return parsed.netloc
        except Exception:
            return None
            
    def load_urls_from_file(self, filepath: str, batch_size: int = 1000) -> Dict[str, int]:
        """
        Load URLs from a text file and organize them by domain.
    
        Args:
            filepath: Path to file containing URLs (one per line)
            batch_size: Number of URLs to process in each batch
    
        Returns:
            Dict with domains as keys and number of URLs added as values
        """
        if not os.path.exists(filepath):
            logger.error("File not found: %s", filepath)
            return {}
            
        domains_added: Dict[str, int] = {}
        batch: Dict[str, List[str]] = {}
        batch_count = 0
        
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    url = line.strip()
                    if not url:
                        continue
                        
                    domain = self.extract_domain_from_url(url)
                    if not domain:
                        continue
    
                    if domain not in batch:
                        batch[domain] = []
                        
                    batch[domain].append(url)
                    batch_count += 1
                    
                    # Process batch if it reaches batch size
                    if batch_count >= batch_size:
                        self._process_domain_url_batch(batch, domains_added)
                        batch = {}
                        batch_count = 0
                
                # Process remaining URLs
                if batch_count > 0:
                    self._process_domain_url_batch(batch, domains_added)
            
            return domains_added
        except Exception as e:
            logger.error("Error loading URLs from file: %s", str(e))
            return domains_added
            
    def _process_domain_url_batch(self, batch: Dict[str, List[str]], domains_added: Dict[str, int]) -> None:
        """
        Process a batch of domain->URLs mappings.
    
        Args:
            batch: Dictionary of domain -> list of URLs
            domains_added: Counter dictionary to update with results
        """
        total_urls = 0
        
        logger.info("Processing batch with %d domains...", len(batch))
        for domain, urls in batch.items():
            # Add domain to the domains collection if it doesn't exist
            self.add_domain(domain)
            
            domain_url_count = 0
            for url in urls:
                added = self.add_url_to_domain(domain, url)
                if added:
                    if domain not in domains_added:
                        domains_added[domain] = 0
                    domains_added[domain] += 1
                    domain_url_count += 1
                    total_urls += 1
            
            if domain_url_count > 0:
                logger.info("  Added %d URLs for domain %s", domain_url_count, domain)
        
        logger.info("Processed %d URLs across %d domains", total_urls, len(batch))

    def add_domain(self, domain: str) -> bool:
        """
        Add a domain to the set of domains to be crawled.
        
        Args:
            domain: The domain to add
            
        Returns:
            True if successfully added, False otherwise
        """
        try:
            # Try to insert the domain
            try:
                self.domains_collection.insert_one({
                    "domain": domain,
                    "status": STATUS_PENDING,
                    "added_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                })
                logger.debug("Added new domain: %s", domain)
                return True
            except pymongo.errors.DuplicateKeyError:
                # Domain already exists, check if we need to update its status
                existing = self.domains_collection.find_one({"domain": domain})
                if existing and existing.get("status") != STATUS_PENDING:
                    # Only update if status is not already pending
                    self.domains_collection.update_one(
                        {"domain": domain},
                        {"$set": {"status": STATUS_PENDING, "last_updated": datetime.now().isoformat()}}
                    )
                    logger.debug("Updated existing domain: %s", domain)
                return True
        except Exception as e:
            logger.error("Error adding domain %s: %s", domain, str(e))
            return False

    def add_url_to_domain(self, domain: str, url: str, metadata: Optional[Dict] = None) -> bool:
        """
        Add a URL to a specific domain's queue.
        
        Args:
            domain: The domain this URL belongs to
            url: The URL to add
            metadata: Additional metadata for the URL
            
        Returns:
            True if successfully added, False otherwise
        """
        try:
            # Ensure the domain exists
            self.add_domain(domain)
            
            # Try to insert the URL
            timestamp = datetime.now().isoformat()
            url_data = {
                "domain": domain,
                "url": url,
                "added_at": timestamp,
                "status": STATUS_PENDING,
                "retries": 0,
                "last_updated": timestamp
            }
            
            if metadata:
                url_data.update(metadata)
                
            try:
                self.urls_collection.insert_one(url_data)
                logger.debug("Added URL %s to domain %s", url, domain)
                return True
            except pymongo.errors.DuplicateKeyError:
                # URL already exists for this domain, we can update metadata if needed
                if metadata:
                    self.urls_collection.update_one(
                        {"domain": domain, "url": url},
                        {"$set": {"metadata": metadata, "last_updated": timestamp}}
                    )
                logger.debug("URL %s already exists for domain %s", url, domain)
                return False
        except Exception as e:
            logger.error("Error adding URL %s to domain %s: %s", url, domain, str(e))
            return False

    def add_urls_to_domain(self, domain: str, urls: List[Union[str, Dict]]) -> int:
        """
        Add multiple URLs to a specific domain's queue.
        
        Args:
            domain: The domain these URLs belong to
            urls: The URLs to add (either strings or dictionaries with url and metadata)
            
        Returns:
            Number of URLs successfully added
        """
        count = 0
        
        # Ensure the domain exists
        self.add_domain(domain)
        
        # Add each URL individually (could optimize with bulk operations if needed)
        for url_item in urls:
            # Handle both string URLs and dictionary objects
            if isinstance(url_item, str):
                # Simple string URL
                if self.add_url_to_domain(domain, url_item):
                    count += 1
            elif isinstance(url_item, dict) and 'url' in url_item:
                # Dictionary with URL and optional metadata
                url = url_item.pop('url')  # Extract the URL
                metadata = url_item  # Use remaining dict as metadata
                
                if self.add_url_to_domain(domain, url, metadata):
                    count += 1
            else:
                logger.warning("Invalid URL item format: %s", url_item)
                
        logger.info("Added %d new URLs to domain %s", count, domain)
        return count

    def claim_domain(self, worker_id: Optional[str] = None) -> Optional[str]:
        """
        Claim an unclaimed domain for processing.
            
        Args:
            worker_id: Unique identifier for this worker (generated if not provided)
        
        Returns:
            The claimed domain or None if no domains are available
        """
        if worker_id is None:
            worker_id = str(uuid.uuid4())
            
        try:
            # Find a pending domain and atomically update its status
            timestamp = datetime.now().isoformat()
            result = self.domains_collection.find_one_and_update(
                {"status": STATUS_PENDING},
                {"$set": {
                    "status": STATUS_PROCESSING,
                    "claimed_at": timestamp,
                    "worker_id": worker_id,
                    "last_updated": timestamp,
                    "heartbeat": datetime.now().timestamp()
                }},
                return_document=pymongo.ReturnDocument.AFTER
            )
            
            if result:
                domain = result.get("domain")
                logger.info("Worker %s claimed domain: %s", worker_id, domain)
                return domain
            else:
                logger.info("No pending domains available for worker %s", worker_id)
                return None
        except Exception as e:
            logger.error("Error claiming domain: %s", str(e))
            return None

    def get_next_domain_url(self, domain: str) -> Optional[Dict]:
        """
        Get the next URL to process for a specific domain.
        
        Args:
            domain: The domain to get a URL for
            
        Returns:
            URL data dictionary or None if no URLs are available
        """
        try:
            # Find a pending URL for this domain and atomically update its status
            timestamp = datetime.now().isoformat()
            result = self.urls_collection.find_one_and_update(
                {"domain": domain, "status": STATUS_PENDING},
                {"$set": {
                    "status": STATUS_PROCESSING,
                    "processing_started": timestamp,
                    "last_updated": timestamp
                }},
                return_document=pymongo.ReturnDocument.AFTER
            )
            
            if result:
                # Convert MongoDB document to dictionary
                url_data = dict(result)
                logger.debug("Got next URL for domain %s: %s", domain, url_data.get("url"))
                
                # Return the URL with its data
                return {
                    "url": url_data.get("url"),
                    "domain": domain,
                    "data": url_data
                }
            else:
                logger.debug("No pending URLs available for domain %s", domain)
                return None
        except Exception as e:
            logger.error("Error getting next URL for domain %s: %s", domain, str(e))
            return None

    def get_domain_urls_batch(self, domain: str, batch_size: int = 10) -> List[Dict]:
        """
        Get multiple URLs to process for a specific domain in a single batch.
        
        Args:
            domain: The domain to get URLs for
            batch_size: Number of URLs to retrieve at once
            
        Returns:
            List of URL data dictionaries or empty list if no URLs are available
        """
        try:
            # Find multiple pending URLs for this domain and atomically update their status
            timestamp = datetime.now().isoformat()
            results = []
            
            # Use bulk operations for better performance
            bulk_ops = []
            pending_urls = list(self.urls_collection.find(
                {"domain": domain, "status": STATUS_PENDING},
                limit=batch_size
            ))
            
            if not pending_urls:
                logger.debug("No pending URLs available for domain %s", domain)
                return []
                
            # Prepare bulk update operations
            for url_doc in pending_urls:
                url_id = url_doc["_id"]
                bulk_ops.append(
                    pymongo.UpdateOne(
                        {"_id": url_id},
                        {"$set": {
                            "status": STATUS_PROCESSING,
                            "processing_started": timestamp,
                            "last_updated": timestamp
                        }}
                    )
                )
            
            # Execute bulk updates if we have operations
            if bulk_ops:
                self.urls_collection.bulk_write(bulk_ops)
                
                # Return the URL data
                for url_doc in pending_urls:
                    url_data = dict(url_doc)
                    results.append({
                        "url": url_data.get("url"),
                        "domain": domain,
                        "data": url_data
                    })
                
                logger.info("Got batch of %d URLs for domain %s", len(results), domain)
                return results
            else:
                return []
                
        except Exception as e:
            logger.error("Error getting URL batch for domain %s: %s", domain, str(e))
            return []

    def mark_url_completed(self, domain: str, url: str, metadata: Optional[Dict] = None) -> bool:
        """
        Mark a domain URL as completed.
        
        Args:
            domain: The domain the URL belongs to
            url: The URL that was processed
            metadata: Additional metadata about the crawl results
            
        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = datetime.now().isoformat()
            update_data = {
                "status": STATUS_COMPLETED,
                "completed_at": timestamp,
                "last_updated": timestamp
            }
            
            if metadata:
                update_data["results"] = metadata
                
            # Update the URL status
            result = self.urls_collection.update_one(
                {"domain": domain, "url": url},
                {"$set": update_data}
            )
                
            if result.modified_count > 0:
                logger.debug("Marked URL %s as completed for domain %s", url, domain)
                
                # Check if domain is complete
                if self.is_domain_processing_complete(domain):
                    self.mark_domain_completed(domain)
                
                return True
            else:
                logger.warning("Failed to mark URL %s as completed (not found or already completed)", url)
                return False
        except Exception as e:
            logger.error("Error marking URL %s as completed for domain %s: %s", url, domain, str(e))
            return False

    def mark_url_failed(self, domain: str, url: str, error: Optional[str] = None) -> bool:
        """
        Mark a domain URL as failed.
        
        Args:
            domain: The domain the URL belongs to
            url: The URL that failed
            error: Error message
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current URL data
            url_data = self.urls_collection.find_one({"domain": domain, "url": url})
            if not url_data:
                logger.warning("URL %s not found for domain %s", url, domain)
                return False
                
            timestamp = datetime.now().isoformat()
            retries = url_data.get("retries", 0)
            
            update_data = {
                "failed_at": timestamp,
                "last_updated": timestamp,
                "retries": retries + 1
            }
            
            if error:
                update_data["last_error"] = error
                
            # Check retry count
            if retries < MAX_RETRIES:
                # Reset to pending with incremented retry count
                update_data["status"] = STATUS_PENDING
            else:
                # Max retries reached
                update_data["status"] = STATUS_FAILED
            
            # Update the URL status
            result = self.urls_collection.update_one(
                {"domain": domain, "url": url},
                {"$set": update_data}
            )
                
            if result.modified_count > 0:
                logger.debug("Marked URL %s as failed for domain %s (retry %d/%d)", url, domain, retries + 1, MAX_RETRIES)
                return True
            else:
                logger.warning("Failed to mark URL %s as failed (not found)", url)
                return False
        except Exception as e:
            logger.error("Error marking URL %s as failed for domain %s: %s", url, domain, str(e))
            return False

    def mark_domain_completed(self, domain: str, metadata: Optional[Dict] = None) -> bool:
        """
        Mark a domain as completely processed.
        
        Args:
            domain: The domain that was processed
            metadata: Additional metadata about the domain processing
            
        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = datetime.now().isoformat()
            update_data = {
                "status": STATUS_COMPLETED,
                "completed_at": timestamp,
                "last_updated": timestamp
            }
            
            if metadata:
                update_data.update(metadata)
                
            # Update the domain status
            result = self.domains_collection.update_one(
                {"domain": domain},
                {"$set": update_data}
            )
                
            if result.modified_count > 0:
                logger.info("Marked domain %s as completed", domain)
                return True
            else:
                logger.warning("Failed to mark domain %s as completed (not found or already completed)", domain)
                return False
        except Exception as e:
            logger.error("Error marking domain %s as completed: %s", domain, str(e))
            return False

    def release_domain(self, domain: str, worker_id: Optional[str] = None) -> bool:
        """
        Release a domain so it can be claimed by another worker.
        
        Args:
            domain: Domain to release
            worker_id: Worker ID that currently has the domain claimed (for verification)
            
        Returns:
            True if domain was released, False otherwise
        """
        try:
            # If worker_id provided, verify it matches the current worker
            query = {"domain": domain, "status": STATUS_PROCESSING}
            if worker_id:
                query["worker_id"] = worker_id
            
            # Reset domain status to pending
            result = self.domains_collection.update_one(
                query,
                {"$set": {
                    "status": STATUS_PENDING,
                    "released_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                },
                "$unset": {"worker_id": "", "heartbeat": ""}}
            )
                
            if result.modified_count > 0:
                logger.info("Released domain %s", domain)
                return True
            else:
                logger.warning("Failed to release domain %s (not found, wrong worker, or not processing)", domain)
                return False
        except Exception as e:
            logger.error("Error releasing domain %s: %s", domain, str(e))
            return False
            
    def update_worker_heartbeat(self, worker_id: str) -> bool:
        """
        Update worker heartbeat to indicate it's still active.
        
        Args:
            worker_id: Worker ID to update
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            # Update heartbeat for all domains owned by this worker
            result = self.domains_collection.update_many(
                {"worker_id": worker_id},
                {"$set": {"heartbeat": datetime.now().timestamp()}}
            )
            
            logger.debug("Updated heartbeat for worker %s (%d domains)", worker_id, result.modified_count)
            return True
        except Exception as e:
            logger.error("Error updating worker heartbeat: %s", str(e))
            return False
            
    def get_worker_domains(self, worker_id: str) -> List[str]:
        """
        Get domains currently claimed by a worker.
        
        Args:
            worker_id: Worker ID to check
            
        Returns:
            List of domains claimed by the worker
        """
        domains = []
        try:
            # Find all domains claimed by this worker
            cursor = self.domains_collection.find({"worker_id": worker_id})
            for doc in cursor:
                domains.append(doc.get("domain"))
                    
            logger.debug("Worker %s has %d domains claimed", worker_id, len(domains))
            return domains
        except Exception as e:
            logger.error("Error getting worker domains: %s", str(e))
            return domains
            
    def reset_stalled_domains(self, timeout_minutes: int = 30) -> int:
        """
        Reset domains that have been processing for too long.
        
        Args:
            timeout_minutes: Number of minutes after which a worker is considered stalled
            
        Returns:
            Number of domains reset
        """
        reset_count = 0
        try:
            # Get all processing domains
            current_time = datetime.now().timestamp()
            timeout_seconds = timeout_minutes * 60
            
            # Find domains with old heartbeats or missing heartbeats
            cutoff_time = current_time - timeout_seconds
            
            # Find domains with old heartbeats
            stalled_domains = list(self.domains_collection.find({
                "status": STATUS_PROCESSING,
                "heartbeat": {"$lt": cutoff_time}
            }))
            
            # Also find domains with missing heartbeats
            missing_heartbeat = list(self.domains_collection.find({
                "status": STATUS_PROCESSING,
                "heartbeat": {"$exists": False}
            }))
            
            stalled_domains.extend(missing_heartbeat)
            
            # Reset each stalled domain
            for domain_doc in stalled_domains:
                domain = domain_doc.get("domain")
                worker_id = domain_doc.get("worker_id", "unknown")
                
                result = self.domains_collection.update_one(
                    {"domain": domain},
                    {"$set": {
                        "status": STATUS_PENDING,
                        "stalled_reset_at": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat(),
                        "stalled_worker": worker_id
                    },
                    "$unset": {"worker_id": "", "heartbeat": ""}}
                )
                
                if result.modified_count > 0:
                    reset_count += 1
                    logger.info("Reset stalled domain %s (worker: %s)", domain, worker_id)
            
            logger.info("Reset %d stalled domains", reset_count)
            return reset_count
        except Exception as e:
            logger.error("Error resetting stalled domains: %s", str(e))
            return reset_count
            
    def is_domain_processing_complete(self, domain: str) -> bool:
        """
        Check if a domain has been completely processed (no pending or processing URLs).
        
        Args:
            domain: The domain to check
            
        Returns:
            True if domain processing is complete, False otherwise
        """
        try:
            counts = self.get_domain_urls_count(domain)
            return counts.get('pending', 0) == 0 and counts.get('processing', 0) == 0
        except Exception as e:
            logger.error("Error checking if domain %s is complete: %s", domain, str(e))
            return False
            
    def get_domain_urls_count(self, domain: str) -> Dict[str, int]:
        """
        Get count of URLs by status for a specific domain.
        
        Args:
            domain: The domain to get counts for
            
        Returns:
            Dictionary with counts by status
        """
        try:
            # Get counts by aggregation
            pipeline = [
                {"$match": {"domain": domain}},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }}
            ]
            
            result = self.urls_collection.aggregate(pipeline)
            
            # Initialize counts
            counts = {
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0,
                'total': 0
            }
            
            # Process aggregation results
            for doc in result:
                status = doc.get("_id", "unknown")
                count = doc.get("count", 0)
                counts[status] = count
                counts['total'] += count
                
            return counts
        except Exception as e:
            logger.error("Error getting URL counts for domain %s: %s", domain, str(e))
            return {'error': str(e), 'total': 0}

    def get_domain_status(self, domain: str) -> str:
        """
        Get the current status of a domain.
        
        Args:
            domain: The domain to check
            
        Returns:
            Domain status
        """
        try:
            domain_doc = self.domains_collection.find_one({"domain": domain})
            return domain_doc.get("status", STATUS_PENDING) if domain_doc else STATUS_PENDING
        except Exception as e:
            logger.error("Error getting status for domain %s: %s", domain, str(e))
            return STATUS_PENDING

    def get_all_domains_stats(self) -> Dict[str, Dict]:
        """
        Get statistics for all domains.
        
        Returns:
            Dictionary with domain statistics and summary totals
        """
        try:
            result = {}
            total_urls = 0
            total_domains = 0
            
            # Get all domains
            domains_cursor = self.domains_collection.find()
            
            for domain_doc in domains_cursor:
                domain = domain_doc.get("domain")
                if not domain:
                    continue
                    
                status = domain_doc.get("status", STATUS_PENDING)
                url_counts = self.get_domain_urls_count(domain)
                
                # Get worker information if domain is being processed
                worker_info = None
                if status == STATUS_PROCESSING:
                    worker_id = domain_doc.get("worker_id")
                    heartbeat = domain_doc.get("heartbeat")
                    
                    if worker_id:
                        worker_info = {
                            'worker_id': worker_id,
                            'last_heartbeat': datetime.fromtimestamp(heartbeat).isoformat() if heartbeat else None
                        }
                
                result[domain] = {
                    'status': status,
                    'url_counts': url_counts,
                    'worker': worker_info
                }
                
                total_domains += 1
                total_urls += url_counts.get('total', 0)
            
            # Add summary statistics
            result['summary'] = {
                'total_domains': total_domains,
                'total_urls': total_urls
            }
                
            return result
        except Exception as e:
            logger.error("Error getting stats for all domains: %s", str(e))
            return {'error': str(e), 'summary': {'total_domains': 0, 'total_urls': 0}}

    def reset_stalled_url_tasks(self, timeout_minutes: int = 30) -> int:
        """
        Reset URLs that have been processing for too long across all domains.
        
        Args:
            timeout_minutes: Number of minutes after which a task is considered stalled
        
        Returns:
            Number of URLs reset
        """
        reset_count = 0
        try:
            # Calculate cutoff time
            timeout_seconds = timeout_minutes * 60
            cutoff_time = datetime.now() - datetime.timedelta(seconds=timeout_seconds)
            cutoff_iso = cutoff_time.isoformat()
            
            # Find URLs that have been processing for too long
            query = {
                "status": STATUS_PROCESSING,
                "processing_started": {"$lt": cutoff_iso}
            }
            
            # Get list of stalled URLs
            stalled_urls = list(self.urls_collection.find(query))
            
            # Reset each stalled URL
            for url_doc in stalled_urls:
                domain = url_doc.get("domain")
                url = url_doc.get("url")
                retries = url_doc.get("retries", 0) + 1
                
                # Set status based on retry count
                new_status = STATUS_PENDING if retries < MAX_RETRIES else STATUS_FAILED
                
                result = self.urls_collection.update_one(
                    {"domain": domain, "url": url},
                    {"$set": {
                        "status": new_status,
                        "retries": retries,
                        "reset_at": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat()
                    }}
                )
                
                if result.modified_count > 0:
                    reset_count += 1
                    logger.debug("Reset stalled URL %s for domain %s (retry %d/%d)", url, domain, retries, MAX_RETRIES)
            
            logger.info("Reset %d stalled URL tasks", reset_count)
            return reset_count
        except Exception as e:
            logger.error("Error resetting stalled URL tasks: %s", str(e))
            return reset_count
            
    def get_active_workers(self) -> Dict[str, Dict]:
        """
        Get information about active workers and their claimed domains.
        
        Returns:
            Dictionary with worker IDs as keys and worker information as values
        """
        workers = {}
        try:
            # Find all domains with workers
            worker_domains = self.domains_collection.find({"worker_id": {"$exists": True}})
            
            for domain_doc in worker_domains:
                worker_id = domain_doc.get("worker_id")
                if not worker_id:
                    continue
                    
                domain = domain_doc.get("domain")
                heartbeat = domain_doc.get("heartbeat")
                
                if worker_id not in workers:
                    workers[worker_id] = {
                        'worker_id': worker_id,
                        'last_heartbeat': datetime.fromtimestamp(heartbeat).isoformat() if heartbeat else None,
                        'domains': []
                    }
                
                # Add domain to worker's list
                workers[worker_id]['domains'].append({
                    'domain': domain,
                    'status': domain_doc.get("status"),
                    'url_counts': self.get_domain_urls_count(domain)
                })
            
            return workers
        except Exception as e:
            logger.error("Error getting active workers: %s", str(e))
            return workers

    def get_all_domain_urls(self, domain: str, limit: int = 500, offset: int = 0) -> List[Dict]:
        """
        Get all URLs for a domain with pagination support.
        
        Args:
            domain: The domain to get URLs for
            limit: Maximum number of URLs to return
            offset: Offset for pagination
            
        Returns:
            List of URL data dictionaries
        """
        try:
            # Find all URLs for the domain with pagination
            cursor = self.urls_collection.find(
                {"domain": domain},
                {"url": 1, "status": 1, "is_discovered": 1}
            ).skip(offset).limit(limit)
            
            results = []
            for doc in cursor:
                results.append(dict(doc))
                
            logger.debug("Got %d URLs for domain %s (offset: %d, limit: %d)", 
                        len(results), domain, offset, limit)
            return results
        except Exception as e:
            logger.error("Error getting all URLs for domain %s: %s", domain, str(e))
            return []


def load_validated_urls(file_path: str, batch_size: int = 1000) -> Dict[str, int]:
    """
    Load validated URLs from a file into MongoDB.
    
    Args:
        file_path: Path to the file containing validated URLs (one per line)
        batch_size: Number of URLs to process in each batch
        
    Returns:
        Dictionary with domains as keys and number of URLs added as values
    """
    return domain_manager.load_urls_from_file(file_path, batch_size)


# Make the DomainUrlManager accessible
domain_manager = DomainUrlManager() 
