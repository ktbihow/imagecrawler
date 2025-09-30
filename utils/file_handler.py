# utils/file_handler.py
import json
import os
import re
import requests
from datetime import datetime
from urllib.parse import urlparse
from .constants import CONFIG_FILE, STOP_URLS_FILE, DOMAIN_DIR, MAX_URLS, HEADERS

# --- Các hàm load/save cũ (giữ nguyên) ---
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError:
        print(f"LỖI: Không tìm thấy file config tại: {CONFIG_FILE}")
        return []

def load_stop_urls():
    try:
        with open(STOP_URLS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_stop_urls(stop_urls):
    with open(STOP_URLS_FILE, 'w', encoding='utf-8') as f: json.dump(stop_urls, f, indent=2)

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
    if discarded_count > 0: console_report += f" Discarded {discarded_count} old URLs."
    console_report += f" Total: {len(all_urls)}"
    print(console_report)
    return len(unique_new_urls), len(all_urls)

# --- Hàm tiện ích và chức năng download nâng cấp ---
def sanitize_filename(name):
    """Làm sạch một chuỗi để nó trở thành một tên file hợp lệ."""
    if not name: return ""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.replace(" ", "-").lower()
    return name[:150]

def download_images_for_domain(final_results, domain, url_data):
    """
    Tải ảnh với logic tạo tên file 4 cấp độ ưu tiên: Regex Replace > Regex Cut > Tiêu đề > Tên gốc.
    """
    if not final_results: return
    
    # Lấy các tùy chọn download từ config
    replace_config = url_data.get("download_filename_regex_replace")
    cut_pattern = url_data.get("download_filename_regex_cut")
    use_title_as_filename = url_data.get("download_filename_from_title", False)

    base_download_dir = os.path.join(os.path.dirname(DOMAIN_DIR), 'downloaded')
    os.makedirs(base_download_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    temp_folder_name = f"{domain}.{timestamp}.temp"
    temp_download_path = os.path.join(base_download_dir, temp_folder_name)
    os.makedirs(temp_download_path, exist_ok=True)
    
    print(f"[{domain}] Bắt đầu tải {len(final_results)} ảnh vào thư mục tạm: {temp_folder_name}")
    download_count = 0
    
    for item in final_results:
        image_url = item.get('image_url')
        product_url = item.get('product_url')
        if not image_url or not product_url: continue
        
        try:
            # --- LOGIC TẠO TÊN FILE 4 CẤP ƯU TIÊN ---
            filename_base = ""
            slug = urlparse(product_url).path.split('/')[-1]
            
            # 1. Ưu tiên 1: Tìm và thay thế bằng Regex (Mới)
            if replace_config and isinstance(replace_config, dict):
                pattern = replace_config.get('pattern')
                replacement = replace_config.get('replacement', '')
                if pattern:
                    filename_base = re.sub(pattern, replacement, slug)
                    # Xử lý các trường hợp tạo ra dấu -- hoặc bắt đầu/kết thúc bằng -
                    filename_base = re.sub(r'--+', '-', filename_base).strip('-')

            # 2. Ưu tiên 2: Cắt chuỗi bằng Regex (Cũ)
            if not filename_base and cut_pattern:
                filename_base = re.sub(cut_pattern, "", slug)

            # 3. Ưu tiên 3: Dùng tiêu đề sản phẩm
            if not filename_base and use_title_as_filename and item.get('product_title'):
                filename_base = item.get('product_title')

            # 4. Ưu tiên 4: Dùng tên file gốc
            original_image_name = image_url.split('/')[-1].split('?')[0]
            if not filename_base:
                filename_base = os.path.splitext(original_image_name)[0]
            
            safe_filename_base = sanitize_filename(filename_base)
            file_extension = os.path.splitext(original_image_name)[1] or '.webp'
            filename = f"{safe_filename_base}{file_extension}"
            # --- KẾT THÚC LOGIC TẠO TÊN FILE ---

            filepath = os.path.join(temp_download_path, filename)
            if os.path.exists(filepath):
                print(f"    -> Bỏ qua (Tên file đã tồn tại): {filename}")
                continue

            r = requests.get(image_url, headers=HEADERS, timeout=60, stream=True)
            r.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            
            download_count += 1
            print(f"    ({download_count}/{len(final_results)}) Tải thành công: {filename}")

        except Exception as e:
            print(f"    -> Lỗi trong quá trình download/xử lý file: {e}")

    # Đổi tên thư mục tạm thành tên cuối cùng
    if download_count > 0:
        final_folder_name = f"{domain}.{timestamp}.{download_count}_images"
        final_download_path = os.path.join(base_download_dir, final_folder_name)
        os.rename(temp_download_path, final_download_path)
        print(f"✅ Hoàn tất! Đã lưu {download_count} ảnh vào thư mục: {final_folder_name}")
    else:
        os.rmdir(temp_download_path)
        print(f"[{domain}] Không có ảnh mới nào được tải về.")