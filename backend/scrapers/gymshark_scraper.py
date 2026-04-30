"""
Gymshark (row.gymshark.com) scraper.
Uses Gymshark's sitemap + __NEXT_DATA__ (embedded Next.js JSON) to extract
product data without needing a browser. Extremely fast and reliable.

Data source:
  - Sitemap: https://row.gymshark.com/sitemap_products_1.xml → all product URLs
  - Each product page embeds __NEXT_DATA__ with full product info, variants,
    sizes, stock status, and inventory quantities.
"""

import re
import json
import asyncio
import logging
from typing import Optional
from xml.etree import ElementTree

import aiohttp

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant, HealthCheckResult

logger = logging.getLogger(__name__)

# Concurrency limit to avoid hammering the server
MAX_CONCURRENT_REQUESTS = 5
# Max products to scrape per run (Gymshark has ~1700+ products, set 0 for unlimited)
MAX_PRODUCTS = 0  # 0 = scrape all

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


class GymsharkScraper(BaseScraper):
    BRAND_SLUG = "gymshark"
    BRAND_NAME = "Gymshark"
    BASE_URL = "https://row.gymshark.com/"
    SITEMAP_URL = "https://row.gymshark.com/sitemap_products_1.xml"

    HEALTH_SELECTORS = {}  # Not needed — API-based scraper

    # ── Override scrape() — no browser needed ──────────────────────────

    async def scrape(self) -> tuple[list[ScrapedProduct], HealthCheckResult]:
        health = HealthCheckResult()
        products = []

        logger.info(f"[{self.BRAND_NAME}] Starting API-based scrape via Playwright...")

        try:
            await self._start_browser()
            page = await self._new_page()

            # Step 1: Get product URLs from sitemap
            logger.info(f"[{self.BRAND_NAME}] Fetching sitemap...")
            response = await page.goto(self.SITEMAP_URL, wait_until="domcontentloaded", timeout=30000)
            if not response or response.status != 200:
                health.add_issue("sitemap", f"Sitemap returned {response.status if response else 'None'}", "critical")
                return products, health

            xml_text = await response.text()
            
            import xml.etree.ElementTree as ElementTree
            root = ElementTree.fromstring(xml_text)
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            product_urls = []
            for loc in root.findall(".//s:loc", ns):
                url = loc.text.strip() if loc.text else ""
                if "/products/" in url and "gift-card" not in url:
                    product_urls.append(url)

            if not product_urls:
                health.add_issue("sitemap", "No product URLs found in sitemap", "critical")
                return products, health

            logger.info(f"[{self.BRAND_NAME}] Found {len(product_urls)} products in sitemap")
            if MAX_PRODUCTS:
                product_urls = product_urls[:MAX_PRODUCTS]

            # Step 2: Fetch each product page
            for i, url in enumerate(product_urls):
                try:
                    await asyncio.sleep(0.5)
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    if not resp or resp.status != 200:
                        continue
                        
                    html = await resp.text()
                    product = self._parse_next_data(html, url)
                    if product:
                        products.append(product)
                        
                    if (i + 1) % 50 == 0:
                        logger.info(f"[{self.BRAND_NAME}] Processed {i + 1}/{len(product_urls)} products")
                except Exception as e:
                    logger.debug(f"[{self.BRAND_NAME}] Fetch error for {url}: {e}")
                    
            health = await self._run_health_checks(products, len(product_urls))

        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")
        finally:
            await self._close_browser()

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")
        return products, health



    # ── Abstract method stubs (not used, but required by BaseScraper) ──

    async def get_product_links(self) -> list[str]:
        return []

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        return None

    # ── Sitemap Parsing ────────────────────────────────────────────────

    async def _get_product_urls_from_sitemap(
        self, session: aiohttp.ClientSession
    ) -> list[str]:
        """Fetch and parse the product sitemap XML."""
        try:
            async with session.get(self.SITEMAP_URL) as resp:
                if resp.status != 200:
                    logger.error(f"[{self.BRAND_NAME}] Sitemap returned {resp.status}")
                    return []

                xml_text = await resp.text()
                root = ElementTree.fromstring(xml_text)

                # Namespace-aware parsing
                ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                urls = []
                for loc in root.findall(".//s:loc", ns):
                    url = loc.text.strip() if loc.text else ""
                    if "/products/" in url and "gift-card" not in url:
                        urls.append(url)

                logger.info(f"[{self.BRAND_NAME}] Sitemap: {len(urls)} product URLs")
                return urls

        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Sitemap parse error: {e}")
            return []

    # ── Product Fetching ───────────────────────────────────────────────

    async def _fetch_product(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        url: str,
    ) -> Optional[ScrapedProduct]:
        """Fetch a single product page and extract data from __NEXT_DATA__."""
        async with semaphore:
            try:
                # Small random delay to be polite
                await asyncio.sleep(0.3 + (hash(url) % 10) * 0.1)

                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        logger.debug(f"[{self.BRAND_NAME}] {url} returned {resp.status}")
                        return None

                    html = await resp.text()
                    return self._parse_next_data(html, url)

            except asyncio.TimeoutError:
                logger.debug(f"[{self.BRAND_NAME}] Timeout: {url}")
                return None
            except Exception as e:
                logger.debug(f"[{self.BRAND_NAME}] Fetch error for {url}: {e}")
                return None

    # ── __NEXT_DATA__ Parsing ──────────────────────────────────────────

    def _parse_next_data(self, html: str, url: str) -> Optional[ScrapedProduct]:
        """Extract product data from __NEXT_DATA__ JSON embedded in the page."""
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            logger.debug(f"[{self.BRAND_NAME}] No __NEXT_DATA__ in {url}")
            return None

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.debug(f"[{self.BRAND_NAME}] Invalid JSON in __NEXT_DATA__ for {url}")
            return None

        page_props = data.get("props", {}).get("pageProps", {})
        product_data = page_props.get("productData", {})
        product = product_data.get("product", {})

        if not product:
            return None

        # ── Name ──
        name = product.get("title", "")
        if not name:
            return None

        # ── Price ──
        price = None
        raw_price = product.get("price")
        if raw_price is not None:
            try:
                price = float(raw_price)
            except (ValueError, TypeError):
                pass

        # ── Compare-at price (for sale items) ──
        compare_price = product.get("compareAtPrice")

        # ── Image ──
        image_url = None
        featured_media = product.get("featuredMedia", {})
        if isinstance(featured_media, dict):
            image_url = featured_media.get("src") or featured_media.get("url")

        # ── Description ──
        description = product.get("description", "")
        if description:
            # Strip HTML tags
            description = re.sub(r'<[^>]+>', ' ', description).strip()
            description = re.sub(r'\s+', ' ', description)[:500]

        # ── Category from type ──
        category = product.get("type", "Apparel")

        # ── Color ──
        color = product.get("colour", "")

        # ── Sizes & Variants ──
        variants = []
        available_sizes = product.get("availableSizes", [])

        for size_data in available_sizes:
            if not isinstance(size_data, dict):
                continue

            size = size_data.get("size", "")
            in_stock = size_data.get("inStock", False)
            quantity = size_data.get("inventoryQuantity")
            sku = size_data.get("sku", "")

            variants.append(ScrapedVariant(
                size=size.upper() if size else None,
                color=color or None,
                in_stock=in_stock,
                quantity=quantity,
                sku=sku or None,
            ))

        # Also add color variants from the variants array
        color_variants = product_data.get("variants", [])
        for cv in color_variants:
            if not isinstance(cv, dict):
                continue
            cv_color = cv.get("colour", "")
            cv_handle = cv.get("handle", "")
            # Skip the current product's color (already included above)
            if cv_handle == product.get("handle"):
                continue
            # Just note other color variants exist — don't add duplicate sizes
            # The variant data for other colors is on their own pages

        if not variants:
            # Fallback: single variant
            variants.append(ScrapedVariant(
                color=color or None,
                in_stock=product.get("inStock", True),
            ))

        return ScrapedProduct(
            name=name,
            url=url,
            price=price,
            currency="USD",
            image_url=image_url,
            category=category,
            description=description,
            variants=variants,
        )
