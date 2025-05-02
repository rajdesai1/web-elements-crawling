#!/usr/bin/env python3
"""
Browser manager module for handling Patchright browser instances and page operations.
"""

import asyncio
import os
import time
from typing import Dict

# Renamed for avoiding bot detection
from patchright.async_api import async_playwright, Page

from src.config.settings import (
    BROWSER_SETTINGS, 
    DATA_DIR,
    REQUEST_TIMEOUT
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class BrowserManager:
    """Manager for handling browser instances and page operations."""
    
    def __init__(self, headless: bool = BROWSER_SETTINGS["headless"], user_data_dir: str = None,
                storage_state_path: str = None):
        """
        Initialize the browser manager.
        
        Args:
            headless: Whether to run the browser in headless mode
            user_data_dir: Directory to store user data for persistent context
            storage_state_path: Path to a storage state file with cookies and localStorage
            extension_path: Path to a Chrome extension to load
        """
        self.headless = headless
        self.user_data_dir = user_data_dir or BROWSER_SETTINGS.get("user_data_dir") or os.path.join(os.path.expanduser("~"), ".patchright_browser_data")
        self.storage_state_path = storage_state_path or os.path.join(DATA_DIR, "storage_state.json")
        self.extension_path = BROWSER_SETTINGS['extension_path']
        self.context = None
        self.page = None
        self.playwright = None
    
    async def init(self) -> None:
        """Initialize the browser with persistent context and extension if provided."""
        try:
            logger.info("Initializing browser with context")
            
            self.playwright = await async_playwright().start()
            
            # Check if extension path is provided and valid
            if self.extension_path:
                if not os.path.exists(self.extension_path):
                    logger.error("Extension path does not exist: %s", self.extension_path)
                    raise FileNotFoundError(f"Extension path does not exist: {self.extension_path}")
                    
                # Check if manifest.json exists in the extension path
                manifest_path = os.path.join(self.extension_path, "manifest.json")
                if not os.path.exists(manifest_path):
                    logger.error("Extension manifest.json not found at: %s", manifest_path)
                    raise FileNotFoundError(f"Extension manifest.json not found at: {manifest_path}")
                
                logger.info("Loading extension from: %s", self.extension_path)
                
                # Use persistent context for extension loading (required for Chrome extensions)
                self.context = await self.playwright.chromium.launch_persistent_context(
                    channel="chrome",
                    user_data_dir=self.user_data_dir,
                    headless=self.headless,
                    viewport=BROWSER_SETTINGS["viewport"],
                    user_agent=BROWSER_SETTINGS.get("user_agent", 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'),
                    locale=BROWSER_SETTINGS.get("locale", "en-US"),
                    device_scale_factor=BROWSER_SETTINGS["device_scale_factor"],
                    timezone_id=BROWSER_SETTINGS.get("timezone_id", "America/New_York"),
                    bypass_csp=True,  # Bypass Content Security Policy
                    args=[
                        f"--disable-extensions-except={self.extension_path}",
                        f"--load-extension={self.extension_path}",
                        '--disable-blink-features=AutomationControlled',
                    ]
                )
            else:
                # Create browser instance without extension
                browser = await self.playwright.chromium.launch(
                    headless=self.headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                    ]
                )
                
                # Create a context with specific settings
                self.context = await browser.new_context(
                    viewport=BROWSER_SETTINGS["viewport"],
                    user_agent=BROWSER_SETTINGS.get("user_agent", 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'),
                    locale=BROWSER_SETTINGS.get("locale", "en-US"),
                    device_scale_factor=BROWSER_SETTINGS["device_scale_factor"],
                    timezone_id=BROWSER_SETTINGS.get("timezone_id", "America/New_York"),
                    bypass_csp=True  # Bypass Content Security Policy
                )
            
            # Set default timeout
            self.context.set_default_timeout(BROWSER_SETTINGS.get("default_timeout", REQUEST_TIMEOUT * 1000))
            
            # Wait for extension to initialize
            if self.extension_path:
                logger.info("Waiting for extension to initialize...")
                await asyncio.sleep(2)
                
                # Try to get background page if available
                # try:
                #     background_pages = self.context.background_pages
                #     if background_pages:
                #         logger.info("Extension background page detected: %d pages", len(background_pages))
                #     else:
                #         logger.info("No extension background pages found yet, waiting...")
                #         # Wait for the background page event
                #         try:
                #             # Try to wait for background page with a timeout
                #             await asyncio.wait_for(
                #                 self.context.wait_for_event("backgroundpage"), 
                #                 timeout=5.0
                #             )
                #             logger.info("Background page loaded")
                #         except asyncio.TimeoutError:
                #             logger.warning("Timed out waiting for extension background page")
                # except Exception as e:
                #     logger.warning("Error checking for extension background pages: %s", str(e))
            
            logger.info("Browser with context initialized successfully")
        except Exception as e:
            logger.error("Error initializing browser with context: %s", str(e))
            raise
    
    async def new_page(self) -> Page:
        """
        Create a new page.
        
        Returns:
            Browser page
        """
    
        if not self.context:
            logger.debug("No browser context available, initializing browser")
            await self.init()
        
        logger.debug("Creating new browser page")
        
        self.page = await self.context.new_page()
        
        # Set default navigation timeout
        self.page.set_default_navigation_timeout(REQUEST_TIMEOUT * 1000)  # Convert to milliseconds
        
        return self.page
    
    async def navigate(self, url: str, options: Dict = None) -> bool:
        """
        Navigate to a URL.
        
        Args:
            url: URL to navigate to
            options: Navigation options
            
        Returns:
            True if navigation succeeded, False otherwise
        """
        if not self.page:
            await self.new_page()
        
        options = options or {}
        wait_until = options.get("wait_until", "networkidle")
        timeout = options.get("timeout", REQUEST_TIMEOUT * 1000)  # Convert to milliseconds
        
        try:
            logger.info("Navigating to %s", url)
            response = await self.page.goto(url, wait_until=wait_until, timeout=timeout)
            
            if not response:
                logger.warning("No response received for %s", url)
                return False
            
            if response.status >= 400:
                logger.warning("Navigation to %s resulted in status code %d", url, response.status)
                return False
            
            # Wait for page to be fully loaded and JavaScript to execute
            await self.page.wait_for_load_state("domcontentloaded")
            
            # Additional wait to ensure JavaScript has fully executed
            await asyncio.sleep(2)
            
            logger.info("Successfully navigated to %s", url)
            return True
        except Exception as e:
            logger.error("Error navigating to %s: %s", url, str(e))
            return False
    
    async def scroll_page(self, distance: int = 300, timeout: int = 30, max_scrolls: int = 20, 
                        max_total_height: int = 50000, min_scrolls: int = 3, 
                        content_detection_threshold: int = 3, scroll_pause: float = 0.8) -> Dict:
        """
        Scroll the page to reveal more content with adaptive behavior for different page types.
        
        Args:
            distance: Scroll distance in pixels per scroll
            timeout: Maximum scroll time in seconds
            max_scrolls: Maximum number of scroll operations
            max_total_height: Maximum total height to scroll in pixels (hard limit for infinite scroll pages)
            min_scrolls: Minimum number of scrolls to attempt even if no new content appears
            content_detection_threshold: Number of consecutive scrolls with no new content before stopping
            scroll_pause: Time to pause between scrolls in seconds
            
        Returns:
            Dictionary with scrolling results
        """
        if not self.page:
            logger.error("No page available for scrolling")
            return {"success": False, "scrolls": 0, "reason": "No page available"}
        
        try:
            scrolls = 0
            consecutive_no_change = 0
            start_time = time.time()
            last_height = await self.page.evaluate("document.documentElement.scrollHeight")
            start_height = last_height
            
            # Try to detect if we're at the top of the page and scroll to it if not
            current_scroll_position = await self.page.evaluate("window.scrollY || window.pageYOffset")
            if current_scroll_position > 0:
                await self.page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(scroll_pause)
                
            # Get the viewport height to calculate visible content
            viewport_height = (await self.page.evaluate("window.innerHeight")) or 800
            adaptive_distance = min(distance, viewport_height * 0.8)  # Cap scroll at 80% of viewport
                
            while scrolls < max_scrolls and (time.time() - start_time) < timeout:
                # Get current position before scrolling
                before_scroll_pos = await self.page.evaluate("window.scrollY || window.pageYOffset")
                
                # Scroll down
                await self.page.evaluate(f"window.scrollBy(0, {adaptive_distance})")
                
                # Wait for page to load more content
                await asyncio.sleep(scroll_pause)
                
                # Verify if the scroll was actually executed
                after_scroll_pos = await self.page.evaluate("window.scrollY || window.pageYOffset")
                if after_scroll_pos <= before_scroll_pos and scrolls > 0:
                    logger.info("Could not scroll further, reached end of page")
                    break
                
                # Get new scroll height
                new_height = await self.page.evaluate("document.documentElement.scrollHeight")
                total_scrolled = after_scroll_pos - 0  # Total pixels scrolled from top
                
                # If we've exceeded the maximum total height to scroll
                if total_scrolled > max_total_height:
                    logger.info("Reached maximum scroll height limit of %dpx", max_total_height)
                    break
                
                
                # Check if new content was loaded
                if new_height <= last_height:
                    consecutive_no_change += 1
                    # Only stop if we've done the minimum number of scrolls
                    # and we've seen several scrolls with no new content
                    if scrolls >= min_scrolls and consecutive_no_change >= content_detection_threshold:
                        logger.info("No new content detected after %d scrolls", content_detection_threshold)
                        break
                else:
                    # Reset the counter as we found new content
                    consecutive_no_change = 0
                
                last_height = new_height
                scrolls += 1
                
                # Adapt scroll distance based on page behavior
                if new_height > start_height * 3:
                    # We're on a potentially infinite scroll page, increase scroll distance
                    adaptive_distance = min(distance * 2, viewport_height * 0.9)
                
            time_taken = time.time() - start_time
            final_height = await self.page.evaluate("document.documentElement.scrollHeight")
            scrolled_pixels = await self.page.evaluate("window.scrollY || window.pageYOffset")
            
            logger.info("Scrolled page %d times, covering %dpx in %.2fs", scrolls, scrolled_pixels, time_taken)
            
            # Return a result dictionary with scroll metrics
            return {
                "success": True,
                "scrolls": scrolls,
                "time_taken": time_taken,
                "start_height": start_height,
                "final_height": final_height,
                "scrolled_pixels": scrolled_pixels,
                "reached_bottom": consecutive_no_change >= content_detection_threshold or scrolls >= max_scrolls
            }
        except Exception as e:
            logger.error("Error scrolling page: %s", str(e))
            return {"success": False, "scrolls": 0, "reason": str(e)}
    
    async def calculate_scrollability(self, page: Page) -> Dict:
        """
        Calculate detailed scrollability metrics for a page.
        
        Determines:
        - If the page can be scrolled (vertically and horizontally)
        - The number of viewports in the page
        - The current scroll position and progress
        - Exact scroll points for each viewport
        
        Args:
            page: Page to analyze
            
        Returns:
            Dictionary with detailed scrollability metrics
        """
        if not page:
            logger.error("No page available for scrollability calculation")
            return {}
            
        try:
            # Execute the calculation in the page context
            scrollability = await page.evaluate("""
            () => {
                // Get document dimensions
                const totalHeight = document.documentElement.scrollHeight;
                const totalWidth = document.documentElement.scrollWidth;
                const viewportHeight = window.innerHeight;
                const viewportWidth = window.innerWidth;
                const currentScrollTop = document.documentElement.scrollTop || window.pageYOffset || document.body.scrollTop;
                const currentScrollLeft = document.documentElement.scrollLeft || window.pageXOffset || document.body.scrollLeft;
                
                // Calculate maximum scroll positions
                const maxScrollTop = Math.max(0, totalHeight - viewportHeight);
                const maxScrollLeft = Math.max(0, totalWidth - viewportWidth);
                
                // Determine if page can be scrolled from current position
                const totalCanScrollVertically = totalHeight > viewportHeight;
                const totalCanScrollHorizontally = totalWidth > viewportWidth;
                
                // Determine if there's remaining scroll from current position
                const canScrollMoreVertically = totalCanScrollVertically && (currentScrollTop < maxScrollTop - 1); // -1 to account for rounding
                const canScrollMoreHorizontally = totalCanScrollHorizontally && (currentScrollLeft < maxScrollLeft - 1);
                
                // Calculate scrollable viewports
                const verticalViewports = Math.ceil(totalHeight / viewportHeight);
                const horizontalViewports = Math.ceil(totalWidth / viewportWidth);
                
                // Calculate remaining viewports from current position (no +1 when at the end)
                const remainingDistance = totalHeight - currentScrollTop - viewportHeight;
                const remainingVerticalViewports = canScrollMoreVertically ? 
                    Math.ceil(Math.max(0, remainingDistance) / viewportHeight) + 1 : 0;
                    
                const remainingHorizontalDistance = totalWidth - currentScrollLeft - viewportWidth;
                const remainingHorizontalViewports = canScrollMoreHorizontally ? 
                    Math.ceil(Math.max(0, remainingHorizontalDistance) / viewportWidth) + 1 : 0;
                
                // Calculate scroll progress percentages
                const verticalScrollProgress = totalCanScrollVertically ? 
                    Math.min(100, (currentScrollTop / maxScrollTop * 100)) : 0;
                const horizontalScrollProgress = totalCanScrollHorizontally ? 
                    Math.min(100, (currentScrollLeft / maxScrollLeft * 100)) : 0;
                
                // Define scroll start and end points
                const scrollStartPoint = { x: 0, y: 0 };
                const scrollEndPoint = { x: maxScrollLeft, y: maxScrollTop };
                
                // Calculate viewport scroll steps (useful for programmatic scrolling)
                const viewportScrollSteps = [];
                if (totalCanScrollVertically) {
                    for (let i = 0; i < verticalViewports; i++) {
                        const scrollPosition = Math.min(maxScrollTop, i * viewportHeight);
                        viewportScrollSteps.push({
                            index: i,
                            scrollTop: scrollPosition,
                            isCurrentViewport: (
                                scrollPosition <= currentScrollTop && 
                                currentScrollTop < scrollPosition + viewportHeight
                            ),
                            isLastViewport: (scrollPosition + viewportHeight >= totalHeight)
                        });
                    }
                }
                
                // Determine current viewport index
                const currentViewportIndex = viewportScrollSteps.findIndex(step => step.isCurrentViewport);
                
                return {
                    vertical: {
                        canScroll: canScrollMoreVertically,
                        isAtEnd: currentScrollTop >= maxScrollTop - 1,
                        totalCanScroll: totalCanScrollVertically,
                        totalViewports: verticalViewports,
                        remainingViewports: remainingVerticalViewports,
                        currentViewportIndex: currentViewportIndex !== -1 ? currentViewportIndex : 0,
                        totalHeight,
                        viewportHeight,
                        currentPosition: currentScrollTop,
                        maxScrollPosition: maxScrollTop,
                        progress: verticalScrollProgress,
                        startPoint: scrollStartPoint.y,
                        endPoint: scrollEndPoint.y,
                        viewportScrollPositions: totalCanScrollVertically ? 
                            viewportScrollSteps.map(step => step.scrollTop) : []
                    },
                    horizontal: {
                        canScroll: canScrollMoreHorizontally,
                        isAtEnd: currentScrollLeft >= maxScrollLeft - 1,
                        totalCanScroll: totalCanScrollHorizontally,
                        totalViewports: horizontalViewports,
                        remainingViewports: remainingHorizontalViewports,
                        totalWidth,
                        viewportWidth,
                        currentPosition: currentScrollLeft,
                        maxScrollPosition: maxScrollLeft,
                        progress: horizontalScrollProgress,
                        startPoint: scrollStartPoint.x,
                        endPoint: scrollEndPoint.x
                    },
                    scrollStartPoint,
                    scrollEndPoint,
                    viewportSteps: totalCanScrollVertically ? viewportScrollSteps : [],
                    isFullyScrolled: {
                        vertical: currentScrollTop >= maxScrollTop - 1,
                        horizontal: currentScrollLeft >= maxScrollLeft - 1
                    }
                };
            }
            """)
            
            return scrollability
        
        except Exception as e:
            logger.error("Error calculating scrollability: %s", str(e))
            return {}
    
    async def detect_interactive_elements(self, page: Page) -> Dict:
        """
        Detect interactive elements on the page using multiple techniques to work around 
        Patchright's extensions limitations.
        
        Args:
            page: Page to analyze
            
        Returns:
            Dictionary with interactive elements data
        """
        logger.info("Detecting interactive elements on page with enhanced methods")
        
        try:
            # METHOD 1 (Now priority): Try injecting a content script manually through Chrome Debug Protocol
            try:
                logger.info("Trying CDP content script injection...")
                # Get CDP session
                cdp_session = await page.context.new_cdp_session(page)
                
                # Execute script in main world
                cdp_result = await cdp_session.send('Runtime.evaluate', {
                    'expression': """
                        (function() {
                            if (typeof window.domTreeResult === 'function') {
                                return window.domTreeResult({
                                    doHighlightElements: false,
                                    focusHighlightIndex: -1,
                                    viewportExpansion: 0,
                                    debugMode: false
                                });
                            } else {
                                return {error: 'domTreeResult not found via CDP'};
                            }
                        })()
                    """,
                    'returnByValue': True,
                    'awaitPromise': True
                })
                
                if (cdp_result and 
                    cdp_result.get('result') and 
                    cdp_result.get('result').get('value') and
                    not cdp_result.get('result').get('value').get('error')):
                    extension_result = cdp_result.get('result').get('value')
                    logger.info("Successfully got data via CDP content script")
                    logger.info("Found %d interactive elements", len(extension_result.get('interactiveElements', [])))
                    return extension_result
            except Exception as e:
                logger.warning("CDP content script injection failed: %s", str(e))
            
            # METHOD 2: Try exposing a function from extension to window via Object.defineProperty
            # This sometimes works for accessing extension context from page context
            try:
                logger.info("Trying property definition approach...")
                await page.evaluate("""
                    () => {
                        // Try to use Object.defineProperty to access extension function
                        try {
                            let cachedResult = null;
                            Object.defineProperty(window, '_domTreeResultProxy', {
                                get: function() {
                                    try {
                                        if (window.domTreeResult) {
                                            cachedResult = window.domTreeResult({
                                                doHighlightElements: false,
                                                focusHighlightIndex: -1,
                                                viewportExpansion: 0,
                                                debugMode: false
                                            });
                                        }
                                    } catch(e) {
                                        console.error("Error in property getter:", e);
                                    }
                                    return cachedResult;
                                }
                            });
                            console.log("Defined proxy property for extension function");
                        } catch(e) {
                            console.error("Failed to define property:", e);
                        }
                    }
                """)
                
                # Try to access the proxy property
                proxy_result = await page.evaluate("() => window._domTreeResultProxy")
                if proxy_result:
                    logger.info("Successfully retrieved results from proxy property")
                    logger.info("Found %d interactive elements", len(proxy_result.get('interactiveElements', [])))
                    return proxy_result
            except Exception as e:
                logger.warning("Property definition approach failed: %s", str(e))
            
            # METHOD 3 (Fallback): Try injecting a script tag directly into the page
            # This can sometimes bypass context isolation issues
            try:
                logger.info("Trying DOM script injection approach...")
                # Create a unique ID for our results
                result_id = f"ext_result_{int(time.time() * 1000)}"
                
                # Inject a script tag into the DOM
                await page.evaluate(f"""
                    () => {{
                        // Create a global variable to hold results
                        window.{result_id} = null;
                        
                        // Create and inject a script element
                        const script = document.createElement('script');
                        script.textContent = `
                            try {{
                                console.log("Injected script running");
                                if (typeof window.domTreeResult === 'function') {{
                                    console.log("Found domTreeResult in injected script");
                                    const result = window.domTreeResult({{
                                        doHighlightElements: false,
                                        focusHighlightIndex: -1,
                                        viewportExpansion: 0,
                                        debugMode: false
                                    }});
                                    window.{result_id} = result;
                                    console.log("Stored result in window.{result_id}");
                                    
                                    // Also store in localStorage as backup
                                    try {{
                                        localStorage.setItem('{result_id}', JSON.stringify(result));
                                        console.log("Backed up result to localStorage");
                                    }} catch(e) {{
                                        console.error("Failed to save to localStorage:", e);
                                    }}
                                    
                                    // Create a DOM element to store the result
                                    const dataElement = document.createElement('div');
                                    dataElement.id = '{result_id}_element';
                                    dataElement.style.display = 'none';
                                    dataElement.setAttribute('data-result', JSON.stringify(result));
                                    document.body.appendChild(dataElement);
                                    console.log("Created data element in DOM");
                                }} else {{
                                    console.error("domTreeResult function not found in injected script");
                                }}
                            }} catch(e) {{
                                console.error("Error in injected script:", e);
                            }}
                        `;
                        document.head.appendChild(script);
                        console.log("Script injected into DOM");
                    }}
                """)
                
                # Try to retrieve results from global variable
                result = await page.evaluate(f"return window.{result_id};")
                if result:
                    logger.info("Successfully retrieved results from injected script global variable")
                    logger.info("Found %d interactive elements", len(result.get('interactiveElements', [])))
                    return result
                
                # Fallback: Try getting from localStorage
                try:
                    localStorage_result = await page.evaluate(f"""
                        () => {{
                            try {{
                                const storedData = localStorage.getItem('{result_id}');
                                if (storedData) {{
                                    return JSON.parse(storedData);
                                }}
                            }} catch(e) {{
                                console.error("Error retrieving from localStorage:", e);
                            }}
                            return null;
                        }}
                    """)
                    
                    if localStorage_result:
                        logger.info("Successfully retrieved results from localStorage")
                        logger.info("Found %d interactive elements", len(localStorage_result.get('interactiveElements', [])))
                        return localStorage_result
                except Exception as e:
                    logger.warning("Error checking localStorage: %s", str(e))
                
                # Fallback: Try getting from DOM element
                try:
                    dom_result = await page.evaluate(f"""
                        () => {{
                            const dataElement = document.getElementById('{result_id}_element');
                            if (dataElement) {{
                                const resultAttr = dataElement.getAttribute('data-result');
                                if (resultAttr) {{
                                    return JSON.parse(resultAttr);
                                }}
                            }}
                            return null;
                        }}
                    """)
                    
                    if dom_result:
                        logger.info("Successfully retrieved results from DOM element")
                        logger.info("Found %d interactive elements", len(dom_result.get('interactiveElements', [])))
                        return dom_result
                except Exception as e:
                    logger.warning("Error checking DOM element: %s", str(e))
                
            except Exception as e:
                logger.warning("Script injection approach failed: %s", str(e))
            
            # If all methods failed, return empty result
            logger.warning("All methods to access domTreeResult failed")
            return {'interactiveElements': []}
            
        except Exception as e:
            logger.error("Error running interactive element detection: %s", str(e))
            return {'interactiveElements': []}
    
    async def scroll_element_into_view(self, page: Page, element: Dict) -> bool:
        """
        Scroll an element into view using its XPath.
        
        Args:
            page: Page containing the element
            element: Element data with elementPath
            
        Returns:
            True if scrolled successfully, False otherwise
        """
        try:
            # Check if element has elementPath, skip if not available
            element_path = element.get('elementPath')
            if not element_path:
                logger.info("Element doesn't have elementPath, skipping")
                return False
            
            # Create a locator using the XPath
            locator = page.locator(f"xpath={element_path}")
            
            # Check if element exists
            if not locator:
                logger.warning("Element not found with XPath: %s", element_path)
                return False

            # Scroll element into view
            logger.info("Scrolling element into view using XPath: %s", element_path)
            await locator.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)  # Wait for scroll to complete

            # Verify element is now visible
            is_visible = await locator.is_visible()
            if is_visible:
                logger.info("Successfully scrolled to element")
                return True
            else:
                logger.warning("Element found but not visible after scroll")
                return False

        except Exception as e:
            logger.error("Error scrolling element into view: %s", e)
            return False
    
    async def close(self) -> None:
        """Close the browser and clean up resources."""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
                
            logger.info("Browser closed successfully")
        except Exception as e:
            logger.error("Error closing browser: %s", str(e))
    
    async def set_up_new_page_listener(self, original_page: Page, callback=None):
        """
        Set up a listener for new pages (tabs) that may open from the current page.
        
        Args:
            original_page: The original page to associate with new tabs
            callback: Optional callback function to execute when a new page is created
                      Should accept (original_page, new_page) as parameters
                      
        Returns:
            The listener function that was created
        """
        if not self.context:
            logger.error("No browser context available for page listener")
            return None
            
        # Store page reference for tracking purposes
        if not hasattr(original_page, '_page_id'):
            original_page._page_id = id(original_page)
            
        async def on_page(new_page):
            try:
                logger.info("New page detected, likely opened from original page")
                
                # Store reference to original page
                new_page._opened_from = original_page._page_id
                
                # Wait for the new page to load
                await new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                
                # Execute callback if provided
                if callback and callable(callback):
                    try:
                        await callback(original_page, new_page)
                    except Exception as e:
                        logger.error("Error in new page callback: %s", str(e))
                        
            except Exception as e:
                logger.error("Error handling new page: %s", str(e))
        
        # Add the listener to the context
        self.context.on("page", on_page)
        logger.info("New page listener set up for context")
        
        return on_page
    
    async def handle_new_page(self, original_page: Page, new_page: Page, capture_data=True, close_after=True):
        """
        Handle a new page that was opened from interaction with original page.
        
        Args:
            original_page: The original page that opened the new page
            new_page: The newly opened page
            capture_data: Whether to capture screenshot and page data
            close_after: Whether to close the new page after capturing data
            
        Returns:
            Dictionary with captured data from the new page
        """
        result = {}
        
        try:
            logger.info("Handling new page at URL: %s", new_page.url)
            
            # Wait for page to be fully loaded
            await new_page.wait_for_load_state("networkidle", timeout=15000)
            
            # Capture the URL
            result["url"] = new_page.url
            
            # Take screenshot if requested
            if capture_data:
                # Create screenshot
                screenshot_bytes = await new_page.screenshot()
                result["screenshot"] = screenshot_bytes
                
                # Get page title
                result["title"] = await new_page.title()
                
                # Capture page content if needed
                result["html"] = await new_page.content()
                
                # Optionally capture more data here
                logger.info("Captured data from new page: %s", new_page.url)
            
            # Close the new page if requested
            if close_after:
                await new_page.close()
                logger.info("Closed new page after capturing data")
            
            return result
            
        except Exception as e:
            logger.error("Error handling new page: %s", str(e))
            
            # Try to close the page to avoid leaking resources
            try:
                if close_after and new_page:
                    await new_page.close()
            except:
                pass
                
            return {"error": str(e)}
            
    async def detect_popup_windows(self, page: Page, action_timeout=5000):
        """
        Detect if any popup windows appeared after an action.
        
        Args:
            page: The page to check for popups
            action_timeout: Time to wait for popups after action in ms
            
        Returns:
            List of new pages that were detected
        """
        new_pages = []
        
        try:
            # Create a future to capture any new pages
            pages_future = asyncio.get_event_loop().create_future()
            pages_detected = []
            
            def on_popup(page):
                pages_detected.append(page)
                if not pages_future.done():
                    pages_future.set_result(True)
            
            # Set up the listener for the popup
            self.context.on("page", on_popup)
            
            # Wait for the specified timeout or until a popup is detected
            try:
                await asyncio.wait_for(pages_future, timeout=action_timeout/1000)
            except asyncio.TimeoutError:
                logger.debug("No popups detected within timeout period")
            
            # Remove the listener to avoid memory leaks
            self.context.remove_listener("page", on_popup)
            
            # Return the detected pages
            new_pages = pages_detected
            
            # Add reference to parent page
            for new_page in new_pages:
                new_page._parent_page = page
                logger.info("Detected new page/popup at URL: %s", await new_page.evaluate("location.href"))
            
            return new_pages
        
        except Exception as e:
            logger.error("Error detecting popup windows: %s", str(e))
            return []
    
    async def scroll_to(self, page: Page, options: Dict = None) -> bool:
        """
        Scroll to different parts of the page with more control than scroll_page.
        
        Args:
            page: Page to scroll
            options: Dictionary with scrolling options:
                - position: 'top', 'bottom', 'middle' or specific pixel value
                - selector: CSS selector to scroll to
                - x: horizontal scroll position
                - y: vertical scroll position
                - behavior: 'smooth' or 'auto'
                
        Returns:
            True if scroll was successful
        """
        if not page:
            logger.error("No page available for scrolling")
            return False
            
        options = options or {}
        behavior = options.get('behavior', 'smooth')
        
        try:
            # Scroll to element if selector provided
            if 'selector' in options:
                selector = options['selector']
                result = await page.evaluate(f"""
                    () => {{
                        try {{
                            const element = document.querySelector('{selector}');
                            if (element) {{
                                element.scrollIntoView({{ behavior: '{behavior}', block: 'center' }});
                                return true;
                            }}
                        }} catch (e) {{
                            console.error('Error scrolling to element:', e);
                        }}
                        return false;
                    }}
                """)
                if result:
                    await asyncio.sleep(0.5 if behavior == 'smooth' else 0.2)
                    return True
                    
            # Scroll to position
            elif 'position' in options:
                position = options['position']
                script = ""
                
                if position == 'top':
                    script = "window.scrollTo({ top: 0, behavior: '" + behavior + "' })"
                elif position == 'bottom':
                    script = "window.scrollTo({ top: document.body.scrollHeight, behavior: '" + behavior + "' })"
                elif position == 'middle':
                    script = "window.scrollTo({ top: document.body.scrollHeight / 2, behavior: '" + behavior + "' })"
                else:
                    # Try to parse as a number
                    try:
                        y_pos = int(position)
                        script = f"window.scrollTo({{ top: {y_pos}, behavior: '{behavior}' }})"
                    except ValueError:
                        logger.error("Invalid scroll position: %s", position)
                        return False
                
                await page.evaluate(script)
                await asyncio.sleep(0.5 if behavior == 'smooth' else 0.2)
                return True
                
            # Scroll to specific coordinates
            elif 'x' in options or 'y' in options:
                x = options.get('x', 0)
                y = options.get('y', 0)
                await page.evaluate(f"window.scrollTo({{ top: {y}, left: {x}, behavior: '{behavior}' }})")
                await asyncio.sleep(0.5 if behavior == 'smooth' else 0.2)
                return True
                
            else:
                logger.warning("No valid scroll options provided")
                return False
                
        except Exception as e:
            logger.error("Error in scroll_to: %s", str(e))
            return False
    
    async def scroll_next_viewport(self, page: Page, pause_after_scroll: float = 1.0) -> Dict:
        """
        Scroll down by one viewport height from the current position.
        
        Args:
            page: Page to scroll
            pause_after_scroll: Time to pause after scrolling in seconds
            
        Returns:
            Dictionary with scrolling results for this viewport
        """
        if not page:
            logger.error("No page available for scrolling")
            return {
                "scroll_action": "error",
                "error": "No page available"
            }
            
        try:
            # Get viewport height and current position
            viewport_height = await page.evaluate("window.innerHeight")
            current_position = await page.evaluate("window.scrollY || window.pageYOffset")
            page_height = await page.evaluate("document.body.scrollHeight")
            
            # Calculate next position
            next_position = current_position + viewport_height
            
            # Check if we'd be scrolling past the bottom of the page
            if next_position >= page_height - viewport_height + 50:  # Add 50px margin
                logger.info("Already near bottom of page at position %dpx", current_position)
                return {
                    "scroll_action": "complete",
                    "viewport_height": viewport_height,
                    "current_position": current_position,
                    "is_last_viewport": True,
                    "reached_bottom": True,
                    "page_height": page_height
                }
            
            # Scroll to the next position
            logger.info("Scrolling from %dpx to %dpx", current_position, next_position)
            await page.evaluate(f"window.scrollTo(0, {next_position})")
            await asyncio.sleep(pause_after_scroll)  # Wait for content to load
            
            # Get new position and height after scrolling (may have changed)
            new_position = await page.evaluate("window.scrollY || window.pageYOffset")
            new_page_height = await page.evaluate("document.body.scrollHeight")
            
            # Check if we've actually moved
            if new_position <= current_position + 10:  # 10px margin for rounding
                logger.info("Reached bottom of page at position %dpx", new_position)
                return {
                    "scroll_action": "complete",
                    "viewport_height": viewport_height,
                    "current_position": new_position,
                    "is_last_viewport": True,
                    "reached_bottom": True,
                    "page_height": new_page_height
                }
            
            # Check if we're near the bottom
            if new_position + viewport_height >= new_page_height - 50:  # 50px margin
                logger.info("Near bottom of page at position %dpx", new_position)
                is_last_viewport = True
                reached_bottom = True
            else:
                is_last_viewport = False
                reached_bottom = False
                
            logger.info("Scrolled to position: %dpx", new_position)
            
            return {
                "scroll_action": "scrolled",
                "viewport_height": viewport_height,
                "current_position": new_position, 
                "is_last_viewport": is_last_viewport,
                "reached_bottom": reached_bottom,
                "page_height": new_page_height
            }
            
        except Exception as e:
            logger.error("Error scrolling to next viewport: %s", str(e))
            return {
                "scroll_action": "error",
                "error": str(e)
            } 