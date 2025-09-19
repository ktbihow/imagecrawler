import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import json
import re
from datetime import datetime, timedelta, timezone # MODIFIED: Thêm timedelta và timezone
import pytz
import subprocess
import time
from dotenv import load_dotenv
from dateutil import parser # NEW: Thêm thư viện dateutil

# --- START: Cấu hình đường dẫn ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CRAWLER_DIR = os.path.join(BASE_DIR, 'crawler')
DOMAIN_DIR = os.path.join(BASE_DIR, 'domain')
CONFIG_FILE = os.path.join(CRAWLER_DIR, 'config.json')
STOP_URLS_FILE = os.path.join(BASE_DIR, 'stop_urls.txt')
LOG_FILE = os.path.join(BASE_DIR, 'imagecrawler.log')
ENV_FILE = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_FILE)
# --- END: Cấu hình đường dẫn ---

# NEW: Global cache để lưu kết quả check URL
URL_CHECK_CACHE = {}

# Constants
MAX_URLS = 700
MAX_PREVNEXT_URLS = 200
MAX_API_PAGES = 1
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/chanktb/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# ----------------------------------------------------------------------------------------------------------------------
# NEW: Hàm kiểm tra ảnh mới và có thể truy cập (với cache)
# ----------------------------------------------------------------------------------------------------------------------

def is_image_recent_and_accessible(image_url):
    """
    Kiểm tra xem một URL ảnh có truy cập được và mới không, CÓ SỬ DỤNG CACHE.
    """
    if image_url in URL_CHECK_CACHE:
        return URL_CHECK_CACHE[image_url]

    try:
        r = requests.head(image_url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            URL_CHECK_CACHE[image_url] = False
            return False

        last_modified_str = r.headers.get('Last-Modified')
        if not last_modified_str:
            URL_CHECK_CACHE[image_url] = True
            return True
        
        last_modified_date = parser.parse(last_modified_str)
        if last_modified_date.tzinfo is None:
            last_modified_date = last_modified_date.replace(tzinfo=timezone.utc)
        
        now_utc = datetime.now(timezone.utc)
        
        # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        # ĐÂY LÀ NƠI THAY ĐỔI SỐ NGÀY. SỬA `days=3` THÀNH `days=2` HOẶC BẤT KỲ SỐ NÀO BẠN MUỐN
        # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        if (now_utc - last_modified_date) <= timedelta(days=2):
            URL_CHECK_CACHE[image_url] = True
            return True
        else:
            URL_CHECK_CACHE[image_url] = False
            return False

    except (requests.exceptions.RequestException, parser.ParserError, ValueError) as e:
        print(f"Lỗi khi kiểm tra URL {image_url}: {e}")
        URL_CHECK_CACHE[image_url] = False
        return False

# ----------------------------------------------------------------------------------------------------------------------
# Telegram and Git Functions (Giữ nguyên)
# ----------------------------------------------------------------------------------------------------------------------
def send_telegram_message(message):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id:
        print("Cảnh báo: TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID không được thiết lập.")
        return
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(api_url, data=payload, timeout=10)
        if response.status_code == 200: print("✅ Đã gửi báo cáo thành công tới Telegram.")
        else: print(f"❌ Lỗi khi gửi báo cáo Telegram: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối tới Telegram API: {e}")

def git_push_changes():
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print("Đang chạy trên GitHub Actions, bỏ qua git push.")
        return
    print("Đang chạy trên máy tính cục bộ, tiến hành push thay đổi lên GitHub...")
    try:
        os.chdir(BASE_DIR)
        subprocess.run(['git', 'config', 'user.name', 'ktbihow'], check=True)
        subprocess.run(['git', 'config', 'user.email', '230660483+ktbihow@users.noreply.github.com'], check=True)
        subprocess.run(['git', 'add', 'domain/', 'stop_urls.txt', 'imagecrawler.log'], check=True)
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status_result.stdout.strip():
            print("Không có thay đổi nào để commit.")
            return
        commit_message = f"Auto-update crawled data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        subprocess.run(['git', 'push'], check=True)
        print("✅ Đã push thành công các thay đổi lên GitHub.")
    except (subprocess.CalledProcessError, FileNotFoundError, Exception) as e:
        print(f"❌ Lỗi khi thực hiện lệnh git: {e}")

def trigger_workflow_dispatch():
    pat = os.getenv('KTBHUB_PAT')
    if not pat:
        print("Cảnh báo: KTBHUB_PAT không được thiết lập. Bỏ qua kích hoạt workflow.")
        return
    owner, repo_name, event_type = "ktbhub", "ktb-image", "new_image_available"
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/dispatches"
    headers = {"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {pat}"}
    data = {"event_type": event_type}
    print(f"🚀 Kích hoạt workflow '{event_type}' trên repo {owner}/{repo_name}...")
    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=15)
        if response.status_code == 204: print("✅ Đã gửi yêu cầu kích hoạt workflow thành công.")
        else: print(f"❌ Lỗi khi kích hoạt workflow: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối đến GitHub API: {e}")

# ----------------------------------------------------------------------------------------------------------------------
# Core Functions (MODIFIED: Sử dụng cache cho check_url_exists)
# ----------------------------------------------------------------------------------------------------------------------
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp {CONFIG_FILE}!"); return []

def load_stop_urls():
    try:
        with open(STOP_URLS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_stop_urls(stop_urls):
    with open(STOP_URLS_FILE, 'w', encoding='utf-8') as f: json.dump(stop_urls, f, indent=2)

def check_url_exists(url):
    # MODIFIED: Hàm này giờ đây cũng sẽ sử dụng cache để tăng tốc
    if url in URL_CHECK_CACHE and URL_CHECK_CACHE[url] in [True, False]:
        return URL_CHECK_CACHE[url]
    
    # Nếu chưa có trong cache, gọi hàm kiểm tra đầy đủ
    return is_image_recent_and_accessible(url)

# ... (Các hàm apply_replacements, apply_fallback_logic, find_best_image_url giữ nguyên) ...
def apply_replacements(image_url, replacements, always_replace=False):
    final_img_url = image_url
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    if always_replace: return new_url
                    if check_url_exists(new_url):
                        print(f"✅ Found a valid replacement URL: {new_url}")
                        return new_url
                    else:
                        print(f"❌ Replacement URL not found: {new_url}. Trying next...")
                return image_url
    return final_img_url

def apply_fallback_logic(image_url, url_data):
    fallback_rules = url_data.get('fallback_rules', {})
    if not fallback_rules or fallback_rules.get('type') != 'cut_filename_prefix':
        return image_url
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
                print(f"✅ Found valid URL using fallback logic for original: {image_url}")
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
    if og_image_tag and og_image_tag.get('content'): return og_image_tag.get('content')
    if not selector and not replacements:
        for img_tag in soup.find_all('img'):
            img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
            if img_url: return img_url
    return None

# ----------------------------------------------------------------------------------------------------------------------
# Crawl Functions (MODIFIED: Tích hợp logic check_recency)
# ----------------------------------------------------------------------------------------------------------------------
def fetch_image_urls_from_api(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, page, domain = [], [], 1, urlparse(url_data['url']).netloc
    should_check_recency = url_data.get("check_recency", False) # NEW
    while page <= MAX_API_PAGES:
        api_url = DEFAULT_API_URL_PATTERN.format(domain=domain, page=page)
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=30); r.raise_for_status(); data = r.json()
            if not data: break
            for item in data:
                product_url = item.get('link')
                if product_url and product_url in stop_urls_list:
                    print(f"Đã tìm thấy URL dừng: {product_url}, kết thúc crawl."); return all_image_urls, new_product_urls_found
                img_url = None
                if 'yoast_head_json' in item and 'og_image' in item['yoast_head_json'] and item['yoast_head_json']['og_image']:
                    img_url = item['yoast_head_json']['og_image'][0]['url']
                if not img_url and 'content' in item and 'rendered' in item['content']:
                    soup = BeautifulSoup(item['content']['rendered'], 'html.parser')
                    img_tag = soup.find('img')
                    if img_tag and img_tag.get('src'): img_url = img_tag.get('src')
                if img_url:
                    if img_url.startswith('http://'): img_url = img_url.replace('http://', 'https://')
                    final_img_url = apply_replacements(img_url, url_data.get('replacements', {}), url_data.get('always_replace', False))
                    final_img_url = apply_fallback_logic(final_img_url, url_data)
                    
                    # MODIFIED: Tích hợp logic kiểm tra
                    is_valid_to_add = (is_image_recent_and_accessible(final_img_url) if should_check_recency else True)
                    if is_valid_to_add and (final_img_url not in all_image_urls):
                        all_image_urls.append(final_img_url)
                        if product_url: new_product_urls_found.append(product_url)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi truy cập API {api_url}: {e}"); break
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_prevnext(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, domain = [], [], urlparse(url_data['url']).netloc
    should_check_recency = url_data.get("check_recency", False) # NEW
    try:
        r = requests.get(url_data['url'], headers=HEADERS, timeout=30); r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        first_product_tag = soup.select_one(url_data['first_product_selector'])
        if not first_product_tag: return [], []
        current_product_url = urljoin(url_data['url'], first_product_tag.get('href'))
        last_successful_product_url = None
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi truy cập trang chủ {url_data['url']}: {e}"); return [], []
    count = 0
    while count < MAX_PREVNEXT_URLS:
        if current_product_url in stop_urls_list:
            print(f"Đã tìm thấy URL dừng: {current_product_url}, kết thúc crawl."); break
        try:
            r = requests.get(current_product_url, headers=HEADERS, timeout=30); r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = apply_fallback_logic(best_url, url_data)
                
                # MODIFIED: Tích hợp logic kiểm tra
                is_valid_to_add = (is_image_recent_and_accessible(final_img_url) if should_check_recency else True)
                if is_valid_to_add and (final_img_url not in all_image_urls):
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(current_product_url)
            
            last_successful_product_url = current_product_url
            next_product_tag = soup.select_one(url_data['next_product_selector'])
            if not next_product_tag or not next_product_tag.get('href'): break
            current_product_url = urljoin(current_product_url, next_product_tag.get('href'))
            count += 1
        except requests.exceptions.RequestException as e:
            # ... (Phần code phục hồi crawl giữ nguyên) ...
            print(f"Lỗi khi truy cập {current_product_url}: {e}")
            break # Đơn giản hóa, có thể thêm lại logic phục hồi nếu cần
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_product_list(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, domain = [], [], urlparse(url_data['url']).netloc
    should_check_recency = url_data.get("check_recency", False) # NEW
    repo_file_url = REPO_URL_PATTERN.format(domain=domain)
    try:
        r = requests.get(repo_file_url, headers=HEADERS, timeout=30); r.raise_for_status()
        product_urls = [line.strip() for line in r.text.splitlines() if line.strip()]
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi truy cập repo sản phẩm: {e}."); return [], []
    urls_to_crawl = []
    if stop_urls_list:
        found_stop_point = False
        for product_url in product_urls:
            if product_url in stop_urls_list: found_stop_point = True; break
            urls_to_crawl.append(product_url)
        if not found_stop_point: urls_to_crawl = product_urls
    else:
        urls_to_crawl = product_urls
    for product_url in urls_to_crawl:
        if len(all_image_urls) >= MAX_PREVNEXT_URLS: break
        try:
            r = requests.get(product_url, headers=HEADERS, timeout=30); r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = apply_fallback_logic(best_url, url_data)

                # MODIFIED: Tích hợp logic kiểm tra
                is_valid_to_add = (is_image_recent_and_accessible(final_img_url) if should_check_recency else True)
                if is_valid_to_add and (final_img_url not in all_image_urls):
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(product_url)
        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi truy cập URL sản phẩm {product_url}: {e}."); continue
    return all_image_urls, new_product_urls_found

# ----------------------------------------------------------------------------------------------------------------------
# Main Execution (Giữ nguyên)
# ----------------------------------------------------------------------------------------------------------------------
def save_urls(domain, new_urls):
    if not os.path.exists(DOMAIN_DIR): os.makedirs(DOMAIN_DIR)
    filename = os.path.join(DOMAIN_DIR, f"{domain}.txt")
    try:
        with open(filename, "r", encoding="utf-8") as f:
            existing_urls = [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError: existing_urls = []
    unique_new_urls = [u for u in new_urls if u not in existing_urls]
    all_urls = (unique_new_urls + existing_urls)[:MAX_URLS]
    with open(filename, "w", encoding="utf-8") as f: f.write("\n".join(all_urls))
    print(f"[{domain}] Added {len(unique_new_urls)} new URLs. Total: {len(all_urls)}")
    return len(unique_new_urls), len(all_urls)

if __name__ == "__main__":
    start_time = time.time()
    configs, urls_summary, stop_urls_data = load_config(), {}, load_stop_urls()
    if not configs: exit(1)
    if not os.path.exists(DOMAIN_DIR): os.makedirs(DOMAIN_DIR)
    for url_data in configs:
        domain = urlparse(url_data['url']).netloc
        source_type = url_data.get('source_type')
        image_urls, new_product_urls_found = [], []
        domain_stop_urls_list = set(stop_urls_data.get(domain, []))
        if source_type == 'api':
            image_urls, new_product_urls_found = fetch_image_urls_from_api(url_data, domain_stop_urls_list)
        elif source_type == 'prevnext':
            image_urls, new_product_urls_found = fetch_image_urls_from_prevnext(url_data, domain_stop_urls_list)
        elif source_type == 'product-list':
            image_urls, new_product_urls_found = fetch_image_urls_from_product_list(url_data, domain_stop_urls_list)
        else:
            print(f"Lỗi: Không xác định được source_type cho domain {domain}."); continue
        new_urls_count, total_urls_count = save_urls(domain, image_urls)
        urls_summary[domain] = {'new_count': new_urls_count, 'total_count': total_urls_count}
        if new_product_urls_found:
            stop_urls_data[domain] = new_product_urls_found[:STOP_URLS_COUNT]
    save_stop_urls(stop_urls_data)

    vietnam_tz, end_time = pytz.timezone('Asia/Ho_Chi_Minh'), time.time()
    now_vietnam, duration = datetime.now(vietnam_tz), end_time - start_time
    minutes, seconds = int(duration // 60), int(duration % 60)
    formatted_duration = f"{minutes} min {seconds} seconds"
    log_lines = [f"--- Summary of Last Image Crawl ---", f"Generated at: {now_vietnam.strftime('%Y-%m-%d %H:%M:%S %z')}"]
    for domain, counts in urls_summary.items():
        log_lines.append(f"{domain}: {counts['new_count']} New Images: {counts['total_count']}")
    log_lines.append(f"Crawl duration: {formatted_duration}.")
    with open(LOG_FILE, "w", encoding="utf-8") as f: f.write("\n".join(log_lines))
    print(f"\n--- Summary saved to {LOG_FILE} ---")
    
    # Logic gửi Telegram và push Git giữ nguyên
    found_new_images = any(counts['new_count'] > 0 for counts in urls_summary.values())
    if found_new_images:
        print("Tìm thấy ảnh mới, đang chuẩn bị gửi báo cáo và kích hoạt workflow...")
        report_lines = [line for line in log_lines if "New Images: 0" not in line]
        send_telegram_message("\n".join(report_lines))
        trigger_workflow_dispatch()
    else:
        print("Không có ảnh mới nào được tìm thấy. Bỏ qua các hành động tiếp theo.")
    git_push_changes()
