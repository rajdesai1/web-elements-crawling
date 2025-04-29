#!/usr/bin/env python3

import argparse
import asyncio
import json
import os
import sys
import time
from typing import List, Dict, Optional
from urllib.parse import urlparse

# Add parent directory to path to ensure imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from test.redis_queue import domain_manager
from src.config.settings import REDIS_HOST, REDIS_PORT, REDIS_USERNAME, REDIS_PASSWORD
from src.utils.logger import setup_logger

# Configure logging
logger = setup_logger(__name__)

def print_domain_stats(domain: str, stats: Dict) -> None:
    """
    Print domain URL statistics in a readable format.
    
    Args:
        domain: Domain name
        stats: Statistics dictionary
    """
    logger.info("\nDomain: %s", domain)
    logger.info("  Total URLs: %d", stats['total_urls'])
    logger.info("  Waiting URLs: %d", stats['waiting_urls'])
    logger.info("  Processing URLs: %d", stats['processing_urls'])
    logger.info("  Completed URLs: %d", stats['completed_urls'])
    logger.info("  Failed URLs: %d", stats['failed_urls'])
    
    # Print sample waiting URLs
    waiting_urls = stats.get('sample_waiting_urls', [])
    if waiting_urls:
        logger.info("\n  Sample waiting URLs:")
        for i, url in enumerate(waiting_urls[:5], 1):
            logger.info("    %d. %s", i, url)
        if len(waiting_urls) > 5:
            logger.info("    ... and %d more", len(waiting_urls) - 5)

def add_urls_from_file(filename: str, normalize_domains: bool = False) -> Dict:
    """
    Add URLs from a file to the queue.
    
    Args:
        filename: Path to the file containing URLs (one per line)
        normalize_domains: Whether to normalize domains (strip www. prefix)
        
    Returns:
        Dictionary with statistics on URLs added
    """
    results = {
        'total_urls': 0,
        'added_urls': 0,
        'domains': {}
    }
    
    try:
        with open(filename, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
            
        results['total_urls'] = len(urls)
        
        # Group URLs by domain
        domain_urls = {}
        for url in urls:
            # Extract domain
            parsed_url = urlparse(url)
            if not parsed_url.netloc:
                logger.warning("Skipping invalid URL: %s", url)
                continue
                
            domain = parsed_url.netloc
            if normalize_domains and domain.startswith('www.'):
                domain = domain[4:]
                
            if domain not in domain_urls:
                domain_urls[domain] = []
                
            domain_urls[domain].append(url)
        
        # Add URLs for each domain
        for domain, domain_url_list in domain_urls.items():
            domain_result = domain_manager.add_urls_to_domain(domain, domain_url_list)
            results['domains'][domain] = {
                'urls_count': len(domain_url_list),
                'added_count': domain_result
            }
            results['added_urls'] += domain_result
            
        return results
        
    except Exception as e:
        logger.error("Error adding URLs from file: %s", e)
        return {'error': str(e)}

def list_domains(limit: int = 20, sort_by: str = 'total') -> List[Dict]:
    """
    List domains in the queue with statistics.
    
    Args:
        limit: Maximum number of domains to return
        sort_by: How to sort the domains ('total', 'waiting', 'completed', 'failed')
        
    Returns:
        List of domain statistic dictionaries
    """
    all_domains = domain_manager.get_all_domains()
    domain_stats = []
    
    for domain in all_domains:
        stats = domain_manager.get_domain_stats(domain)
        domain_stats.append({
            'domain': domain,
            **stats
        })
    
    # Sort domains based on the specified criteria
    sort_key = f"{sort_by}_urls" if sort_by != 'total' else 'total_urls'
    domain_stats.sort(key=lambda x: x.get(sort_key, 0), reverse=True)
    
    return domain_stats[:limit]

def get_domain_details(domain: str, include_sample_urls: bool = True) -> Dict:
    """
    Get detailed statistics for a domain.
    
    Args:
        domain: Domain to get statistics for
        include_sample_urls: Whether to include sample URLs
        
    Returns:
        Dictionary with domain statistics
    """
    stats = domain_manager.get_domain_stats(domain)
    
    if include_sample_urls:
        # Get sample waiting URLs
        waiting_urls = domain_manager.get_domain_waiting_urls(domain, limit=10)
        stats['sample_waiting_urls'] = waiting_urls
        
        # Get sample completed URLs with metadata
        completed_urls = domain_manager.get_domain_completed_urls(domain, limit=10)
        stats['sample_completed_urls'] = completed_urls
        
        # Get sample failed URLs with error information
        failed_urls = domain_manager.get_domain_failed_urls(domain, limit=10)
        stats['sample_failed_urls'] = failed_urls
    
    return stats

def purge_domain(domain: str) -> Dict:
    """
    Purge all URLs for a domain.
    
    Args:
        domain: Domain to purge
        
    Returns:
        Dictionary with purge results
    """
    # Get current stats for reporting
    before_stats = domain_manager.get_domain_stats(domain)
    
    # Purge the domain
    domain_manager.purge_domain(domain)
    
    # Get new stats to confirm purge
    after_stats = domain_manager.get_domain_stats(domain)
    
    return {
        'domain': domain,
        'before': before_stats,
        'after': after_stats,
        'purged': {
            'total': before_stats['total_urls'] - after_stats['total_urls'],
            'waiting': before_stats['waiting_urls'] - after_stats['waiting_urls'],
            'processing': before_stats['processing_urls'] - after_stats['processing_urls'],
            'completed': before_stats['completed_urls'] - after_stats['completed_urls'],
            'failed': before_stats['failed_urls'] - after_stats['failed_urls']
        }
    }

def reset_processing_urls(domain: str = None) -> Dict:
    """
    Reset processing URLs to waiting state.
    
    Args:
        domain: Optional domain to reset (if None, reset all domains)
        
    Returns:
        Dictionary with reset results
    """
    if domain:
        result = domain_manager.reset_processing_urls(domain)
        return {
            'domain': domain,
            'reset_count': result
        }
    else:
        domains = domain_manager.get_all_domains()
        results = {}
        total_reset = 0
        
        for domain in domains:
            reset_count = domain_manager.reset_processing_urls(domain)
            results[domain] = reset_count
            total_reset += reset_count
            
        return {
            'domains': len(domains),
            'reset_count': total_reset,
            'details': results
        }

def main():
    parser = argparse.ArgumentParser(description="Manage URLs in the Redis queue")
    
    # Common arguments
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    # Create subparsers for different actions
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")
    
    # Add URLs from file
    add_parser = subparsers.add_parser("add", help="Add URLs from a file")
    add_parser.add_argument("file", help="File containing URLs (one per line)")
    add_parser.add_argument("--normalize", action="store_true", help="Normalize domains (strip www. prefix)")
    
    # List domains
    list_parser = subparsers.add_parser("list-domains", help="List domains in the queue")
    list_parser.add_argument("--limit", type=int, default=20, help="Maximum number of domains to list")
    list_parser.add_argument("--sort-by", choices=["total", "waiting", "processing", "completed", "failed"], 
                             default="total", help="Sort domains by this criteria")
    
    # Get domain details
    details_parser = subparsers.add_parser("domain-details", help="Get detailed statistics for a domain")
    details_parser.add_argument("domain", help="Domain to get statistics for")
    
    # Purge domain
    purge_parser = subparsers.add_parser("purge", help="Purge all URLs for a domain")
    purge_parser.add_argument("domain", help="Domain to purge")
    purge_parser.add_argument("--force", action="store_true", help="Purge without confirmation")
    
    # Reset processing URLs
    reset_parser = subparsers.add_parser("reset-processing", help="Reset URLs stuck in processing state")
    reset_parser.add_argument("--domain", help="Domain to reset (if omitted, reset all domains)")
    
    # Health check
    subparsers.add_parser("health", help="Check Redis connection health")
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Check Redis connection
    if not domain_manager.healthcheck():
        logger.error("Redis connection failed. Please check your connection settings.")
        logger.error("Redis settings: host=%s, port=%s, username=%s, password=%s", 
                    REDIS_HOST, REDIS_PORT, 
                    '[set]' if REDIS_USERNAME else '[not set]', 
                    '[set]' if REDIS_PASSWORD else '[not set]')
        return 1
    
    if args.action == "health":
        logger.info("Redis connection: SUCCESS")
        return 0
    
    # Perform the requested action
    try:
        if args.action == "add":
            result = add_urls_from_file(args.file, args.normalize)
            logger.info("Added %d of %d URLs to the queue", result['added_urls'], result['total_urls'])
            logger.info("URLs added by domain:")
            for domain, stats in result['domains'].items():
                logger.info("  %s: %d of %d URLs", domain, stats['added_count'], stats['urls_count'])
        
        elif args.action == "list-domains":
            domain_stats = list_domains(limit=args.limit, sort_by=args.sort_by)
            logger.info("Found %d domains (sorted by %s URLs):", len(domain_stats), args.sort_by)
            
            for i, stats in enumerate(domain_stats, 1):
                domain = stats['domain']
                logger.info("%d. %s", i, domain)
                logger.info("   Total: %d, Waiting: %d, Processing: %d, Completed: %d, Failed: %d",
                           stats['total_urls'], stats['waiting_urls'], stats['processing_urls'], 
                           stats['completed_urls'], stats['failed_urls'])
        
        elif args.action == "domain-details":
            stats = get_domain_details(args.domain)
            print_domain_stats(args.domain, stats)
            
            # Print sample failed URLs with errors
            if 'sample_failed_urls' in stats and stats['sample_failed_urls']:
                logger.info("\n  Sample failed URLs:")
                for i, url_data in enumerate(stats['sample_failed_urls'][:5], 1):
                    url = url_data.get('url', 'Unknown URL')
                    error = url_data.get('error', 'Unknown error')
                    logger.info("    %d. %s", i, url)
                    logger.info("       Error: %s", error)
        
        elif args.action == "purge":
            if not args.force:
                logger.info("Are you sure you want to purge all URLs for domain '%s'?", args.domain)
                logger.info("This action cannot be undone.")
                confirmation = input("Type 'yes' to confirm: ")
                
                if confirmation.lower() != "yes":
                    logger.info("Purge cancelled.")
                    return 0
            
            result = purge_domain(args.domain)
            logger.info("Purged domain: %s", args.domain)
            logger.info("  Total URLs purged: %d", result['purged']['total'])
            logger.info("  Waiting URLs purged: %d", result['purged']['waiting'])
            logger.info("  Processing URLs purged: %d", result['purged']['processing'])
            logger.info("  Completed URLs purged: %d", result['purged']['completed'])
            logger.info("  Failed URLs purged: %d", result['purged']['failed'])
        
        elif args.action == "reset-processing":
            if args.domain:
                result = reset_processing_urls(args.domain)
                logger.info("Reset %d processing URLs for domain %s", result['reset_count'], args.domain)
            else:
                result = reset_processing_urls()
                logger.info("Reset %d processing URLs across %d domains", result['reset_count'], result['domains'])
        
        else:
            parser.print_help()
    
    except Exception as e:
        logger.error("Error executing command: %s", e)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 