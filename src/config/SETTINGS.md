# TRANCE Crawler Settings Reference

This document provides a reference for the centralized settings system used in the TRANCE crawler.

## Settings Architecture

All settings for the TRANCE crawler are centralized in a single file: `src/config/settings.py`. This eliminates duplicate settings, ensures consistency, and makes configuration management easier.

## Key Principles

1. **Single Source of Truth**: All settings are defined in `settings.py`
2. **Default Values**: Components use default values from settings.py
3. **Hierarchical Settings**: Settings are grouped logically
4. **Explicit References**: Settings are referenced explicitly by name

## Key Setting Categories

### System and Path Configuration
- `ROOT_DIR`: Base directory for the project
- `EXTENSION_PATH`: Path to Chrome extension

### Data Storage Settings
- `DATA_DIR`: Base directory for storing crawl data
- Various subdirectories for specific data types

### Browser Settings
- `BROWSER_SETTINGS`: Dictionary containing browser configuration
  - `headless`: Whether to run in headless mode
  - `viewport`: Browser viewport size
  - Other browser-specific settings

### Worker Settings
- `DEFAULT_WORKER_ID`: Default worker identifier
- `CONCURRENT_DOMAINS`: Number of domains to process concurrently

### Crawler Behavior Settings
- `MAX_RETRIES`: Maximum retries for failed operations
- `REQUEST_TIMEOUT`: HTTP request timeout in seconds
- `DOMAIN_MAX_URLS_PER_SESSION`: Max URLs per domain session

### MongoDB Settings
- `MONGODB_URI`: Connection string for MongoDB
- Collection names and other MongoDB specifics

## How Settings Flow

The settings flow through the application as follows:

1. `settings.py` defines all settings
2. Classes import settings directly from `settings.py`
3. Classes use default parameter values from settings
4. `main.py` only passes non-default values

## Best Practices

When working with the settings system:

1. **Always add new settings to settings.py**, never hardcode values
2. **Use default parameter values** in class/function definitions
3. **Import settings directly** rather than passing them through functions
4. **Document new settings** with clear comments
5. **Group related settings** in the appropriate section

## Example Usage

```python
# In a module:
from src.config.settings import BROWSER_SETTINGS, REQUEST_TIMEOUT

# Use settings directly
timeout_ms = REQUEST_TIMEOUT * 1000
is_headless = BROWSER_SETTINGS["headless"]

# In a class, use as default parameter values
def __init__(self, headless=BROWSER_SETTINGS["headless"]):
    self.headless = headless
```

## Settings Verification

The `verify_settings()` function in `main.py` can be used to verify that critical settings are properly configured before starting the crawler. 