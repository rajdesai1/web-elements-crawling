#!/usr/bin/env python3
"""
Main entry point for running the TRANCE web crawler.
This script initializes and runs the ExtensionCrawler which detects interactive elements on web pages.
Using settings directly from settings.py.
"""

import asyncio
import sys
from pathlib import Path

from src.crawler.extension_crawler import ExtensionCrawler
from src.config.settings import (
    DATA_DIR,
    DOMAIN_MAX_URLS_PER_SESSION,
    FORM_DATA_VARIETY,
    FORM_DATA_REGION,
    PROFILES_FILE,
    EXTENSION_PATH,
    BROWSER_SETTINGS,
    DEFAULT_WORKER_ID,
    CONCURRENT_DOMAINS,
)
from src.utils.mongodb_queue import domain_manager
from src.utils.logger import setup_logger

# Configure logger for this module
logger = setup_logger(__name__)


async def run_crawler():
    """Initialize and run the web crawler with settings from settings.py."""
    # Check MongoDB connection
    if not domain_manager.healthcheck():
        logger.error("MongoDB connection failed. Please check your connection settings.")
        return

    logger.info("MongoDB connection successful!")
    
    # Create and start the crawler using settings from ExtensionCrawler's defaults
    crawler = ExtensionCrawler(worker_id=DEFAULT_WORKER_ID)

    logger.info("Starting crawler with worker ID: %s", DEFAULT_WORKER_ID)
    await crawler.start()  # Uses CONCURRENT_DOMAINS from settings by default


def main():
    """Run the crawler using settings from settings.py."""
    logger.info("Starting crawler with the following settings:")
    logger.info("Worker ID: %s", DEFAULT_WORKER_ID)
    logger.info("Headless mode: %s", BROWSER_SETTINGS["headless"])
    logger.info("Concurrent domains: %s", CONCURRENT_DOMAINS)
    logger.info("Data directory: %s", DATA_DIR)
    logger.info("Extension path: %s", EXTENSION_PATH)
    
    # Run the crawler
    asyncio.run(run_crawler())


if __name__ == "__main__":
    main() 