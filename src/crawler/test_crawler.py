#!/usr/bin/env python3
"""
Test script for the ExtensionCrawler to crawl specific URLs without using the database.
This is a standalone script for testing purposes.
"""

import argparse
import asyncio
import os
import sys
from typing import Dict, List
from urllib.parse import urlparse

# Add the project root to the Python path so 'src' can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.config.settings import DATA_DIR, EXTENSION_PATH
from src.crawler.browser_manager import BrowserManager
from src.crawler.extension_crawler import ExtensionCrawler
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class TestCrawler:
    """
    Test wrapper for ExtensionCrawler that bypasses the database for URL retrieval.
    """
    
    def __init__(
        self,
        urls: List[str],
        headless: bool = False,
        extension_path: str = None,
        data_dir: str = None,
    ):
        """
        Initialize the test crawler with a list of URLs to process.
        
        Args:
            urls: List of URLs to process
            headless: Whether to run browser in headless mode
            extension_path: Path to the Chrome extension directory
            data_dir: Directory to store crawl data
        """
        self.urls = urls
        self.headless = headless
        self.extension_path = extension_path or EXTENSION_PATH
        self.data_dir = data_dir or os.path.join(DATA_DIR)
        
        # Create the crawler instance
        self.crawler = ExtensionCrawler(
            worker_id="test_worker",
            headless=self.headless,
            extension_path=self.extension_path,
            data_dir=self.data_dir,
        )
        
        logger.info(f"TestCrawler initialized with {len(urls)} URLs")
        logger.info(f"Data directory: {self.data_dir}")
        logger.info(f"Extension path: {self.extension_path}")
    
    async def start(self):
        """
        Start the test crawler and process the provided URLs.
        """
        logger.info("Starting TestCrawler")
        
        # Initialize the browser manager
        self.crawler.browser_manager = BrowserManager(headless=self.headless)
        await self.crawler.browser_manager.init()
        
        try:
            # Process each URL
            results = []
            for url in self.urls:
                domain = urlparse(url).netloc
                logger.info(f"Processing URL: {url}")
                
                try:
                    result = await self.crawler.process_url(url, domain)
                    results.append(result)
                    
                    if result["success"]:
                        logger.info(f"✅ Successfully processed {url}")
                        logger.info(f"   Found {len(result['elements'])} elements")
                        logger.info(f"   Discovered {len(result['discovered_urls'])} URLs")
                    else:
                        logger.error(f"❌ Failed to process {url}: {result['error']}")
                        
                except Exception as e:
                    logger.error(f"Error processing {url}: {e}")
            
            # Print summary
            successful = sum(1 for r in results if r.get("success", False))
            logger.info(f"Completed processing {len(self.urls)} URLs: {successful} successful, {len(self.urls) - successful} failed")
            
        finally:
            # Close the browser
            if self.crawler.browser_manager:
                await self.crawler.browser_manager.close()
    
    @staticmethod
    def parse_url_file(file_path: str) -> List[str]:
        """
        Parse a file containing URLs (one per line).
        
        Args:
            file_path: Path to the file containing URLs
            
        Returns:
            List of URLs
        """
        urls = []
        with open(file_path, 'r') as f:
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):
                    urls.append(url)
        return urls


async def main():
    """Main entry point for the test crawler."""
    parser = argparse.ArgumentParser(description="Test crawler for specific URLs")
    
    # URL input options (mutually exclusive)
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument("--url", help="Single URL to crawl")
    url_group.add_argument("--urls", nargs="+", help="Multiple URLs to crawl")
    url_group.add_argument("--url-file", help="File containing URLs to crawl (one URL per line)")
    
    # Other options
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--extension-path", help="Path to the Chrome extension directory")
    parser.add_argument("--data-dir", help="Directory to store crawl data")
    
    args = parser.parse_args()
    
    # Collect URLs from the selected input method
    urls = []
    if args.url:
        urls = [args.url]
    elif args.urls:
        urls = args.urls
    elif args.url_file:
        urls = TestCrawler.parse_url_file(args.url_file)
    
    logger.info(f"Processing {len(urls)} URLs: {', '.join(urls)}")
    
    # Create and start the test crawler
    test_crawler = TestCrawler(
        urls=urls,
        headless=args.headless,
        extension_path=args.extension_path,
        data_dir=args.data_dir
    )
    
    await test_crawler.start()


if __name__ == "__main__":
    asyncio.run(main()) 
