#!/usr/bin/env python3
"""
Utility script to load URLs into the Redis queue organized by domain.
"""

import argparse
import os
import sys
import time
from typing import Dict, List

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test.redis_queue import domain_manager

def load_urls_from_file(filepath: str, batch_size: int = 1000) -> Dict[str, int]:
    """
    Load URLs from a file and organize them by domain in Redis.
    
    Args:
        filepath: Path to file containing URLs (one per line)
        batch_size: Number of URLs to process in each batch
        
    Returns:
        Dictionary with domains as keys and number of URLs added as values
    """
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return {}
    
    print(f"Loading URLs from {filepath} (batch size: {batch_size})...")
    start_time = time.time()
    
    # First count total URLs and organize by domain for reporting
    print("Scanning file and organizing URLs by domain...")
    total_urls = 0
    domains_count = {}
    
    with open(filepath, 'r') as f:
        for line in f:
            url = line.strip()
            if not url:
                continue
            
            domain = domain_manager.extract_domain_from_url(url)
            if domain:
                domains_count[domain] = domains_count.get(domain, 0) + 1
                total_urls += 1
                
                if total_urls % 10000 == 0:
                    print(f"Scanned {total_urls} URLs so far...")
    
    print(f"Found {total_urls} valid URLs across {len(domains_count)} domains")
    print(f"Top 5 domains by URL count:")
    sorted_domains = sorted(domains_count.items(), key=lambda x: x[1], reverse=True)
    for domain, count in sorted_domains[:5]:
        print(f"  {domain}: {count} URLs")
    
    # Now load URLs into Redis with progress updates
    print("\nNow loading URLs into Redis...")
    loaded_start_time = time.time()
    domains_added = {}
    
    # Use the DomainUrlManager to load URLs but with progress reporting
    with open(filepath, 'r') as f:
        batch = {}
        batch_count = 0
        total_processed = 0
        last_report_time = time.time()
        
        for line in f:
            url = line.strip()
            if not url:
                continue
            
            domain = domain_manager.extract_domain_from_url(url)
            if not domain:
                continue
            
            if domain not in batch:
                batch[domain] = []
            
            batch[domain].append(url)
            batch_count += 1
            total_processed += 1
            
            # Process batch if it reaches batch size
            if batch_count >= batch_size:
                # Add progress report
                current_time = time.time()
                if current_time - last_report_time >= 2 or batch_count >= batch_size:
                    progress_pct = (total_processed / total_urls) * 100
                    elapsed = current_time - loaded_start_time
                    estimated_total = (elapsed / total_processed) * total_urls if total_processed > 0 else 0
                    remaining = estimated_total - elapsed
                    
                    print(f"Processing batch with {batch_count} URLs ({total_processed}/{total_urls}, {progress_pct:.1f}%)")
                    print(f"Time elapsed: {elapsed:.1f}s, Est. remaining: {remaining:.1f}s")
                    last_report_time = current_time
                
                # Process the batch
                _process_batch(batch, domains_added)
                batch = {}
                batch_count = 0
        
        # Process any remaining URLs
        if batch_count > 0:
            print(f"Processing final batch with {batch_count} URLs")
            _process_batch(batch, domains_added)
    
    # Print results
    loading_duration = time.time() - loaded_start_time
    total_duration = time.time() - start_time
    total_domains = len(domains_added)
    total_urls_added = sum(domains_added.values())
    
    print(f"\nLoaded {total_urls_added} URLs across {total_domains} domains")
    print(f"Scanning time: {loaded_start_time - start_time:.2f} seconds")
    print(f"Loading time: {loading_duration:.2f} seconds")
    print(f"Total processing time: {total_duration:.2f} seconds")
    print(f"Processing rate: {total_urls_added/loading_duration:.1f} URLs/second")
    
    print("\nTop domains:")
    
    # Sort domains by number of URLs and print top 10
    sorted_domains = sorted(domains_added.items(), key=lambda x: x[1], reverse=True)
    for domain, count in sorted_domains[:10]:
        print(f"  {domain}: {count} URLs")
    
    if len(sorted_domains) > 10:
        print(f"  ... and {len(sorted_domains) - 10} more domains")
    
    return domains_added

def _process_batch(batch: Dict[str, List[str]], domains_added: Dict[str, int]) -> None:
    """
    Process a batch of URLs and update the domains_added counter.
    
    Args:
        batch: Dictionary of domain -> list of URLs
        domains_added: Counter dictionary to update with results
    """
    # Process the batch through domain_manager without trying to get counts first
    # This avoids timing out on slow Redis operations for statistics
    urls_added = 0
    for domain, urls in batch.items():
        try:
            count = domain_manager.add_urls_to_domain(domain, urls)
            if domain not in domains_added:
                domains_added[domain] = 0
            domains_added[domain] += count
            urls_added += count
            
            if count > 0:
                print(f"  Added {count} URLs to {domain}")
        except Exception as e:
            print(f"Error adding URLs for domain {domain}: {e}")
    
    if urls_added == 0:
        print("  No new URLs were added in this batch (duplicates or errors)")

def main():
    parser = argparse.ArgumentParser(description="Load URLs into Redis organized by domain")
    parser.add_argument("file", help="Path to file containing URLs (one per line)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Number of URLs to process in each batch")
    parser.add_argument("--clear", action="store_true", help="Clear existing domains before loading")
    parser.add_argument("--skip-stats", action="store_true", help="Skip getting statistics (faster)")
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
    
    # Get current queue stats if not skipped
    before_domains = 0
    before_total = 0
    if not args.skip_stats:
        try:
            print("Getting current Redis statistics (this may take a while for large datasets)...")
            before_stats = domain_manager.get_all_domains_stats()
            before_domains = len(before_stats) - 1  # Subtract 1 for the 'summary' key
            before_total = before_stats.get('summary', {}).get('total_urls', 0)
            print(f"Domains before loading: {before_domains}")
            print(f"URLs before loading: {before_total}")
        except KeyboardInterrupt:
            print("\nStats gathering interrupted. Proceeding with URL loading...")
            args.skip_stats = True
        except Exception as e:
            print(f"Error getting statistics: {e}. Proceeding with URL loading...")
            args.skip_stats = True
    else:
        print("Skipping initial statistics gathering...")
    
    # Load URLs
    domains_added = load_urls_from_file(args.file, args.batch_size)
    
    # Get updated queue stats if not skipped
    if not args.skip_stats:
        try:
            print("\nGetting updated Redis statistics (this may take a while for large datasets)...")
            after_stats = domain_manager.get_all_domains_stats()
            after_domains = len(after_stats) - 1  # Subtract 1 for the 'summary' key
            after_total = after_stats.get('summary', {}).get('total_urls', 0)
            
            print(f"Domains after loading: {after_domains}")
            print(f"URLs after loading: {after_total}")
            print(f"Net new domains added: {after_domains - before_domains}")
            print(f"Net new URLs added: {after_total - before_total}")
        except Exception as e:
            print(f"Error getting statistics: {e}")
            print("\nSummary based on processing results:")
            print(f"Domains processed: {len(domains_added)}")
            print(f"URLs processed: {sum(domains_added.values())}")
    else:
        print("\nSummary based on processing results:")
        print(f"Domains processed: {len(domains_added)}")
        print(f"URLs processed: {sum(domains_added.values())}")

if __name__ == "__main__":
    main() 