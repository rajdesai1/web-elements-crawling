# New Tab and Popup Window Handling

This document explains how to use the new tab and popup window handling features in the crawler.

## Overview

When interacting with web pages, often clicking on links or buttons will open new tabs or popup windows. The crawler now has the ability to:

1. Detect when new tabs/windows are opened
2. Capture data from these new tabs (screenshots, HTML, URLs, etc.)
3. Close these tabs and return to the original page
4. Track the relationship between the original page and new tabs

## How It Works

The system works by setting up event listeners on the browser context to detect when new pages are created. When a new page is detected, the system can execute custom logic to process it.

## Methods Available

The following methods are available in the `BrowserManager` class:

### `set_up_new_page_listener(original_page, callback)`

Sets up a listener for new pages that might open from interactions with the original page.

```python
async def my_callback(original_page, new_page):
    # Do something with the new page
    print(f"New page opened with URL: {new_page.url}")
    # Take a screenshot
    await new_page.screenshot(path="new_page.png")
    # Close the new page
    await new_page.close()

# Set up the listener
await browser_manager.set_up_new_page_listener(page, my_callback)
```

### `handle_new_page(original_page, new_page, capture_data=True, close_after=True)`

Handles a new page by capturing its data and optionally closing it.

```python
# Process a new page and get data from it
data = await browser_manager.handle_new_page(original_page, new_page)
print(f"Captured URL: {data['url']}")
print(f"Page title: {data['title']}")
```

### `detect_popup_windows(page, action_timeout=5000)`

Detects popup windows that might appear after an action on a page.

```python
# Start tracking for popups
popup_task = asyncio.create_task(browser_manager.detect_popup_windows(page))

# Perform an action that might open a popup
await page.click("button#open-popup")

# Wait for popups to be detected
new_pages = await popup_task

# Process each popup
for popup in new_pages:
    data = await browser_manager.handle_new_page(page, popup)
    print(f"Processed popup: {data['url']}")
```

## Example Implementation in Extension Crawler

The `ExtensionCrawler.interact_with_clickable_elements` method has been enhanced to handle new tabs that open after clicking elements:

1. It sets up an event listener before clicking
2. After clicking, it checks if a new page was detected
3. If a new page is found, it processes the page:
   - Takes a screenshot
   - Extracts URLs and interactive elements
   - Saves the HTML
   - Closes the tab
4. Then it returns to the original page

## How to Run the Demo

To see the new tab handling in action, run the example script:

```bash
python3 examples/new_tab_handling_demo.py
```

This will:
1. Open a page
2. Create test elements that open new tabs/popups
3. Demonstrate the different methods for handling new tabs
4. Save screenshots of the new tabs

## Integration with Existing Workflows

To use new tab handling in your own code:

```python
# Initialize the browser manager
browser_manager = BrowserManager()
await browser_manager.init()

# Create a page
page = await browser_manager.new_page()

# Navigate to a URL
await browser_manager.navigate("https://example.com")

# Set up new page listener with your custom callback
await browser_manager.set_up_new_page_listener(page, my_callback_function)

# ... interact with the page ...
```

## Tips

- Always make sure to close new tabs after you're done with them to avoid memory leaks
- Use the `_opened_from` attribute on new pages to track which page opened them
- You can access properties like `page._page_id` to identify original pages
- When extracting data from new tabs, watch out for cross-origin restrictions 