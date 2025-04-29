#!/usr/bin/env python3
"""
Parallel URL loader using multiprocessing for faster Redis queue population.

This script loads URLs from a file into Redis, organized by domain.
Features:
- Multi-process parallel loading for speed (uses all available CPU cores by default)
- Automatic URL deduplication (skips URLs that already exist in the database)
- Detailed progress reporting

Usage examples:
  python3 src/utils/load_urls_multiprocess.py urls.txt
  python3 src/utils/load_urls_multiprocess.py urls.txt --batch-size 50 --workers 4
  python3 src/utils/load_urls_multiprocess.py new_urls.txt  # adds only new URLs, skips existing ones
"""

import argparse
import os
import sys
import time
import multiprocessing
from multiprocessing import Process, Queue, Value, Lock
from typing import Dict, List, Set, Tuple
import ctypes

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(parent_dir)

# Import domain_manager directly
from test.redis_queue import domain_manager

def worker_process(worker_id: int, urls_queue: Queue, results_queue: Queue, 
                 batch_size: int, stats_counter: Value, total_urls: int,
                 print_lock: Lock):
    """
    Worker process that loads URLs from the queue into Redis.
    
    Args:
        worker_id: ID of this worker
        urls_queue: Queue of URLs to process
        results_queue: Queue to store results
        batch_size: Batch size for processing
        stats_counter: Shared counter for progress reporting
        total_urls: Total number of URLs to process
        print_lock: Lock for synchronized printing
    """
    # Initialize local variables
    domains_added = {}
    batch = {}
    batch_count = 0
    processed_count = 0
    
    # Process URLs from the queue
    while True:
        try:
            # Get next URL, timeout after 1 second
            item = urls_queue.get(timeout=1)
            
            # Check for sentinel value (None) indicating end of queue
            if item is None:
                break
                
            url, domain = item
            
            # Add URL to batch
            if domain not in batch:
                batch[domain] = []
            batch[domain].append(url)
            batch_count += 1
            processed_count += 1
            
            # Process batch if it reaches batch_size
            if batch_count >= batch_size:
                # Process the batch
                process_batch(worker_id, batch, domains_added, print_lock)
                batch = {}
                batch_count = 0
                
                # Update shared counter for progress reporting
                with stats_counter.get_lock():
                    stats_counter.value += batch_size
                
                # Report progress
                with print_lock:
                    progress = (stats_counter.value / total_urls) * 100
                    print(f"Worker {worker_id}: {progress:.1f}% complete ({stats_counter.value}/{total_urls})")
                
        except multiprocessing.queues.Empty:
            # No more items in queue, check if we should process remaining batch
            if batch_count > 0:
                process_batch(worker_id, batch, domains_added, print_lock)
                with stats_counter.get_lock():
                    stats_counter.value += batch_count
                batch = {}
                batch_count = 0
            continue
        except Exception as e:
            with print_lock:
                print(f"Worker {worker_id} error: {e}")
    
    # Process any remaining items in the batch
    if batch_count > 0:
        process_batch(worker_id, batch, domains_added, print_lock)
        with stats_counter.get_lock():
            stats_counter.value += batch_count
    
    # Put results in the results queue
    results_queue.put((worker_id, domains_added, processed_count))
    
    with print_lock:
        print(f"Worker {worker_id} completed, processed {processed_count} URLs")

def process_batch(worker_id: int, batch: Dict[str, List[str]], domains_added: Dict[str, int], print_lock: Lock):
    """
    Process a batch of URLs into Redis.
    
    Args:
        worker_id: ID of this worker
        batch: Dictionary of domain -> list of URLs
        domains_added: Counter dictionary to update
        print_lock: Lock for synchronized printing
    """
    for domain, urls in batch.items():
        try:
            # Add URLs to domain
            count = domain_manager.add_urls_to_domain(domain, urls)
            
            # Update counts
            if domain not in domains_added:
                domains_added[domain] = 0
            domains_added[domain] += count
            
            # Print summary (with lock to prevent output garbling)
            if count > 0:
                with print_lock:
                    print(f"Worker {worker_id}: Added {count} URLs to {domain}")
            
            # Report skipped URLs if any
            skipped = len(urls) - count
            if skipped > 0:
                with print_lock:
                    print(f"Worker {worker_id}: Skipped {skipped} existing URLs for {domain}")
        except Exception as e:
            with print_lock:
                print(f"Worker {worker_id}: Error adding URLs for domain {domain}: {e}")

def load_urls_parallel(filepath: str, batch_size: int = 1000, worker_count: int = None) -> Dict[str, int]:
    """
    Load URLs from a file in parallel using multiple worker processes.
    
    Args:
        filepath: Path to file containing URLs (one per line)
        batch_size: Batch size for each worker
        worker_count: Number of worker processes (defaults to CPU count)
        
    Returns:
        Dictionary with domains as keys and number of URLs added as values
    """
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return {}
    
    # Determine number of workers
    if worker_count is None:
        worker_count = multiprocessing.cpu_count()
    print(f"Loading URLs using {worker_count} parallel workers (batch size: {batch_size})...")
    
    start_time = time.time()
    
    # First scan file to count URLs and organize by domain
    print("Scanning file and organizing URLs by domain...")
    total_urls = 0
    domains_count = {}
    all_urls = []  # Store (url, domain) tuples
    
    with open(filepath, 'r') as f:
        for line in f:
            url = line.strip()
            if not url:
                continue
            
            domain = domain_manager.extract_domain_from_url(url)
            if domain:
                domains_count[domain] = domains_count.get(domain, 0) + 1
                all_urls.append((url, domain))
                total_urls += 1
                
                if total_urls % 10000 == 0:
                    print(f"Scanned {total_urls} URLs so far...")
    
    print(f"Found {total_urls} valid URLs across {len(domains_count)} domains")
    print(f"Top 5 domains by URL count:")
    sorted_domains = sorted(domains_count.items(), key=lambda x: x[1], reverse=True)
    for domain, count in sorted_domains[:5]:
        print(f"  {domain}: {count} URLs")
    
    # Create shared progress counter
    stats_counter = Value(ctypes.c_int, 0)
    print_lock = Lock()
    
    # Create queues for URLs and results
    urls_queue = Queue()
    results_queue = Queue()
    
    # Fill the queue with URLs
    print("Filling URL queue...")
    for url_item in all_urls:
        urls_queue.put(url_item)
    
    # Add sentinel values to signal end of queue
    for _ in range(worker_count):
        urls_queue.put(None)
    
    # Start worker processes
    workers = []
    print(f"Starting {worker_count} worker processes...")
    for i in range(worker_count):
        p = Process(
            target=worker_process, 
            args=(i+1, urls_queue, results_queue, batch_size, stats_counter, total_urls, print_lock)
        )
        workers.append(p)
        p.start()
    
    # Wait for all workers to finish
    for p in workers:
        p.join()
    
    # Collect results
    domains_added = {}
    total_processed = 0
    
    for _ in range(worker_count):
        worker_id, worker_domains, worker_processed = results_queue.get()
        total_processed += worker_processed
        
        # Merge domain counts
        for domain, count in worker_domains.items():
            domains_added[domain] = domains_added.get(domain, 0) + count
    
    # Calculate skipped URLs
    total_urls_added = sum(domains_added.values())
    total_urls_skipped = total_urls - total_urls_added
    
    # Print results
    duration = time.time() - start_time
    total_domains = len(domains_added)
    
    print(f"\nCompleted in {duration:.2f} seconds")
    print(f"Loaded {total_urls_added} URLs across {total_domains} domains")
    print(f"Skipped {total_urls_skipped} duplicate URLs")
    print(f"Processing rate: {total_urls_added/duration:.1f} URLs/second")
    
    print("\nTop domains:")
    
    # Sort domains by number of URLs and print top 10
    sorted_domains = sorted(domains_added.items(), key=lambda x: x[1], reverse=True)
    for domain, count in sorted_domains[:10]:
        print(f"  {domain}: {count} URLs")
    
    if len(sorted_domains) > 10:
        print(f"  ... and {len(sorted_domains) - 10} more domains")
    
    return domains_added

def main():
    parser = argparse.ArgumentParser(description="Load URLs into Redis using multiple worker processes")
    parser.add_argument("file", help="Path to file containing URLs (one per line)")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for each worker")
    parser.add_argument("--workers", type=int, default=None, help="Number of worker processes (default: CPU count)")
    parser.add_argument("--clear", action="store_true", help="Clear existing domains before loading")
    parser.add_argument("--force-reload", action="store_true", help="Reload URLs even if they already exist (default is to skip duplicates)")
    args = parser.parse_args()
    
    # Check Redis connection
    print("Checking Redis connection...")
    if not domain_manager.healthcheck():
        print("Redis connection failed. Please check your connection settings.")
        return
    
    print("Redis connection successful!")
    
    # Clear queues if requested
    if args.clear:
        confirm = input("Are you sure you want to clear all domains and queues? (y/n): ")
        if confirm.lower() == 'y':
            from test.redis_queue import clear_all_queues
            clear_all_queues()
            print("All domains and queues cleared.")
        else:
            print("Clear operation cancelled.")
    
    # Set up reload behavior info message
    if args.force_reload:
        print("Warning: Force reload is enabled. Duplicate URLs will be reloaded.")
        # Currently not implemented as Redis queue automatically skips duplicates
        print("Note: The Redis queue implementation automatically skips duplicates, so this setting has no effect.")
    else:
        print("Duplicate URLs will be automatically skipped.")
    
    # Load URLs
    domains_added = load_urls_parallel(args.file, args.batch_size, args.workers)
    
    print("\nURL loading completed!")

if __name__ == "__main__":
    main() 