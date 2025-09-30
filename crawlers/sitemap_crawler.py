# crawlers/sitemap_crawler.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from utils.constants import HEADERS
from utils.url_processor import process_and_finalize_url

def crawl(url_data, stop_urls_list):
    """
    Crawl sitemap with mandatory keyword filtering and optional design deduplication.
    """
    unfiltered_results = []
    new_product_urls_found = []
    processed_design_bases = set()

    # Lấy các tùy chọn nâng cao từ config
    main_sitemap_url = url_data['url']
    product_url_keywords = url_data.get('product_url_keywords', [])
    product_url_exclusions = url_data.get('product_url_exclusions', [])
    crawl_backwards = url_data.get('crawl_sitemap_backwards', False)
    sitemap_limit = url_data.get('sitemap_crawl_limit', 1)
    
    # Lấy "công tắc" điều khiển việc khử trùng lặp design, mặc định là True
    enable_deduplication = url_data.get('enable_design_deduplication', True)

    try:
        # Giai đoạn 1: Lấy danh sách sitemap sản phẩm
        # ... (Phần code này giữ nguyên) ...
        print(f"-> Đang quét sitemap chính: {main_sitemap_url}")
        r_index = requests.get(main_sitemap_url, headers=HEADERS, timeout=30)
        r_index.raise_for_status()
        soup_index = BeautifulSoup(r_index.content, 'xml')
        product_sitemaps = [loc.text for loc in soup_index.find_all('loc') if '_products_' in loc.text]
        if not product_sitemaps:
            print("LỖI: Không tìm thấy sitemap sản phẩm.")
            return [], []
        target_sitemaps = product_sitemaps[-sitemap_limit:]
        print(f"-> Tìm thấy {len(target_sitemaps)} sitemap sản phẩm để quét.")

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

            for url_entry in url_entries:
                product_url_tag = url_entry.find('loc')
                if not product_url_tag: continue
                product_url = product_url_tag.text

                # --- BỘ LỌC KEYWORDS (LUÔN CHẠY) ---
                url_path = urlparse(product_url).path
                # Cổng 1: Inclusion
                if product_url_keywords and not any(keyword in url_path for keyword in product_url_keywords):
                    continue
                # Cổng 2: Exclusion
                if product_url_exclusions and any(keyword in url_path for keyword in product_url_exclusions):
                    continue
                
                # --- LOGIC KHỬ TRÙNG LẶP DESIGN (CÓ THỂ BẬT/TẮT) ---
                if enable_deduplication:
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

                if product_url in stop_urls_list:
                    print(f"-> Đã gặp stop URL. Dừng toàn bộ quá trình quét sitemap.")
                    stop_url_was_hit = True
                    break

                image_url_tag = url_entry.find('image:loc')
                if not image_url_tag: continue
                raw_image_url = image_url_tag.text
                final_img_url = process_and_finalize_url(raw_image_url, url_data)

                if final_img_url:
                    unfiltered_results.append({
                        'image_url': final_img_url,
                        'product_url': product_url,
                        'product_title': ''
                    })
                    new_product_urls_found.append(product_url)
            
            if stop_url_was_hit:
                break

    except Exception as e:
        print(f"LỖI: Có lỗi xảy ra trong quá trình xử lý sitemap. {e}")
        return [], []

    return unfiltered_results, new_product_urls_found