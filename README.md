# Bangalore Builder Properties

Next.js app that displays Bangalore builder project data (new launch, under construction, ready to move) scraped from **99acres**, with filters and dark mode. Deploy on **Vercel** or run locally.

## Run the app (Next.js)

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The app loads data from `/properties.json` (served from `public/properties.json`).

## Build & deploy (Vercel)

```bash
npm run build
```

Then connect the repo to [Vercel](https://vercel.com); deployment is automatic. No Python or scraper runs on Vercel—only the Next.js app and static `public/properties.json` are deployed.

## Scrape data (optional, local only)

To refresh property data:

```bash
cd scraper
pip install -r requirements.txt
python -m playwright install firefox
python scraper.py
```

This writes to `public/properties.json` in the project root. Use `python scraper.py --quick` for a quick test (1 page per category) or `python scraper.py --max-pages 25` to limit pages.

## Filters

- **Price min / max (Lakhs)** – Filter by price range.
- **Handover year** – 2026–2032 or “Ready to move”.
- **Status** – New launch, Under construction, Ready to move.
- **Locality** – Text filter (e.g. Whitefield, Sarjapur).
- **Builder** – Text filter (e.g. Prestige, Brigade).
- **Sort by handover** – Recent first or late first.

Filters and sort update the list in real time. Toggle dark mode with the button in the header.
