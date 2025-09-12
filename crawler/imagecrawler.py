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
# Lấy đường dẫn thư mục gốc của dự án (imagecrawler/)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

CRAWLER_DIR = os.path.join(BASE_DIR, 'crawler')
DOMAIN_DIR = os.path.join(BASE_DIR, 'domain')
CONFIG_FILE = os.path.join(CRAWLER_DIR, 'config.json')
STOP_URLS_FILE = os.path.join(BASE_DIR, 'stop_urls.txt')
LOG_FILE = os.path.join(BASE_DIR, 'imagecrawler.log')
ENV_FILE = os.path.join(BASE_DIR, '.env')

# Tải biến môi trường từ file .env
load_dotenv(dotenv_path=ENV_FILE)
# --- END: Cấu hình đường dẫn ---


# Constants
MAX_URLS = 500
MAX_PREVNEXT_URLS = 200
MAX_API_PAGES = 1
DEFAULT_API_URL_PATTERN = "https://{domain}/wp-json/wp/v2/product?per_page=100&page={page}&orderby=date&order=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
REPO_URL_PATTERN = "https://raw.githubusercontent.com/chanktb/productcrawler/main/domain/{domain}.txt"
STOP_URLS_COUNT = 10

# ----------------------------------------------------------------------------------------------------------------------
# NEW: Các hàm cho Telegram và Git
# ----------------------------------------------------------------------------------------------------------------------

def send_telegram_message(message):
    """Gửi tin nhắn báo cáo tới Telegram."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        print("Cảnh báo: TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID không được thiết lập. Bỏ qua việc gửi tin nhắn.")
        return

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(api_url, data=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Đã gửi báo cáo thành công tới Telegram.")
        else:
            print(f"❌ Lỗi khi gửi báo cáo Telegram: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối tới Telegram API: {e}")

def git_push_changes():
    """Tự động commit và push các thay đổi lên GitHub nếu không chạy trên GitHub Actions."""
    # Kiểm tra biến môi trường GITHUB_ACTIONS, nếu có nghĩa là đang chạy trên Actions
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print("Đang chạy trên GitHub Actions, bỏ qua git push.")
        return

    print("Đang chạy trên máy tính cục bộ, tiến hành push thay đổi lên GitHub...")
    try:
        # Chuyển vào thư mục gốc của repo
        os.chdir(BASE_DIR)

        # Cấu hình user git
        subprocess.run(['git', 'config', 'user.name', 'ktbihow'], check=True)
        subprocess.run(['git', 'config', 'user.email', '230660483+ktbihow@users.noreply.github.com'], check=True)

        # Add, commit và push
        subprocess.run(['git', 'add', 'domain/', 'stop_urls.txt', 'imagecrawler.log'], check=True)
        
        # Kiểm tra xem có thay đổi để commit không
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status_result.stdout.strip():
            print("Không có thay đổi nào để commit.")
            return

        commit_message = f"Auto-update crawled data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        subprocess.run(['git', 'push'], check=True)
        
        print("✅ Đã push thành công các thay đổi lên GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi khi thực hiện lệnh git: {e}")
    except FileNotFoundError:
        print("❌ Lỗi: Lệnh 'git' không được tìm thấy. Hãy chắc chắn Git đã được cài đặt và có trong PATH.")
    except Exception as e:
        print(f"❌ Đã xảy ra lỗi không xác định khi push: {e}")

def trigger_workflow_dispatch():
    """
    Kích hoạt một sự kiện repository_dispatch trên một repo khác
    nếu có PAT được cung cấp.
    """
    pat = os.getenv('KTBHUB_PAT')
    if not pat:
        print("Cảnh báo: Biến môi trường KTBHUB_PAT không được thiết lập. Bỏ qua việc kích hoạt workflow.")
        return

    owner = "ktbhub"
    repo_name = "ktb-image"
    event_type = "new_image_available"
    
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/dispatches"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {pat}",
    }
    
    data = {"event_type": event_type}

    print(f"🚀 Kích hoạt workflow '{event_type}' trên repo {owner}/{repo_name}...")
    
    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=15)
        # Mã 204 No Content là thành công cho API này
        if response.status_code == 204:
            print("✅ Đã gửi yêu cầu kích hoạt workflow thành công.")
        else:
            print(f"❌ Lỗi khi kích hoạt workflow: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối đến GitHub API: {e}")

# ----------------------------------------------------------------------------------------------------------------------
# Core Functions (MODIFIED paths)
# ----------------------------------------------------------------------------------------------------------------------

def load_config():
    """Tải cấu hình từ config.json trong thư mục crawler."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp {CONFIG_FILE}!")
        return []

def load_stop_urls():
    """Tải danh sách URL dừng từ stop_urls.txt ở thư mục gốc."""
    try:
        with open(STOP_URLS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_stop_urls(stop_urls):
    """Lưu danh sách URL dừng vào stop_urls.txt ở thư mục gốc."""
    with open(STOP_URLS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stop_urls, f, indent=2)

def check_url_exists(url):
    """Kiểm tra xem một URL có tồn tại không bằng cách gửi yêu cầu HEAD."""
    try:
        r = requests.head(url, headers=HEADERS, timeout=10)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False

def apply_replacements(image_url, replacements, always_replace=False):
    """
    Áp dụng logic thay thế URL hình ảnh.
    Đối với API, nếu always_replace=True, sẽ thay thế mà không cần checkhead.
    """
    final_img_url = image_url
    
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    
                    if always_replace:
                        return new_url
                    
                    if check_url_exists(new_url):
                        print(f"✅ Found a valid replacement URL: {new_url}")
                        return new_url
                    else:
                        print(f"❌ Replacement URL not found: {new_url}. Trying next...")
                return image_url
    
    return final_img_url

def apply_fallback_logic(image_url, url_data):
    """
    Áp dụng logic thay thế đặc biệt (cut_filename_prefix) một cách thông minh hơn.
    Nó chỉ áp dụng logic này nếu tên file phù hợp với định dạng nhiễu đã cho (ví dụ: 8 ký tự + '-').
    """
    fallback_rules = url_data.get('fallback_rules', {})

    if not fallback_rules or fallback_rules.get('type') != 'cut_filename_prefix':
        return image_url

    parsed_url = urlparse(image_url)
    if parsed_url.netloc != fallback_rules.get('domain'):
        return image_url

    path_parts = parsed_url.path.split('/')
    filename = path_parts[-1]
    prefix_length = fallback_rules.get('prefix_length', 0)
    
    if len(filename) > prefix_length and filename[prefix_length - 1] == '-':
        prefix = filename[:prefix_length-1]
        
        if re.match(r'^[a-zA-Z0-9_-]+$', prefix):
            new_filename = filename[prefix_length:]
            new_path = '/'.join(path_parts[:-1] + [new_filename])
            modified_url = parsed_url._replace(path=new_path).geturl()

            print(f"[{url_data['url']}] Checking fallback URL: {modified_url}")
            if check_url_exists(modified_url):
                print(f"[{url_data['url']}] ✅ Found valid URL using fallback logic for original: {image_url}")
                return modified_url
            else:
                print(f"[{url_data['url']}] ❌ Fallback URL not found. Using original.")
                
    return image_url
# ----------------------------------------------------------------------------------------------------------------------
# Crawl Functions
# ----------------------------------------------------------------------------------------------------------------------
def find_best_image_url(soup, url_data):
    """
    Tìm URL hình ảnh tốt nhất dựa trên logic ưu tiên.
    Áp dụng cho loại `product-list` và `prevnext`.
    """
    replacements = url_data.get('replacements', {})
    selector = url_data.get('selector')
    
    if isinstance(replacements, list):
        for suffix in replacements:
            if selector:
                image_tags_to_search = soup.select(selector)
            else:
                image_tags_to_search = soup.find_all('img')

            for img_tag in image_tags_to_search:
                img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
                if img_url and img_url.endswith(suffix):
                    print(f"Found prioritized URL in HTML: {img_url}")
                    return img_url
    
    og_image_tag = soup.find('meta', property='og:image')
    if og_image_tag:
        img_url = og_image_tag.get('content')
        if img_url:
            print(f"Using fallback og:image URL: {img_url}")
            return img_url
            
    if not selector and not replacements:
        for img_tag in soup.find_all('img'):
            img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
            if img_url:
                print(f"Using standard img tag URL: {img_url}")
                return img_url
            
    return None

def fetch_image_urls_from_api(url_data, stop_urls_list):
    """
    Tải và phân tích URL hình ảnh từ API.
    """
    all_image_urls = []
    new_product_urls_found = []
    page = 1
    domain = urlparse(url_data['url']).netloc
    
    while page <= MAX_API_PAGES:
        api_url = DEFAULT_API_URL_PATTERN.format(domain=domain, page=page)
        print(f"Fetching from API: {api_url}")
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            
            for item in data:
                product_url = item.get('link')
                if product_url and product_url in stop_urls_list:
                    print(f"Đã tìm thấy URL dừng: {product_url}, kết thúc crawl.")
                    return all_image_urls, new_product_urls_found
                
                img_url = None
                if 'yoast_head_json' in item and 'og_image' in item['yoast_head_json'] and len(item['yoast_head_json']['og_image']) > 0:
                    img_url = item['yoast_head_json']['og_image'][0]['url']
                
                if not img_url and 'content' in item and 'rendered' in item['content']:
                    soup = BeautifulSoup(item['content']['rendered'], 'html.parser')
                    img_tag = soup.find('img')
                    if img_tag and img_tag.get('src'):
                        img_url = img_tag.get('src')
                
                if img_url:
                    if img_url.startswith('http://'):
                        img_url = img_url.replace('http://', 'https://')
                    
                    final_img_url = apply_replacements(img_url, url_data.get('replacements', {}), url_data.get('always_replace', False))
                    final_img_url = apply_fallback_logic(final_img_url, url_data)
                    
                    if final_img_url not in all_image_urls:
                        all_image_urls.append(final_img_url)
                        if product_url:
                            new_product_urls_found.append(product_url)
            
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi truy cập API {api_url}: {e}")
            break
            
    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_prevnext(url_data, stop_urls_list):
    """Crawl sản phẩm theo chuỗi next/prev."""
    all_image_urls = []
    new_product_urls_found = []
    domain = urlparse(url_data['url']).netloc

    try:
        r = requests.get(url_data['url'], headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        first_product_tag = soup.select_one(url_data['first_product_selector'])
        if not first_product_tag:
            print(f"Không tìm thấy sản phẩm đầu tiên trên {url_data['url']}")
            return [], []
        current_product_url = urljoin(url_data['url'], first_product_tag.get('href'))
        last_successful_product_url = None
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi truy cập trang chủ {url_data['url']}: {e}")
        return [], []

    count = 0
    while count < MAX_PREVNEXT_URLS:
        if current_product_url in stop_urls_list:
            print(f"Đã tìm thấy URL dừng: {current_product_url}, kết thúc crawl.")
            break

        try:
            r = requests.get(current_product_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = apply_fallback_logic(best_url, url_data)
                
                if final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(current_product_url)
            
            last_successful_product_url = current_product_url
            
            next_product_tag = soup.select_one(url_data['next_product_selector'])
            if not next_product_tag or not next_product_tag.get('href'):
                print("Không tìm thấy sản phẩm tiếp theo, kết thúc.")
                break
            
            current_product_url = urljoin(current_product_url, next_product_tag.get('href'))
            count += 1
        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi truy cập {current_product_url}: {e}")
            print(f"URL thành công gần nhất: {last_successful_product_url}")
            
            repo_file_url = REPO_URL_PATTERN.format(domain=domain)
            try:
                repo_file = requests.get(repo_file_url, headers=HEADERS, timeout=30)
                if repo_file.status_code == 200:
                    repo_urls = [line.strip() for line in repo_file.text.splitlines() if line.strip()]
                    if last_successful_product_url and last_successful_product_url in repo_urls:
                        last_crawled_index = repo_urls.index(last_successful_product_url)
                        next_urls_to_check = repo_urls[last_crawled_index + 1 : last_crawled_index + 4]
                        
                        found_next_valid = False
                        for next_url in next_urls_to_check:
                            if check_url_exists(next_url):
                                current_product_url = next_url
                                print(f"Phục hồi crawl từ URL: {current_product_url}")
                                found_next_valid = True
                                break
                        
                        if found_next_valid:
                            continue
                        else:
                            print("Không thể tìm thấy URL hợp lệ trong repo, kết thúc.")
                            break
                    else:
                        print("URL gần nhất không có trong repo, kết thúc.")
                        break
                else:
                    print(f"Không thể truy cập repo {repo_file_url}, kết thúc.")
                    break
            except requests.exceptions.RequestException as ex:
                print(f"Lỗi khi truy cập repo: {ex}, kết thúc.")
                break

    return all_image_urls, new_product_urls_found

def fetch_image_urls_from_product_list(url_data, stop_urls_list):
    """Tải danh sách URL sản phẩm từ repo và crawl từng trang để lấy ảnh."""
    all_image_urls = []
    new_product_urls_found = []
    domain = urlparse(url_data['url']).netloc
    repo_file_url = REPO_URL_PATTERN.format(domain=domain)
    
    try:
        r = requests.get(repo_file_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        product_urls = [line.strip() for line in r.text.splitlines() if line.strip()]
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi truy cập repo sản phẩm: {e}. Bỏ qua domain này.")
        return [], []
    
    urls_to_crawl = []
    
    if stop_urls_list:
        found_stop_point = False
        for product_url in product_urls:
            if product_url in stop_urls_list:
                print(f"Đã tìm thấy URL dừng: {product_url}, kết thúc tìm kiếm sản phẩm mới.")
                found_stop_point = True
                break
            urls_to_crawl.append(product_url)
        
        if not found_stop_point:
            print(f"Không tìm thấy URL dừng cho {domain}. Crawl toàn bộ danh sách.")
            urls_to_crawl = product_urls
    else:
        urls_to_crawl = product_urls

    for product_url in urls_to_crawl:
        if len(all_image_urls) >= MAX_PREVNEXT_URLS:
            print("Đạt giới hạn URL, kết thúc crawl.")
            break

        try:
            r = requests.get(product_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = apply_fallback_logic(best_url, url_data)
                
                if final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(product_url)

        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi truy cập URL sản phẩm {product_url}: {e}. Bỏ qua.")
            continue

    return all_image_urls, new_product_urls_found

# ----------------------------------------------------------------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------------------------------------------------------------

def save_urls(domain, new_urls):
    """Lưu các URL mới vào đầu tệp của domain trong thư mục `domain`."""
    if not os.path.exists(DOMAIN_DIR):
        os.makedirs(DOMAIN_DIR)
        
    filename = os.path.join(DOMAIN_DIR, f"{domain}.txt")

    try:
        with open(filename, "r", encoding="utf-8") as f:
            existing_urls = [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        existing_urls = []

    unique_new_urls = [u for u in new_urls if u not in existing_urls]
    all_urls = unique_new_urls + existing_urls
    all_urls = all_urls[:MAX_URLS]
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(all_urls))

    print(f"[{domain}] Added {len(unique_new_urls)} new URLs. Total: {len(all_urls)}")
    return len(unique_new_urls), len(all_urls)

if __name__ == "__main__":
    start_time = time.time()
    
    configs = load_config()
    if not configs:
        exit(1)

    urls_summary = {}
    stop_urls_data = load_stop_urls()
    
    if not os.path.exists(DOMAIN_DIR):
        os.makedirs(DOMAIN_DIR)

    for url_data in configs:
        domain = urlparse(url_data['url']).netloc
        
        domain_file_path = os.path.join(DOMAIN_DIR, f"{domain}.txt")
        try:
            with open(domain_file_path, "r", encoding="utf-8") as f:
                existing_urls = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            existing_urls = []
        
        source_type = url_data.get('source_type')
        
        image_urls = []
        new_product_urls_found = []
        
        if source_type == 'api':
            domain_stop_urls_list = stop_urls_data.get(domain, [])
            image_urls, new_product_urls_found = fetch_image_urls_from_api(url_data, set(domain_stop_urls_list))
        elif source_type == 'prevnext':
            domain_stop_urls_list = stop_urls_data.get(domain, [])
            image_urls, new_product_urls_found = fetch_image_urls_from_prevnext(url_data, set(domain_stop_urls_list))
        elif source_type == 'product-list':
            domain_stop_urls_list = stop_urls_data.get(domain, [])
            image_urls, new_product_urls_found = fetch_image_urls_from_product_list(url_data, set(domain_stop_urls_list))
        else:
            print(f"Lỗi: Không xác định được source_type cho domain {domain}. Bỏ qua.")
            continue
            
        print(f"[{domain}] Found {len(image_urls)} potential image URLs.")
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