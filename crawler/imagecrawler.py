import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import json
import re
from datetime import datetime
import pytz
import subprocess
import time
from dotenv import load_dotenv

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

# Constants
MAX_URLS = 700
MAX_PREVNEXT_URLS = 200
MAX_API_PAGES = 1
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/chanktb/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# ----------------------------------------------------------------------------------------------------------------------
# DEBUG FUNCTION: Hàm chẩn đoán lỗi so sánh
# ----------------------------------------------------------------------------------------------------------------------
def debug_stop_url_comparison(product_url, stop_urls_list, domain):
    """
    Hàm này không sửa lỗi, chỉ in ra thông tin chi tiết để tìm ra vấn đề.
    """
    print("\n--- DEBUGGING STOP URL ---")
    print(f"Domain: {domain}")
    print(f"URL từ Web      : '{product_url}'")
    print(f"Loại dữ liệu    : {type(product_url)}")
    print(f"Độ dài chuỗi    : {len(product_url)}")
    print("-" * 20)
    
    found_match = False
    if not stop_urls_list:
        print("Danh sách Stop URLs đang rỗng.")
    else:
        print(f"Kiểm tra với {len(stop_urls_list)} Stop URLs:")
        for i, stop_url in enumerate(stop_urls_list):
            # Chỉ in chi tiết 5 URL đầu tiên và các URL có khả năng khớp để tránh làm loãng log
            if i < 5 or len(product_url) == len(stop_url):
                is_match = (product_url == stop_url)
                if is_match:
                    found_match = True
                
                print(f"  - So sánh với Stop URL: '{stop_url}'")
                print(f"    -> Loại dữ liệu    : {type(stop_url)}")
                print(f"    -> Độ dài chuỗi    : {len(stop_url)}")
                print(f"    -> KẾT QUẢ SO SÁNH : {is_match}")
                # Nếu không khớp, in ra ký tự khác biệt đầu tiên
                if not is_match and len(product_url) == len(stop_url):
                    for char_index, (c1, c2) in enumerate(zip(product_url, stop_url)):
                        if c1 != c2:
                            print(f"    -> Khác biệt đầu tiên ở vị trí {char_index}: Web='{c1}' (mã {ord(c1)}) vs File='{c2}' (mã {ord(c2)})")
                            break

    print(f"\n>>> KẾT LUẬN DEBUG: Script sẽ DỪNG? -> {product_url in stop_urls_list}")
    print("--- END DEBUGGING ---\n")

# ----------------------------------------------------------------------------------------------------------------------
# Core Functions (Lấy từ code gốc của bạn)
# ----------------------------------------------------------------------------------------------------------------------

def send_telegram_message(message):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id: return
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
    try: requests.post(api_url, data=payload, timeout=10)
    except requests.exceptions.RequestException: pass

def git_push_changes():
    if os.getenv('GITHUB_ACTIONS') == 'true': return
    try:
        os.chdir(BASE_DIR)
        subprocess.run(['git', 'config', 'user.name', 'ktbihow'], check=True)
        subprocess.run(['git', 'config', 'user.email', '230660483+ktbihow@users.noreply.github.com'], check=True)
        subprocess.run(['git', 'add', 'domain/', 'stop_urls.txt', 'imagecrawler.log'], check=True)
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status_result.stdout.strip(): return
        commit_message = f"Auto-update crawled data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        subprocess.run(['git', 'push'], check=True)
    except Exception: pass

def trigger_workflow_dispatch():
    pat = os.getenv('KTBHUB_PAT')
    if not pat: return
    owner, repo_name, event_type = "ktbhub", "ktb-image", "new_image_available"
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/dispatches"
    headers = {"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {pat}"}
    data = {"event_type": event_type}
    try: requests.post(api_url, headers=headers, json=data, timeout=15)
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

def check_url_exists(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=10)
        return r.status_code == 200
    except requests.exceptions.RequestException: return False

def apply_replacements(image_url, replacements, always_replace=False):
    final_img_url = image_url
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    if always_replace: return new_url
                    if check_url_exists(new_url): return new_url
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
            if check_url_exists(modified_url): return modified_url
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

def fetch_image_urls_from_api(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, page, domain = [], [], 1, urlparse(url_data['url']).netloc
    while page <= MAX_API_PAGES:
        api_url = DEFAULT_API_URL_PATTERN.format(domain=domain, page=page)
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=30); r.raise_for_status(); data = r.json()
            if not data: break
            for item in data:
                product_url = item.get('link')
                if product_url:
                    # GỌI HÀM CHẨN ĐOÁN
                    debug_stop_url_comparison(product_url, stop_urls_list, domain)
                    if product_url in stop_urls_list:
                        print(f"==> SCRIPT ĐÃ DỪNG TẠI API <==")
                        return all_image_urls, new_product_urls_found
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
        # GỌI HÀM CHẨN ĐOÁN
        debug_stop_url_comparison(current_product_url, stop_urls_list, domain)
        if current_product_url in stop_urls_list:
            print(f"==> SCRIPT ĐÃ DỪNG TẠI PREVNEXT <==")
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
        except requests.exceptions.RequestException: break
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
            # GỌI HÀM CHẨN ĐOÁN
            debug_stop_url_comparison(product_url, stop_urls_list, domain)
            if product_url in stop_urls_list:
                print(f"==> SCRIPT ĐÃ DỪNG TẠI PRODUCT-LIST <==")
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
# Main Execution (Sử dụng logic gốc của bạn)
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    start_time = time.time()
    configs = load_config()
    if not configs: exit(1)

    urls_summary = {}
    stop_urls_data = load_stop_urls()
    
    if not os.path.exists(DOMAIN_DIR): os.makedirs(DOMAIN_DIR)

    for url_data in configs:
        domain = urlparse(url_data['url']).netloc
        source_type = url_data.get('source_type')
        image_urls = []
        new_product_urls_found = []
        domain_stop_urls_list = set(stop_urls_data.get(domain, []))

        if source_type == 'api':
            image_urls, new_product_urls_found = fetch_image_urls_from_api(url_data, domain_stop_urls_list)
        elif source_type == 'prevnext':
            image_urls, new_product_urls_found = fetch_image_urls_from_prevnext(url_data, domain_stop_urls_list)
        elif source_type == 'product-list':
            image_urls, new_product_urls_found = fetch_image_urls_from_product_list(url_data, domain_stop_urls_list)
        else:
            continue
            
        new_urls_count, total_urls_count = save_urls(domain, image_urls)
        urls_summary[domain] = {'new_count': new_urls_count, 'total_count': total_urls_count}
        
        if new_product_urls_found:
            stop_urls_data[domain] = new_product_urls_found[:STOP_URLS_COUNT]
        elif domain in stop_urls_data:
            stop_urls_data[domain] = stop_urls_data.get(domain, [])[:STOP_URLS_COUNT]
        
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
