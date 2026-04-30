"""
Skims (skims.com) scraper.
Uses Skims' sitemap for product discovery and LD+JSON (application/ld+json)
structured data for product details. No browser needed — pure HTTP.

Data source:
  - Sitemap: https://skims.com/sitemap-products.xml → all product URLs
  - Each product page embeds application/ld+json with @type=ProductGroup
    containing full variant info (size, price, stock, SKU, GTIN).
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

# Concurrency limit to be polite
MAX_CONCURRENT_REQUESTS = 5
# Max products per run (Skims has ~3000+ products, set 0 for unlimited)
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


class SkimsScraper(BaseScraper):
    BRAND_SLUG = "skims"
    BRAND_NAME = "Skims"
    BASE_URL = "https://skims.com/en-in/"
    SITEMAP_URL = "https://skims.com/sitemap-products.xml"

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
                if "/products/" in url:
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
                    try:
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        # Skims redirects aggressively, page.goto may throw
                        pass
                    
                    # Use page.content() instead of resp.text() because
                    # Skims redirects pages (e.g. /products/x -> /en-in/products/x)
                    # which makes the response object stale
                    html = await page.content()
                    product = self._parse_ld_json(html, url)
                    if product:
                        products.append(product)
                        
                    if (i + 1) % 50 == 0:
                        logger.info(f"[{self.BRAND_NAME}] Processed {i + 1}/{len(product_urls)} products ({len(products)} parsed)")
                except Exception as e:
                    logger.warning(f"[{self.BRAND_NAME}] Fetch error for {url}: {e}")
                    
            health = await self._run_health_checks(products, len(product_urls))

        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")
        finally:
            await self._close_browser()

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")
        return products, health



    # ── Abstract method stubs (required by BaseScraper) ────────────────

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

                ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                urls = []
                for loc in root.findall(".//s:loc", ns):
                    url = loc.text.strip() if loc.text else ""
                    if "/products/" in url:
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
        """Fetch a product page and extract data from LD+JSON."""
        async with semaphore:
            try:
                await asyncio.sleep(0.3 + (hash(url) % 10) * 0.1)

                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.debug(f"[{self.BRAND_NAME}] {url} returned {resp.status}")
                        return None

                    html = await resp.text()
                    return self._parse_ld_json(html, url)

            except asyncio.TimeoutError:
                logger.debug(f"[{self.BRAND_NAME}] Timeout: {url}")
                return None
            except Exception as e:
                logger.debug(f"[{self.BRAND_NAME}] Fetch error for {url}: {e}")
                return None

    # ── LD+JSON Parsing ────────────────────────────────────────────────

    def _parse_ld_json(self, html: str, url: str) -> Optional[ScrapedProduct]:
        """Extract product data from application/ld+json ProductGroup."""
        ld_matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            html,
            re.DOTALL,
        )

        product_data = None
        for match in ld_matches:
            try:
                data = json.loads(match)
                if data.get("@type") in ("ProductGroup", "Product"):
                    product_data = data
                    break
            except json.JSONDecodeError:
                continue

        if not product_data:
            logger.debug(f"[{self.BRAND_NAME}] No ProductGroup LD+JSON in {url}")
            return None

        # ── Name ──
        raw_name = product_data.get("name", "")
        if not raw_name:
            return None
        # Clean up name — remove color suffix after pipe
        name_parts = raw_name.split("|")
        name = name_parts[0].strip()

        # ── Color (from name or URL) ──
        color = None
        if len(name_parts) > 1:
            color = name_parts[1].strip().title()
        if not color:
            # Try extracting from URL slug
            slug_match = re.search(r'/products/.*?-([a-z-]+)$', url)
            if slug_match:
                color = slug_match.group(1).replace("-", " ").title()

        # ── Description ──
        description = product_data.get("description", "")
        if description:
            description = re.sub(r'<[^>]+>', ' ', description).strip()
            description = re.sub(r'\s+', ' ', description)[:500]

        # ── Image ──
        image_url = None
        image = product_data.get("image")
        if isinstance(image, str):
            image_url = image
        elif isinstance(image, list) and image:
            image_url = image[0] if isinstance(image[0], str) else image[0].get("url", "")
        elif isinstance(image, dict):
            image_url = image.get("url", "")

        # ── Category from URL or product type ──
        category = "Apparel"
        url_lower = url.lower()
        if "bra" in url_lower or "bralette" in url_lower:
            category = "Bras"
        elif "legging" in url_lower or "pant" in url_lower or "jogger" in url_lower:
            category = "Bottoms"
        elif "dress" in url_lower or "skirt" in url_lower:
            category = "Dresses"
        elif "thong" in url_lower or "brief" in url_lower or "boxer" in url_lower or "underwear" in url_lower:
            category = "Underwear"
        elif "bodysuit" in url_lower:
            category = "Bodysuits"
        elif "t-shirt" in url_lower or "tee" in url_lower or "top" in url_lower or "tank" in url_lower:
            category = "Tops"
        elif "hoodie" in url_lower or "sweat" in url_lower or "jacket" in url_lower:
            category = "Outerwear"
        elif "sock" in url_lower:
            category = "Socks"
        elif "short" in url_lower:
            category = "Shorts"
        elif "swim" in url_lower or "bikini" in url_lower:
            category = "Swim"
        elif "clip" in url_lower or "accessories" in url_lower:
            category = "Accessories"

        # ── Variants ──
        variants = []
        has_variant = product_data.get("hasVariant", [])

        # Determine currency from first variant
        currency = "INR"

        for v in has_variant:
            if not isinstance(v, dict):
                continue

            size = v.get("size", "")
            sku = v.get("mpn", "")

            offers = v.get("offers", {})
            if not isinstance(offers, dict):
                continue

            # Price
            variant_price = None
            raw_price = offers.get("price")
            if raw_price is not None:
                try:
                    variant_price = float(raw_price)
                except (ValueError, TypeError):
                    pass

            # Currency
            variant_currency = offers.get("priceCurrency", currency)
            if variant_currency:
                currency = variant_currency

            # Availability
            availability = offers.get("availability", "")
            in_stock = "InStock" in str(availability)

            variants.append(ScrapedVariant(
                size=size or None,
                color=color,
                in_stock=in_stock,
                sku=sku or None,
            ))

        # Get the price from the first variant
        price = None
        if has_variant:
            first_offers = has_variant[0].get("offers", {})
            if isinstance(first_offers, dict):
                try:
                    price = float(first_offers.get("price", 0))
                except (ValueError, TypeError):
                    pass

        if not variants:
            variants.append(ScrapedVariant(
                color=color,
                in_stock=True,
            ))

        return ScrapedProduct(
            name=name,
            url=url,
            price=price,
            currency=currency,
            image_url=image_url,
            category=category,
            description=description,
            variants=variants,
        )
