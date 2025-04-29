#!/usr/bin/env python3
"""
Script to load validated URLs into the Redis queue for crawling.
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test.redis_queue import (
    healthcheck, add_urls, get_queue_stats, clear_all_queues
)

def load_urls_from_file(file_path, batch_size=100):
    """
    Load URLs from a text file and add them to the Redis queue.
    
    Args:
        file_path (str): Path to file containing URLs (one per line)
        batch_size (int): Number of URLs to add in each batch
    
    Returns:
        int: Number of URLs added to the queue
    """
    try:
        with open(file_path, 'r') as f:
            all_urls = [line.strip() for line in f if line.strip()]
        
        total_added = 0
        for i in range(0, len(all_urls), batch_size):
            batch = all_urls[i:i + batch_size]
            added = add_urls(batch)
            total_added += added
            print(f"Added batch of {added} URLs to queue (total: {total_added}/{len(all_urls)})")
        
        return total_added
    except Exception as e:
        print(f"Error loading URLs: {e}")
        return 0

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Load validated URLs into the Redis queue")
    parser.add_argument('--file', default='validated_urls.txt', help="File containing validated URLs")
    parser.add_argument('--batch-size', type=int, default=100, help="Batch size for adding URLs")
    parser.add_argument('--clear', action='store_true', help="Clear existing queues before loading")
    args = parser.parse_args()
    
    # Check if file exists
    if not Path(args.file).exists():
        print(f"Error: File {args.file} does not exist")
        return
    
    # Check Redis connection
    if not healthcheck():
        print("Redis connection failed. Please check your connection settings.")
        return
    
    print("Redis connection successful!")
    
    # Get initial queue stats
    initial_stats = get_queue_stats()
    print(f"Initial queue stats: {initial_stats}")
    
    # Clear queues if requested
    if args.clear:
        clear_all_queues()
        print("All queues cleared.")
    
    # Load URLs
    total_added = load_urls_from_file(args.file, args.batch_size)
    
    # Get final queue stats
    final_stats = get_queue_stats()
    print(f"Final queue stats: {final_stats}")
    print(f"Added {total_added} URLs to the queue")

if __name__ == "__main__":
    main() 