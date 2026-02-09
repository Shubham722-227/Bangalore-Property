"""
Scrape bank auction properties (land, home) from eauctionsindia.com for Bengaluru.
Output: public/auctions.json for the Next.js viewer (Bank Auctions mode).
Filters: price, sq ft, bank name, contact, address, category, auction dates.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Config ---
# Fetch from filtered search: residential, Bengaluru, Karnataka (~3,887 listings, ~324 pages)
OUTPUT_JSON = Path(__file__).resolve().parent.parent / "public" / "auctions.json"
BASE_URL = "https://www.eauctionsindia.com"
# URL pattern: /search/{page}?category=residential&city=bengaluru&state=karnataka
SEARCH_BASE = "https://www.eauctionsindia.com/search"
SEARCH_PARAMS = "category=residential&city=bengaluru&state=karnataka"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}
REQUEST_DELAY_SEC = 1.5
REQUEST_TIMEOUT = 25
MAX_LISTING_PAGES = 324   # residential Bengaluru has ~324 pages
MAX_DETAIL_PAGES = 5000   # fetch all property details


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  Fetch error: {e}")
        return None


def extract_property_ids_from_html(html: str) -> list[str]:
    """Find all /properties/<id> links in HTML."""
    ids = []
    for m in re.finditer(r"/properties/(\d+)", html):
        ids.append(m.group(1))
    return list(dict.fromkeys(ids))  # preserve order, dedupe


def parse_price_lakhs(text: str) -> float | None:
    """Parse reserve price / value into lakhs. Handles Rs. 45.5 Lakh, ₹ 1.2 Cr, ₹36,90,000.00 etc."""
    if not text:
        return None
    raw = text.replace(",", "").replace("₹", "").replace("Rs.", "").strip()
    m = re.search(r"([\d.]+)\s*Cr", raw, re.I)
    if m:
        try:
            return float(m.group(1)) * 100
        except ValueError:
            pass
    m = re.search(r"([\d.]+)\s*(?:Lakh|Lac|L)\b", raw, re.I)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"([\d.]+)\s*(?:Crore|Cr)", raw, re.I)
    if m:
        try:
            return float(m.group(1)) * 100
        except ValueError:
            pass
    # Indian format: ₹36,90,000.00 -> 36.9 lakhs
    m = re.search(r"[\d,]+(?:\.\d{2})?", raw)
    if m:
        try:
            num = float(m.group(0).replace(",", ""))
            return num / 100_000  # paise to lakhs if needed; value is in rupees so /100000 = lakhs
        except ValueError:
            pass
    return None


def parse_rupee_amount(text: str) -> tuple[str, float | None]:
    """Find first ₹ amount in text; return (raw_display, lakhs). E.g. ₹36,90,000.00 -> ('₹36,90,000.00', 36.9)."""
    m = re.search(r"₹\s*([\d,]+(?:\.\d{2})?)", text)
    if not m:
        return "", None
    raw = m.group(0).strip()
    num_str = m.group(1).replace(",", "")
    try:
        rupees = float(num_str)
        lakhs = rupees / 100_000
        return raw, lakhs
    except ValueError:
        return raw, None


def parse_sqft(text: str) -> str | None:
    """Extract sq ft / carpet area."""
    if not text:
        return None
    m = re.search(r"(\d[\d,.]*)\s*(?:sq\.?\s*ft|sqft|sft)", text, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:carpet|built-up|super)\s*[:\s]*(\d[\d,.]*)\s*sq", text, re.I)
    if m:
        return m.group(1).strip()
    return None


def parse_detail_page(html: str, url: str, prop_id: str) -> dict | None:
    """Extract title, reserve price, EMD, bank, branch, contact, description, etc. from detail page."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True) or ""
    text_flat = re.sub(r"\s+", " ", text)

    # --- Title: full property title e.g. "Axis Bank Non-Agricultural Land Auction in Anekal, Bengaluru" ---
    name = ""
    for tag in soup.find_all(["h1", "h2"]):
        t = (tag.get_text(strip=True) or "").strip()
        if len(t) > 10 and len(t) < 250 and ("auction" in t.lower() or "bank" in t.lower() or "bengaluru" in t.lower()):
            name = t[:250]
            break
    if not name:
        for tag in soup.find_all(["h1", "h2"]):
            t = (tag.get_text(strip=True) or "").strip()
            if len(t) > 5 and len(t) < 250:
                name = t[:250]
                break
    if not name:
        name = f"Property {prop_id}"

    # --- Reserve Price: "Reserve Price : ₹36,90,000.00" ---
    price_display = ""
    price_lakhs = None
    reserve_m = re.search(r"Reserve\s*Price\s*[:\s]*₹\s*([\d,]+(?:\.\d{2})?)", text_flat, re.I)
    if reserve_m:
        price_display, price_lakhs = parse_rupee_amount(reserve_m.group(0))
    if not price_display:
        for s in re.finditer(r"(?:reserve\s*price|value|amount)\s*[:\s]*[Rr]s\.?\s*[\d,.]+\s*(?:Lakh|Lac|Cr|Crore)?", text_flat, re.I):
            chunk = text_flat[max(0, s.start() - 10) : s.end() + 60]
            price_lakhs = parse_price_lakhs(chunk)
            if price_lakhs is not None:
                price_display = f"₹ {price_lakhs:.2f} L" if price_lakhs < 100 else f"₹ {price_lakhs/100:.2f} Cr"
                break

    # --- EMD (Earnest Money Deposit) ---
    emd_display = ""
    emd_lakhs = None
    emd_m = re.search(r"EMD\s*[:\s]*₹\s*([\d,]+(?:\.\d{2})?)", text_flat, re.I)
    if not emd_m:
        emd_m = re.search(r"Earnest\s*Money\s*Deposit\s*[:\s]*₹\s*([\d,]+(?:\.\d{2})?)", text_flat, re.I)
    if emd_m:
        emd_display, emd_lakhs = parse_rupee_amount(emd_m.group(0))

    # --- Bank Name (from "Bank Name" or "Bank Details" section) ---
    bank_name = ""
    bank_m = re.search(r"Bank\s*Name\s*[:\s]*([A-Za-z][A-Za-z0-9\s&.,'-]{2,80}?)(?:\s*Reserve|\s*EMD|\s*Branch|$)", text_flat, re.I)
    if bank_m:
        bank_name = re.sub(r"\s+", " ", bank_m.group(1).strip())[:120]
    if not bank_name:
        for m in re.finditer(r"(Axis Bank|SBI|HDFC|ICICI|PNB|BOB|Canara|Union Bank|Bank of Baroda|State Bank|DCB Bank|Ujjivan|PNB Housing)", text_flat, re.I):
            bank_name = m.group(1).strip()[:100]
            break

    # --- Branch Name ---
    branch_name = ""
    branch_m = re.search(r"Branch\s*Name\s*[:\s]*([^\n]{2,120}?)(?:\s*Service|\s*Contact|$)", text_flat, re.I)
    if branch_m:
        branch_name = re.sub(r"\s+", " ", branch_m.group(1).strip())[:120]

    # --- Contact: "contact Mr. Raghunath (Mobile No. 919886960484)" ---
    contact = ""
    contact_person = ""
    contact_mobile = ""
    contact_m = re.search(r"contact\s+(Mr\.?\s*[A-Za-z][A-Za-z\s.]{1,40}?)\s*\(?\s*Mobile\s*No\.?\s*[\s:]*([\d\s-]{10,15})", text_flat, re.I)
    if contact_m:
        contact_person = contact_m.group(1).strip()[:80]
        contact_mobile = re.sub(r"\s+", "", contact_m.group(2).strip())[:20]
        contact = f"{contact_person} (Mobile: {contact_mobile})"
    if not contact:
        for m in re.finditer(r"(?:contact|mobile|phone)[\s:]*([^\n]{5,80})", text_flat, re.I):
            contact = re.sub(r"\s+", " ", m.group(1).strip())[:100]
            break
    if not contact:
        for m in re.finditer(r"(\+?91[\s-]?\d{5}[\s-]?\d{5})", text_flat):
            contact = m.group(1).strip()[:50]
            break

    # --- Auction date & time: "18-02-2025 11:00 AM" ---
    auction_datetime = ""
    dt_m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+\d{1,2}:\d{2}\s*[AP]M)", text_flat, re.I)
    if dt_m:
        auction_datetime = dt_m.group(1).strip()
    auction_start = auction_datetime
    auction_end = ""
    for m in re.finditer(r"(?:end|closing)\s*[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text_flat, re.I):
        auction_end = m.group(1).strip()
        break

    # --- Description: main content block (before "Bank Details") ---
    description = ""
    bank_details_pos = text_flat.find("Bank Details")
    if bank_details_pos > 100:
        before_bank = text_flat[:bank_details_pos]
        # Take a substantial block that looks like description (skip nav/title repetition)
        parts = re.split(r"\s*(?:Auction ID|Reserve Price|Share|Login|Register)\s*", before_bank, 1)
        if len(parts) > 1:
            candidate = parts[-1].strip()
        else:
            candidate = before_bank[-4000:] if len(before_bank) > 4000 else before_bank
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if len(candidate) > 100:
            description = candidate[:3000]
    if not description:
        for tag in soup.find_all(["div", "section", "p"], class_=re.compile(r"description|content|detail|body", re.I)):
            desc_text = (tag.get_text(separator=" ", strip=True) or "").strip()
            if len(desc_text) > 150 and "reserve" not in desc_text.lower()[:50]:
                description = re.sub(r"\s+", " ", desc_text)[:3000]
                break

    sq_ft = parse_sqft(text_flat)
    address = ""
    for m in re.finditer(r"(?:address|location|situated at|property at)[\s:]*([^.]{15,200})", text_flat, re.I):
        addr = m.group(1).strip()
        if "bengaluru" in addr.lower() or "bangalore" in addr.lower() or len(addr) > 25:
            address = re.sub(r"\s+", " ", addr)[:250]
            break

    category = "Residential"
    if "non-agricultural land" in text_flat.lower() or "land" in name.lower():
        category = "Land"
    elif "plot" in text_flat.lower() or "plot" in name.lower():
        category = "Land"
    elif "commercial" in text_flat.lower():
        category = "Commercial"
    elif "flat" in text_flat.lower() or "apartment" in text_flat.lower():
        category = "Residential"

    return {
        "id": prop_id,
        "name": name,
        "description": description,
        "price_display": price_display or "",
        "price_lakhs": price_lakhs,
        "emd_display": emd_display,
        "emd_lakhs": emd_lakhs,
        "sq_ft": sq_ft,
        "bank_name": bank_name,
        "branch_name": branch_name,
        "contact": contact,
        "contact_person": contact_person,
        "contact_mobile": contact_mobile,
        "address": address,
        "url": url,
        "auction_start": auction_start,
        "auction_end": auction_end,
        "auction_datetime": auction_datetime,
        "category": category,
        "source": "eauctionsindia",
    }


def run_scraper() -> list[dict]:
    all_ids = []
    # Fetch from: /search/{page}?category=residential&city=bengaluru&state=karnataka
    for page in range(1, MAX_LISTING_PAGES + 1):
        url = f"{SEARCH_BASE}/{page}?{SEARCH_PARAMS}"
        print(f"Fetching listing page {page}: {url}")
        html = fetch(url)
        if html:
            ids = extract_property_ids_from_html(html)
            print(f"  -> {len(ids)} property IDs")
            all_ids.extend(ids)
        time.sleep(REQUEST_DELAY_SEC)

    unique_ids = list(dict.fromkeys(all_ids))[:MAX_DETAIL_PAGES]
    print(f"Total unique property IDs to fetch: {len(unique_ids)} (capped at {MAX_DETAIL_PAGES})")

    results = []
    for i, prop_id in enumerate(unique_ids):
        url = f"{BASE_URL}/properties/{prop_id}"
        print(f"  [{i+1}/{len(unique_ids)}] {url}")
        html = fetch(url)
        if html and len(html) > 1000:
            rec = parse_detail_page(html, url, prop_id)
            if rec:
                results.append(rec)
        time.sleep(REQUEST_DELAY_SEC)

    return results


def main():
    print("Scraping eauctionsindia.com — residential, Bengaluru, Karnataka...")
    data = run_scraper()
    if not data:
        data = [
            {
                "id": "sample1",
                "name": "Sample Bank Residential Auction in Bengaluru",
                "description": "",
                "price_display": "₹ 45.00 L",
                "price_lakhs": 45,
                "emd_display": "",
                "emd_lakhs": None,
                "sq_ft": "1200",
                "bank_name": "SBI",
                "branch_name": "",
                "contact": "+91 98765 43210",
                "contact_person": "",
                "contact_mobile": "",
                "address": "Sample layout, Bengaluru",
                "url": "https://www.eauctionsindia.com/properties/1",
                "auction_start": "",
                "auction_end": "",
                "auction_datetime": "",
                "category": "Residential",
                "source": "eauctionsindia",
            },
        ]
        print("No data scraped; using sample record.")
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data)} auctions to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
