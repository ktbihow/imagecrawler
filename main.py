# main.py
import time
import pytz
from datetime import datetime
from urllib.parse import urlparse

# Import các hàm tiện ích từ thư mục utils
from utils.file_handler import load_config, load_stop_urls, save_stop_urls, save_urls
from utils.notifier import send_telegram_message
from utils.git_handler import git_push_changes, trigger_workflow_dispatch
from utils.url_processor import is_image_recent
from utils.constants import STOP_URLS_COUNT, LOG_FILE

# Import các module crawler
from crawlers import api_crawler, prevnext_crawler, product_list_crawler
from crawlers import sitemap_crawler, api_attachment_crawler
# --- Crawler Registry ---
# Ánh xạ 'source_type' trong config.json tới hàm crawl tương ứng
CRAWLER_MAPPING = {
    'api': api_crawler.crawl,
    'prevnext': prevnext_crawler.crawl,
    'product-list': product_list_crawler.crawl,
    'api-attachment': api_attachment_crawler.crawl,
    'sitemap': sitemap_crawler.crawl,
}

def main():
    """Hàm chính điều phối toàn bộ quá trình crawl."""
    start_time = time.time()
    configs = load_config()
    stop_urls_data = load_stop_urls()
    urls_summary = {}

    for url_data in configs:
        domain = urlparse(url_data['url']).netloc
        source_type = url_data.get('source_type')
        domain_stop_urls_list = set(stop_urls_data.get(domain, []))

        print(f"\n--- Processing domain: {domain} (type: {source_type}) ---")

        # Lấy hàm crawl tương ứng từ registry
        crawler_function = CRAWLER_MAPPING.get(source_type)
        if not crawler_function:
            print(f"CẢNH BÁO: Không tìm thấy crawler cho source_type '{source_type}'. Bỏ qua domain này.")
            continue

        # Gọi hàm crawl và nhận kết quả
        unfiltered_image_urls, new_product_urls_found = crawler_function(url_data, domain_stop_urls_list)

        # Lọc các ảnh không đủ mới (nếu được cấu hình)
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
        
        # Lưu kết quả và cập nhật summary
        new_urls_count, total_urls_count = save_urls(domain, final_image_urls, discarded_count)
        urls_summary[domain] = {'new_count': new_urls_count, 'total_count': total_urls_count}
        
        # Cập nhật danh sách stop_urls
        if new_product_urls_found:
            stop_urls_data[domain] = new_product_urls_found[:STOP_URLS_COUNT]
    
    save_stop_urls(stop_urls_data)
    
    # --- Tổng kết và báo cáo ---
    end_time = time.time()
    duration = end_time - start_time
    now_vietnam = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
    
    log_header = [
        f"--- Summary of Last Image Crawl ---",
        f"Timestamp: {now_vietnam.strftime('%Y-%m-%d %H:%M:%S %z')}"
    ]
    
    found_new_images = any(c['new_count'] > 0 for c in urls_summary.values())
    
    reportable_lines = []
    full_log_lines = list(log_header)
    
    for domain, counts in urls_summary.items():
        log_line = f"{domain}: {counts['new_count']} New Images. Total: {counts['total_count']}"
        full_log_lines.append(log_line)
        if counts['new_count'] > 0:
            reportable_lines.append(log_line)
    
    duration_line = f"Crawl duration: {int(duration // 60)} min {int(duration % 60)} seconds."
    full_log_lines.append(duration_line)
    
    print(f"\n--- Summary saved to {LOG_FILE} ---")
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(full_log_lines))
    
    if found_new_images:
        print("Tìm thấy ảnh mới, đang chuẩn bị gửi báo cáo và kích hoạt workflow...")
        final_report_lines = log_header + reportable_lines + [duration_line]
        send_telegram_message("\n".join(final_report_lines))
        # trigger_workflow_dispatch() # Bỏ comment nếu muốn kích hoạt workflow
    else:
        print("Không có ảnh mới nào được tìm thấy. Bỏ qua các hành động tiếp theo.")
    
    git_push_changes()

if __name__ == "__main__":
    main()