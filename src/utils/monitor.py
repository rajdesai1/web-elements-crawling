"""
Monitoring script for tracking the progress of the distributed crawler.
"""

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from test.redis_queue import (get_queue_stats, healthcheck, redis_client,
                              reset_stalled_tasks)

from src.config.settings import REDIS_CONFIG
from utils.logger import setup_logger

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize logger
logger = setup_logger(__name__)

# Define constants for Redis keys used in monitoring
# These keys are kept here for backward compatibility with monitoring tools
PROCESSING_KEY = 'crawler:urls:processing' # URLs currently being processed

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def format_number(num):
    """Format a number with commas as thousands separators."""
    return f"{num:,}"

def format_time(seconds):
    """Format seconds as a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

def monitor_progress(refresh_rate=5, data_dir='data'):
    """
    Monitor the progress of the distributed crawler.
    
    Args:
        refresh_rate (int): How often to refresh the display in seconds
        data_dir (str): Directory containing crawl data
    """
    try:
        while True:
            clear_screen()
            logger.info("=" * 80)
            logger.info("DISTRIBUTED CRAWLER MONITOR - %s", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            logger.info("=" * 80)
            
            # Get queue stats
            queue_stats = get_queue_stats()
            
            # Calculate processing rate
            if hasattr(monitor_progress, 'last_completed'):
                time_diff = time.time() - monitor_progress.last_time
                completed_diff = queue_stats.get('completed', 0) - monitor_progress.last_completed
                rate = completed_diff / time_diff if time_diff > 0 else 0
                
                estimated_time = "N/A"
                if rate > 0:
                    remaining = queue_stats.get('queue', 0) + queue_stats.get('processing', 0)
                    estimated_seconds = remaining / rate
                    estimated_time = format_time(estimated_seconds)
            else:
                rate = 0
                estimated_time = "Calculating..."
            
            # Update last values
            monitor_progress.last_completed = queue_stats.get('completed', 0)
            monitor_progress.last_time = time.time()
            
            # Display queue stats
            logger.info("\nQUEUE STATUS:")
            logger.info("  Pending:     %s", format_number(queue_stats.get('queue', 0)))
            logger.info("  Processing:  %s", format_number(queue_stats.get('processing', 0)))
            logger.info("  Completed:   %s", format_number(queue_stats.get('completed', 0)))
            logger.info("  Failed:      %s", format_number(queue_stats.get('failed', 0)))
            logger.info("  Total:       %s", format_number(queue_stats.get('total', 0)))
            logger.info("  Rate:        %.2f URLs/second", rate)
            logger.info("  Est. Time:   %s", estimated_time)
            
            # Get worker status
            processing_urls = {}
            try:
                processing_data = redis_client.hgetall(PROCESSING_KEY)
                
                for url, data in processing_data.items():
                    try:
                        url_obj = json.loads(data)
                        worker_id = url_obj.get('worker_id', 'unknown')
                        started_at = url_obj.get('started_at', '')
                        
                        # Calculate processing time
                        if started_at:
                            started = datetime.datetime.fromisoformat(started_at)
                            processing_time = (datetime.datetime.now() - started).total_seconds()
                            processing_time_str = format_time(processing_time)
                        else:
                            processing_time_str = "Unknown"
                        
                        if worker_id not in processing_urls:
                            processing_urls[worker_id] = []
                            
                        processing_urls[worker_id].append({
                            'url': url.decode('utf-8') if isinstance(url, bytes) else url,
                            'time': processing_time_str
                        })
                    except (json.JSONDecodeError, TypeError, ValueError) as e:
                        continue
            except Exception as e:
                logger.error("\nError getting processing URLs: %s", e)
            
            # Display active workers
            logger.info("\nACTIVE WORKERS:")
            if not processing_urls:
                logger.info("  No active workers")
            else:
                for worker_id, urls in sorted(processing_urls.items()):
                    logger.info("  %s (%d URLs):", worker_id, len(urls))
                    for i, url_info in enumerate(urls[:3]):  # Show up to 3 URLs per worker
                        url_display = url_info['url']
                        if len(url_display) > 70:
                            url_display = url_display[:67] + "..."
                        logger.info("    - %s (%s)", url_display, url_info['time'])
                    if len(urls) > 3:
                        logger.info("    - ... and %d more", len(urls) - 3)
            
            # Get data directory stats
            data_path = Path(data_dir)
            if data_path.exists():
                total_domains = len([d for d in data_path.iterdir() if d.is_dir()])
                total_sessions = sum(1 for _ in data_path.glob("*/*"))
                total_size = sum(f.stat().st_size for f in data_path.glob("**/*") if f.is_file())
                total_size_mb = total_size / (1024 * 1024)
                
                logger.info("\nDATA COLLECTION:")
                logger.info("  Domains:     %s", format_number(total_domains))
                logger.info("  Sessions:    %s", format_number(total_sessions))
                logger.info("  Total Size:  %.2f MB", total_size_mb)
                
                # Sample of recently processed domains
                recent_sessions = sorted(
                    data_path.glob("*/*"), 
                    key=lambda p: p.stat().st_mtime, 
                    reverse=True
                )[:5]
                
                if recent_sessions:
                    logger.info("\nRECENT DOMAINS:")
                    for session in recent_sessions:
                        domain = session.parent.name
                        timestamp = datetime.datetime.fromtimestamp(session.stat().st_mtime)
                        time_ago = (datetime.datetime.now() - timestamp).total_seconds()
                        
                        logger.info("  %s (%s ago)", domain, format_time(time_ago))
            
            # Reset stalled tasks periodically
            if hasattr(monitor_progress, 'last_reset'):
                if time.time() - monitor_progress.last_reset > 300:  # 5 minutes
                    reset_count = reset_stalled_tasks(timeout_minutes=30)
                    if reset_count > 0:
                        logger.info("\nReset %d stalled tasks", reset_count)
                    monitor_progress.last_reset = time.time()
            else:
                monitor_progress.last_reset = time.time()
            
            logger.info("\nPress Ctrl+C to exit...")
            time.sleep(refresh_rate)
            
    except KeyboardInterrupt:
        logger.info("\nMonitoring stopped.")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Monitor distributed crawler progress")
    parser.add_argument("--refresh", type=int, default=5, help="Refresh rate in seconds")
    parser.add_argument("--data-dir", default="data", help="Directory containing crawl data")
    args = parser.parse_args()
    
    # Check Redis connection
    if not healthcheck():
        logger.error("Redis connection failed. Please check your connection settings.")
        return
    
    monitor_progress(refresh_rate=args.refresh, data_dir=args.data_dir)

if __name__ == "__main__":
    main() 
