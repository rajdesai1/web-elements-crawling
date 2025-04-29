#!/usr/bin/env python3
"""
Script to reset the MongoDB database to its initial state.
This resets all statuses, removes worker assignments, and puts everything back to pending state.
"""

import os
import sys
from datetime import datetime
from typing import Any, Dict

from pymongo import MongoClient, UpdateMany

from src.config.settings import (MONGODB_DB_NAME, MONGODB_DOMAINS_COLLECTION,
                                 MONGODB_URI, MONGODB_URLS_COLLECTION,
                                 STATUS_PENDING)
from src.utils.logger import setup_logger

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = setup_logger(__name__)

def reset_database(confirm: bool = False) -> Dict[str, Any]:
    """
    Reset the MongoDB database to its initial state.
    This includes:
    - Resetting all domain statuses to pending
    - Removing worker assignments
    - Resetting URL statuses to pending
    - Clearing processing timestamps and metadata
    
    Args:
        confirm: Whether to skip confirmation prompt
        
    Returns:
        Dictionary with reset statistics
    """
    if not confirm:
        response = input("⚠️ WARNING: This will reset all data to initial state. Are you sure? (y/N): ")
        if response.lower() != 'y':
            logger.info("Database reset cancelled.")
            return {"status": "cancelled", "timestamp": datetime.now().isoformat()}

    try:
        # Connect to MongoDB
        logger.info("Connecting to MongoDB...")
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DB_NAME]
        
        # Get initial counts for statistics
        total_domains = db[MONGODB_DOMAINS_COLLECTION].count_documents({})
        total_urls = db[MONGODB_URLS_COLLECTION].count_documents({})
        
        processing_domains = db[MONGODB_DOMAINS_COLLECTION].count_documents({"status": {"$ne": STATUS_PENDING}})
        processing_urls = db[MONGODB_URLS_COLLECTION].count_documents({"status": {"$ne": STATUS_PENDING}})
        
        # Reset domains collection
        logger.info("Resetting domains collection...")
        domains_update = {
            "$set": {
                "status": STATUS_PENDING,
                "last_updated": datetime.now().isoformat()
            },
            "$unset": {
                "worker_id": "",
                "claimed_at": "",
                "completed_at": "",
                "processing_started": "",
                "error": "",
                "stats": "",
                "heartbeat": ""
            }
        }
        db[MONGODB_DOMAINS_COLLECTION].update_many({}, domains_update)
        
        # Reset URLs collection
        logger.info("Resetting URLs collection...")
        urls_update = {
            "$set": {
                "status": STATUS_PENDING,
                "retries": 0,
                "last_updated": datetime.now().isoformat()
            },
            "$unset": {
                "worker_id": "",
                "processing_started": "",
                "completed_at": "",
                "error": "",
                "elements_count": "",
                "discovered_urls_count": "",
                "processing_stats": "",
                "metadata": "",
                "heartbeat": ""
            }
        }
        db[MONGODB_URLS_COLLECTION].update_many({}, urls_update)
        
        result = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "statistics": {
                "total_domains": total_domains,
                "total_urls": total_urls,
                "reset_domains": processing_domains,
                "reset_urls": processing_urls
            }
        }
        
        logger.info("✅ Database reset complete!")
        logger.info("Reset %d domains and %d URLs to pending state", processing_domains, processing_urls)
        logger.info("Total items in database: %d domains, %d URLs", total_domains, total_urls)
        
        return result
        
    except Exception as e:
        error_msg = f"Error resetting database: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "error",
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Reset the MongoDB database to initial state")
    parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    
    reset_database(confirm=args.force) 
