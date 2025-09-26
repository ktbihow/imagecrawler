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

# --- Đường dẫn đã được sửa lỗi ---
SCRIPT_PATH = os.path.abspath(__file__)
CRAWLER_DIR = os.path.dirname(SCRIPT_PATH)
BASE_DIR = os.path.dirname(CRAWLER_DIR)

DOMAIN_DIR = os.path.join(BASE_DIR, 'domain')
CONFIG_FILE = os.path.join(CRAWLER_DIR, 'config.json')
STOP_URLS_FILE = os.path.join(BASE_DIR, 'stop_urls.txt')
LOG_FILE = os.path.join(BASE_DIR, 'imagecrawler.log')
ENV_FILE = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_FILE)

# --- Constants ---
MAX_URLS = 700
MAX_PREVNEXT_URLS = 200
MAX_API_PAGES = 2
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/chanktb/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# --- Cache ---
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
                if (now_utc - last_modified_date) > timedelta(days=1):
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
# Các hàm tiện ích (ĐÃ THÊM LẠI BÁO CÁO)
# ----------------------------------------------------------------------------------------------------------------------
def send_telegram_message(message):
    bot_token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id: return
    print("Đang gửi báo cáo tới Telegram...")
    try: 
        response = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data={'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}, timeout=10)
        if response.status_code == 200: print("✅ Đã gửi báo cáo thành công tới Telegram.")
        else: print(f"❌ Lỗi khi gửi báo cáo Telegram: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối tới Telegram API: {e}")

def git_push_changes():
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print("Đang chạy trên GitHub Actions, bỏ qua git push.")
        return

    print("Đang chạy trên máy tính cục bộ, tiến hành push thay đổi lên GitHub...")
    try:
        os.chdir(BASE_DIR)
        subprocess.run(['git', 'add', 'domain/', 'stop_urls.txt', 'imagecrawler.log'], check=True)
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status_result.stdout.strip():
            print("Không có thay đổi nào để commit.")
            return
        branch_result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True, check=True)
        current_branch = branch_result.stdout.strip()
        commit_message = f"Auto-update crawled data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git', 'commit', '--amend', '-m', commit_message], check=True)
        print(f"✅ Đã amend commit cuối cùng với message: '{commit_message}'")
        subprocess.run(['git', 'push', '--force', 'origin', current_branch], check=True)
        print("✅ Đã force push thành công các thay đổi lên GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Đã xảy ra lỗi khi thực thi lệnh Git:")
        print(f"   Lệnh: {' '.join(e.cmd)}")
        print(f"   Exit code: {e.returncode}")
        print(f"   Stderr: {e.stderr.decode('utf-8', errors='ignore').strip()}")
        print(f"   Stdout: {e.stdout.decode('utf-8', errors='ignore').strip()}")
    except Exception as e:
        print(f"❌ Đã xảy ra lỗi không xác định khi push: {e}")

def trigger_workflow_dispatch():
    pat = os.getenv('KTBHUB_PAT')
    if not pat: return
    print("🚀 Kích hoạt workflow 'new_image_available' trên repo ktbhub/ktb-image...")
    try: 
        response = requests.post(f"https://api.github.com/repos/ktbhub/ktb-image/dispatches", headers={"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {pat}"}, json={"event_type": "new_image_available"}, timeout=15)
        if response.status_code == 204: print("✅ Đã gửi yêu cầu kích hoạt workflow thành công.")
        else: print(f"❌ Lỗi khi kích hoạt workflow: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối đến GitHub API: {e}")

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError: print(f"LỖI: Không tìm thấy file config tại: {CONFIG_FILE}"); return []

def load_stop_urls():
    try:
        with open(STOP_URLS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_stop_urls(stop_urls):
    with open(STOP_URLS_FILE, 'w', encoding='utf-8') as f: json.dump(stop_urls, f, indent=2)

def apply_replacements(image_url, replacements, always_replace=False):
    if not image_url: return image_url
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    print(f"    -> Checking replacement: {new_url}")
                    if always_replace or check_url_exists(new_url):
                        print(f"    => ✅ Replacement found: {new_url}")
                        return new_url
                print(f"    => ❌ No valid replacement found for '{original}'.")
    return image_url

def apply_fallback_logic(image_url, url_data):
    if not image_url: return image_url
    fallback_rules = url_data.get('fallback_rules', {})
    if not fallback_rules or fallback_rules.get('type') != 'cut_filename_prefix': return image_url
    print(f"    -> Applying fallback for: {image_url}")
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
            if check_url_exists(modified_url):
                print(f"    => ✅ Fallback successful: {modified_url}")
                return modified_url
    print(f"    => ❌ Fallback failed.")
    return image_url

def process_and_finalize_url(image_url, url_data):
    """
    Applies fallback and replacement logic in the correct order.
    1. Fallback is applied first to get a clean base URL.
    2. Replacements are applied to the clean URL to find variants.
    """
    if not image_url:
        return None

    # Step 1: Apply fallback logic first to remove any random prefixes.
    clean_url = apply_fallback_logic(image_url, url_data)

    # Step 2: Apply replacements on the (potentially cleaned) URL.
    final_url = apply_replacements(clean_url, url_data.get('replacements', {}), url_data.get('always_replace', False))
    
    return final_url

def find_best_image_url(soup, url_data):
    base_url = url_data['url']
    replacements, selector = url_data.get('replacements', {}), url_data.get('selector')
    image_tags = soup.select(selector) if selector else soup.find_all('img')
    if isinstance(replacements, list):
        for suffix in replacements:
            for img_tag in image_tags:
                img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
                if img_url and img_url.endswith(suffix):
                    print(f"    -> Found prioritized image by suffix '{suffix}'")
                    return urljoin(base_url, img_url)
    og_image_tag = soup.find('meta', property='og:image')
    if og_image_tag and og_image_tag.get('content'):
        img_url = urljoin(base_url, og_image_tag.get('content'))
        print(f"    -> Found og:image: {img_url}")
        return img_url
    if not selector and not replacements:
        for img_tag in image_tags:
            img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
            if img_url:
                img_url = urljoin(base_url, img_url)
                print(f"    -> Found first available image tag: {img_url}")
                return img_url
    return None

def save_urls(domain, new_urls, discarded_count=0):
    if not os.path.exists(DOMAIN_DIR): os.makedirs(DOMAIN_DIR)
    filename = os.path.join(DOMAIN_DIR, f"{domain}.txt")
    try:
        with open(filename, "r", encoding="utf-8") as f: existing_urls = [line.strip() for line in f]
    except FileNotFoundError: existing_urls = []
    unique_new_urls = [u for u in new_urls if u not in existing_urls]
    all_urls = (unique_new_urls + existing_urls)[:MAX_URLS]
    with open(filename, "w", encoding="utf-8") as f: f.write("\n".join(all_urls))
    console_report = f"[{domain}] Added {len(unique_new_urls)} new URLs."
    if discarded_count > 0:
        console_report += f" Discarded {discarded_count} old URLs."
    console_report += f" Total: {len(all_urls)}"
    print(console_report)
    return len(unique_new_urls), len(all_urls)

def fetch_image_urls_from_api(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, page, domain = [], [], 1, urlparse(url_data['url']).netloc
    stop_url_found = None
    while page <= MAX_API_PAGES and not stop_url_found:
        api_url = DEFAULT_API_URL_PATTERN.format(domain=domain, page=page)
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=30); r.raise_for_status(); data = r.json()
            if not data: break
            for item in data:
                product_url = item.get('link')
                if product_url and product_url in stop_urls_list:
                    stop_url_found = product_url; break
                img_url = (item.get('yoast_head_json', {}).get('og_image', [{}])[0].get('url') or 
                         (img_tag.get('src') if (img_tag := BeautifulSoup(item.get('content', {}).get('rendered', ''), 'html.parser').find('img')) else None))
                if img_url:
                    if img_url.startswith('http://'): img_url = img_url.replace('http://', 'https://')
                    
                    # Sử dụng hàm xử lý mới với thứ tự logic đã được sửa
                    final_img_url = process_and_finalize_url(img_url, url_data)
                    
                    if final_img_url and final_img_url not in all_image_urls:
                        all_image_urls.append(final_img_url)
                        if product_url: new_product_urls_found.append(product_url)
            page += 1
        except requests.exceptions.RequestException: break
    if stop_url_found: print(f"[{domain}] Found {len(new_product_urls_found)} new URLs. Stopped at stop URL.")
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
    stop_url_found = None
    while count < MAX_PREVNEXT_URLS:
        if current_product_url in stop_urls_list:
            stop_url_found = current_product_url; break
        print(f"Crawling: {current_product_url}")
        try:
            r = requests.get(current_product_url, headers=HEADERS, timeout=30); r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                # Sử dụng hàm xử lý mới với thứ tự logic đã được sửa
                final_img_url = process_and_finalize_url(best_url, url_data)

                if final_img_url and final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(current_product_url)
            next_product_tag = soup.select_one(url_data['next_product_selector'])
            if not next_product_tag or not next_product_tag.get('href'): break
            current_product_url = urljoin(current_product_url, next_product_tag.get('href'))
            count += 1
        except requests.exceptions.RequestException: break
    if stop_url_found: print(f"[{domain}] Found {len(new_product_urls_found)} new URLs. Stopped at stop URL.")
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_product_list(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, domain = [], [], urlparse(url_data['url']).netloc
    repo_file_url = REPO_URL_PATTERN.format(domain=domain)
    try:
        r = requests.get(repo_file_url, headers=HEADERS, timeout=30); r.raise_for_status()
        product_urls = [line.strip() for line in r.text.splitlines() if line.strip()]
    except requests.exceptions.RequestException: return [], []
    
    urls_to_crawl, stop_url_found = [], None
    if stop_urls_list:
        for product_url in product_urls:
            if product_url in stop_urls_list:
                stop_url_found = product_url; break
            urls_to_crawl.append(product_url)
        if not stop_url_found: urls_to_crawl = product_urls
    else: urls_to_crawl = product_urls

    if stop_url_found: print(f"[{domain}] Found {len(urls_to_crawl)} new URLs to crawl. Will stop at: {stop_url_found}")

    for product_url in urls_to_crawl:
        if len(all_image_urls) >= MAX_PREVNEXT_URLS: break
        print(f"Crawling: {product_url}")
        try:
            with requests.get(product_url, headers=HEADERS, timeout=30, stream=True) as r:
                r.raise_for_status()
                content = b''.join(r.iter_content(chunk_size=8192))
                soup = BeautifulSoup(content, "html.parser")
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                # Sử dụng hàm xử lý mới với thứ tự logic đã được sửa
                final_img_url = process_and_finalize_url(best_url, url_data)

                if final_img_url and final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(product_url)
        except requests.exceptions.RequestException: continue
    return all_image_urls, new_product_urls_found

# ----------------------------------------------------------------------------------------------------------------------
# Main Execution
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

        print(f"\n--- Processing domain: {domain} ({source_type}) ---")
        
        if source_type == 'api':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_api(url_data, domain_stop_urls_list)
        elif source_type == 'prevnext':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_prevnext(url_data, domain_stop_urls_list)
        elif source_type == 'product-list':
            unfiltered_image_urls, new_product_urls_found = fetch_image_urls_from_product_list(url_data, domain_stop_urls_list)
        
        final_image_urls, discarded_count = [], 0
        if url_data.get("check_recency", False):
            print(f"[{domain}] Filtering {len(unfiltered_image_urls)} found URLs for recency...")
            for img_url in unfiltered_image_urls:
                if is_image_recent(img_url):
                    final_image_urls.append(img_url)
                else:
                    discarded_count += 1
        else:
            final_image_urls = unfiltered_image_urls
        
        new_urls_count, total_urls_count = save_urls(domain, final_image_urls, discarded_count)
        urls_summary[domain] = { 'new_count': new_urls_count, 'total_count': total_urls_count }
        
        if new_product_urls_found:
            stop_urls_data[domain] = new_product_urls_found[:STOP_URLS_COUNT]
    
    save_stop_urls(stop_urls_data)
    
    end_time = time.time()
    duration, now_vietnam = end_time - start_time, datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
    log_lines = [f"--- Summary of Last Image Crawl ---", f"Generated at: {now_vietnam.strftime('%Y-%m-%d %H:%M:%S %z')}"]
    found_new_images = any(c['new_count'] > 0 for c in urls_summary.values())

    reportable_lines, full_log_lines = [], log_lines[:1]
    for domain, counts in urls_summary.items():
        log_line = f"{domain}: {counts['new_count']} New Images. Total: {counts['total_count']}"
        full_log_lines.append(log_line)
        if counts['new_count'] > 0:
            reportable_lines.append(log_line)
    
    duration_line = f"Crawl duration: {int(duration // 60)} min {int(duration % 60)} seconds."
    full_log_lines.append(duration_line)
    
    print(f"\n--- Summary saved to {LOG_FILE} ---")
    with open(LOG_FILE, "w", encoding="utf-8") as f: f.write("\n".join(full_log_lines))
    
    if found_new_images:
        print("Tìm thấy ảnh mới, đang chuẩn bị gửi báo cáo và kích hoạt workflow...")
        final_report = log_lines[:1] + reportable_lines
        final_report.append(duration_line)
        send_telegram_message("\n".join(final_report))
        #trigger_workflow_dispatch()
    else:
        print("Không có ảnh mới nào được tìm thấy. Bỏ qua các hành động tiếp theo.")
    
    git_push_changes()
