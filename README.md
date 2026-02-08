# Bangalore Builder Properties Scraper & Viewer

Scrapes Bangalore builder project data (new launch, under construction, ready to move) from **99acres** and displays it in a simple HTML viewer with filters.

## Setup

```bash
cd Banglprop
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install firefox
```

The scraper uses **Playwright with Firefox** first (avoids HTTP/2 errors on 99acres); if Firefox fails it tries Chromium, then `requests`. Install Firefox: `python -m playwright install firefox`.

## Scrape data

```bash
python scraper.py
```

This fetches listings from 99acres and writes `properties.json` in the same folder. If the site structure changes or requests are blocked, the script falls back to sample data so you always get a valid JSON file.

## View the data

1. **Option A (recommended)** – Serve the folder and open in the browser:
   ```bash
   python -m http.server 8000
   ```
   Then open: **http://localhost:8000**

2. **Option B** – Open `index.html` directly in the browser.  
   If `properties.json` is in the same folder, some browsers may load it; otherwise you’ll see “Could not load properties.json” and should use Option A.

## Filters in the viewer

- **Price min / max (Lakhs)** – Filter by price range (e.g. 50–300 lakhs).
- **Handover year** – 2026, 2027, … or “Ready to move”.
- **Status** – New launch, Under construction, Ready to move.
- **Locality** – Text filter (e.g. Whitefield, Sarjapur).
- **Builder** – Text filter (e.g. Prestige, Brigade).

Apply / Reset to update the list.

## Data sources

- **99acres**: New launch, under construction, and ready-to-move projects in Bangalore.  
- **MagicBricks**: Can be added later (URLs may require different handling).

## Known issues

- **Firefox** is used first; if it fails, Chromium (HTTP/2 disabled) is tried, then `requests`.
- **Requests** may time out (60s) or be throttled; then sample data is used so the viewer still works.
- Install Firefox: `python -m playwright install firefox` (Chromium optional for fallback).

**Quick test (1 page per category):** `python scraper.py --quick`

## Notes

- Scraping is rate-limited (delay between requests). Respect the sites’ terms of use.
- For more reliable scraping if the site is heavily JavaScript-based, consider using Playwright or Selenium and extending `scraper.py`.
