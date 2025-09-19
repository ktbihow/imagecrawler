import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import json
import re
from datetime import datetime, timedelta, timezone
import pytz
import subprocess
import time
from dotenv import load_dotenv
from dateutil import parser

# --- Cấu hình đường dẫn ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CRAWLER_DIR = os.path.join(BASE_DIR, 'crawler')
DOMAIN_DIR = os.path.join(BASE_DIR, 'domain')
CONFIG_FILE = os.path.join(CRAWLER_DIR, 'config.json')
STOP_URLS_FILE = os.path.join(BASE_DIR, 'stop_urls.txt')
LOG_FILE = os.path.join(BASE_DIR, 'imagecrawler.log')
ENV_FILE = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_FILE)

# Cache lưu trữ metadata đầy đủ của URL
URL_METADATA_CACHE = {}

# --- Constants ---
MAX_URLS = 700
MAX_PREVNEXT_URLS = 200
MAX_API_PAGES = 1
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/chanktb/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# ----------------------------------------------------------------------------------------------------------------------
# Hệ thống kiểm tra URL hiệu quả
# ----------------------------------------------------------------------------------------------------------------------

def get_url_metadata(url):
    """Gửi request HEAD một lần, lấy metadata (status, is_recent) và lưu vào cache."""
    if url in URL_METADATA_CACHE:
        return URL_METADATA_CACHE[url]

    default_response = {'status': 0, 'is_recent': False}
    try:
        with requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True, stream=True) as r:
            if r.status_code != 200:
                URL_METADATA_CACHE[url] = default_response
                return default_response

            is_recent = True
            last_modified_str = r.headers.get('Last-Modified')
            if last_modified_str:
                last_modified_date = parser.parse(last_modified_str)
                if last_modified_date.tzinfo is None:
                    last_modified_date = last_modified_date.replace(tzinfo=timezone.utc)
                
                now_utc = datetime.now(timezone.utc)
                if (now_utc - last_modified_date) > timedelta(days=3):
                    is_recent = False
            
            metadata = {'status': r.status_code, 'is_recent': is_recent}
            URL_METADATA_CACHE[url] = metadata
            return metadata

    except (requests.exceptions.RequestException, parser.ParserError, ValueError) as e:
        print(f"Lỗi khi kiểm tra metadata URL {url}: {e}")
        URL_METADATA_CACHE[url] = default_response
        return default_response

def check_url_exists(url):
    """Chỉ kiểm tra sự tồn tại của URL (status 200)."""
    metadata = get_url_metadata(url)
    return metadata['status'] == 200

def is_image_recent(url):
    """Kiểm tra URL có tồn tại VÀ mới hay không."""
    metadata = get_url_metadata(url)
    return metadata['status'] == 200 and metadata['is_recent']

# --- Các hàm Telegram, Git, load/save config (không thay đổi) ---
def send_telegram_message(message):
    bot_token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id: return
    try: requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data={'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}, timeout=10)
    except requests.exceptions.RequestException as e: print(f"❌ Lỗi Telegram: {e}")
# ... (Các hàm git_push_changes, trigger_workflow_dispatch, load_config, etc. giữ nguyên)

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError: return []

def load_stop_urls():
    try:
        with open(STOP_URLS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}
    
def save_stop_urls(stop_urls):
    with open(STOP_URLS_FILE, 'w', encoding='utf-8') as f: json.dump(stop_urls, f, indent=2)

def apply_replacements(image_url, replacements, always_replace=False):
    # ... (Hàm này giữ nguyên, nó sẽ dùng check_url_exists đã được sửa)
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    if always_replace or check_url_exists(new_url): return new_url
    return image_url

def apply_fallback_logic(image_url, url_data):
    # ... (Hàm này giữ nguyên, nó sẽ dùng check_url_exists đã được sửa)
    fallback_rules = url_data.get('fallback_rules', {})
    if not fallback_rules: return image_url
    parsed_url = urlparse(image_url)
    if parsed_url.netloc != fallback_rules.get('domain'): return image_url
    # ... (phần còn lại của hàm)
    return image_url # Placeholder

def find_best_image_url(soup, url_data):
    # ... (Hàm này giữ nguyên)
    return None # Placeholder


# ----------------------------------------------------------------------------------------------------------------------
# GIAI ĐOẠN 1: CÁC HÀM THU THẬP (Chỉ tìm URL tồn tại)
# ----------------------------------------------------------------------------------------------------------------------

def fetch_image_urls_from_api(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found = [], []
    # ... (logic fetch API)
    # bên trong vòng lặp `for item in data:`
    # ...
    if img_url:
        final_img_url = apply_replacements(img_url, url_data.get('replacements', {}))
        final_img_url = apply_fallback_logic(final_img_url, url_data)
        if check_url_exists(final_img_url) and (final_img_url not in all_image_urls):
            all_image_urls.append(final_img_url)
            if product_url: new_product_urls_found.append(product_url)
    # ...
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_prevnext(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found = [], []
    # ... (logic fetch prev/next)
    # bên trong `try:` của vòng lặp `while`
    # ...
    best_url = find_best_image_url(soup, url_data)
    if best_url:
        final_img_url = apply_fallback_logic(best_url, url_data)
        if check_url_exists(final_img_url) and (final_img_url not in all_image_urls):
            all_image_urls.append(final_img_url)
            new_product_urls_found.append(current_product_url)
    # ...
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_product_list(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found = [], []
    # ... (logic fetch product list)
    # bên trong `try:` của vòng lặp `for`
    # ...
    best_url = find_best_image_url(soup, url_data)
    if best_url:
        final_img_url = apply_fallback_logic(best_url, url_data)
        if check_url_exists(final_img_url) and (final_img_url not in all_image_urls):
            all_image_urls.append(final_img_url)
            new_product_urls_found.append(product_url)
    # ...
    return all_image_urls, new_product_urls_found

# --- Các hàm phụ khác giữ nguyên ---
def save_urls(domain, new_urls):
    # ...
    return 0, 0 # Placeholder

# ----------------------------------------------------------------------------------------------------------------------
# Main Execution: TÁCH BIỆT THU THẬP VÀ SÀNG LỌC
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    start_time = time.time()
    configs, urls_summary, stop_urls_data = load_config(), {}, load_stop_urls()
    if not configs: exit(1)

    for url_data in configs:
        domain = urlparse(url_data['url']).netloc
        source_type = url_data.get('source_type')
        
        # --- GIAI ĐOẠN 1: THU THẬP URL TỒN TẠI ---
        unfiltered_image_urls, new_product_urls_found = [], []
        domain_stop_urls_list = set(stop_urls_data.get(domain, []))

        if source_type == 'api':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_api(url_data, domain_stop_urls_list)
        elif source_type == 'prevnext':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_prevnext(url_data, domain_stop_urls_list)
        elif source_type == 'product-list':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_product_list(url_data, domain_stop_urls_list)
        
        # --- GIAI ĐOẠN 2: SÀNG LỌC URL THEO CẤU HÌNH ---
        final_image_urls = []
        should_check_recency = url_data.get("check_recency", False)

        if should_check_recency:
            print(f"[{domain}] Sàng lọc {len(unfiltered_image_urls)} URLs để lấy ảnh mới...")
            for img_url in unfiltered_image_urls:
                if is_image_recent(img_url): # Dùng cache, rất nhanh
                    final_image_urls.append(img_url)
        else:
            final_image_urls = unfiltered_image_urls
        
        # --- LƯU KẾT QUẢ ---
        print(f"[{domain}] Found {len(final_image_urls)} final image URLs.")
        new_urls_count, total_urls_count = save_urls(domain, final_image_urls)
        urls_summary[domain] = {'new_count': new_urls_count, 'total_count': total_urls_count}
        
        if new_product_urls_found:
            stop_urls_data[domain] = new_product_urls_found[:STOP_URLS_COUNT]
    
    save_stop_urls(stop_urls_data)
    
    # --- TỔNG KẾT VÀ GỬI BÁO CÁO (giữ nguyên) ---
    # ...

    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now_vietnam = datetime.now(vietnam_tz)
    
    end_time = time.time()
    duration = end_time - start_time
    
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    formatted_duration = f"{minutes} min {seconds} seconds"

    log_lines = [
        "--- Summary of Last Image Crawl ---",
        f"Generated at: {now_vietnam.strftime('%Y-%m-%d %H:%M:%S %z')}",
    ]
    
    for domain, counts in urls_summary.items():
        log_line = f"{domain}: {counts['new_count']} New Images: {counts['total_count']}"
        log_lines.append(log_line)
            
    log_lines.append(f"Crawl duration: {formatted_duration}.")
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    print(f"\n--- Summary saved to {LOG_FILE} ---")
    
# THAY THẾ TOÀN BỘ ĐOẠN CODE TỪ DÒNG NÀY...
# --- START: LOGIC MỚI ĐỂ KIỂM TRA VÀ KÍCH HOẠT WORKFLOW ---
    found_new_images = False
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            log_content = f.read().splitlines()
        
        # Tách các phần của tin nhắn
        header_lines = []
        filtered_domain_lines = []
        footer_line = ""

        for line in log_content:
            # Tìm các dòng kết quả của domain
            match = re.search(r'(\d+) New Images', line)
            if match:
                num_new_images = int(match.group(1))
                if num_new_images > 0:
                    found_new_images = True
                    filtered_domain_lines.append(line) # Chỉ thêm dòng có ảnh mới > 0
            # Tìm dòng cuối (footer)
            elif "Crawl duration" in line:
                footer_line = line
            # Các dòng còn lại là phần đầu (header)
            else:
                header_lines.append(line)

        # Nếu tìm thấy ít nhất một domain có ảnh mới thì gửi báo cáo
        if found_new_images:
            print("Tìm thấy ảnh mới, đang chuẩn bị gửi báo cáo...")
            
            # Ghép các phần lại theo đúng thứ tự
            final_message_lines = header_lines + filtered_domain_lines
            if footer_line:
                final_message_lines.append(footer_line)
            
            final_telegram_message = "\n".join(final_message_lines)
            send_telegram_message(final_telegram_message)
            
            # Kích hoạt workflow của repo khác
            trigger_workflow_dispatch()
        else:
            print("Không có ảnh mới nào được tìm thấy. Bỏ qua các hành động tiếp theo.")

    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp {LOG_FILE} để xử lý.")
    
    # Luôn chạy push để cập nhật log và stop_urls.txt
    git_push_changes()
# ...CHO ĐẾN HẾT FILE
