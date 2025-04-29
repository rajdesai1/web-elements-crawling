"""
Utility script to load URLs into the Redis queue from a file.
"""

import argparse
import csv
import os
import sys
from urllib.parse import urlparse

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test.redis_queue import (
    healthcheck, add_urls, get_queue_stats, clear_all_queues
)
from utils.logger import setup_logger

# Initialize logger
logger = setup_logger(__name__)

def is_valid_url(url):
    """Basic validation to ensure URL has a proper scheme and netloc."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def load_urls_from_file(filename, batch_size=1000):
    """
    Load URLs from a file and add them to the Redis queue.
    
    Args:
        filename (str): Path to the file containing URLs (one per line or CSV)
        batch_size (int): Number of URLs to add in each batch
    
    Returns:
        tuple: (total_added, total_invalid)
    """
    total_added = 0
    total_invalid = 0
    
    # Determine file type based on extension
    is_csv = filename.lower().endswith('.csv')
    
    urls_batch = []
    
    try:
        with open(filename, 'r') as file:
            if is_csv:
                # Assume first column contains URLs
                reader = csv.reader(file)
                try:
                    # Check if first row is header
                    header = next(reader)
                    # If the first element doesn't look like a URL, assume it's a header
                    if not is_valid_url(header[0]):
                        logger.info("Detected header: %s", header)
                    else:
                        # If it looks like a URL, it's not a header, so add it
                        if is_valid_url(header[0]):
                            urls_batch.append(header[0])
                        else:
                            total_invalid += 1
                except StopIteration:
                    pass  # Empty file
                
                # Process remaining rows
                for row in reader:
                    if not row:
                        continue
                    
                    url = row[0].strip()
                    if is_valid_url(url):
                        urls_batch.append(url)
                    else:
                        total_invalid += 1
                    
                    # Process batch if it reaches the batch size
                    if len(urls_batch) >= batch_size:
                        added = add_urls(urls_batch)
                        total_added += added
                        logger.info("Added batch of %d URLs to queue (total: %d)", added, total_added)
                        urls_batch = []
            else:
                # Regular text file with one URL per line
                for line in file:
                    url = line.strip()
                    if is_valid_url(url):
                        urls_batch.append(url)
                    else:
                        total_invalid += 1
                    
                    # Process batch if it reaches the batch size
                    if len(urls_batch) >= batch_size:
                        added = add_urls(urls_batch)
                        total_added += added
                        logger.info("Added batch of %d URLs to queue (total: %d)", added, total_added)
                        urls_batch = []
        
        # Process remaining URLs
        if urls_batch:
            added = add_urls(urls_batch)
            total_added += added
            logger.info("Added final batch of %d URLs to queue (total: %d)", added, total_added)
    
    except Exception as e:
        logger.error("Error loading URLs: %s", e)
    
    return total_added, total_invalid

def main():
    parser = argparse.ArgumentParser(description="Load URLs into Redis queue from a file")
    parser.add_argument("file", help="Path to file containing URLs (one per line or CSV)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Number of URLs to add in each batch")
    parser.add_argument("--clear", action="store_true", help="Clear existing queues before loading")
    args = parser.parse_args()
    
    # Check Redis connection
    if not healthcheck():
        logger.error("Redis connection failed. Please check your connection settings.")
        return
    
    logger.info("Redis connection successful!")
    
    # Clear queues if requested
    if args.clear:
        clear_all_queues()
        logger.info("Queues cleared.")
    
    # Get current queue stats
    before_stats = get_queue_stats()
    logger.info("Queue stats before loading: %s", before_stats)
    
    # Load URLs
    total_added, total_invalid = load_urls_from_file(args.file, args.batch_size)
    
    # Get updated queue stats
    after_stats = get_queue_stats()
    logger.info("Queue stats after loading: %s", after_stats)
    
    logger.info("Summary: Added %d URLs, %d invalid URLs skipped", total_added, total_invalid)

if __name__ == "__main__":
    main() 