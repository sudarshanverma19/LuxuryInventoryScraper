"""
Abstract base scraper class.
All brand-specific scrapers inherit from this and implement
get_product_links() and parse_product() methods.
"""

import json
import asyncio
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from playwright_stealth import stealth_async

from config import (
    HEADLESS, SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX,
    RATE_LIMIT_RPM, BLOCK_TRACKING_SCRIPTS, COOKIES_DIR,
    CAMOUFOX_BRANDS, PRODUCT_COUNT_ANOMALY_THRESHOLD,
    DATA_COMPLETENESS_THRESHOLD,
)
from utils.anti_detect import (
    get_random_user_agent, random_delay, get_random_viewport,
    get_random_fingerprint, setup_request_interception,
    get_stealth_launch_args, human_scroll, human_mouse_move,
)
from utils.proxy_manager import proxy_manager

logger = logging.getLogger(__name__)


class ScrapedProduct:
    """Data class for a scraped product."""

    def __init__(
        self,
        name: str,
        url: str,
        price: Optional[float] = None,
        currency: str = "USD",
        image_url: Optional[str] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        variants: Optional[list] = None,
    ):
        self.name = name
        self.url = url
        self.price = price
        self.currency = currency
        self.image_url = image_url
        self.category = category
        self.description = description
        self.variants = variants or []  # List of ScrapedVariant

    def __repr__(self):
        return f"<ScrapedProduct(name='{self.name}', variants={len(self.variants)})>"


class ScrapedVariant:
    """Data class for a scraped product variant."""

    def __init__(
        self,
        size: Optional[str] = None,
        color: Optional[str] = None,
        color_hex: Optional[str] = None,
        in_stock: bool = True,
        quantity: Optional[int] = None,
        sku: Optional[str] = None,
    ):
        self.size = size
        self.color = color
        self.color_hex = color_hex
        self.in_stock = in_stock
        self.quantity = quantity
        self.sku = sku

    def __repr__(self):
        stock = "in_stock" if self.in_stock else "out_of_stock"
        return f"<ScrapedVariant(size='{self.size}', color='{self.color}', {stock})>"


class HealthCheckResult:
    """Result of a scraper health check."""

    def __init__(self):
        self.issues: list[dict] = []  # {"check_type": str, "details": str, "severity": str}

    def add_issue(self, check_type: str, details: str, severity: str = "warning"):
        self.issues.append({
            "check_type": check_type,
            "details": details,
            "severity": severity,
        })

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def has_critical(self) -> bool:
        return any(i["severity"] == "critical" for i in self.issues)


class BaseScraper(ABC):
    """
    Abstract base scraper class with built-in anti-detection,
    cookie persistence, rate limiting, and health checks.
    """

    # Subclasses must define these
    BRAND_SLUG: str = ""
    BRAND_NAME: str = ""
    BASE_URL: str = ""

    # Health check selectors — subclasses define expected selectors
    HEALTH_SELECTORS: dict[str, str] = {}

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._request_count = 0
        self._request_window_start = None
        self._playwright = None

    # ── Public API ─────────────────────────────────────────────────────────

    async def scrape(self) -> tuple[list[ScrapedProduct], HealthCheckResult]:
        """
        Main entry point. Scrapes all products and runs health checks.
        Returns (products, health_check_result).
        """
        health = HealthCheckResult()
        products = []

        try:
            await self._start_browser()

            logger.info(f"[{self.BRAND_NAME}] Starting scrape...")

            # Get product listing page(s) and collect links
            product_links = await self.get_product_links()

            if not product_links:
                health.add_issue("selector", f"No product links found on {self.BASE_URL}", "critical")
                logger.warning(f"[{self.BRAND_NAME}] No product links found!")
                return products, health

            logger.info(f"[{self.BRAND_NAME}] Found {len(product_links)} product links")

            # Scrape each product page
            for i, link in enumerate(product_links):
                try:
                    await self._rate_limit()
                    await random_delay(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX)

                    logger.info(f"[{self.BRAND_NAME}] Scraping product {i+1}/{len(product_links)}: {link}")
                    product = await self.parse_product(link)

                    if product:
                        products.append(product)

                except Exception as e:
                    logger.error(f"[{self.BRAND_NAME}] Error scraping {link}: {e}")
                    continue

            # Run health checks
            health = await self._run_health_checks(products, len(product_links))

        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("response", f"Scrape failed with error: {str(e)}", "critical")

        finally:
            await self._close_browser()

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")
        return products, health

    # ── Abstract Methods (Brand-specific) ──────────────────────────────────

    @abstractmethod
    async def get_product_links(self) -> list[str]:
        """
        Navigate to product listing page(s) and collect all product URLs.
        Must be implemented by each brand scraper.
        """
        pass

    @abstractmethod
    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        """
        Navigate to a product page and extract all data.
        Must be implemented by each brand scraper.
        """
        pass

    # ── Browser Management ─────────────────────────────────────────────────

    async def _start_browser(self):
        """Launch Playwright browser with stealth settings."""
        self._playwright = await async_playwright().start()

        viewport = get_random_viewport()
        fingerprint = get_random_fingerprint()
        ua = get_random_user_agent()

        # Proxy settings
        proxy = proxy_manager.get_random_proxy() if proxy_manager.enabled else None

        # Launch browser
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=get_stealth_launch_args(),
        )

        # Create context with fingerprint
        context_args = {
            "viewport": viewport,
            "user_agent": ua,
            "locale": fingerprint["locale"],
            "timezone_id": fingerprint["timezone_id"],
        }

        if proxy:
            context_args["proxy"] = proxy

        self._context = await self._browser.new_context(**context_args)

        # Load saved cookies if they exist
        await self._load_cookies()

    async def _close_browser(self):
        """Save cookies and close the browser."""
        if self._context:
            await self._save_cookies()
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_page(self) -> Page:
        """Create a new page with stealth and interception applied."""
        page = await self._context.new_page()

        # Apply stealth
        await stealth_async(page)

        # Block tracking scripts
        if BLOCK_TRACKING_SCRIPTS:
            await setup_request_interception(page)

        return page

    # ── Cookie Persistence ─────────────────────────────────────────────────

    def _cookie_path(self) -> Path:
        return COOKIES_DIR / f"{self.BRAND_SLUG}_cookies.json"

    async def _save_cookies(self):
        """Save cookies to appear as a returning visitor."""
        try:
            cookies = await self._context.cookies()
            with open(self._cookie_path(), "w") as f:
                json.dump(cookies, f, indent=2)
            logger.debug(f"[{self.BRAND_NAME}] Saved {len(cookies)} cookies")
        except Exception as e:
            logger.debug(f"[{self.BRAND_NAME}] Failed to save cookies: {e}")

    async def _load_cookies(self):
        """Load saved cookies if available."""
        cookie_file = self._cookie_path()
        if cookie_file.exists():
            try:
                with open(cookie_file, "r") as f:
                    cookies = json.load(f)
                await self._context.add_cookies(cookies)
                logger.debug(f"[{self.BRAND_NAME}] Loaded {len(cookies)} saved cookies")
            except Exception as e:
                logger.debug(f"[{self.BRAND_NAME}] Failed to load cookies: {e}")

    # ── Rate Limiting ──────────────────────────────────────────────────────

    async def _rate_limit(self):
        """Enforce rate limiting: max N requests per minute."""
        now = asyncio.get_event_loop().time()

        if self._request_window_start is None:
            self._request_window_start = now
            self._request_count = 0

        elapsed = now - self._request_window_start

        if elapsed >= 60:
            # Reset window
            self._request_window_start = now
            self._request_count = 0

        self._request_count += 1

        if self._request_count >= RATE_LIMIT_RPM:
            wait_time = 60 - elapsed
            if wait_time > 0:
                logger.info(f"[{self.BRAND_NAME}] Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self._request_window_start = asyncio.get_event_loop().time()
                self._request_count = 0

    # ── Health Checks ──────────────────────────────────────────────────────

    async def _run_health_checks(
        self,
        products: list[ScrapedProduct],
        links_found: int,
    ) -> HealthCheckResult:
        """Run all health checks after scraping."""
        health = HealthCheckResult()

        # 1. Product count anomaly
        if len(products) == 0 and links_found > 0:
            health.add_issue(
                "count_anomaly",
                f"Found {links_found} product links but parsed 0 products",
                "critical",
            )

        # 2. Data completeness
        if products:
            missing_name = sum(1 for p in products if not p.name)
            missing_price = sum(1 for p in products if p.price is None)
            total = len(products)

            name_pct = (missing_name / total) * 100
            price_pct = (missing_price / total) * 100

            if name_pct > DATA_COMPLETENESS_THRESHOLD:
                health.add_issue(
                    "data_completeness",
                    f"{name_pct:.0f}% of products missing name (threshold: {DATA_COMPLETENESS_THRESHOLD}%)",
                    "critical",
                )

            if price_pct > DATA_COMPLETENESS_THRESHOLD:
                health.add_issue(
                    "data_completeness",
                    f"{price_pct:.0f}% of products missing price (threshold: {DATA_COMPLETENESS_THRESHOLD}%)",
                    "warning",
                )

        # 3. Variant data check
        products_without_variants = sum(1 for p in products if len(p.variants) == 0)
        if products and products_without_variants == len(products):
            health.add_issue(
                "data_completeness",
                "All products have 0 variants — variant extraction may be broken",
                "warning",
            )

        return health

    # ── Helper Methods for Subclasses ──────────────────────────────────────

    async def _navigate_with_retry(self, page: Page, url: str, retries: int = 3) -> bool:
        """Navigate to a URL with retry logic and exponential backoff."""
        for attempt in range(retries):
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                if response and response.status == 200:
                    return True

                if response and response.status in (429, 503):
                    wait = (2 ** attempt) * 5 + random.uniform(1, 3)
                    logger.warning(f"[{self.BRAND_NAME}] Got {response.status}, retrying in {wait:.1f}s")
                    await asyncio.sleep(wait)
                    continue

                if response and response.status == 403:
                    logger.warning(f"[{self.BRAND_NAME}] Got 403 Forbidden for {url}")
                    return False

                return True  # Other status codes, try to parse anyway

            except Exception as e:
                if attempt < retries - 1:
                    wait = (2 ** attempt) * 3
                    logger.warning(f"[{self.BRAND_NAME}] Navigation error: {e}, retrying in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"[{self.BRAND_NAME}] Navigation failed after {retries} attempts: {e}")
                    return False

        return False

    async def _wait_for_selector_safe(self, page: Page, selector: str, timeout: int = 10000):
        """Wait for a selector with a safe timeout — returns True if found."""
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def _get_text(self, page: Page, selector: str) -> Optional[str]:
        """Safely get text content from a selector."""
        try:
            element = await page.query_selector(selector)
            if element:
                text = await element.text_content()
                return text.strip() if text else None
        except Exception:
            pass
        return None

    async def _get_attribute(self, page: Page, selector: str, attr: str) -> Optional[str]:
        """Safely get an attribute from a selector."""
        try:
            element = await page.query_selector(selector)
            if element:
                return await element.get_attribute(attr)
        except Exception:
            pass
        return None

    async def _get_all_texts(self, page: Page, selector: str) -> list[str]:
        """Get text content from all matching elements."""
        try:
            elements = await page.query_selector_all(selector)
            texts = []
            for el in elements:
                text = await el.text_content()
                if text and text.strip():
                    texts.append(text.strip())
            return texts
        except Exception:
            return []
