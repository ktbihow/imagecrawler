# utils/constants.py
import os

# --- Paths ---
# Xác định đường dẫn gốc của dự án một cách linh hoạt
# BASE_DIR sẽ là thư mục 'image-crawler-project'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOMAIN_DIR = os.path.join(BASE_DIR, 'domain')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
STOP_URLS_FILE = os.path.join(BASE_DIR, 'stop_urls.txt')
LOG_FILE = os.path.join(BASE_DIR, 'imagecrawler.log')
ENV_FILE = os.path.join(BASE_DIR, '.env')

# --- Constants ---
MAX_URLS = 500
MAX_PREVNEXT_URLS = 100
MAX_API_PAGES = 2
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/ktbteam/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# --- Cache ---
# Cache được quản lý trong module xử lý URL để tránh biến toàn cục
URL_METADATA_CACHE = {}