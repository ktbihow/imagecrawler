# crawlers/prevnext_crawler.py
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from utils.constants import MAX_PREVNEXT_URLS, HEADERS
from utils.url_processor import process_and_finalize_url, find_best_image_url

def crawl(url_data, stop_urls_list):
    """Crawl images by following 'previous' and 'next' links on product pages."""
    all_image_urls, new_product_urls_found = [], []
    domain = urlparse(url_data['url']).netloc

    try:
        r = requests.get(url_data['url'], headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        first_product_tag = soup.select_one(url_data['first_product_selector'])
        if not first_product_tag: return [], []
        current_product_url = urljoin(url_data['url'], first_product_tag.get('href'))
    except requests.exceptions.RequestException:
        return [], []

    count = 0
    stop_url_found = None
    while count < MAX_PREVNEXT_URLS:
        if current_product_url in stop_urls_list:
            stop_url_found = current_product_url
            break
        print(f"Crawling: {current_product_url}")
        try:
            r = requests.get(current_product_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = process_and_finalize_url(best_url, url_data)
                if final_img_url and final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(current_product_url)

            next_product_tag = soup.select_one(url_data['next_product_selector'])
            if not next_product_tag or not next_product_tag.get('href'): break
            current_product_url = urljoin(current_product_url, next_product_tag.get('href'))
            count += 1
        except requests.exceptions.RequestException:
            break
            
    if stop_url_found:
        print(f"[{domain}] Found {len(new_product_urls_found)} new URLs. Stopped at stop URL.")
        
    return all_image_urls, new_product_urls_found