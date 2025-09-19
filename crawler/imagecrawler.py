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

# --- SỬA LỖI ĐƯỜNG DẪN TRIỆT ĐỂ ---
# Lấy đường dẫn của chính file script này
SCRIPT_PATH = os.path.abspath(__file__)
# Lấy đường dẫn của thư mục chứa file script này (crawler/)
CRAWLER_DIR = os.path.dirname(SCRIPT_PATH)
# Lấy đường dẫn thư mục gốc của dự án (cao hơn một cấp so với crawler/)
BASE_DIR = os.path.dirname(CRAWLER_DIR)

# Các đường dẫn khác giờ đây sẽ được tính toán chính xác
DOMAIN_DIR = os.path.join(BASE_DIR, 'domain')
CONFIG_FILE = os.path.join(CRAWLER_DIR, 'config.json')
STOP_URLS_FILE = os.path.join(BASE_DIR, 'stop_urls.txt')
LOG_FILE = os.path.join(BASE_DIR, 'imagecrawler.log')
ENV_FILE = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_FILE)

# --- Constants (Giữ nguyên) ---
MAX_URLS = 700
MAX_PREVNEXT_URLS = 200
MAX_API_PAGES = 1
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/chanktb/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# --- Cache để tối ưu hóa việc kiểm tra URL ---
URL_METADATA_CACHE = {}

# ----------------------------------------------------------------------------------------------------------------------
# Hệ thống kiểm tra URL và Lọc ảnh cũ
# ----------------------------------------------------------------------------------------------------------------------

def get_url_metadata(url):
    if not url or not url.startswith('http'): return {'status': 0, 'is_recent': False}
    if url in URL_METADATA_CACHE: return URL_METADATA_CACHE[url]
    default_response = {'status': 0, 'is_recent': False}
    try:
        with requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True) as r:
            if r.status_code != 200:
                URL_METADATA_CACHE[url] = default_response; return default_response
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
            URL_METADATA_CACHE[url] = metadata; return metadata
    except (requests.exceptions.RequestException, parser.ParserError, ValueError):
        URL_METADATA_CACHE[url] = default_response; return default_response

def check_url_exists(url):
    return get_url_metadata(url)['status'] == 200

def is_image_recent(url):
    metadata = get_url_metadata(url)
    return metadata['status'] == 200 and metadata['is_recent']

# ----------------------------------------------------------------------------------------------------------------------
# Các hàm gốc của bạn (không thay đổi logic)
# ----------------------------------------------------------------------------------------------------------------------
def send_telegram_message(message):
    bot_token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id: return
    try: requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data={'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}, timeout=10)
    except requests.exceptions.RequestException: pass

def git_push_changes():
    if os.getenv('GITHUB_ACTIONS') == 'true': return
    try:
        os.chdir(BASE_DIR)
        subprocess.run(['git', 'config', 'user.name', 'ktbihow'], check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', '230660483+ktbihow@users.noreply.github.com'], check=True, capture_output=True)
        subprocess.run(['git', 'add', 'domain/', 'stop_urls.txt', 'imagecrawler.log'], check=True, capture_output=True)
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status_result.stdout.strip(): return
        commit_message = f"Auto-update crawled data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_message], check=True, capture_output=True)
        subprocess.run(['git', 'push'], check=True, capture_output=True)
    except Exception: pass

def trigger_workflow_dispatch():
    pat = os.getenv('KTBHUB_PAT')
    if not pat: return
    try: requests.post(f"https://api.github.com/repos/ktbhub/ktb-image/dispatches", headers={"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {pat}"}, json={"event_type": "new_image_available"}, timeout=15)
    except requests.exceptions.RequestException: pass

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError: print(f"LỖI: Không tìm thấy file config tại: {CONFIG_FILE}"); return []

def load_stop_urls():
    print(f"Đang tải stop URLs từ: {STOP_URLS_FILE}")
    try:
        with open(STOP_URLS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print("Tải file stop_urls.txt thành công.")
            return data
    except FileNotFoundError:
        print("CẢNH BÁO: Không tìm thấy file stop_urls.txt. Sẽ chạy mà không có điểm dừng.")
        return {}
    except json.JSONDecodeError:
        print("LỖI: File stop_urls.txt bị lỗi định dạng JSON.")
        return {}

def apply_replacements(image_url, replacements, always_replace=False):
    if not image_url: return image_url
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    if always_replace or check_url_exists(new_url): return new_url
    return image_url

def apply_fallback_logic(image_url, url_data):
    if not image_url: return image_url
    fallback_rules = url_data.get('fallback_rules', {})
    if not fallback_rules or fallback_rules.get('type') != 'cut_filename_prefix': return image_url
    parsed_url = urlparse(image_url)
    if parsed_url.netloc != fallback_rules.get('domain'): return image_url
    path_parts = parsed_url.path.split('/')
    filename = path_parts[-1]
    prefix_length = fallback_rules.get('prefix_length', 0)
    if len(filename) > prefix_length and filename[prefix_length - 1] == '-':
        if re.match(r'^[a-zA-Z0-9_-]+$', filename[:prefix_length-1]):
            new_filename = filename[prefix_length:]
            new_path = '/'.join(path_parts[:-1] + [new_filename])
            modified_url = parsed_url._replace(path=new_path).geturl()
            if check_url_exists(modified_url): return modified_url
    return image_url

def find_best_image_url(soup, url_data):
    base_url = url_data.get('url', '')
    # ... (Giữ nguyên hàm gốc)
    return None

def save_urls(domain, new_urls):
    if not os.path.exists(DOMAIN_DIR): os.makedirs(DOMAIN_DIR)
    filename = os.path.join(DOMAIN_DIR, f"{domain}.txt")
    try:
        with open(filename, "r", encoding="utf-8") as f: existing_urls = [line.strip() for line in f]
    except FileNotFoundError: existing_urls = []
    unique_new_urls = [u for u in new_urls if u not in existing_urls]
    all_urls = (unique_new_urls + existing_urls)[:MAX_URLS]
    with open(filename, "w", encoding="utf-8") as f: f.write("\n".join(all_urls))
    return len(unique_new_urls), len(all_urls)

def fetch_image_urls_from_api(url_data, stop_urls_list):
    # Giữ nguyên hàm gốc
    all_image_urls, new_product_urls_found, page, domain = [], [], 1, urlparse(url_data['url']).netloc
    while page <= MAX_API_PAGES:
        #...
        pass # Placeholder
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_prevnext(url_data, stop_urls_list):
    # Giữ nguyên hàm gốc
    all_image_urls, new_product_urls_found = [], []
    #...
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_product_list(url_data, stop_urls_list):
    # Giữ nguyên hàm gốc
    all_image_urls, new_product_urls_found, domain = [], [], urlparse(url_data['url']).netloc
    repo_file_url = REPO_URL_PATTERN.format(domain=domain)
    try:
        r = requests.get(repo_file_url, headers=HEADERS, timeout=30); r.raise_for_status()
        product_urls = [line.strip() for line in r.text.splitlines() if line.strip()]
    except requests.exceptions.RequestException: return [], []
    
    urls_to_crawl = []
    if stop_urls_list:
        found_stop_point = False
        for product_url in product_urls:
            if product_url in stop_urls_list:
                print(f"[{domain}] Dừng product-list vì gặp stop URL: {product_url}")
                found_stop_point = True; break
            urls_to_crawl.append(product_url)
        if not found_stop_point: urls_to_crawl = product_urls
    else: urls_to_crawl = product_urls

    for product_url in urls_to_crawl:
        if len(all_image_urls) >= MAX_PREVNEXT_URLS: break
        try:
            r = requests.get(product_url, headers=HEADERS, timeout=30); r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = apply_fallback_logic(best_url, url_data)
                if final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(product_url)
        except requests.exceptions.RequestException: continue
    return all_image_urls, new_product_urls_found

# ----------------------------------------------------------------------------------------------------------------------
# Main Execution (Cấu trúc gốc của bạn + Logic sàng lọc mới)
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    start_time = time.time()
    configs = load_config()
    stop_urls_data = load_stop_urls()
    urls_summary = {}

    for url_data in configs:
        domain = urlparse(url_data['url']).netloc
        source_type = url_data.get('source_type')
        
        unfiltered_image_urls, new_product_urls_found = [], []
        domain_stop_urls_list = set(stop_urls_data.get(domain, []))

        print(f"\n--- Bắt đầu xử lý domain: {domain} ---")
        print(f"Số lượng stop URLs đã tải cho domain này: {len(domain_stop_urls_list)}")

        if source_type == 'api':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_api(url_data, domain_stop_urls_list)
        elif source_type == 'prevnext':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_prevnext(url_data, domain_stop_urls_list)
        elif source_type == 'product-list':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_product_list(url_data, domain_stop_urls_list)
        
        final_image_urls = []
        if url_data.get("check_recency", False):
            print(f"[{domain}] Sàng lọc {len(unfiltered_image_urls)} URLs để lấy ảnh mới...")
            for img_url in unfiltered_image_urls:
                if is_image_recent(img_url): final_image_urls.append(img_url)
        else:
            final_image_urls = unfiltered_image_urls
        
        new_urls_count, total_urls_count = save_urls(domain, final_image_urls)
        urls_summary[domain] = {'new_count': new_urls_count, 'total_count': total_urls_count}
        
        if new_product_urls_found:
            stop_urls_data[domain] = new_product_urls_found[:STOP_URLS_COUNT]
    
    save_stop_urls(stop_urls_data)

    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now_vietnam = datetime.now(vietnam_tz)
    end_time = time.time()
    duration = end_time - start_time
    minutes, seconds = int(duration // 60), int(duration % 60)
    formatted_duration = f"{minutes} min {seconds} seconds"
    log_lines = ["--- Summary of Last Image Crawl ---", f"Generated at: {now_vietnam.strftime('%Y-%m-%d %H:%M:%S %z')}"]
    
    for domain, counts in urls_summary.items():
        log_lines.append(f"{domain}: {counts['new_count']} New Images: {counts['total_count']}")
    log_lines.append(f"Crawl duration: {formatted_duration}.")
    
    with open(LOG_FILE, "w", encoding="utf-8") as f: f.write("\n".join(log_lines))

    found_new_images = any(c['new_count'] > 0 for c in urls_summary.values())
    if found_new_images:
        filtered_domain_lines = [line for line in log_lines if "New Images: 0" not in line]
        send_telegram_message("\n".join(filtered_domain_lines))
        trigger_workflow_dispatch()
    
    git_push_changes()
