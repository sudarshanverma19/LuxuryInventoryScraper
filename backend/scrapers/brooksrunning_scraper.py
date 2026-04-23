"""
Brooks Running India (brooksrunningindia.com) scraper.
Shopify JSON API: https://brooksrunningindia.com/products.json?limit=250&page=1
"""

import re
import aiohttp
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant, HealthCheckResult

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class BrooksRunningScraper(BaseScraper):
    BRAND_SLUG = "brooks-running"
    BRAND_NAME = "Brooks Running India"
    BASE_URL = "https://brooksrunningindia.com/"
    PRODUCTS_API_URL = "https://brooksrunningindia.com/products.json"

    HEALTH_SELECTORS = {}

    async def scrape(self) -> tuple[list[ScrapedProduct], HealthCheckResult]:
        health = HealthCheckResult()
        products = []
        logger.info(f"[{self.BRAND_NAME}] Starting scrape using JSON API...")
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                page_num = 1
                while True:
                    url = f"{self.PRODUCTS_API_URL}?limit=250&page={page_num}"
                    logger.info(f"[{self.BRAND_NAME}] Fetching page {page_num}...")
                    async with session.get(url) as response:
                        if response.status != 200:
                            health.add_issue("api_error", f"API returned {response.status}", "critical")
                            break
                        data = await response.json()
                        page_products = data.get("products", [])
                        if not page_products:
                            break
                        for item in page_products:
                            product_url = f"{self.BASE_URL}products/{item['handle']}"
                            products.append(self._parse_shopify_json(item, product_url))
                        logger.info(f"[{self.BRAND_NAME}] Page {page_num}: {len(page_products)} products")
                        if len(page_products) < 250:
                            break
                        page_num += 1
                        await asyncio.sleep(0.5)
            health = await self._run_health_checks(products, len(products))
        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")
        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")
        return products, health

    async def get_product_links(self) -> list[str]:
        return []

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        return None

    def _parse_shopify_json(self, data: dict, url: str) -> ScrapedProduct:
        name = data.get("title", "")
        description = data.get("body_html", "")
        if description:
            description = re.sub(r'<[^>]+>', ' ', description).strip()
            description = re.sub(r'\s+', ' ', description)[:500]
        image_url = None
        images = data.get("images", [])
        if images:
            src = images[0].get("src", "")
            image_url = src if src.startswith("http") else f"https:{src}" if src else None
        category = data.get("product_type", "") or "Running Shoes"
        variants = []
        for v in data.get("variants", []):
            variants.append(ScrapedVariant(
                size=v.get("title", "Default Title"),
                in_stock=v.get("available", False),
                quantity=v.get("inventory_quantity"),
                sku=v.get("sku") or None,
            ))
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
            name=name, url=url, price=price, currency="INR",
            image_url=image_url, category=category,
            description=description, variants=variants,
        )
