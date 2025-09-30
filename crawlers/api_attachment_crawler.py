# crawlers/api_attachment_crawler.py
import requests
from urllib.parse import urlparse

from utils.constants import MAX_API_PAGES, DEFAULT_API_URL_PATTERN, HEADERS
from utils.url_processor import process_and_finalize_url

def crawl(url_data, stop_urls_list):
    """
    Crawl images from 'wp:attachment', prioritizing `media_details.sizes`
    and falling back to `guid.rendered`.
    """
    all_image_urls = []
    new_product_urls_found = []
    page = 1
    domain = urlparse(url_data['url']).netloc
    stop_url_found = None
    
    search_prefix = url_data.get("attachment_prefix_filter")
    if not search_prefix:
        print(f"CẢNH BÁO: [{domain}] Cấu hình thiếu 'attachment_prefix_filter'. Crawler này sẽ không hoạt động.")
        return [], []

    while page <= MAX_API_PAGES and not stop_url_found:
        api_url = DEFAULT_API_URL_PATTERN.format(domain=domain, page=page)
        try:
            product_response = requests.get(api_url, headers=HEADERS, timeout=30)
            product_response.raise_for_status()
            products_data = product_response.json()
            if not products_data:
                break

            for item in products_data:
                product_url = item.get('link')
                if product_url and product_url in stop_urls_list:
                    stop_url_found = product_url
                    break
                
                attachment_link = item.get('_links', {}).get('wp:attachment', [{}])[0].get('href')
                if not attachment_link:
                    continue

                try:
                    attachment_response = requests.get(attachment_link, headers=HEADERS, timeout=20)
                    attachment_response.raise_for_status()
                    media_list = attachment_response.json()

                    for media_item in media_list:
                        # --- LOGIC LẤY URL ẢNH ĐÃ NÂNG CẤP ---
                        img_url = None
                        
                        # Bước 1: Ưu tiên tìm URL từ `media_details` với chất lượng tốt nhất
                        media_details = media_item.get('media_details', {})
                        sizes = media_details.get('sizes', {})
                        preferred_sizes = ['full', 'large', 'medium', 'thumbnail']
                        
                        for size in preferred_sizes:
                            if size in sizes and sizes[size].get('source_url'):
                                img_url = sizes[size]['source_url']
                                print(f"    -> Tìm thấy ảnh từ media_details (size: {size})")
                                break # Đã tìm thấy ảnh tốt nhất, dừng tìm kiếm

                        # Bước 2: Nếu không tìm thấy, quay về phương pháp cũ (guid.rendered) làm dự phòng
                        if not img_url:
                            img_url = media_item.get('guid', {}).get('rendered', '')
                            if img_url:
                                print(f"    -> Tìm thấy ảnh bằng phương pháp dự phòng (guid)")
                        # --- KẾT THÚC LOGIC NÂNG CẤP ---

                        # Chỉ xử lý nếu đã tìm được img_url
                        if img_url:
                            filename = img_url.split('/')[-1]
                            if filename.lower().startswith(search_prefix.lower()):
                                final_img_url = process_and_finalize_url(img_url, url_data)
                                if final_img_url and final_img_url not in [d.get('image_url') for d in all_image_urls]:
                                    all_image_urls.append({"image_url": final_img_url, "product_url": product_url})
                                    if product_url:
                                        new_product_urls_found.append(product_url)
                                break 
                
                except requests.exceptions.RequestException as e:
                    print(f"    -> Lỗi khi gọi API attachment {attachment_link}: {e}")
                    continue

            page += 1
        except requests.exceptions.RequestException as e:
            print(f"    -> Lỗi khi gọi API sản phẩm {api_url}: {e}")
            break
            
    if stop_url_found:
        print(f"[{domain}] Found {len(new_product_urls_found)} new URLs. Stopped at stop URL.")
        
    # Chuyển đổi cấu trúc dữ liệu trả về để nhất quán với các crawler khác
    final_image_urls = [item['image_url'] for item in all_image_urls]
    return final_image_urls, new_product_urls_found