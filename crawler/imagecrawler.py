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
# Hệ thống kiểm tra URL
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

# --- Các hàm phụ (Telegram, Git, Config, ...) ---
def send_telegram_message(message):
    bot_token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id: return
    try: requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data={'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}, timeout=10)
    except requests.exceptions.RequestException as e: print(f"❌ Lỗi Telegram: {e}")

def git_push_changes():
    if os.getenv('GITHUB_ACTIONS') == 'true': return
    try:
        os.chdir(BASE_DIR)
        subprocess.run(['git', 'add', 'domain/', 'stop_urls.txt', 'imagecrawler.log'], check=True)
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status_result.stdout.strip(): return
        commit_message = f"Auto-update crawled data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        subprocess.run(['git', 'push'], check=True)
    except Exception as e: print(f"❌ Lỗi git: {e}")

def trigger_workflow_dispatch():
    pat = os.getenv('KTBHUB_PAT')
    if not pat: return
    owner, repo_name, event_type = "ktbhub", "ktb-image", "new_image_available"
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/dispatches"
    headers = {"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {pat}"}
    data = {"event_type": event_type}
    try: requests.post(api_url, headers=headers, json=data, timeout=15)
    except requests.exceptions.RequestException as e: print(f"❌ Lỗi GitHub API: {e}")

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
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    if always_replace or check_url_exists(new_url): return new_url
    return image_url

def apply_fallback_logic(image_url, url_data):
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
    replacements, selector = url_data.get('replacements', {}), url_data.get('selector')
    if isinstance(replacements, list):
        tags_to_search = soup.select(selector) if selector else soup.find_all('img')
        for suffix in replacements:
            for img_tag in tags_to_search:
                img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
                if img_url and img_url.endswith(suffix): return urljoin(url_data['url'], img_url)
    og_image_tag = soup.find('meta', property='og:image')
    if og_image_tag and og_image_tag.get('content'): return urljoin(url_data['url'], og_image_tag.get('content'))
    if not selector and not replacements:
        for img_tag in soup.find_all('img'):
            img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
            if img_url: return urljoin(url_data['url'], img_url)
    return None

# ----------------------------------------------------------------------------------------------------------------------
# GIAI ĐOẠN 1: CÁC HÀM THU THẬP
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
                if product_url in stop_urls_list: return all_image_urls, new_product_urls_found
                img_url = None
                if 'yoast_head_json' in item and 'og_image' in item['yoast_head_json'] and item['yoast_head_json']['og_image']:
                    img_url = item['yoast_head_json']['og_image'][0]['url']
                if not img_url and 'content' in item and 'rendered' in item['content']:
                    img_tag = BeautifulSoup(item['content']['rendered'], 'html.parser').find('img')
                    if img_tag and img_tag.get('src'): img_url = img_tag.get('src')
                if img_url:
                    final_img_url = apply_replacements(img_url, url_data.get('replacements', {}))
                    final_img_url = apply_fallback_logic(final_img_url, url_data)
                    if check_url_exists(final_img_url) and final_img_url not in all_image_urls:
                        all_image_urls.append(final_img_url)
                        if product_url: new_product_urls_found.append(product_url)
            page += 1
        except requests.exceptions.RequestException as e: break
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_prevnext(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, domain = [], [], urlparse(url_data['url']).netloc
    try:
        r = requests.get(url_data['url'], headers=HEADERS, timeout=30); r.raise_for_status()
        first_product_tag = BeautifulSoup(r.text, "html.parser").select_one(url_data['first_product_selector'])
        if not first_product_tag: return [], []
        current_product_url = urljoin(url_data['url'], first_product_tag.get('href'))
    except requests.exceptions.RequestException: return [], []
    count = 0
    while count < MAX_PREVNEXT_URLS:
        if current_product_url in stop_urls_list: break
        print(f"Crawling: {current_product_url}")
        try:
            with requests.get(current_product_url, headers=HEADERS, timeout=30, stream=True) as r:
                r.raise_for_status()
                content = b''.join(chunk for chunk in r.iter_content(chunk_size=8192))
                soup = BeautifulSoup(content, "html.parser")
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = apply_fallback_logic(best_url, url_data)
                if check_url_exists(final_img_url) and final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(current_product_url)
            next_product_tag = soup.select_one(url_data['next_product_selector'])
            if not next_product_tag or not next_product_tag.get('href'): break
            current_product_url = urljoin(current_product_url, next_product_tag.get('href'))
            count += 1
        except requests.exceptions.RequestException as e: break
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_product_list(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, domain = [], [], urlparse(url_data['url']).netloc
    repo_file_url = REPO_URL_PATTERN.format(domain=domain)
    try:
        r = requests.get(repo_file_url, headers=HEADERS, timeout=30); r.raise_for_status()
        product_urls = [line.strip() for line in r.text.splitlines() if line.strip()]
    except requests.exceptions.RequestException: return [], []
    urls_to_crawl = []
    found_stop_point = False
    for product_url in product_urls:
        if product_url in stop_urls_list: found_stop_point = True; break
        urls_to_crawl.append(product_url)
    if not found_stop_point: urls_to_crawl = product_urls
    for product_url in urls_to_crawl:
        if len(all_image_urls) >= MAX_PREVNEXT_URLS: break
        print(f"Crawling: {product_url}")
        try:
            with requests.get(product_url, headers=HEADERS, timeout=30, stream=True) as r:
                r.raise_for_status()
                content = b''.join(chunk for chunk in r.iter_content(chunk_size=8192))
                soup = BeautifulSoup(content, "html.parser")
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = apply_fallback_logic(best_url, url_data)
                if check_url_exists(final_img_url) and final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(product_url)
        except requests.exceptions.RequestException as e: continue
    return all_image_urls, new_product_urls_found

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
# Main Execution
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    start_time = time.time()
    configs, urls_summary, stop_urls_data = load_config(), {}, load_stop_urls()
    if not configs: exit(1)

    for url_data in configs:
        domain = urlparse(url_data['url']).netloc
        
        # GIAI ĐOẠN 1: THU THẬP
        unfiltered_image_urls, new_product_urls_found = [], []
        domain_stop_urls_list = set(stop_urls_data.get(domain, []))
        source_type = url_data.get('source_type')
        if source_type == 'api':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_api(url_data, domain_stop_urls_list)
        elif source_type == 'prevnext':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_prevnext(url_data, domain_stop_urls_list)
        elif source_type == 'product-list':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_product_list(url_data, domain_stop_urls_list)
        
        # GIAI ĐOẠN 2: SÀNG LỌC
        final_image_urls = []
        if url_data.get("check_recency", False):
            print(f"[{domain}] Filtering {len(unfiltered_image_urls)} URLs for recent images...")
            for img_url in unfiltered_image_urls:
                if is_image_recent(img_url): final_image_urls.append(img_url)
        else:
            final_image_urls = unfiltered_image_urls
        
        # LƯU KẾT QUẢ
        new_urls_count, total_urls_count = save_urls(domain, final_image_urls)
        urls_summary[domain] = {'new_count': new_urls_count, 'total_count': total_urls_count}
        if new_product_urls_found:
            stop_urls_data[domain] = new_product_urls_found[:STOP_URLS_COUNT]
    
    save_stop_urls(stop_urls_data)
    
    # TỔNG KẾT VÀ BÁO CÁO
    end_time = time.time()
    duration, now_vietnam = end_time - start_time, datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
    log_lines = [f"Generated at: {now_vietnam.strftime('%Y-%m-%d %H:%M:%S %z')}"]
    for domain, counts in urls_summary.items():
        log_lines.append(f"{domain}: {counts['new_count']} New Images: {counts['total_count']}")
    log_lines.append(f"Crawl duration: {int(duration // 60)} min {int(duration % 60)} seconds.")
    with open(LOG_FILE, "w", encoding="utf-8") as f: f.write("\n".join(log_lines))
    
    if any(c['new_count'] > 0 for c in urls_summary.values()):
        report_lines = [line for line in log_lines if "New Images: 0" not in line]
        send_telegram_message("\n".join(report_lines))
        trigger_workflow_dispatch()
    
    git_push_changes()
