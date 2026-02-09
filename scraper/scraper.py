"""
Bangalore property data scraper for builder projects.
Scrapes: 99acres (new launch, under construction, ready to move) + NoBroker (new projects).
Output: public/properties.json for the Next.js viewer.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Config ---
OUTPUT_JSON = Path(__file__).resolve().parent.parent / "public" / "properties.json"
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

# NoBroker new projects listing (single listing; status inferred from card "Status" field)
NOBROKER_BASE = "https://www.nobroker.in"
NOBROKER_LISTING_URL = "https://www.nobroker.in/new-projects-in-bangalore"
NOBROKER_PAGE_URL = "https://www.nobroker.in/new-projects-in-bangalore-page-{page}"

# Names that are page titles / nav links, not actual project names (exclude from results)
JUNK_PROJECT_NAMES = {
    "new launch projects in bangalore",
    "under construction projects in bangalore",
    "ready to move projects in bangalore",
    "new projects in bangalore",
    "projects in bangalore",
    "upcoming projects in bangalore",
    "new projects by reputed bangalore builders in bangalore",
    "ready to move & pre launch",
    "list", "map", "filter your search", "reset", "sort by",
    "find other projects matching your search nearby",
    "quick links",
    "bangalore",
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


def _fetch_playwright_generic(url: str, sleep_sec: int = 5) -> str | None:
    """Fetch URL with Playwright without 99acres-specific wait (for NoBroker etc)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    ua = REQUEST_HEADERS.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=ua)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(sleep_sec)
                html = page.content()
                return html
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as e:
        print(f"  Playwright (generic) failed: {e}")
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


# Shorter timeout for detail-page fetches (avoid hanging on 200+ pages)
# (connect_sec, read_sec) so a stuck server doesn't block the whole run
DETAIL_PAGE_TIMEOUT = 10
DETAIL_PAGE_TIMEOUT_TUPLE = (3, 6)  # 3s connect, 6s read; fail fast if NoBroker/99acres is slow

def fetch_nobroker(url: str) -> str | None:
    """Fetch NoBroker listing page (JS-rendered); fallback to requests."""
    html = _fetch_playwright_generic(url, sleep_sec=5)
    if html and len(html) > 5000:
        return html
    print("  NoBroker Playwright failed or short response, trying requests...")
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  Attempt {attempt}/{RETRY_ATTEMPTS} failed: {e}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SEC * (2 ** (attempt - 1)))
    return None


def fetch_nobroker_detail(url: str) -> str | None:
    """Fetch a single NoBroker detail page with requests only. Uses (connect, read) timeout to avoid hanging."""
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=DETAIL_PAGE_TIMEOUT_TUPLE)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def fetch_99acres_detail(url: str) -> str | None:
    """Fetch a single 99acres project detail page (requests only, short timeout)."""
    if not url or "99acres.com" not in url or "npxid" not in url:
        return None
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=DETAIL_PAGE_TIMEOUT_TUPLE)
        r.raise_for_status()
        return r.text
    except Exception:
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

    # 4) "X lacs onwards" / "X lac onwards" -> min only
    m = re.search(r"([\d.]+)\s*(?:lacs?|lakhs?|lac)\s+onwards?", raw, re.I)
    if m:
        try:
            n = float(m.group(1))
            if n < 10000:
                return n, None
        except ValueError:
            pass
    # 5) "Starting ₹ X Cr" / "₹ X Cr onwards"
    m = re.search(r"(?:Starting\s+)?(?:₹\s*)?([\d.]+)\s*Cr\s*(?:onwards)?", raw, re.I)
    if m:
        try:
            n = float(m.group(1)) * 100
            if n < 10000:
                return n, None
        except ValueError:
            pass
    # 6) Fallback: single "X Cr" or "X - Y Cr" already tried; try single "X L"
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


def _is_junk_project_name(name: str) -> bool:
    """Return True if name is a page title/nav text, not a real project name."""
    if not name or len(name) < 4:
        return True
    key = name.strip().lower()[:120]
    if key in JUNK_PROJECT_NAMES:
        return True
    if "projects in bangalore" in key or ("projects in " in key and "bangalore" in key):
        if key.startswith("new ") or key.startswith("under ") or key.startswith("ready ") or key.startswith("upcoming "):
            return True
    # Section titles like "New Projects by Reputed Bangalore Builders in bangalore"
    if "by reputed" in key and "builders" in key and "bangalore" in key:
        return True
    return False


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


# Text that indicates nav/filter/UI, not real property data (strip from fields or drop record)
PROPERTY_JUNK_SUBSTRINGS = (
    "filter your search", "sort by", "reset", "list", "map", "quick links",
    "find other projects", "next >>", "<< prev", "bangalore, india", "property list",
)

# Sane bounds for price (lakhs) and handover year
PRICE_MAX_LAKHS = 50000
PRICE_MIN_LAKHS = 0.1
HANDOVER_YEAR_MIN = 2020
HANDOVER_YEAR_MAX = 2040


def _normalize_str(s: str | None, max_len: int = 200) -> str:
    """Trim, collapse spaces, and cap length. Empty or only junk -> ''."""
    if not s or not isinstance(s, str):
        return ""
    t = re.sub(r"\s+", " ", s.strip())
    if not t:
        return ""
    for junk in PROPERTY_JUNK_SUBSTRINGS:
        if junk in t.lower():
            t = re.sub(re.escape(junk), " ", t, flags=re.I)
            t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len] if t else ""


def verify_and_clean_property(record: dict) -> dict | None:
    """
    Verify and normalize a scraped property record. Returns cleaned record or None if invalid.
    - Normalizes name, builder, locality, handover, bhk, price_display
    - Validates price range (min <= max, within sane bounds)
    - Validates handover_year
    - Drops records with no usable name or URL
    """
    if not record or not isinstance(record, dict):
        return None
    url = (record.get("url") or "").strip()
    if not url or "http" not in url:
        return None

    name = _normalize_str(record.get("name"), 200)
    if not name or _is_junk_project_name(name):
        return None
    builder = _normalize_str(record.get("builder"), 100)
    locality = _normalize_str(record.get("locality"), 150)
    handover = _normalize_str(record.get("handover"), 50)
    bhk = _normalize_str(record.get("bhk"), 30)
    price_display = _normalize_str(record.get("price_display"), 80)

    # Price: ensure numeric consistency and sane range
    try:
        pmin = record.get("price_min_lakhs")
        pmax = record.get("price_max_lakhs")
        if pmin is not None and not isinstance(pmin, (int, float)):
            pmin = float(pmin) if pmin != "" else None
        if pmax is not None and not isinstance(pmax, (int, float)):
            pmax = float(pmax) if pmax != "" else None
    except (TypeError, ValueError):
        pmin, pmax = None, None
    if pmin is not None and (pmin < PRICE_MIN_LAKHS or pmin > PRICE_MAX_LAKHS):
        pmin = None
    if pmax is not None and (pmax < PRICE_MIN_LAKHS or pmax > PRICE_MAX_LAKHS):
        pmax = None
    if pmin is not None and pmax is not None and pmin > pmax:
        pmin, pmax = pmax, pmin
    if pmin is not None or pmax is not None:
        price_display = _format_price_display(pmin, pmax)

    # Handover year
    hy = record.get("handover_year")
    if hy is not None:
        try:
            hy = int(hy)
            if hy < HANDOVER_YEAR_MIN or hy > HANDOVER_YEAR_MAX:
                hy = None
        except (TypeError, ValueError):
            hy = None

    status = (record.get("status") or "").strip().lower()
    if status not in ("new_launch", "under_construction", "ready_to_move"):
        status = "new_launch"
    source = (record.get("source") or "").strip() or "99acres"
    pid = (record.get("id") or "").strip() or re.sub(r"[^a-zA-Z0-9]", "", url)[-14:]

    return {
        "id": pid,
        "source": source,
        "status": status,
        "name": name,
        "builder": builder,
        "locality": locality,
        "price_min_lakhs": pmin,
        "price_max_lakhs": pmax,
        "price_display": price_display,
        "handover": handover,
        "handover_year": hy,
        "bhk": bhk,
        "url": url,
    }


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

        # Prefer name & locality from URL (source of truth for which project this link points to).
        # DOM text often comes from a different card on the listing page and causes wrong names.
        url_name, url_locality = _name_and_locality_from_href(href)
        if url_name:
            name = url_name
            locality = url_locality or ""
        else:
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
                name = re.sub(r"-npxid.*", "", href.split("/")[-1].replace("-", " ")).title()
            name = (name or "Project").strip()[:200]
            locality = ""
            block_text = _card_text_for_link(a, soup)
            loc_m = re.search(r"([A-Za-z\s]+),\s*Bangalore\s*(?:North|South|East|West)", block_text)
            if loc_m:
                locality = loc_m.group(1).strip()[:100]
            if not locality:
                locality = url_locality

        # Use card-scoped text for price/possession/BHK only (not name/locality when URL had them)
        block_text = _card_text_for_link(a, soup)

        price_min, price_max = parse_price_range(block_text)
        possession = parse_possession(block_text)
        if not locality:
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
        if _is_junk_project_name(record["name"]):
            continue
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


def _nobroker_slug(name: str, locality: str) -> str:
    """Build a URL slug from project name and locality for NoBroker-style URLs."""
    parts = []
    if name:
        parts.append(re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80])
    if locality:
        loc_clean = re.sub(r",\s*Bangalore.*", "", locality, flags=re.I).strip()
        if loc_clean:
            parts.append(re.sub(r"[^a-z0-9]+", "-", loc_clean.lower()).strip("-")[:50])
    if not parts:
        return "project-bangalore"
    return "-".join(parts) + "-bangalore"


def _parse_nobroker_card_text(block: str, project_url: str) -> dict | None:
    """Parse one NoBroker card text block into a property dict. Returns None if too little info."""
    block = (block or "").strip()
    if len(block) < 30:
        return None
    # First line often: "Project Name, Locality, Bangalore, India"
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    name = ""
    locality = ""
    for i, ln in enumerate(lines):
        if "Bangalore" in ln and "," in ln and len(ln) < 200:
            # "Adarsh Welkin Park, Off Sarjapura Road, Bangalore, India"
            name = ln.split(",")[0].strip()[:200]
            locality = ",".join(ln.split(",")[1:-2]).strip() if ln.count(",") >= 2 else ""
            locality = locality.replace(", Bangalore", "").strip()[:100]
            break
    if not name and lines:
        name = lines[0][:200] if len(lines[0]) > 3 else ""
    if not name:
        return None
    # Price: try every line for numeric price
    price_min, price_max = None, None
    for ln in lines:
        if "₹" in ln or "lac" in ln.lower() or "cr" in ln.lower() or "lakh" in ln.lower():
            pmin, pmax = parse_price_range(ln)
            if pmin is not None or pmax is not None:
                if price_min is None:
                    price_min = pmin
                elif pmin is not None:
                    price_min = min(price_min, pmin)
                if price_max is None:
                    price_max = pmax
                elif pmax is not None:
                    price_max = max(price_max, pmax)
    if price_min is None and price_max is None:
        price_min, price_max = parse_price_range(block)
    # Builder: line after price or "X Group" / "X Developers"
    builder = ""
    for ln in lines:
        if re.search(r"(Group|Developers?|Limited|Pvt|Builders?|Realty|Ventures?|Constructions?)$", ln, re.I) and len(ln) < 80:
            builder = ln.strip()[:100]
            break
    if not builder and name:
        builder = name.split()[0] if name.split() else ""
    # BHK from "BHK-2,3,4" or "Configurations" "BHK-x"
    bhk = ""
    for ln in lines:
        bhk_m = re.search(r"BHK[-\s]*([\d.,\s]+)", ln, re.I)
        if bhk_m:
            bhk = bhk_m.group(1).strip().replace(" ", "")[:30]
            break
    # Status: "Ready" -> ready_to_move, "Under Construction" -> under_construction
    status = "new_launch"
    for ln in lines:
        if "Under Construction" in ln or "under construction" in ln.lower():
            status = "under_construction"
            break
        if "Ready" in ln and "Status" in block:
            status = "ready_to_move"
            break
    handover = "Ready to move" if status == "ready_to_move" else ""
    return {
        "id": re.sub(r"[^a-zA-Z0-9]", "", project_url)[-14:] or str(hash(block) % 10**10),
        "source": "nobroker",
        "status": status,
        "name": name[:200],
        "builder": builder[:100] if builder else extract_builder_from_title(name),
        "locality": locality[:100] if locality else "",
        "price_min_lakhs": price_min,
        "price_max_lakhs": price_max,
        "price_display": _format_price_display(price_min, price_max) or ("" if (price_min is not None or price_max is not None) else ""),
        "handover": handover,
        "handover_year": None if status == "ready_to_move" else None,
        "bhk": bhk,
        "url": project_url,
    }


def scrape_nobroker_list(html: str, base_url: str) -> list[dict]:
    """Parse NoBroker new-projects listing HTML and return list of property dicts."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_urls: set[str] = set()

    # Find project detail links: nobroker.in/xxx where xxx contains bangalore, not listing/page
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href.startswith("http") and not href.startswith("/"):
            continue
        full_url = urljoin(base_url, href).split("?")[0].rstrip("/")
        if "nobroker.in" not in full_url:
            continue
        path = full_url.replace("https://www.nobroker.in/", "").replace("http://www.nobroker.in/", "").strip("/")
        if not path or "new-projects-in" in path or "-page-" in path:
            continue
        if path in ("about", "terms", "contact", "home", "flats-for-sale", "property"):
            continue
        # Skip location listing pages (new-projects-in-area-bangalore)
        if path.startswith("new-projects-in-") and path.endswith("-bangalore"):
            continue
        if full_url in seen_urls:
            continue
        # Project detail pages usually have longer slugs (project-name-area-bangalore)
        if len(path) < 10:
            continue
        seen_urls.add(full_url)
        parent = a.find_parent(["article", "div", "section", "li"])
        card_text = ""
        if parent:
            card_text = parent.get_text(separator="\n", strip=True) or ""
            if len(card_text) < 50:
                parent = parent.find_parent(["article", "div", "section", "li"])
                if parent:
                    card_text = parent.get_text(separator="\n", strip=True) or ""
        if not card_text:
            card_text = a.get_text(separator="\n", strip=True) or ""
        name_from_link = (a.get_text(strip=True) or "").strip()[:200]
        if len(name_from_link) > 4 and name_from_link not in ("List", "Map", "Filter your Search", "Reset", "Sort By", "Next >>", "<< Prev"):
            if not card_text or len(card_text) < 20:
                card_text = name_from_link + "\n" + card_text
        rec = _parse_nobroker_card_text(card_text, full_url)
        if rec and rec.get("name") and not _is_junk_project_name(rec.get("name", "")):
            rec["name"] = rec["name"] or name_from_link or rec["name"]
            results.append(rec)

    # Dedupe by url
    seen = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    # Regex fallback: find blocks that look like "Project Name" + "Name, Locality, Bangalore"
    if len(unique) < 5 and len(html) > 3000:
        fallback = _nobroker_extract_from_raw(html, base_url)
        for r in fallback:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)
    return unique


def _parse_nobroker_detail_page(html: str) -> dict:
    """Extract price, builder, address, status, handover, BHK from a NoBroker project detail page."""
    out = {}
    if not html or len(html) < 500:
        return out
    # Strip tags for regex
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    # Price: "₹1.42 Cr - ₹2.22 Cr" or "Rs. 1.04 Crores to Rs. 2.07 Crores" or "₹ 1.42 cr - 2.22 cr"
    for pattern in [
        r"₹\s*([\d.]+)\s*Cr\s*-\s*₹?\s*([\d.]+)\s*Cr",
        r"Rs\.\s*([\d.]+)\s*Crores?\s+to\s+Rs\.\s*([\d.]+)\s*Crores?",
        r"([\d.]+)\s*Crores?\s*-\s*([\d.]+)\s*Crores?",
    ]:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                low, high = float(m.group(1)), float(m.group(2))
                if low <= high and high < 1000:
                    out["price_min_lakhs"] = low * 100
                    out["price_max_lakhs"] = high * 100
                    out["price_display"] = _format_price_display(low * 100, high * 100)
                    break
            except ValueError:
                pass
    if "price_min_lakhs" not in out:
        pmin, pmax = parse_price_range(text)
        if pmin is not None or pmax is not None:
            out["price_min_lakhs"] = pmin
            out["price_max_lakhs"] = pmax
            out["price_display"] = _format_price_display(pmin, pmax)
    # Builder: "By Goyal And Co Hariyana Group" or "## By ..."
    m = re.search(r"By\s+([A-Za-z][A-Za-z0-9\s&.,'-]{2,80}?)(?:\s+Est\.|\s*$|\.)", text)
    if m:
        out["builder"] = m.group(1).strip()[:100]
    # Full address: "Near RS Palace ..., Gunjur Village, Varthur Main Road, Bangalore."
    m = re.search(r"(Near\s+[^,]+,(?:\s*[^,]+,)*\s*[^,]+,\s*Bangalore\.?)", text)
    if m:
        addr = m.group(1).strip()
        if 15 < len(addr) < 200 and "nobroker" not in addr.lower():
            out["locality"] = addr[:150]
    if "locality" not in out:
        m = re.search(r"([A-Za-z][^.]{15,120}?,?\s*(?:Gunjur|Varthur|Whitefield|Sarjapur|Bellandur|Marathahalli)[^.]*?Bangalore\.?)", text)
        if m:
            addr = m.group(1).strip()
            if "nobroker" not in addr.lower():
                out["locality"] = addr[:150]
    # Status
    if "under construction" in text.lower():
        out["status"] = "under_construction"
    elif "ready to move" in text.lower() or "ready" in text.lower() and "possession" not in text[max(0, text.lower().find("ready") - 20) : text.lower().find("ready") + 50]:
        out["status"] = "ready_to_move"
    # Possession: "Possession in February 2030" or "Possession in Dec 2028"
    m = re.search(r"Possession\s+in\s+([A-Za-z]+\s+\d{4})", text, re.I)
    if m:
        out["handover"] = m.group(1).strip()
        y = _year_from_possession(out["handover"])
        if y:
            out["handover_year"] = y
    elif "possession" in text.lower() and "february 2030" in text.lower():
        out["handover"] = "Feb 2030"
        out["handover_year"] = 2030
    # BHK: "2, 2.5, 3 BHK" or "2 BHK - 1260"
    m = re.search(r"(\d[\d.,\s]*(?:\d+\.?\d*)?)\s*BHK", text)
    if m:
        out["bhk"] = m.group(1).strip().replace(" ", "")[:30]
    return out


def _parse_99acres_detail_page(html: str, page_url: str) -> dict:
    """Extract canonical name, locality, builder, status, handover, BHK, price from 99acres project detail page."""
    out = {}
    if not html or len(html) < 500:
        return out
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    # Name + locality: "Prestige Raintree Park Whitefield, Bangalore" or title "Prestige Raintree Park, Whitefield, Bangalore"
    m = re.search(r"#\s*([A-Za-z0-9][A-Za-z0-9\s&.\'-]{3,100}?)\s+([A-Za-z][A-Za-z\s]+),\s*Bangalore", text)
    if m:
        out["name"] = m.group(1).strip()[:200]
        out["locality"] = (m.group(2).strip() + ", Bangalore")[:100]
    if "name" not in out:
        m = re.search(r"([A-Za-z0-9][A-Za-z0-9\s&.\'-]{3,80}),\s*([A-Za-z][A-Za-z\s]+),\s*Bangalore\s*-\s*Price", text)
        if m:
            out["name"] = m.group(1).strip()[:200]
            out["locality"] = (m.group(2).strip() + ", Bangalore")[:100]
    if "name" not in out and page_url:
        url_name, url_locality = _name_and_locality_from_href("/" + page_url.split("/")[-1])
        if url_name:
            out["name"] = url_name
            if url_locality:
                out["locality"] = url_locality

    # Builder: "Brought to you by Prestige Group," or "About Prestige Group"
    m = re.search(r"Brought\s+to\s+you\s+by\s+([A-Za-z][A-Za-z0-9\s&.,\'-]+?)\s*[,.]", text, re.I)
    if m:
        out["builder"] = m.group(1).strip()[:100]
    if "builder" not in out:
        m = re.search(r"About\s+([A-Za-z][A-Za-z0-9\s&.,\'-]{2,60}?)\s+The\s+[A-Za-z]", text, re.I)
        if m:
            out["builder"] = m.group(1).strip()[:100]
    if "builder" not in out and out.get("name"):
        out["builder"] = extract_builder_from_title(out["name"])

    # Status: "Under Construction" / "Construction Status"
    if "under construction" in text.lower():
        out["status"] = "under_construction"
    elif "ready to move" in text.lower() or "ready to move in" in text.lower():
        out["status"] = "ready_to_move"
    elif "new launch" in text.lower():
        out["status"] = "new_launch"

    # Handover: "Completion from Dec, 2028 onwards" or "Possession in Dec 2028"
    m = re.search(r"Completion\s+from\s+([A-Za-z]+),\s*(\d{4})\s+onwards", text, re.I)
    if m:
        out["handover"] = f"{m.group(1).strip()[:3]} {m.group(2)}"
        try:
            out["handover_year"] = int(m.group(2))
        except ValueError:
            pass
    if "handover" not in out:
        m = re.search(r"Possession\s+(?:in\s+)?([A-Za-z]+\s+\d{4})", text, re.I)
        if m:
            out["handover"] = m.group(1).strip()[:50]
            out["handover_year"] = _year_from_possession(out["handover"])
    if "handover" not in out and "ready to move" in text.lower():
        out["handover"] = "Ready to move"

    # Price: "₹ 1.77 - 5.37 Cr" or "₹1.77 - 5.37 Cr"
    pmin, pmax = parse_price_range(text)
    if pmin is not None or pmax is not None:
        out["price_min_lakhs"] = pmin
        out["price_max_lakhs"] = pmax
        out["price_display"] = _format_price_display(pmin, pmax)

    # BHK: "1, 2, 3, 4, 5 BHK" or "PRICE RANGE1, 2, 3, 4, 5 BHK"
    m = re.search(r"(?:PRICE\s*RANGE\s*)?(\d[\d.,\s]*)\s*BHK\s+Apartment", text, re.I)
    if m:
        out["bhk"] = m.group(1).strip().replace(" ", "")[:30]
    if "bhk" not in out:
        m = re.search(r"(\d[\d.,\s]+)\s*BHK", text)
        if m:
            out["bhk"] = m.group(1).strip().replace(" ", "")[:30]
    return out


def _enrich_99acres_from_detail(record: dict) -> None:
    """Fetch 99acres project detail page and merge canonical name, builder, locality, etc. into record (in place)."""
    url = record.get("url")
    if not url or "99acres.com" not in url or "npxid" not in url:
        return
    html = fetch_99acres_detail(url)
    if not html:
        return
    details = _parse_99acres_detail_page(html, url)
    for key, value in details.items():
        if value is not None and value != "":
            record[key] = value


def _enrich_nobroker_from_detail(record: dict) -> None:
    """Fetch project detail page and merge price, builder, locality, etc. into record (in place)."""
    url = record.get("url")
    if not url or "nobroker.in" not in url:
        return
    if "new-projects-in" in url or "-page-" in url:
        return
    # Use fast requests-only fetch (15s timeout); avoids Playwright hang on 200+ pages
    html = fetch_nobroker_detail(url)
    if not html:
        return
    details = _parse_nobroker_detail_page(html)
    for key, value in details.items():
        if value is not None and value != "":
            record[key] = value


def _nobroker_extract_from_raw(html: str, base_url: str) -> list[dict]:
    """Extract project cards from raw HTML using regex (when DOM structure is unclear)."""
    results = []
    # Pattern: >Project Name</ then nearby "Project Name, Locality, Bangalore, India"
    name_loc = re.findall(
        r"([A-Za-z0-9][A-Za-z0-9\s&\.\'-]{4,120}),\s*([^,<]+),\s*Bangalore\s*,?\s*India",
        html
    )
    for name, locality in name_loc:
        name = name.strip()[:200]
        locality = locality.strip()[:100]
        slug = _nobroker_slug(name, locality)
        url = f"{NOBROKER_BASE}/{slug}"
        block = html
        idx = block.find(name + ",")
        if idx == -1:
            idx = block.find(name)
        if idx != -1:
            block = block[max(0, idx - 100):idx + 800]
        block_clean = re.sub(r"<[^>]+>", " ", block)
        block_clean = re.sub(r"\s+", " ", block_clean)
        rec = _parse_nobroker_card_text(name + ", " + locality + ", Bangalore, India\n\n" + block_clean, url)
        if rec and rec.get("name"):
            results.append(rec)
    return results


def run_scraper(max_pages_per_category: int | None = None, do_skip_enrich: bool = True) -> list[dict]:
    """Fetch 99acres + NoBroker; merge, deduplicate. Enrich NoBroker from detail pages only if --enrich."""
    all_properties = []
    max_pages = max_pages_per_category if max_pages_per_category is not None else 999

    # --- 99acres ---
    for status, url in SOURCE_URLS.items():
        print(f"Scraping 99acres {status}: {url}")
        html = fetch(url)
        if html:
            items = scrape_99acres_list(html, url, status)
            print(f"  -> {len(items)} items")
            all_properties.extend(items)
        time.sleep(REQUEST_DELAY_SEC)

    for status, base_url in SOURCE_URLS.items():
        page = 2
        while page <= max_pages:
            page_url = base_url + f"-page-{page}"
            print(f"Scraping 99acres {status} page {page}: {page_url}")
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

    # --- NoBroker new projects in Bangalore ---
    print(f"Scraping NoBroker: {NOBROKER_LISTING_URL}")
    html = fetch_nobroker(NOBROKER_LISTING_URL)
    if html:
        items = scrape_nobroker_list(html, NOBROKER_BASE)
        print(f"  -> {len(items)} items")
        all_properties.extend(items)
    time.sleep(REQUEST_DELAY_SEC)

    page = 2
    while page <= max_pages:
        page_url = NOBROKER_PAGE_URL.format(page=page)
        print(f"Scraping NoBroker page {page}: {page_url}")
        html = fetch_nobroker(page_url)
        if not html:
            print(f"  -> fetch failed, stopping NoBroker pagination")
            break
        items = scrape_nobroker_list(html, NOBROKER_BASE)
        if not items:
            print(f"  -> 0 items, no more NoBroker pages")
            break
        print(f"  -> {len(items)} items")
        all_properties.extend(items)
        time.sleep(REQUEST_DELAY_SEC)
        page += 1

    # Deduplicate by URL (same project may appear in multiple sources/pages)
    seen_urls = set()
    unique = []
    for p in all_properties:
        if p["url"] not in seen_urls:
            seen_urls.add(p["url"])
            unique.append(p)
    # Drop junk entries (page titles, nav links)
    unique = [p for p in unique if not _is_junk_project_name((p.get("name") or "").strip())]
    # Verify and clean each record (normalize fields, validate price/handover, drop invalid)
    before_verify = len(unique)
    unique = [p for p in (verify_and_clean_property(p) for p in unique) if p is not None]
    if before_verify > len(unique):
        print(f"After verification: dropped {before_verify - len(unique)} invalid/incomplete records")
    print(f"Total after deduplication and junk filter: {len(unique)} properties")

    # Enrich from detail pages when --enrich: 99acres and NoBroker get canonical name, builder, locality, etc.
    if not do_skip_enrich:
        # 99acres: fetch each project page to get exact name, locality, builder, handover, BHK
        acres_list = [p for p in unique if (p.get("source") or "").strip() == "99acres"]
        if acres_list:
            total = len(acres_list)
            print(f"Enriching {total} 99acres properties from detail pages...", flush=True)
            failed = 0
            for i, p in enumerate(acres_list):
                n = i + 1
                print(f"  99acres {n}/{total}", flush=True)  # before fetch so progress never "stuck"
                try:
                    _enrich_99acres_from_detail(p)
                except Exception as e:
                    failed += 1
                    if failed <= 3:
                        print(f"  Skip 99acres #{n} ({(p.get('name') or '')[:40]}...): {e}", flush=True)
                if i < len(acres_list) - 1:
                    time.sleep(1)
            if failed:
                print(f"  Skipped {failed} 99acres detail pages (timeout or error).", flush=True)
            print("  99acres done.", flush=True)
            # Checkpoint save: if you stop during NoBroker, you still have JSON with enriched 99acres
            try:
                OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
                checkpoint = [p for p in (verify_and_clean_property(p) for p in unique) if p is not None]
                if checkpoint:
                    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                        json.dump(checkpoint, f, indent=2, ensure_ascii=False)
                    print(f"  Checkpoint: saved {len(checkpoint)} properties (99acres enriched).", flush=True)
            except Exception as e:
                print(f"  Checkpoint save failed: {e}", flush=True)
        # NoBroker: same as before
        nobroker_list = [p for p in unique if (p.get("source") or "").strip() == "nobroker"]
        if nobroker_list:
            total_nb = len(nobroker_list)
            print(f"Enriching {total_nb} NoBroker properties from detail pages...", flush=True)
            failed = 0
            for i, p in enumerate(nobroker_list):
                n = i + 1
                print(f"  NoBroker {n}/{total_nb} ", end="", flush=True)
                try:
                    _enrich_nobroker_from_detail(p)
                    print("ok", flush=True)
                except Exception as e:
                    failed += 1
                    print("skip", flush=True)
                    if failed <= 3:
                        print(f"    ({str(e)[:80]})", flush=True)
                if i < len(nobroker_list) - 1:
                    time.sleep(1)
            if failed:
                print(f"  Skipped {failed} detail pages (timeout or error).", flush=True)
            print("  Done.", flush=True)

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
    do_skip_enrich = "--enrich" not in sys.argv  # default: don't enrich (use --enrich to fetch detail pages)
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
    if not do_skip_enrich:
        print("NoBroker detail-page enrichment enabled (--enrich)")
    data = run_scraper(max_pages_per_category=max_pages, do_skip_enrich=do_skip_enrich)
    data = ensure_sample_data(data)
    # Final verification pass before write (normalizes sample data too)
    data = [p for p in (verify_and_clean_property(p) for p in data) if p is not None]
    if not data:
        data = ensure_sample_data([])  # fallback so we always write something
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data)} properties to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
