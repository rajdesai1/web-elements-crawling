"""
Centralized settings file for the TRANCE web crawler application.
All configuration parameters should be defined here.
"""
import os
import uuid
from pathlib import Path

#################################################
# System and Path Configuration
#################################################

# Base directory for the project (automatically determined)
ROOT_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Chrome extension path
EXTENSION_PATH = ROOT_DIR / "chrome_extension"

#################################################
# Data Storage Settings
#################################################

# Base directories for storing various data
DATA_DIR = Path('data_new_testing')  # Base directory for storing crawl data
LOGS_DIR = DATA_DIR / 'logs'  # Directory for logs
SITEMAPS_DIR = DATA_DIR / 'sitemaps'  # Directory for sitemap data

# Create directories if they don't exist
for directory in [DATA_DIR, LOGS_DIR, SITEMAPS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

#################################################
# Crawler Configuration
#################################################

# Browser settings
BROWSER_SETTINGS = {
    "viewport": {"width": 1366, "height": 768},
    "device_scale_factor": 2,
    "headless": False,
    "extension_path": str(EXTENSION_PATH)
}

# Worker settings
WORKER_ID_PREFIX = "worker"  # Prefix for worker IDs
DEFAULT_WORKER_ID = f"{WORKER_ID_PREFIX}-{str(uuid.uuid4())[:8]}"  # Default worker ID
CONCURRENT_DOMAINS = 2  # Number of domains to process concurrently
URL_BATCH_SIZE = 10  # Number of URLs to process in a batch

# Crawler behavior settings
MAX_RETRIES = 3  # Maximum number of retries for failed URLs
REQUEST_TIMEOUT = 60  # Timeout for HTTP requests in seconds
DOMAIN_MAX_URLS_PER_SESSION = 100  # Maximum URLs to process per domain
DOMAIN_MAX_CONCURRENT_URLS = 5  # Maximum concurrent URLs per domain

# Viewport crawling settings
MAX_VIEWPORTS_PER_URL = 9  # Maximum number of viewports to process per URL
VIEWPORT_SCREENSHOT_QUALITY = 80  # Quality of viewport screenshots (1-100)

# Interaction limits
MAX_INTERACTIONS_PER_URL = 20  # Maximum total interactions per URL
MAX_CLICK_INTERACTIONS_PER_URL = 10  # Maximum click interactions per URL
MAX_FORM_INTERACTIONS_PER_URL = 10  # Maximum form interactions per URL

# Domain time limit settings
DOMAIN_TIME_LIMIT_SECONDS = 540  # Maximum time to spend processing a domain (540 seconds = 9 minutes)

# Navigation handling
MAX_REDIRECTS_PER_INTERACTION = 3  # Maximum number of redirects to follow per interaction
REDIRECT_TIMEOUT_MS = 5000  # Maximum time to wait for a redirect to complete
RETURN_TO_ORIGINAL_URL = True  # Whether to return to original URL after redirect

# URL processing timeout setting
URL_PROCESSING_TIMEOUT_SECONDS = 240  # Maximum time to spend processing a single URL (240 seconds = 4 minutes)

#################################################
# Form Filling Settings
#################################################

# Form data configuration
FORM_DATA_VARIETY = 2  # 1=minimal, 2=medium, 3=extensive variation in form data
FORM_DATA_REGION = "india"  # Region to use for form data (india, global)
PROFILES_FILE = None  # Path to JSON file with form filling profiles

#################################################
# Redis Connection Settings
#################################################

# # Redis connection parameters
# REDIS_CONFIG = {
#     'host': '<redis-host>',
#     'port': <redis-port>,
#     'decode_responses': True,
#     'username': "<redis-username>",
#     'password': "<redis-password>",
# }

# # Domain-specific Redis keys
# DOMAINS_SET_KEY = "domains:all"              # Set of all domains
# DOMAIN_STATUS_PREFIX = "domain:status:"      # Current status of a domain
# DOMAIN_URLS_PREFIX = "domain:urls:"          # Hash of all URLs for a domain
# DOMAIN_CLAIMED_PREFIX = "domain:claimed:"    # Claim information for a domain
# DOMAIN_COMPLETED_PREFIX = "domain:completed:" # Completion metadata for a domain
# DOMAIN_WORKER_PREFIX = "domain:worker:"      # Worker ID currently processing a domain
# DOMAIN_WORKER_HEARTBEAT_PREFIX = "domain:worker:heartbeat:" # Last heartbeat timestamp

# # URL Queue Redis keys
# QUEUE_KEY = 'crawler:urls:queue'          # URLs waiting to be processed
# PROCESSING_KEY = 'crawler:urls:processing' # URLs currently being processed
# COMPLETED_KEY = 'crawler:urls:completed'   # Successfully processed URLs
# FAILED_KEY = 'crawler:urls:failed'         # Failed URLs with error information

# # Domain crawler timing settings
# DOMAIN_HEARTBEAT_INTERVAL = 30  # Seconds between worker heartbeats
# DOMAIN_HEARTBEAT_TIMEOUT = 180  # Seconds before a worker is considered dead
# BATCH_SIZE = 10  # Number of URLs to pull at once

#################################################
# MongoDB Connection Settings
#################################################

# MongoDB connection parameters
MONGODB_URI = "<mongodb_uri>"
MONGODB_DB_NAME = "<mongodb_db_name>"
MONGODB_DOMAINS_COLLECTION = "<mongodb_domains_collection>"
MONGODB_URLS_COLLECTION = "<mongodb_urls_collection>"

#################################################
# Status Constants
#################################################

# Status values for domains and URLs
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

#################################################
# Sitemap Crawler Settings
#################################################

# # Sitemap crawler configuration
# SITEMAP_SETTINGS = {
#     "max_retries": 3,
#     "max_urls": 10000,
#     "max_workers": 5,
#     "timeout": 30,
#     "rate_limit_delay": 0.5
# }

#################################################
# Logging Configuration
#################################################

# Logging settings
LOG_LEVEL = "INFO"  # Default logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT_CONSOLE = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
LOG_FORMAT_FILE = "%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S" 