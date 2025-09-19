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

# --- Cấu hình đường dẫn (Lấy từ code gốc của bạn) ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CRAWLER_DIR = os.path.join(BASE_DIR, 'crawler')
DOMAIN_DIR = os.path.join(BASE_DIR, 'domain')
CONFIG_FILE = os.path.join(CRAWLER_DIR, 'config.json')
STOP_URLS_FILE = os.path.join(BASE_DIR, 'stop_urls.txt')
LOG_FILE = os.path.join(BASE_DIR, 'imagecrawler.log')
ENV_FILE = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_FILE)

# --- Constants (Lấy từ code gốc của bạn) ---
MAX_URLS = 700
MAX_PREVNEXT_URLS = 200
MAX_API_PAGES = 1
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/chanktb/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# NEW: Cache để tối ưu hóa việc kiểm tra URL
URL_METADATA_CACHE = {}

# ----------------------------------------------------------------------------------------------------------------------
# Các hàm tiện ích (Telegram, Git, Config) - Lấy từ code gốc của bạn
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
    except FileNotFoundError: return []

def load_stop_urls():
    try:
        with open(STOP_URLS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}
    
def save_stop_urls(stop_urls):
    with open(STOP_URLS_FILE, 'w', encoding='utf-8') as f: json.dump(stop_urls, f, indent=2)

# ----------------------------------------------------------------------------------------------------------------------
# THAY ĐỔI CỐT LÕI: Nâng cấp hàm kiểm tra URL và thêm bộ lọc ảnh cũ
# ----------------------------------------------------------------------------------------------------------------------

def get_url_metadata(url):
    """Gửi request HEAD một lần, lấy metadata (status, is_recent) và lưu vào cache."""
    if url in URL_METADATA_CACHE:
        return URL_METADATA_CACHE[url]
    default_response = {'status': 0, 'is_recent': False}
    try:
        with requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True) as r:
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
        URL_METADATA_CACHE[url] = default_response
        return default_response

def check_url_exists(url):
    """HÀM NÀY THAY THẾ HÀM CŨ: Chỉ kiểm tra sự tồn tại (status 200)."""
    return get_url_metadata(url)['status'] == 200

def is_image_recent(url):
    """HÀM MỚI: Kiểm tra URL có tồn tại VÀ mới hay không."""
    metadata = get_url_metadata(url)
    return metadata['status'] == 200 and metadata['is_recent']

# ----------------------------------------------------------------------------------------------------------------------
# Các hàm xử lý URL (Lấy từ code gốc của bạn, không thay đổi logic)
# ----------------------------------------------------------------------------------------------------------------------
def apply_replacements(image_url, replacements, always_replace=False):
    final_img_url = image_url
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    if always_replace: return new_url
                    if check_url_exists(new_url):
                        return new_url
    return final_img_url

def apply_fallback_logic(image_url, url_data):
    fallback_rules = url_data.get('fallback_rules', {})
    if not fallback_rules or fallback_rules.get('type') != 'cut_filename_prefix': return image_url
    parsed_url = urlparse(image_url)
    if parsed_url.netloc != fallback_rules.get('domain'): return image_url
    path_parts = parsed_url.path.split('/')
    filename = path_parts[-1]
    prefix_length = fallback_rules.get('prefix_length', 0)
    if len(filename) > prefix_length and filename[prefix_length - 1] == '-':
        prefix = filename[:prefix_length-1]
        if re.match(r'^[a-zA-Z0-9_-]+$', prefix):
            new_filename = filename[prefix_length:]
            new_path = '/'.join(path_parts[:-1] + [new_filename])
            modified_url = parsed_url._replace(path=new_path).geturl()
            if check_url_exists(modified_url):
                return modified_url
    return image_url

def find_best_image_url(soup, url_data):
    replacements = url_data.get('replacements', {})
    selector = url_data.get('selector')
    if isinstance(replacements, list):
        tags_to_search = soup.select(selector) if selector else soup.find_all('img')
        for suffix in replacements:
            for img_tag in tags_to_search:
                img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
                if img_url and img_url.endswith(suffix): return img_url
    og_image_tag = soup.find('meta', property='og:image')
    if og_image_tag and og_image_tag.get('content'):
        return og_image_tag.get('content')
    if not selector and not replacements:
        for img_tag in soup.find_all('img'):
            img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
            if img_url: return img_url
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

# ----------------------------------------------------------------------------------------------------------------------
# CÁC HÀM FETCH (LẤY TỪ CODE GỐC, KHÔNG SỬA LOGIC STOP URL)
# ----------------------------------------------------------------------------------------------------------------------
def fetch_image_urls_from_api(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, page, domain = [], [], 1, urlparse(url_data['url']).netloc
    while page <= MAX_API_PAGES:
        api_url = DEFAULT_API_URL_PATTERN.format(domain=domain, page=page)
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=30); r.raise_for_status(); data = r.json()
            if not data: break
            for item in data:
                product_url = item.get('link')
                if product_url and product_url in stop_urls_list:
                    print(f"[{domain}] Dừng API vì gặp stop URL: {product_url}")
                    return all_image_urls, new_product_urls_found # Dùng return để thoát ngay lập tức
                img_url = (item.get('yoast_head_json', {}).get('og_image', [{}])[0].get('url') or 
                         (img_tag.get('src') if (img_tag := BeautifulSoup(item.get('content', {}).get('rendered', ''), 'html.parser').find('img')) else None))
                if img_url:
                    if img_url.startswith('http://'): img_url = img_url.replace('http://', 'https://')
                    final_img_url = apply_replacements(img_url, url_data.get('replacements', {}), url_data.get('always_replace', False))
                    final_img_url = apply_fallback_logic(final_img_url, url_data)
                    if final_img_url not in all_image_urls:
                        all_image_urls.append(final_img_url)
                        if product_url: new_product_urls_found.append(product_url)
            page += 1
        except requests.exceptions.RequestException: break
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_prevnext(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, domain = [], [], urlparse(url_data['url']).netloc
    try:
        r = requests.get(url_data['url'], headers=HEADERS, timeout=30); r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        first_product_tag = soup.select_one(url_data['first_product_selector'])
        if not first_product_tag: return [], []
        current_product_url = urljoin(url_data['url'], first_product_tag.get('href'))
    except requests.exceptions.RequestException: return [], []
    count = 0
    while count < MAX_PREVNEXT_URLS:
        if current_product_url in stop_urls_list:
            print(f"[{domain}] Dừng prev/next vì gặp stop URL: {current_product_url}")
            break
        print(f"Crawling: {current_product_url}")
        try:
            r = requests.get(current_product_url, headers=HEADERS, timeout=30); r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = apply_fallback_logic(best_url, url_data)
                if final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(current_product_url)
            next_product_tag = soup.select_one(url_data['next_product_selector'])
            if not next_product_tag or not next_product_tag.get('href'): break
            current_product_url = urljoin(current_product_url, next_product_tag.get('href'))
            count += 1
        except requests.exceptions.RequestException: break # Giữ logic gốc là dừng khi lỗi
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_product_list(url_data, stop_urls_list):
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
                found_stop_point = True
                break
            urls_to_crawl.append(product_url)
        if not found_stop_point:
            urls_to_crawl = product_urls
    else:
        urls_to_crawl = product_urls

    for product_url in urls_to_crawl:
        if len(all_image_urls) >= MAX_PREVNEXT_URLS: break
        print(f"Crawling: {product_url}")
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
# Main Execution (THAY ĐỔI: Thêm bước sàng lọc)
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    start_time = time.time()
    configs, urls_summary, stop_urls_data = load_config(), {}, load_stop_urls()
    if not configs: exit(1)

    for url_data in configs:
        domain = urlparse(url_data['url']).netloc
        source_type = url_data.get('source_type')
        
        # GIAI ĐOẠN 1: THU THẬP (Sử dụng logic gốc, không thay đổi)
        unfiltered_image_urls, new_product_urls_found = [], []
        domain_stop_urls_list = set(stop_urls_data.get(domain, []))

        if source_type == 'api':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_api(url_data, domain_stop_urls_list)
        elif source_type == 'prevnext':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_prevnext(url_data, domain_stop_urls_list)
        elif source_type == 'product-list':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_product_list(url_data, domain_stop_urls_list)
        
        # GIAI ĐOẠN 2: SÀNG LỌC (Logic mới được thêm vào)
        final_image_urls = []
        if url_data.get("check_recency", False):
            print(f"[{domain}] Sàng lọc {len(unfiltered_image_urls)} URLs để lấy ảnh mới...")
            for img_url in unfiltered_image_urls:
                if is_image_recent(img_url): final_image_urls.append(img_url)
        else:
            final_image_urls = unfiltered_image_urls
        
        # LƯU KẾT QUẢ (Sử dụng kết quả đã sàng lọc)
        new_urls_count, total_urls_count = save_urls(domain, final_image_urls)
        urls_summary[domain] = {'new_count': new_urls_count, 'total_count': total_urls_count}
        if new_product_urls_found:
            stop_urls_data[domain] = new_product_urls_found[:STOP_URLS_COUNT]
    
    save_stop_urls(stop_urls_data)
    
    # TỔNG KẾT VÀ BÁO CÁO (Logic gốc)
    end_time = time.time()
    duration, now_vietnam = end_time - start_time, datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
    log_lines = [f"--- Summary of Last Image Crawl ---", f"Generated at: {now_vietnam.strftime('%Y-%m-%d %H:%M:%S %z')}"]
    found_new_images = any(c['new_count'] > 0 for c in urls_summary.values())

    if found_new_images:
        for domain, counts in urls_summary.items():
            if counts['new_count'] > 0:
                log_lines.append(f"{domain}: {counts['new_count']} New Images: {counts['total_count']}")
    
    log_lines.append(f"Crawl duration: {int(duration // 60)} min {int(duration % 60)} seconds.")
    with open(LOG_FILE, "w", encoding="utf-8") as f: f.write("\n".join(log_lines))
    
    if found_new_images:
        send_telegram_message("\n".join(log_lines))
        trigger_workflow_dispatch()
    
    git_push_changes()
