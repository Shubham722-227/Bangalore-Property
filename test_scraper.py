"""Quick test: fetch one page and parse. Run with: python test_scraper.py"""
import sys
sys.path.insert(0, ".")
import scraper as sc
# Use short timeout for test so we get a result quickly
sc.REQUEST_TIMEOUT = 15
sc.RETRY_ATTEMPTS = 1

url = list(sc.SOURCE_URLS.values())[0]
print(f"Fetching: {url} (Playwright Firefox first, then requests)")
html = sc.fetch(url, use_playwright=True)
if not html:
    print("FAIL: No HTML returned")
    sys.exit(1)
print(f"OK: Got {len(html)} chars")
items = sc.scrape_99acres_list(html, url, "new_launch")
print(f"Parsed: {len(items)} properties")
for i, p in enumerate(items[:5]):
    print(f"  {i+1}. {p.get('name')} | {p.get('price_display')} | {p.get('handover')}")
if len(items) < 3:
    print("WARNING: Few items - raw HTML fallback may have run or page structure changed")
