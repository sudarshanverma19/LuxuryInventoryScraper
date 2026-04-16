"""
Magikart (magikart.in) scraper.
Scrapes Pokemon TCG cards from a Shopify store using the native JSON API.
This bypasses browser rendering entirely for maximum speed and reliability.
"""

import re
import aiohttp
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant, HealthCheckResult

logger = logging.getLogger(__name__)


class MagikartScraper(BaseScraper):
    BRAND_SLUG = "magikart"
    BRAND_NAME = "Magikart"
    BASE_URL = "https://magikart.in/"
    PRODUCTS_API_URL = "https://magikart.in/products.json"

    # Health selectors not strictly needed for API logic but required by base if any checks use it
    HEALTH_SELECTORS = {}

    async def scrape(self) -> tuple[list[ScrapedProduct], HealthCheckResult]:
        """
        Main entry point overriden to use Shopify JSON API directly instead of Playwright.
        """
        health = HealthCheckResult()
        products = []

        logger.info(f"[{self.BRAND_NAME}] Starting scrape using JSON API...")

        try:
            async with aiohttp.ClientSession() as session:
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
                            product_url = f"{self.BASE_URL}products/{item['handle']}"
                            parsed = self._parse_shopify_json(item, product_url)
                            products.append(parsed)
                            
                        if len(page_products) < 250:
                            # Reached the last page
                            break
                            
                        page_num += 1
                        await asyncio.sleep(0.5)
                        
            # Run health checks logic normally
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
        # Strip HTML from description
        if description:
            description = re.sub(r'<[^>]+>', ' ', description).strip()
            description = re.sub(r'\s+', ' ', description)[:500]

        # Image
        image_url = None
        images = data.get("images", [])
        if images:
            src = images[0].get("src", "")
            image_url = src if src.startswith("http") else f"https:{src}" if src else None

        # Category
        category = "Pokemon TCG"
        product_type = data.get("product_type", "")
        if product_type:
            category = product_type

        # Variants
        variants = []
        for v in data.get("variants", []):
            price = None
            price_str = v.get("price", "")
            if price_str:
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    pass

            variants.append(ScrapedVariant(
                size=v.get("title", "Default Title"),
                in_stock=v.get("available", False),
                quantity=v.get("inventory_quantity"),
                sku=v.get("sku"),
            ))

        # Use first variant price as product price
        price = None
        if variants and data.get("variants"):
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
            currency="INR",
            image_url=image_url,
            category=category,
            description=description,
            variants=variants,
        )
