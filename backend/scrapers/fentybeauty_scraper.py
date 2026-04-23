"""
Fenty Beauty (fentybeauty.com) scraper.
Rihanna's beauty brand — makeup, skincare, fragrance, and hair.
Scrapes using the native Shopify JSON API via aiohttp for maximum speed.
"""

import re
import aiohttp
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant, HealthCheckResult

logger = logging.getLogger(__name__)


class FentyBeautyScraper(BaseScraper):
    BRAND_SLUG = "fenty-beauty"
    BRAND_NAME = "Fenty Beauty"
    BASE_URL = "https://fentybeauty.com/"
    PRODUCTS_API_URL = "https://fentybeauty.com/products.json"

    HEALTH_SELECTORS = {}

    async def scrape(self) -> tuple[list[ScrapedProduct], HealthCheckResult]:
        """
        Main entry point overridden to use Shopify JSON API directly instead of Playwright.
        Fenty has a very large catalog (1900+ products) so pagination is critical.
        """
        health = HealthCheckResult()
        products = []

        logger.info(f"[{self.BRAND_NAME}] Starting scrape using JSON API...")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "application/json",
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                page_num = 1
                while True:
                    url = f"{self.PRODUCTS_API_URL}?limit=250&page={page_num}"
                    logger.info(f"[{self.BRAND_NAME}] Fetching page {page_num}...")

                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.error(f"[{self.BRAND_NAME}] API returned {response.status}")
                            health.add_issue("api_error", f"API returned {response.status} on page {page_num}", "critical")
                            break

                        data = await response.json()
                        page_products = data.get("products", [])

                        if not page_products:
                            break

                        for item in page_products:
                            # Skip true GWP/sample items (very low price freebies)
                            variants = item.get("variants", [])
                            if variants:
                                try:
                                    first_price = float(variants[0].get("price", "0"))
                                    if first_price < 3.0:
                                        continue
                                except (ValueError, TypeError):
                                    pass

                            product_url = f"{self.BASE_URL}products/{item['handle']}"
                            parsed = self._parse_shopify_json(item, product_url)
                            products.append(parsed)

                        logger.info(f"[{self.BRAND_NAME}] Page {page_num}: {len(page_products)} raw, "
                                    f"{len(products)} total (after filtering)")

                        if len(page_products) < 250:
                            break

                        page_num += 1
                        await asyncio.sleep(1.0)  # Slightly longer delay for large catalog

            health = await self._run_health_checks(products, len(products))

        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed with error: {str(e)}", "critical")

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")
        return products, health

    # ── Abstract Methods implementation to satisfy BaseScraper ─────────

    async def get_product_links(self) -> list[str]:
        return []

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        return None

    # ── Parsing Logic ──────────────────────────────────────────────────

    def _parse_shopify_json(self, data: dict, url: str) -> ScrapedProduct:
        """Parse Shopify product JSON into ScrapedProduct."""
        name = data.get("title", "")
        description = data.get("body_html", "")
        if description:
            description = re.sub(r'<[^>]+>', ' ', description).strip()
            description = re.sub(r'\s+', ' ', description)[:500]

        # Image
        image_url = None
        images = data.get("images", [])
        if images:
            src = images[0].get("src", "")
            image_url = src if src.startswith("http") else f"https:{src}" if src else None

        # Category — use product_type from Shopify, fallback to Cosmetics
        category = data.get("product_type", "") or "Cosmetics"

        # Variants
        variants = []
        for v in data.get("variants", []):
            # Fenty uses option1 for shade/color/size
            size_label = v.get("option1") or v.get("title", "Default Title")
            color = v.get("option2")  # Sometimes option2 has color info

            variants.append(ScrapedVariant(
                size=size_label,
                color=color,
                in_stock=v.get("available", False),
                quantity=v.get("inventory_quantity"),
                sku=v.get("sku") or None,
            ))

        # Use first variant price as product price
        price = None
        if data.get("variants"):
            price_str = data["variants"][0].get("price", "")
            if price_str:
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    pass

        if not variants:
            variants.append(ScrapedVariant(in_stock=True))

        return ScrapedProduct(
            name=name,
            url=url,
            price=price,
            currency="USD",
            image_url=image_url,
            category=category,
            description=description or None,
            variants=variants,
        )
