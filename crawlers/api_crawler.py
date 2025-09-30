# crawlers/api_crawler.py
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from utils.constants import MAX_API_PAGES, DEFAULT_API_URL_PATTERN, HEADERS
from utils.url_processor import process_and_finalize_url

def crawl(url_data, stop_urls_list):
    """Crawl images from a WordPress API endpoint."""
    all_image_urls, new_product_urls_found = [], []
    page = 1
    domain = urlparse(url_data['url']).netloc
    stop_url_found = None

    while page <= MAX_API_PAGES and not stop_url_found:
        api_url = DEFAULT_API_URL_PATTERN.format(domain=domain, page=page)
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            if not data: break

            for item in data:
                product_url = item.get('link')
                if product_url and product_url in stop_urls_list:
                    stop_url_found = product_url
                    break
                
                img_url = (item.get('yoast_head_json', {}).get('og_image', [{}])[0].get('url') or 
                         (img_tag.get('src') if (img_tag := BeautifulSoup(item.get('content', {}).get('rendered', ''), 'html.parser').find('img')) else None))
                
                if img_url:
                    if img_url.startswith('http://'): img_url = img_url.replace('http://', 'https://')
                    
                    final_img_url = process_and_finalize_url(img_url, url_data)
                    
                    if final_img_url and final_img_url not in all_image_urls:
                        all_image_urls.append(final_img_url)
                        if product_url: new_product_urls_found.append(product_url)
            page += 1
        except requests.exceptions.RequestException:
            break
            
    if stop_url_found:
        print(f"[{domain}] Found {len(new_product_urls_found)} new URLs. Stopped at stop URL.")
        
    return all_image_urls, new_product_urls_found