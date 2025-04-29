# TRANCE Web Crawler

TRANCE (TRacking And Navigating Content Elements) is an advanced web crawler designed to detect and interact with interactive elements on web pages. It uses Chrome with browser extensions to analyze web content and build a dataset of interactive elements for further processing.

## Features

- **Interactive Element Detection**: Automatically identifies clickable elements, forms, and other interactive page components
- **Intelligent Form Filling**: Contextually aware form filling with region-specific data (India, USA)
- **Multi-domain Support**: Process multiple domains concurrently
- **MongoDB Integration**: Store crawling results in MongoDB for further analysis
- **Screenshot Capture**: High-quality screenshots of pages and interactions
- **Adaptive Scrolling**: Smart scrolling to reveal all page content
- **Chrome Extension Support**: Uses custom Chrome extensions for enhanced detection

## Installation

### Prerequisites

- Python 3.8 or higher
- Chrome browser
- MongoDB (local or remote)

### Setup

1. Clone the repository:
   ```
   git clone [repository-url]
   cd elements_crawling
   ```

2. Create and activate a virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install required packages:
   ```
   pip install -r requirements.txt
   ```

4. Install Playwright browsers:
   ```
   python -m playwright install chrome
   ```

## Configuration

The main configuration is located in `src/config/settings.py`. Key configuration options include:

- `DATA_DIR`: Base directory for storing crawl data
- `EXTENSION_PATH`: Path to the Chrome extension
- `BROWSER_SETTINGS`: Browser configuration (viewport size, headless mode, etc.)
- `CONCURRENT_DOMAINS`: Number of domains to process concurrently
- `DOMAIN_MAX_URLS_PER_SESSION`: Maximum URLs to process per domain
- `MONGODB_URI`: MongoDB connection string
- `FORM_DATA_REGION`: Region for form data generation ("india", "usa")

## Usage

### Basic Usage

Run the crawler with default settings:

```bash
python3 main.py
```

### MongoDB Setup

The crawler requires MongoDB for storing URLs and crawl results. Ensure your MongoDB instance is running and accessible. The connection string can be configured in `src/config/settings.py`.

### Custom Form Data

You can customize the form filling behavior by modifying the `FormDataManager` in `src/crawler/form_data_manager.py` or by providing custom profiles.

## Project Structure

```
elements_crawling/
├── data/                  # Data storage directory
├── chrome_extension/      # Chrome extension for element detection
├── main.py                # Main entry point
├── requirements.txt       # Python dependencies
├── src/
│   ├── config/            # Configuration files
│   ├── crawler/           # Core crawler logic
│   │   ├── browser_manager.py         # Browser control
│   │   ├── extension_crawler.py       # Extension-based crawler
│   │   └── form_data_manager.py       # Smart form filling
│   ├── storage/           # Storage management
│   └── utils/             # Utility functions
│       ├── logger.py                  # Logging configuration
│       └── mongodb_queue.py           # MongoDB queue management
└── tests/                 # Test cases
```

## How It Works

1. The crawler starts by claiming domains from MongoDB
2. For each domain, it processes URLs in batches
3. Each URL is loaded in a Chrome browser with the extension
4. The extension detects interactive elements on the page
5. The crawler interacts with elements based on configured rules
6. Results are stored in MongoDB and the local filesystem
7. New URLs discovered during crawling are added to the queue

## Troubleshooting

### Common Issues

- **MongoDB Connection**: Ensure MongoDB is running and the connection string is correct
- **Chrome Extension**: Check that the extension path is properly configured 
- **Permission Issues**: Ensure the data directory is writable

### Logs

Logs are stored in the `data/logs` directory by default. Check these for debugging information.

## License

[License information]

## Contributing

[Contribution guidelines] 