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

# --- Cấu hình và các hằng số (Giữ nguyên như file gốc của bạn) ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CRAWLER_DIR = os.path.join(BASE_DIR, 'crawler')
DOMAIN_DIR = os.path.join(BASE_DIR, 'domain')
CONFIG_FILE = os.path.join(CRAWLER_DIR, 'config.json')
STOP_URLS_FILE = os.path.join(BASE_DIR, 'stop_urls.txt')
LOG_FILE = os.path.join(BASE_DIR, 'imagecrawler.log')
ENV_FILE = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_FILE)
MAX_URLS = 700
MAX_PREVNEXT_URLS = 200
MAX_API_PAGES = 1
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/chanktb/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# --- Các hàm gốc của bạn (không thay đổi logic) ---
def send_telegram_message(message):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id: return
    try: requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data={'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}, timeout=10)
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

def check_url_exists(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=10)
        return r.status_code == 200
    except requests.exceptions.RequestException: return False

def apply_replacements(image_url, replacements, always_replace=False):
    # ... (Giữ nguyên hàm gốc)
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
    # ... (Giữ nguyên hàm gốc)
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
    # ... (Giữ nguyên hàm gốc)
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
    # ... (Giữ nguyên hàm gốc)
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
    # ... (Giữ nguyên hàm gốc)
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
        except requests.exceptions.RequestException: break
    return all_image_urls, new_product_urls_found

# --- HÀM DUY NHẤT ĐƯỢC THAY ĐỔI ĐỂ CHẨN ĐOÁN ---
def fetch_image_urls_from_product_list(url_data, stop_urls_list):
    all_image_urls, new_product_urls_found, domain = [], [], urlparse(url_data['url']).netloc
    repo_file_url = REPO_URL_PATTERN.format(domain=domain)
    
    # --- START SUPER DEBUG BLOCK ---
    print("\n" + "="*60)
    print(f"BẮT ĐẦU CHẨN ĐOÁN CHO DOMAIN (product-list): {domain}")
    print(f"Đang cố gắng tải danh sách sản phẩm từ : {repo_file_url}")
    # --- END SUPER DEBUG BLOCK ---

    product_urls = []
    try:
        r = requests.get(repo_file_url, headers=HEADERS, timeout=30)
        print(f"Phản hồi từ GitHub: Status Code = {r.status_code}")
        r.raise_for_status()
        
        content = r.text
        print(f"Nội dung file nhận được (200 ký tự đầu): '{content[:200].replace(chr(10), ' ')}...'")
        
        product_urls = [line.strip() for line in content.splitlines() if line.strip()]
        print(f"Số lượng URL sản phẩm đã tải được từ repo: {len(product_urls)}")
        print(f"Số lượng Stop URLs được truyền vào         : {len(stop_urls_list)}")
        print("="*60 + "\n")

    except requests.exceptions.RequestException as e:
        print(f"LỖI NGHIÊM TRỌNG: Không thể tải file từ repo. Lỗi: {e}")
        return [], []
    
    # Logic stop URL gốc của bạn
    urls_to_crawl = []
    if stop_urls_list:
        found_stop_point = False
        for product_url in product_urls:
            if product_url in stop_urls_list:
                print(f"==> ĐÃ TÌM THẤY STOP URL VÀ DỪNG LẠI: {product_url} <==")
                found_stop_point = True
                break
            urls_to_crawl.append(product_url)
        if not found_stop_point:
            print("Không tìm thấy stop URL nào trong danh sách sản phẩm, sẽ crawl toàn bộ.")
            urls_to_crawl = product_urls
    else:
        urls_to_crawl = product_urls
    
    print(f"Số lượng URL sẽ thực sự crawl: {len(urls_to_crawl)}")
    for product_url in urls_to_crawl:
        if len(all_image_urls) >= MAX_PREVNEXT_URLS: break
        # print(f"Crawling: {product_url}") # Tạm thời tắt để log gọn hơn
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
    # ... (Giữ nguyên hàm gốc)
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
# Main Execution (Giữ nguyên cấu trúc gốc của bạn)
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
        else: continue
            
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
