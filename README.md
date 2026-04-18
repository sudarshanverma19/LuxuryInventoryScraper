# 📦 InventoryScraper

A Python-based web scraper dashboard for extracting product inventory data from luxury brand e-commerce websites.

## 🚀 Quick Start (One-Click Launch)

### Windows
1. Make sure [Python 3.11+](https://www.python.org/downloads/) is installed
   - ⚠️ **Check "Add Python to PATH"** during installation!
2. **Double-click `Start Scraper.bat`**
3. The dashboard opens automatically in your browser at `http://localhost:8000`
4. Press `Ctrl+C` in the terminal window to stop

### macOS / Linux
1. Make sure Python 3.11+ is installed
   - macOS: `brew install python3`
   - Ubuntu/Debian: `sudo apt install python3 python3-venv python3-pip`
2. Make the script executable (first time only):
   ```bash
   chmod +x start_scraper.sh
   ```
3. **Double-click `start_scraper.sh`** (or run `./start_scraper.sh` in Terminal)
4. The dashboard opens automatically in your browser at `http://localhost:8000`
5. Press `Ctrl+C` in the terminal to stop

> **First launch** takes 1-2 minutes (installs dependencies + Chromium browser).  
> **Subsequent launches** start in seconds.

---

## Features

- **13+ Brand Scrapers**: On Running, Acne Studios, Maison Margiela, Hourglass Cosmetics, Drunk Elephant, and more
- **Anti-Detection (11 layers)**: Stealth browser, UA rotation, fingerprint spoofing, cookie persistence, request interception, rate limiting, proxy support, and more
- **Polished Dashboard**: Dark luxury theme with glassmorphism and micro-animations
- **Stock Alerts**: Auto-detect low stock (< configurable threshold) and out-of-stock items
- **Structure Change Detection**: Health checks alert when a website's HTML structure changes
- **Export**: Download inventory data as CSV or styled Excel

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
|-------|------------|
| Backend | Python 3.11+ / FastAPI |
| Scraping | Playwright (async) + Stealth |
| Database | SQLite + SQLAlchemy |
| Frontend | Vanilla HTML/CSS/JS |
| Export | openpyxl + csv |

## Manual Setup (Advanced)

If you prefer to set up manually instead of using the launcher:

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
