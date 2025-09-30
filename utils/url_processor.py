# utils/url_processor.py
import requests
import re
from urllib.parse import urlparse, urljoin
from datetime import datetime, timedelta, timezone
from dateutil import parser
from bs4 import BeautifulSoup

# Import cache và hằng số từ constants.py
from .constants import HEADERS, URL_METADATA_CACHE

def get_url_metadata(url):
    if not url or not url.startswith('http'): return {'status': 0, 'is_recent': False}
    if url in URL_METADATA_CACHE: return URL_METADATA_CACHE[url]
    default_response = {'status': 0, 'is_recent': False}
    try:
        with requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True) as r:
            if r.status_code != 200:
                URL_METADATA_CACHE[url] = default_response; return default_response
            is_recent = True
            last_modified_str = r.headers.get('Last-Modified')
            if last_modified_str:
                last_modified_date = parser.parse(last_modified_str)
                if last_modified_date.tzinfo is None:
                    last_modified_date = last_modified_date.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                if (now_utc - last_modified_date) > timedelta(days=1):
                    is_recent = False
            metadata = {'status': r.status_code, 'is_recent': is_recent}
            URL_METADATA_CACHE[url] = metadata; return metadata
    except (requests.exceptions.RequestException, parser.ParserError, ValueError):
        URL_METADATA_CACHE[url] = default_response; return default_response

def check_url_exists(url):
    return get_url_metadata(url)['status'] == 200

def is_image_recent(url):
    metadata = get_url_metadata(url)
    return metadata['status'] == 200 and metadata['is_recent']

def apply_replacements(image_url, replacements, always_replace=False):
    if not image_url: return image_url
    if replacements and isinstance(replacements, dict):
        for original, replacement_list in replacements.items():
            if original in image_url:
                for replacement in replacement_list:
                    new_url = image_url.replace(original, replacement)
                    print(f"    -> Checking replacement: {new_url}")
                    if always_replace or check_url_exists(new_url):
                        print(f"    => ✅ Replacement found: {new_url}")
                        return new_url
                print(f"    => ❌ No valid replacement found for '{original}'.")
    return image_url

def apply_fallback_logic(image_url, url_data):
    if not image_url: return image_url
    fallback_rules = url_data.get('fallback_rules', {})
    if not fallback_rules or fallback_rules.get('type') != 'cut_filename_prefix': return image_url
    print(f"    -> Applying fallback for: {image_url}")
    parsed_url = urlparse(image_url)
    if parsed_url.netloc != fallback_rules.get('domain'): return image_url
    path_parts = parsed_url.path.split('/')
    filename = path_parts[-1]
    prefix_length = fallback_rules.get('prefix_length', 0)
    if len(filename) > prefix_length and filename[prefix_length - 1] == '-':
        if re.match(r'^[a-zA-Z0-9_-]+$', filename[:prefix_length-1]):
            new_filename = filename[prefix_length:]
            new_path = '/'.join(path_parts[:-1] + [new_filename])
            modified_url = parsed_url._replace(path=new_path).geturl()
            if check_url_exists(modified_url):
                print(f"    => ✅ Fallback successful: {modified_url}")
                return modified_url
    print(f"    => ❌ Fallback failed.")
    return image_url

def process_and_finalize_url(image_url, url_data):
    if not image_url: return None
    clean_url = apply_fallback_logic(image_url, url_data)
    final_url = apply_replacements(clean_url, url_data.get('replacements', {}), url_data.get('always_replace', False))
    return final_url

def find_best_image_url(soup, url_data):
    base_url = url_data['url']
    replacements, selector = url_data.get('replacements', {}), url_data.get('selector')
    image_tags = soup.select(selector) if selector else soup.find_all('img')
    if isinstance(replacements, list):
        for suffix in replacements:
            for img_tag in image_tags:
                img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
                if img_url and img_url.endswith(suffix):
                    print(f"    -> Found prioritized image by suffix '{suffix}'")
                    return urljoin(base_url, img_url)
    og_image_tag = soup.find('meta', property='og:image')
    if og_image_tag and og_image_tag.get('content'):
        img_url = urljoin(base_url, og_image_tag.get('content'))
        print(f"    -> Found og:image: {img_url}")
        return img_url
    if not selector and not replacements:
        for img_tag in image_tags:
            img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
            if img_url:
                img_url = urljoin(base_url, img_url)
                print(f"    -> Found first available image tag: {img_url}")
                return img_url
    return None