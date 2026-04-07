# 📦 InventoryScraper

A Python-based web scraper dashboard for extracting product inventory data from luxury brand e-commerce websites.

## Features

- **6 Brand Scrapers**: On Running, Hoka, Acne Studios, Maison Margiela, Hourglass Cosmetics, Drunk Elephant
- **Anti-Detection (11 layers)**: Stealth browser, UA rotation, fingerprint spoofing, cookie persistence, request interception, rate limiting, proxy support, and more
- **Polished Dashboard**: Dark luxury theme with glassmorphism and micro-animations
- **Stock Alerts**: Auto-detect low stock (< configurable threshold) and out-of-stock items
- **Structure Change Detection**: Health checks alert when a website's HTML structure changes
- **Export**: Download inventory data as CSV or styled Excel

## Quick Start

```bash
# 1. Install Python dependencies
cd backend
pip install -r requirements.txt

# 2. Install Playwright browsers
playwright install chromium

# 3. Start the server
python main.py
```

Open **http://localhost:8000** in your browser.

## Configuration

Edit `backend/config.py` or create a `.env` file:

```env
# Scraping
HEADLESS=true
SCRAPE_DELAY_MIN=2.0
SCRAPE_DELAY_MAX=6.0
RATE_LIMIT_RPM=10

# Proxies (comma-separated)
PROXY_LIST=http://user:pass@host:port

# Camoufox (enable per brand)
CAMOUFOX_BRANDS=hoka,maison-margiela

# Alerts
LOW_STOCK_THRESHOLD=10
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Scraping | Playwright (async) + Stealth |
| Database | SQLite + SQLAlchemy |
| Frontend | Vanilla HTML/CSS/JS |
| Export | openpyxl + csv |
