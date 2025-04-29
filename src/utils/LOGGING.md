# Logging Best Practices

This document outlines the logging best practices for the TRANCE web crawler project.

## Getting Started

### Basic Logger Setup

Always set up a logger at the top of your module:

```python
from src.utils.logger import setup_logger

# At the top of your module
logger = setup_logger(__name__)
```

### Using Context-Aware Logging

For components that need to include context (like worker_id, URL, domain):

```python
from src.utils.logger import setup_logger

# With static context
logger = setup_logger(__name__, context={"worker_id": worker_id})

# Adding dynamic context later
from src.utils.logger import get_logger_with_context
url_logger = get_logger_with_context(logger, url=url, domain=domain)
```

## Choosing the Right Log Level

Use the appropriate log level for your messages:

| Level | Use Case |
|-------|----------|
| `DEBUG` | Detailed information, typically of interest only when diagnosing problems |
| `INFO` | Confirmation that things are working as expected |
| `WARNING` | An indication that something unexpected happened, or may happen in the near future |
| `ERROR` | Due to a more serious problem, the software was not able to perform a function |
| `CRITICAL` | A serious error, indicating that the program itself may be unable to continue running |

## Message Formatting

### DO:

- Use lazy % formatting: `logger.info("Processing URL: %s", url)`
- Include relevant context: `logger.error("Failed to fetch %s: %s", url, str(error))`
- Be specific and actionable: `logger.warning("Rate limit reached (%d requests/min), backing off for %d seconds", rate, backoff_time)`
- Include numeric values when relevant: `logger.info("Processed %d elements in %0.2f seconds", count, elapsed_time)`

### DON'T:

- Use string concatenation: ❌ `logger.info("Processing URL: " + url)`
- Use f-strings: ❌ `logger.info(f"Processing URL: {url}")`
- Log sensitive information: ❌ `logger.debug("Password: %s", password)`
- Be vague: ❌ `logger.error("Something went wrong")`

## Common Logging Patterns

### Function Entry/Exit

```python
def process_domain(domain, options):
    logger.debug("Entering process_domain with domain=%s, options=%s", domain, options)
    try:
        # Function body
        result = do_something()
        logger.debug("Exiting process_domain with result: %s", result)
        return result
    except Exception as e:
        logger.error("Error in process_domain: %s", e, exc_info=True)
        raise
```

### HTTP Requests/Responses

```python
logger.info("Sending request to %s", url)
try:
    response = await fetch_url(url)
    logger.debug("Received response from %s: status=%d, size=%d bytes", 
                url, response.status, len(response.content))
except Exception as e:
    logger.error("Failed to fetch %s: %s", url, str(e))
```

### Performance Tracking

```python
start_time = time.time()
logger.info("Starting processing of %s", task_name)
# Do work
elapsed = time.time() - start_time
logger.info("Completed %s in %.2f seconds", task_name, elapsed)
```

## Contextual Logging

Use context to trace operations across multiple functions:

```python
# In the domain processing function
domain_logger = get_logger_with_context(logger, domain=domain)
domain_logger.info("Starting domain processing")

# In a URL processing function called from domain processing
url_logger = get_logger_with_context(domain_logger, url=url)
url_logger.info("Processing URL")
```

## Error Handling

Always include detailed error information:

```python
try:
    # Code that might fail
except Exception as e:
    logger.error("Failed to process %s: %s", item, str(e), exc_info=True)
    # Handle or re-raise the exception
```

## Configuration

Logging configuration is managed in `src/config/settings.py`. You can adjust:

- `LOG_LEVEL`: The default logging level
- `LOG_FORMAT_CONSOLE`: Format for console logs
- `LOG_FORMAT_FILE`: Format for file logs
- `LOG_LEVELS`: Component-specific log levels

## Best Practices Summary

1. **Always use the logger** instead of print statements
2. **Choose the appropriate log level** for each message
3. **Use lazy % formatting** for performance and security
4. **Include relevant context** in your log messages
5. **Be specific and actionable** with your messages
6. **Use context adapters** to trace operations across functions
7. **Add timing information** for performance-critical operations 