#!/usr/bin/env python3
"""
Script to load URLs from validated_urls.txt into MongoDB with parallel processing.
This significantly speeds up the initialization of the crawler database.
"""

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pymongo import MongoClient
from pathlib import Path
from src.config.settings import (
    MONGODB_URI, MONGODB_DB_NAME, MONGODB_DOMAINS_COLLECTION, MONGODB_URLS_COLLECTION,
    BATCH_SIZE, MAX_RETRIES, STATUS_PENDING
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Path to validated URLs file
VALIDATED_URLS_FILE = "validated_urls.txt"
# Number of parallel processes to use (default: CPU count - 1)
NUM_PROCESSES = max(1, multiprocessing.cpu_count() - 1)
# Number of lines to process per worker
CHUNK_SIZE = 10000

def extract_domain_from_url(url):
    """Extract domain from URL"""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        return parsed.netloc
    except Exception:
        return None

def process_url_chunk(chunk_id, urls):
    """Process a chunk of URLs and add them to MongoDB"""
    # Create new MongoDB connection for this process
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB_NAME]
    domains_collection = db[MONGODB_DOMAINS_COLLECTION]
    urls_collection = db[MONGODB_URLS_COLLECTION]
    
    # Create indexes if they don't exist
    domains_collection.create_index("domain", unique=True)
    urls_collection.create_index([("domain", 1), ("url", 1)], unique=True)
    
    # Process URLs
    results = {}
    added_count = 0
    skipped_count = 0
    error_count = 0
    
    # Process URLs in batches to improve MongoDB insertion performance
    batch_size = min(500, len(urls))
    url_batches = [urls[i:i + batch_size] for i in range(0, len(urls), batch_size)]
    
    for batch in url_batches:
        domain_batches = {}
        
        # Group URLs by domain
        for url in batch:
            try:
                url = url.strip()
                if not url:
                    continue
                    
                domain = extract_domain_from_url(url)
                if not domain:
                    continue
                
                if domain not in domain_batches:
                    domain_batches[domain] = []
                domain_batches[domain].append(url)
            except Exception:
                error_count += 1
        
        # Process each domain batch
        for domain, domain_urls in domain_batches.items():
            try:
                # Add domain if it doesn't exist
                domains_collection.update_one(
                    {"domain": domain},
                    {"$setOnInsert": {
                        "domain": domain,
                        "status": STATUS_PENDING,
                        "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S")
                    }},
                    upsert=True
                )
                
                # Prepare bulk URL operations
                url_operations = []
                current_time = time.strftime("%Y-%m-%dT%H:%M:%S")
                
                for url in domain_urls:
                    url_doc = {
                        "domain": domain,
                        "url": url,
                        "added_at": current_time,
                        "status": STATUS_PENDING,
                        "retries": 0,
                        "last_updated": current_time
                    }
                    
                    try:
                        # Try to insert the URL
                        urls_collection.insert_one(url_doc)
                        
                        # Update count
                        if domain not in results:
                            results[domain] = 0
                        results[domain] += 1
                        added_count += 1
                    except Exception:
                        # URL likely already exists
                        skipped_count += 1
            except Exception:
                error_count += len(domain_urls)
    
    # Close connection
    client.close()
    
    return {
        "chunk_id": chunk_id,
        "results": results,
        "added": added_count,
        "skipped": skipped_count,
        "errors": error_count
    }

def split_file_into_chunks(file_path, chunk_size=CHUNK_SIZE):
    """Split a file into chunks of lines"""
    chunks = []
    current_chunk = []
    chunk_id = 0
    
    with open(file_path, 'r') as f:
        for line in f:
            current_chunk.append(line.strip())
            if len(current_chunk) >= chunk_size:
                chunks.append((chunk_id, current_chunk))
                current_chunk = []
                chunk_id += 1
        
        # Don't forget the last chunk
        if current_chunk:
            chunks.append((chunk_id, current_chunk))
    
    return chunks

def main():
    """Load validated URLs into MongoDB using parallel processing"""
    logger.info("Starting parallel URL loading process")
    logger.info("Using %d parallel processes", NUM_PROCESSES)
    
    # Check if file exists
    if not os.path.exists(VALIDATED_URLS_FILE):
        logger.error("File not found: %s", VALIDATED_URLS_FILE)
        return False
    
    # Get file size and count lines
    file_size = os.path.getsize(VALIDATED_URLS_FILE) / (1024 * 1024)  # Size in MB
    logger.info("Found %s (%.2f MB)", VALIDATED_URLS_FILE, file_size)
    
    # Split file into chunks
    logger.info("Splitting file into chunks of %d URLs...", CHUNK_SIZE)
    chunks = split_file_into_chunks(VALIDATED_URLS_FILE, CHUNK_SIZE)
    logger.info("File split into %d chunks", len(chunks))
    
    # Start processing in parallel
    start_time = time.time()
    logger.info("Processing %d chunks with %d workers...", len(chunks), NUM_PROCESSES)
    
    all_results = {}
    total_added = 0
    total_skipped = 0
    total_errors = 0
    
    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        futures = [executor.submit(process_url_chunk, chunk_id, urls) for chunk_id, urls in chunks]
        
        for i, future in enumerate(futures):
            try:
                result = future.result()
                chunk_results = result["results"]
                
                # Merge results
                for domain, count in chunk_results.items():
                    if domain not in all_results:
                        all_results[domain] = 0
                    all_results[domain] += count
                
                total_added += result["added"]
                total_skipped += result["skipped"]
                total_errors += result["errors"]
                
                # Log progress
                logger.info("Processed chunk %d (%d/%d): Added %d URLs", 
                           result['chunk_id'], i+1, len(chunks), result['added'])
                
            except Exception as e:
                logger.error("Error processing chunk: %s", e)
    
    # Calculate stats
    elapsed_time = time.time() - start_time
    domains_count = len(all_results)
    urls_count = sum(all_results.values())
    
    logger.info("Completed in %.2f seconds", elapsed_time)
    logger.info("Added %d URLs across %d domains", total_added, domains_count)
    logger.info("Skipped %d URLs (likely duplicates)", total_skipped)
    logger.info("Encountered %d errors", total_errors)
    
    # Show throughput
    if elapsed_time > 0:
        throughput = total_added / elapsed_time
        logger.info("Throughput: %.2f URLs/second", throughput)
    
    # Show sample of domains loaded
    if domains_count > 0:
        logger.info("Sample of domains loaded:")
        for i, (domain, count) in enumerate(list(all_results.items())[:10]):
            logger.info("  %d. %s: %d URLs", i+1, domain, count)
        
        if domains_count > 10:
            logger.info("  ... and %d more domains", domains_count - 10)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 