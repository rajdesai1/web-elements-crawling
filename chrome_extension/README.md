# DOM Tree Analyzer Chrome Extension

This extension injects the BuildDOMTree.js script into every webpage to enable DOM tree analysis. The script analyzes the DOM structure, identifies interactive elements, and provides detailed information about each element.

## Features

- Automatically injects DOM analyzer on page load
- Exposes a global `window.runDOMAnalysis()` function to trigger analysis on demand
- Highlights interactive elements in the DOM (can be toggled)
- Returns detailed information about DOM structure and interactive elements
- Works with iframes and shadow DOM

## Usage

### Manual Installation

1. Clone or download this repository
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable "Developer mode" (toggle in the top right)
4. Click "Load unpacked" button
5. Select the `chrome_extension` directory

### For Developers

The extension provides a global function `window.runDOMAnalysis()` that you can call from the developer console to run the DOM analysis and get the results.

```javascript
// Run the DOM analysis
const result = window.runDOMAnalysis();
console.log(result);
```

### With Python

The extension can be used with Python scripts using Playwright. Example:

```python
import asyncio
from playwright.async_api import async_playwright

async def run_with_extension(url):
    extension_path = "/path/to/chrome_extension"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Extensions don't work in headless mode
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}"
            ]
        )
        
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto(url)
        await page.wait_for_timeout(2000)
        
        # Run the DOM analysis
        result = await page.evaluate("window.runDOMAnalysis()")
        print(result)
        
        await browser.close()

asyncio.run(run_with_extension("https://example.com"))
```

## Extending the Script

To extend or modify the capabilities of the BuildDOMTree.js script:

1. Edit the `buildDOMTree.js` file in the extension directory
2. Add your custom functions and analysis logic
3. Update the `window.runDOMAnalysis()` function in `content.js` if needed
4. Reload the extension in Chrome 