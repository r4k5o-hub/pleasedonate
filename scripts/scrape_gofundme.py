#!/usr/bin/env python3
"""
Reliable scraper for GoFundMe campaigns.
Fetches real raised/goal amounts and updates config.json.
"""
import json
import re
import time
import os
from urllib.request import urlopen, Request
from urllib.error import URLError

ROOT = os.path.dirname(os.path.dirname(__file__)) if os.path.basename(__file__) == 'scrape_gofundme.py' else '.'
CFG_PATH = os.path.join(ROOT, 'config.json')

def fetch_url(url, retries=3, timeout=10):
    """Fetch URL with retries and timeout."""
    for attempt in range(retries):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            req = Request(url, headers=headers)
            response = urlopen(req, timeout=timeout)
            return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"Fetch attempt {attempt+1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
    return None

def parse_gofundme(html):
    """Extract raised and goal from GoFundMe HTML."""
    if not html:
        return None
    
    raised, goal = None, None
    
    # Try to find currentAmount in JSON-like format
    m = re.search(r'"currentAmount"\s*:\s*"?([0-9,.]+)"?', html, re.IGNORECASE)
    if m:
        raised = parse_money(m.group(1))
    
    # Try to find goalAmount
    m = re.search(r'"goalAmount"\s*:\s*"?([0-9,.]+)"?', html, re.IGNORECASE)
    if m:
        goal = parse_money(m.group(1))
    
    # Fallback: look for displayed text
    if not raised:
        m = re.search(r'\$([0-9,]+(?:\.[0-9]{2})?)\s+raised', html, re.IGNORECASE)
        if m:
            raised = parse_money(m.group(1))
    
    if not goal:
        m = re.search(r'goal["\s:]+\$?([0-9,]+(?:\.[0-9]{2})?)', html, re.IGNORECASE)
        if m:
            goal = parse_money(m.group(1))
    
    if raised or goal:
        return {'raised': raised or 0, 'goal': goal or 0}
    
    return None

def parse_money(s):
    """Parse money string to integer (cents)."""
    if not s:
        return 0
    s = str(s).strip().replace(',', '')
    try:
        return int(float(s))
    except:
        return 0

def scrape_donations(config):
    """Scrape all GoFundMe donations."""
    updated = []
    
    for donation in config.get('donations', []):
        if donation.get('platform', '').lower() == 'gofundme' and donation.get('url'):
            url = donation['url']
            print(f"Scraping {donation['name']} ({url})...")
            
            html = fetch_url(url)
            if html:
                data = parse_gofundme(html)
                if data and data['goal'] > 0:
                    old_raised = donation.get('raised', 0)
                    old_goal = donation.get('goal', 0)
                    donation['raised'] = data['raised']
                    donation['goal'] = data['goal']
                    print(f"  Updated: ${data['raised']} / ${data['goal']} (was ${old_raised} / ${old_goal})")
                    updated.append(donation['id'])
                else:
                    print(f"  Failed to parse data")
            else:
                print(f"  Failed to fetch page")
    
    return updated

if __name__ == '__main__':
    print(f"Loading {CFG_PATH}...")
    with open(CFG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    print(f"Scraping {len(config.get('donations', []))} donations...")
    updated = scrape_donations(config)
    
    if updated:
        print(f"Saving updated config...")
        with open(CFG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"Updated {len(updated)} donation(s): {updated}")
    else:
        print("No donations updated")
