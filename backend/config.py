"""
Application configuration for InventoryScraper.
All settings are configurable via environment variables or .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
COOKIES_DIR = DATA_DIR / "cookies"
COOKIES_DIR.mkdir(exist_ok=True)

# ── Database ───────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR / 'inventory.db'}")

# ── Server ─────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# ── Scraping ───────────────────────────────────────────────────────────────
# Delay between page loads (seconds) — gaussian distribution around these values
SCRAPE_DELAY_MIN = float(os.getenv("SCRAPE_DELAY_MIN", "2.0"))
SCRAPE_DELAY_MAX = float(os.getenv("SCRAPE_DELAY_MAX", "6.0"))

# Rate limiting: max requests per minute per domain
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "10"))

# Headless browser mode (set to False for debugging)
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

# ── Proxy ──────────────────────────────────────────────────────────────────
# Format: "http://user:pass@host:port" or "socks5://user:pass@host:port"
# Multiple proxies separated by comma
PROXY_LIST = [p.strip() for p in os.getenv("PROXY_LIST", "").split(",") if p.strip()]
PROXY_ENABLED = bool(PROXY_LIST)

# ── Anti-Detection ─────────────────────────────────────────────────────────
# Block tracking/analytics scripts during scraping
BLOCK_TRACKING_SCRIPTS = os.getenv("BLOCK_TRACKING_SCRIPTS", "true").lower() == "true"

# Camoufox: anti-detect Firefox browser (per-brand toggle)
# Set brand slugs that should use Camoufox, e.g., "hoka,margiela"
CAMOUFOX_BRANDS = [b.strip() for b in os.getenv("CAMOUFOX_BRANDS", "").split(",") if b.strip()]

# ── Alerts ─────────────────────────────────────────────────────────────────
# Low stock alert threshold (quantity below this triggers alert)
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "10"))

# Structure change detection: product count anomaly threshold (percentage drop)
PRODUCT_COUNT_ANOMALY_THRESHOLD = float(os.getenv("PRODUCT_COUNT_ANOMALY_THRESHOLD", "50.0"))

# Data completeness: max percentage of products with missing required fields
DATA_COMPLETENESS_THRESHOLD = float(os.getenv("DATA_COMPLETENESS_THRESHOLD", "20.0"))

# ── Brand Configurations ──────────────────────────────────────────────────
BRANDS = [
    {
        "name": "On Running",
        "slug": "on-running",
        "base_url": "https://www.on.com/en-us/",
        "category": "Shoes/Apparel",
    },
    # Hoka removed — Akamai Bot Manager blocks all automation.
    # Re-add when residential proxies are available.
    # {
    #     "name": "Hoka",
    #     "slug": "hoka",
    #     "base_url": "https://www.hoka.com/en/us/",
    #     "category": "Shoes",
    # },
    {
        "name": "Acne Studios",
        "slug": "acne-studios",
        "base_url": "https://www.acnestudios.com/us/en/home",
        "category": "Fashion",
    },
    {
        "name": "Maison Margiela",
        "slug": "maison-margiela",
        "base_url": "https://www.maisonmargiela.com/wx/",
        "category": "Fashion",
    },
    {
        "name": "Hourglass Cosmetics",
        "slug": "hourglass",
        "base_url": "https://www.hourglasscosmetics.com/",
        "category": "Cosmetics",
    },
    {
        "name": "Drunk Elephant",
        "slug": "drunk-elephant",
        "base_url": "https://www.drunkelephant.com/",
        "category": "Skincare",
    },
]
