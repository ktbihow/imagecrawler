# utils/file_handler.py
import json
import os
from .constants import CONFIG_FILE, STOP_URLS_FILE, DOMAIN_DIR, MAX_URLS

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError:
        print(f"LỖI: Không tìm thấy file config tại: {CONFIG_FILE}")
        return []

def load_stop_urls():
    try:
        with open(STOP_URLS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_stop_urls(stop_urls):
    with open(STOP_URLS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stop_urls, f, indent=2)

def save_urls(domain, new_urls, discarded_count=0):
    if not os.path.exists(DOMAIN_DIR): os.makedirs(DOMAIN_DIR)
    filename = os.path.join(DOMAIN_DIR, f"{domain}.txt")
    try:
        with open(filename, "r", encoding="utf-8") as f:
            existing_urls = [line.strip() for line in f]
    except FileNotFoundError:
        existing_urls = []
    
    unique_new_urls = [u for u in new_urls if u not in existing_urls]
    all_urls = (unique_new_urls + existing_urls)[:MAX_URLS]
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(all_urls))
        
    console_report = f"[{domain}] Added {len(unique_new_urls)} new URLs."
    if discarded_count > 0:
        console_report += f" Discarded {discarded_count} old URLs."
    console_report += f" Total: {len(all_urls)}"
    print(console_report)
    
    return len(unique_new_urls), len(all_urls)