# crawlers/sitemap_crawler.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from utils.constants import HEADERS
from utils.url_processor import process_and_finalize_url

def crawl(url_data, stop_urls_list):
    """
    Crawl the last X sitemaps with advanced filtering and deduplication.
    """
    all_image_urls = []
    new_product_urls_found = []
    processed_design_bases = set()

    # Lấy các tùy chọn nâng cao từ config
    main_sitemap_url = url_data['url']
    product_url_keywords = url_data.get('product_url_keywords', [])
    product_url_exclusions = url_data.get('product_url_exclusions', [])
    crawl_backwards = url_data.get('crawl_sitemap_backwards', False)
    sitemap_limit = url_data.get('sitemap_crawl_limit', 1) # <-- Lấy giới hạn, mặc định là 1

    try:
        # Giai đoạn 1: Lấy danh sách sitemap sản phẩm
        print(f"-> Đang quét sitemap chính: {main_sitemap_url}")
        r_index = requests.get(main_sitemap_url, headers=HEADERS, timeout=30)
        r_index.raise_for_status()
        soup_index = BeautifulSoup(r_index.content, 'xml')
        
        product_sitemaps = [
            loc.text for loc in soup_index.find_all('loc') 
            if '_products_' in loc.text
        ]
        
        if not product_sitemaps:
            print("LỖI: Không tìm thấy sitemap sản phẩm.")
            return [], []
        
        # --- THAY ĐỔI LOGIC: LẤY X SITEMAP CUỐI CÙNG ---
        # Sử dụng slicing để lấy `sitemap_limit` phần tử cuối của danh sách
        target_sitemaps = product_sitemaps[-sitemap_limit:]
        print(f"-> Tìm thấy {len(target_sitemaps)}/{len(product_sitemaps)} sitemap sản phẩm để quét (giới hạn: {sitemap_limit}).")

        # Giai đoạn 2: Lặp qua từng sitemap đã chọn để quét
        stop_url_was_hit = False
        for sitemap_url in target_sitemaps:
            print(f"\n--- Bắt đầu quét sitemap: {sitemap_url} ---")
            r_products = requests.get(sitemap_url, headers=HEADERS, timeout=60)
            r_products.raise_for_status()
            soup_products = BeautifulSoup(r_products.content, 'xml')
            
            url_entries = soup_products.find_all('url')
            if crawl_backwards:
                url_entries.reverse()
                print("-> Đang quét sitemap theo thứ tự ngược.")

            for url_entry in url_entries:
                product_url_tag = url_entry.find('loc')
                if not product_url_tag: continue
                product_url = product_url_tag.text

                # Logic lọc và khử trùng lặp giữ nguyên...
                url_path = urlparse(product_url).path
                if product_url_keywords and not any(keyword in url_path for keyword in product_url_keywords):
                    continue
                if product_url_exclusions and any(keyword in url_path for keyword in product_url_exclusions):
                    continue
                
                slug = url_path.split('/')[-1]
                design_base = None
                if product_url_keywords:
                    for keyword in product_url_keywords:
                        if keyword in slug:
                            pos = slug.find(keyword)
                            design_base = slug[:pos + len(keyword)]
                            break
                if not design_base:
                    last_hyphen_pos = slug.rfind('-')
                    if last_hyphen_pos > 0:
                        design_base = slug[:last_hyphen_pos]
                
                if design_base and design_base in processed_design_bases:
                    continue
                if design_base:
                    processed_design_bases.add(design_base)

                # Cập nhật logic stop_url để dừng tất cả
                if product_url in stop_urls_list:
                    print(f"-> Đã gặp stop URL. Dừng toàn bộ quá trình quét sitemap.")
                    stop_url_was_hit = True
                    break # Dừng quét sitemap hiện tại

                image_url_tag = url_entry.find('image:loc')
                if not image_url_tag: continue
                raw_image_url = image_url_tag.text
                final_img_url = process_and_finalize_url(raw_image_url, url_data)

                if final_img_url and final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(product_url)
            
            # Nếu đã gặp stop_url, dừng luôn vòng lặp các sitemap
            if stop_url_was_hit:
                break

    except Exception as e:
        print(f"LỖI: Có lỗi xảy ra trong quá trình xử lý sitemap. {e}")
        return [], []

    return all_image_urls, new_product_urls_found