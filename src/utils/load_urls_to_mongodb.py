#!/usr/bin/env python3
"""
Script to load validated URLs from a file into MongoDB for crawling.
Uses the DomainUrlManager from mongodb_queue.py to organize URLs by domain.
"""

import os
import sys
import time
from typing import Dict

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.mongodb_queue import load_validated_urls, domain_manager
from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger(__name__)

def main():
    """
    Load validated URLs from file into MongoDB and display statistics.
    """
    # Check MongoDB connection
    if not domain_manager.healthcheck():
        logger.error("MongoDB connection failed, please check configuration")
        return False

    # File path
    file_path = "data/urls_dump/validated_urls.txt"
    
    # Verify file exists
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        return False
        
    # Count URLs in the file
    try:
        with open(file_path, 'r') as f:
            url_count = sum(1 for line in f if line.strip())
        logger.info("Found %d URLs in %s", url_count, file_path)
    except Exception as e:
        logger.error("Error counting URLs in file: %s", str(e))
        return False
    
    # Load URLs into MongoDB
    logger.info("Loading URLs into MongoDB...")
    start_time = time.time()
    
    # Batch size for processing
    batch_size = 1000
    
    # Load URLs
    domains_added = load_validated_urls(file_path, batch_size)
    
    # Calculate timing
    elapsed_time = time.time() - start_time
    
    # Display results
    logger.info("Completed loading URLs in %.2f seconds", elapsed_time)
    logger.info("Added URLs to %d domains", len(domains_added))
    
    # Display top domains by URL count
    top_domains = sorted(domains_added.items(), key=lambda x: x[1], reverse=True)[:10]
    logger.info("Top domains by URL count:")
    for domain, count in top_domains:
        logger.info("  %s: %d URLs", domain, count)
    
    # Display overall statistics
    stats = domain_manager.get_all_domains_stats()
    logger.info("Total domains: %d", stats.get('summary', {}).get('total_domains', 0))
    logger.info("Total URLs: %d", stats.get('summary', {}).get('total_urls', 0))
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 