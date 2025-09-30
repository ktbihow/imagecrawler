# crawlers/product_list_crawler.py
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from utils.constants import REPO_URL_PATTERN, MAX_PREVNEXT_URLS, HEADERS
from utils.url_processor import process_and_finalize_url, find_best_image_url

def crawl(url_data, stop_urls_list):
    """Crawl images by fetching a list of product URLs from a remote file."""
    all_image_urls, new_product_urls_found = [], []
    domain = urlparse(url_data['url']).netloc
    repo_file_url = REPO_URL_PATTERN.format(domain=domain)

    try:
        r = requests.get(repo_file_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        product_urls = [line.strip() for line in r.text.splitlines() if line.strip()]
    except requests.exceptions.RequestException:
        return [], []
    
    urls_to_crawl, stop_url_found = [], None
    if stop_urls_list:
        for product_url in product_urls:
            if product_url in stop_urls_list:
                stop_url_found = product_url
                break
            urls_to_crawl.append(product_url)
        if not stop_url_found: urls_to_crawl = product_urls
    else:
        urls_to_crawl = product_urls

    if stop_url_found:
        print(f"[{domain}] Found {len(urls_to_crawl)} new URLs to crawl. Will stop at: {stop_url_found}")

    for product_url in urls_to_crawl:
        if len(all_image_urls) >= MAX_PREVNEXT_URLS: break
        print(f"Crawling: {product_url}")
        try:
            with requests.get(product_url, headers=HEADERS, timeout=30, stream=True) as r:
                r.raise_for_status()
                content = b''.join(r.iter_content(chunk_size=8192))
                soup = BeautifulSoup(content, "html.parser")
                
            best_url = find_best_image_url(soup, url_data)
            if best_url:
                final_img_url = process_and_finalize_url(best_url, url_data)
                if final_img_url and final_img_url not in all_image_urls:
                    all_image_urls.append(final_img_url)
                    new_product_urls_found.append(product_url)
        except requests.exceptions.RequestException:
            continue
            
    return all_image_urls, new_product_urls_found