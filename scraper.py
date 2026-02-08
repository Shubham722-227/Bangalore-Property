"""
Bangalore property data scraper for builder projects.
Scrapes: Upcoming, Under construction, Ready to move, New launch (resale-relevant) from 99acres.
Output: properties.json for the HTML viewer.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Config ---
OUTPUT_JSON = Path(__file__).resolve().parent / "properties.json"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_DELAY_SEC = 2  # be polite to the server
# Timeout per request so we don't hang indefinitely (retries still happen)
REQUEST_TIMEOUT = 60  # seconds (connect + read)
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SEC = 5  # double after each attempt

# 99acres Bangalore project listing URLs by status
SOURCE_URLS = {
    "new_launch": "https://www.99acres.com/new-launch-projects-in-bangalore-ffid",
    "under_construction": "https://www.99acres.com/under-construction-projects-in-bangalore-ffid",
    "ready_to_move": "https://www.99acres.com/ready-to-move-projects-in-bangalore-ffid",
}


def _fetch_playwright(url: str) -> str | None:
    """Fetch page HTML using Playwright. Tries Chromium (HTTP/2 disabled) then Firefox."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    ua = REQUEST_HEADERS.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")

    def run_browser(browser, name: str) -> str | None:
        try:
            page = browser.new_page(user_agent=ua)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_selector('a[href*="npxid"]', timeout=10000)
            except Exception:
                pass
            time.sleep(2)
            html = page.content()
            browser.close()
            return html
        except Exception as e:
            print(f"  Playwright ({name}) failed: {e}")
            try:
                browser.close()
            except Exception:
                pass
            return None

    try:
        with sync_playwright() as p:
            # Use Firefox first (avoids ERR_HTTP2_PROTOCOL_ERROR that Chromium hits on 99acres)
            browser = p.firefox.launch(headless=True)
            html = run_browser(browser, "Firefox")
            if html:
                return html
            print("  Trying Chromium...")
            browser = p.chromium.launch(headless=True, args=["--disable-http2"])
            return run_browser(browser, "Chromium")
    except Exception as e:
        print(f"  Playwright failed: {e}")
        return None


def fetch(url: str, use_playwright: bool = True) -> str | None:
    """Fetch URL: try Playwright first (gets JS-rendered content), then requests with retries."""
    if use_playwright:
        html = _fetch_playwright(url)
        if html:
            return html
        print("  Falling back to requests...")
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_error = e
            print(f"  Attempt {attempt}/{RETRY_ATTEMPTS} failed: {e}")
            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
    print(f"Fetch error (gave up after {RETRY_ATTEMPTS} attempts) {url}: {last_error}")
    return None


def parse_price_range(text: str) -> tuple[float | None, float | None]:
    """Parse price into (min_lakhs, max_lakhs). Prefer one explicit range so we don't mix numbers from different listings."""
    if not text:
        return None, None
    raw = text.replace(",", "").replace("₹", "").strip()

    # 1) Prefer explicit "X - Y Cr" (both in Crore) -> convert to lakhs
    m = re.search(r"([\d.]+)\s*-\s*([\d.]+)\s*Cr", raw, re.I)
    if m:
        try:
            low, high = float(m.group(1)), float(m.group(2))
            if low <= high and high < 1000:  # sane range in Cr
                return low * 100, high * 100
        except ValueError:
            pass

    # 2) "X L - Y L" or "X Lakh - Y Lakh"
    m = re.search(r"([\d.]+)\s*(?:L|Lakh|Lac)\s*-\s*([\d.]+)\s*(?:L|Lakh|Lac)", raw, re.I)
    if m:
        try:
            low, high = float(m.group(1)), float(m.group(2))
            if low <= high and high < 10000:
                return low, high
        except ValueError:
            pass

    # 3) "X L - Y Cr" (min in Lakh, max in Cr)
    m = re.search(r"([\d.]+)\s*(?:L|Lakh|Lac)\s*-\s*([\d.]+)\s*Cr", raw, re.I)
    if m:
        try:
            low, high = float(m.group(1)), float(m.group(2)) * 100
            if low <= high:
                return low, high
        except ValueError:
            pass

    # 4) Fallback: single "X Cr" or "X - Y Cr" already tried; try single "X L"
    single_cr = re.search(r"([\d.]+)\s*Cr", raw, re.I)
    single_l = re.search(r"([\d.]+)\s*(?:L|Lakh|Lac)", raw, re.I)
    try:
        if single_cr:
            n = float(single_cr.group(1)) * 100
            return n, n
        if single_l:
            n = float(single_l.group(1))
            if n < 10000:
                return n, n
    except ValueError:
        pass
    return None, None


def parse_possession(text: str) -> str | None:
    """Extract only short handover: 'Dec 2026', 'Jan 2032', or 'Ready To Move'. Never return long description text."""
    if not text or not text.strip():
        return None
    text = text.strip()
    if "ready to move" in text.lower() or "ready to move in" in text.lower():
        return "Ready to move"
    m = re.search(r"(?:Possession:?\s*)?([A-Za-z]+\s+\d{4})", text, re.I)
    if m:
        return m.group(1).strip()
    return None


def extract_builder_from_title(title: str) -> str:
    """Heuristic: first part of project name is often builder (e.g. 'Prestige Suncrest' -> Prestige)."""
    if not title:
        return ""
    words = title.split()
    return words[0] if words else ""


def _name_and_locality_from_href(href: str) -> tuple[str, str]:
    """Derive project name and locality from URL slug. Locality = 1 or 2 segments (Whitefield | Sarjapur Road)."""
    path = href.split("?")[0]
    slug = path.rstrip("/").split("/")[-1] or ""
    if "-npxid" not in slug or "bangalore" not in slug.lower():
        return "", ""
    before_npxid = re.sub(r"-npxid.*", "", slug, flags=re.I).strip()
    zone = r"-bangalore-(north|south|east|west)$"
    # Known two-word localities (avoid splitting project name: "Prestige Raintree Park" not "Prestige Raintree" + "Park Whitefield")
    two_word_locality = re.search(r"^(.+)-(sarjapur-road|hennur-road|electronic-city|kanakapura-road|bannerghatta-road|begur-road|hosur-road|mysore-road|devanahalli|marathahalli|whitefield|bagalur|yelahanka|varthur|panathur|nallurhalli|kogilu|nelamangala|kengeri|uttarahalli|rajarajeshwari-nagar|hosa-road|hebbal|thanisandra|kr-puram|malleshwaram|horamavu|gunjur|budigere-cross|doddaballapur|chandapura|jigani|anekal|kasaba-hobli|bidarahalli|sarjapur|hoskote)" + zone, before_npxid, re.I)
    if two_word_locality:
        name_slug, locality_slug = two_word_locality.group(1), two_word_locality.group(2)
        return name_slug.replace("-", " ").strip().title()[:200], locality_slug.replace("-", " ").strip().title()[:100]
    one_seg = re.search(r"^(.+)-([a-z0-9]+)" + zone, before_npxid, re.I)
    if one_seg:
        name_slug, locality_slug = one_seg.group(1), one_seg.group(2)
        return name_slug.replace("-", " ").strip().title()[:200], locality_slug.replace("-", " ").strip().title()[:100]
    name = before_npxid.replace("-", " ").strip().title()
    return name[:200], ""


def _extract_from_raw_html(html: str, base_url: str, status: str) -> list[dict]:
    """Fallback: find project URLs and price/possession in raw HTML (e.g. when DOM has no cards)."""
    # Find all project URLs: /path/slug-bangalore-zone-npxid-r123 or full url
    url_pattern = re.compile(
        r'(https?://(?:www\.)?99acres\.com/[^"\'<>\s]+?npxid[^"\'<>\s]*?r\d+)'
        r'|(/(?:[a-z0-9-]+/)*[a-z0-9-]+-bangalore-(?:north|south|east|west)-npxid-r\d+[^"\'<>\s]*)',
        re.I
    )
    seen_urls = set()
    results = []
    for m in url_pattern.finditer(html):
        full_url = m.group(1) or urljoin(base_url, m.group(2))
        if not full_url or "bangalore" not in full_url.lower() or "npxid" not in full_url:
            continue
        full_url = full_url.split("?")[0].rstrip(".,;:)")
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        # Get a window of text around this URL (500 chars before, 800 after) to find price/possession
        start = max(0, m.start() - 500)
        end = min(len(html), m.end() + 800)
        window = html[start:end]
        # Strip tags for regex
        window_text = re.sub(r"<[^>]+>", " ", window)
        window_text = re.sub(r"\s+", " ", window_text)
        slug = full_url.split("/")[-1] or full_url
        name, locality = _name_and_locality_from_href("/" + slug)
        if not name:
            slug = full_url.split("/")[-1] or full_url
            name = re.sub(r"-npxid.*", "", slug.replace("-", " ")).title() or "Project"
        price_min, price_max = parse_price_range(window_text)
        possession = parse_possession(window_text)
        bhk_match = re.search(r"(\d[\d,\s]*)\s*BHK", window_text)
        bhk = bhk_match.group(1).strip() if bhk_match else ""
        results.append({
            "id": re.sub(r"[^a-zA-Z0-9]", "", full_url)[-12:] or str(len(results)),
            "source": "99acres",
            "status": status,
            "name": name[:200],
            "builder": extract_builder_from_title(name),
            "locality": locality,
            "price_min_lakhs": price_min,
            "price_max_lakhs": price_max,
            "price_display": _format_price_display(price_min, price_max),
            "handover": possession,
            "handover_year": _year_from_possession(possession),
            "bhk": bhk,
            "url": full_url,
        })
    return results


def _card_text_for_link(a, soup) -> str:
    """Get text from the smallest parent that has at most one price range; else use first parent with a price."""
    parent = a.find_parent(["div", "article", "section", "li"])
    candidate_with_price = ""
    while parent and parent != soup:
        block = (parent.get_text(separator=" ", strip=True) or "").strip()
        if len(block) > 5000:
            parent = parent.find_parent(["div", "article", "section", "li"])
            continue
        price_ranges = re.findall(r"[\d.]+[\s-]+[\d.]+\s*(?:L|Lakh|Lac|Cr)", block, re.I)
        if not candidate_with_price and price_ranges:
            candidate_with_price = block
        if len(price_ranges) <= 1 and len(block) >= 80:
            return block
        parent = parent.find_parent(["div", "article", "section", "li"])
    return candidate_with_price or (a.get_text(separator=" ", strip=True) or "").strip()


def scrape_99acres_list(html: str, base_url: str, status: str) -> list[dict]:
    """Parse 99acres listing HTML and return list of property dicts with clear per-card details."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "npxid" not in href or "bangalore" not in href.lower():
            continue
        full_url = urljoin(base_url, href).split("?")[0]
        if not full_url.startswith("http"):
            continue

        # Prefer name & locality from URL (consistent); fallback to DOM
        url_name, url_locality = _name_and_locality_from_href(href)
        name = (a.get_text(strip=True) or "").strip()
        if len(name) < 5 or len(name) > 200:
            name = ""
        parent = a.find_parent(["div", "article", "section", "li"])
        if parent:
            for tag in ["h2", "h3", "h4", "strong"]:
                for h in parent.find_all(tag):
                    t = (h.get_text(strip=True) or "").strip()
                    if 5 <= len(t) <= 200 and "Bangalore" not in t:
                        name = name or t
                        break
                if name:
                    break
        if not name or len(name) < 5:
            name = url_name or re.sub(r"-npxid.*", "", href.split("/")[-1].replace("-", " ")).title()
        name = (name or "Project").strip()[:200]

        # Use card-scoped text so price/possession/BHK belong to this listing only
        block_text = _card_text_for_link(a, soup)

        price_min, price_max = parse_price_range(block_text)
        possession = parse_possession(block_text)
        locality = ""
        loc_m = re.search(r"([A-Za-z\s]+),\s*Bangalore\s*(?:North|South|East|West)", block_text)
        if loc_m:
            locality = loc_m.group(1).strip()[:100]
        if not locality:
            locality = url_locality
        bhk_match = re.search(r"(\d[\d,\s]*)\s*BHK", block_text)
        bhk = (bhk_match.group(1).strip() if bhk_match else "").strip()

        # Build clean record
        prop_id = re.sub(r"[^a-zA-Z0-9]", "", href)[-12:] or str(len(results))
        record = {
            "id": prop_id,
            "source": "99acres",
            "status": status,
            "name": name,
            "builder": extract_builder_from_title(name),
            "locality": locality[:100] if locality else "",
            "price_min_lakhs": price_min,
            "price_max_lakhs": price_max,
            "price_display": _format_price_display(price_min, price_max),
            "handover": (possession.strip() if possession else "") or "",
            "handover_year": _year_from_possession(possession),
            "bhk": bhk,
            "url": full_url,
        }
        results.append(record)

    # Dedupe by url
    seen = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    # If BeautifulSoup found no/very few cards, try regex on raw HTML (works when content is in script or odd structure)
    if len(unique) < 3 and len(html) > 5000:
        raw_list = _extract_from_raw_html(html, base_url, status)
        for r in raw_list:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)
    return unique


def _format_price_display(min_p: float | None, max_p: float | None) -> str:
    if min_p is None and max_p is None:
        return ""
    if min_p is None:
        min_p = max_p
    if max_p is None:
        max_p = min_p
    if max_p >= 100:
        return f"₹ {min_p/100:.2f} - {max_p/100:.2f} Cr"
    return f"₹ {min_p:.2f} - {max_p:.2f} L"


def _year_from_possession(possession: str | None) -> int | None:
    if not possession or "ready" in possession.lower():
        return None
    m = re.search(r"\d{4}", possession)
    return int(m.group(0)) if m else None


def run_scraper(max_pages_per_category: int | None = None) -> list[dict]:
    """Fetch all categories and all pages until no more results. No timeout until all data is extracted."""
    all_properties = []
    # First page of each category
    for status, url in SOURCE_URLS.items():
        print(f"Scraping {status}: {url}")
        html = fetch(url)
        if html:
            items = scrape_99acres_list(html, url, status)
            print(f"  -> {len(items)} items")
            all_properties.extend(items)
        time.sleep(REQUEST_DELAY_SEC)

    # Pagination: scrape all pages until we get a page with no new items (or empty)
    max_pages = max_pages_per_category if max_pages_per_category is not None else 999
    for status, base_url in SOURCE_URLS.items():
        page = 2
        while page <= max_pages:
            page_url = base_url + f"-page-{page}"
            print(f"Scraping {status} page {page}: {page_url}")
            html = fetch(page_url)
            if not html:
                print(f"  -> fetch failed, stopping pagination for {status}")
                break
            items = scrape_99acres_list(html, page_url, status)
            if not items:
                print(f"  -> 0 items, no more pages for {status}")
                break
            print(f"  -> {len(items)} items")
            all_properties.extend(items)
            time.sleep(REQUEST_DELAY_SEC)
            page += 1

    # Deduplicate by URL (same project may appear in multiple categories/pages)
    seen_urls = set()
    unique = []
    for p in all_properties:
        if p["url"] not in seen_urls:
            seen_urls.add(p["url"])
            unique.append(p)
    print(f"Total after deduplication: {len(unique)} properties")
    return unique


def ensure_sample_data(properties: list[dict]) -> list[dict]:
    """If scraping returned nothing, add sample data so the viewer always has something."""
    if properties:
        return properties
    return [
        {
            "id": "sample1",
            "source": "99acres",
            "status": "new_launch",
            "name": "Folium by Sumadhura Phase 3",
            "builder": "Sumadhura",
            "locality": "Whitefield, Bangalore East",
            "price_min_lakhs": 230,
            "price_max_lakhs": 372,
            "price_display": "₹ 2.30 - 3.72 Cr",
            "handover": "Dec 2026",
            "handover_year": 2026,
            "bhk": "3, 4",
            "url": "https://www.99acres.com/folium-by-sumadhura-phase-3-whitefield-bangalore-east-npxid-r420666",
        },
        {
            "id": "sample2",
            "source": "99acres",
            "status": "under_construction",
            "name": "Prestige Suncrest",
            "builder": "Prestige",
            "locality": "Electronic City, Bangalore South",
            "price_min_lakhs": 71,
            "price_max_lakhs": 211,
            "price_display": "₹ 71 - 2.11 Cr",
            "handover": "Sep 2028",
            "handover_year": 2028,
            "bhk": "1, 2, 3",
            "url": "https://www.99acres.com/prestige-suncrest-electronic-city-bangalore-south-npxid-r439895",
        },
        {
            "id": "sample3",
            "source": "99acres",
            "status": "ready_to_move",
            "name": "Brigade El Dorado",
            "builder": "Brigade",
            "locality": "Bagalur, Bangalore North",
            "price_min_lakhs": 49,
            "price_max_lakhs": 177,
            "price_display": "₹ 49 L - 1.77 Cr",
            "handover": "Ready to move",
            "handover_year": None,
            "bhk": "1, 2, 3",
            "url": "https://www.99acres.com/brigade-el-dorado-bagalur-bangalore-north-npxid-r331133",
        },
        {
            "id": "sample4",
            "source": "99acres",
            "status": "new_launch",
            "name": "Sarang by Sumadhura",
            "builder": "Sumadhura",
            "locality": "Whitefield, Bangalore East",
            "price_min_lakhs": 173,
            "price_max_lakhs": 275,
            "price_display": "₹ 1.73 - 2.75 Cr",
            "handover": "Dec 2026",
            "handover_year": 2026,
            "bhk": "3, 4",
            "url": "https://www.99acres.com/sarang-by-sumadhura-whitefield-bangalore-east-npxid-r411425",
        },
        {
            "id": "sample5",
            "source": "99acres",
            "status": "under_construction",
            "name": "Lodha Azur",
            "builder": "Lodha",
            "locality": "Bannerghatta Road, Bangalore South",
            "price_min_lakhs": 230,
            "price_max_lakhs": 360,
            "price_display": "₹ 2.3 - 3.6 Cr",
            "handover": "Apr 2028",
            "handover_year": 2028,
            "bhk": "3, 4",
            "url": "https://www.99acres.com/lodha-azur-bannerghatta-road-bangalore-south-npxid-r424462",
        },
    ]


def main():
    import sys
    quick = "--quick" in sys.argv or "-q" in sys.argv
    do_clear = "--clear" in sys.argv or "-c" in sys.argv
    max_pages = None
    for i, arg in enumerate(sys.argv):
        if arg in ("--max-pages", "-m") and i + 1 < len(sys.argv):
            try:
                max_pages = int(sys.argv[i + 1])
                if max_pages < 1:
                    max_pages = 1
            except ValueError:
                pass
            break
    if quick:
        max_pages = 1
    if do_clear:
        OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump([], f)
        print("Cleared properties.json. Refetching...")
    if quick:
        print("Quick mode: 1 page per category only")
    elif max_pages is not None:
        print(f"Max {max_pages} pages per category (new_launch, under_construction, ready_to_move)")
    data = run_scraper(max_pages_per_category=max_pages)
    data = ensure_sample_data(data)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data)} properties to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
