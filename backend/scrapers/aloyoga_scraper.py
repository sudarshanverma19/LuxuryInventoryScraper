"""
Alo Yoga (aloyoga.com) scraper.
Scrapes products from a Shopify store using the native JSON API.
API: https://www.aloyoga.com/en-in/products.json?limit=250&page=N (15 pages)
"""

import re
import json
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant, HealthCheckResult

logger = logging.getLogger(__name__)

class AloYogaScraper(BaseScraper):
    BRAND_SLUG = "alo-yoga"
    BRAND_NAME = "Alo Yoga"
    BASE_URL = "https://www.aloyoga.com/en-in/"
    PRODUCTS_API_URL = "https://www.aloyoga.com/en-in/products.json"

    HEALTH_SELECTORS = {}

    async def scrape(self) -> tuple[list[ScrapedProduct], HealthCheckResult]:
        """Override scrape() to use Playwright for JSON API."""
        health = HealthCheckResult()
        products = []

        logger.info(f"[{self.BRAND_NAME}] Starting scrape using Playwright JSON API...")

        try:
            await self._start_browser()
            page = await self._new_page()

            page_num = 1
            while True:
                url = f"{self.PRODUCTS_API_URL}?limit=250&page={page_num}"
                logger.info(f"[{self.BRAND_NAME}] Fetching page {page_num}...")

                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                if not response or response.status != 200:
                    # Let's try to parse it anyway in case it's a 403 with JSON payload, 
                    # but typically if it's not 200, it's blocked.
                    if response and response.status in (429, 403, 503):
                        logger.warning(f"[{self.BRAND_NAME}] API returned {response.status}")
                        if response.status == 403:
                            break
                    
                try:
                    data = await response.json()
                except Exception as e:
                    logger.error(f"[{self.BRAND_NAME}] Failed to parse JSON on page {page_num}: {e}")
                    health.add_issue("api_error", f"Failed to parse JSON on page {page_num}", "critical")
                    break

                page_products = data.get("products", [])

                if not page_products:
                    break

                for item in page_products:
                    product_url = f"{self.BASE_URL}products/{item['handle']}"
                    parsed = self._parse_shopify_json(item, product_url)
                    products.append(parsed)

                logger.info(f"[{self.BRAND_NAME}] Page {page_num}: {len(page_products)} products")

                if len(page_products) < 250:
                    break

                page_num += 1
                await asyncio.sleep(0.5)

            health = await self._run_health_checks(products, len(products))

        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")
        finally:
            await self._close_browser()

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")
        return products, health

    async def get_product_links(self) -> list[str]:
        return []

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        return None

    def _parse_shopify_json(self, data: dict, url: str) -> ScrapedProduct:
        """Parse Shopify product JSON into ScrapedProduct."""
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

        category = data.get("product_type", "") or "Activewear"

        variants = []
        for v in data.get("variants", []):
            title = v.get("title", "Default Title")
            sku = v.get("sku") or ""
            variants.append(ScrapedVariant(
                size=title[:50],  # Limit size string to DB max 50 chars
                in_stock=v.get("available", False),
                quantity=v.get("inventory_quantity"),
                sku=sku[:100] if sku else None,  # Limit SKU string to DB max 100 chars
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
            name=name[:300],  # Limit name to DB max 300 chars
            url=url[:1000],   # Limit URL to DB max 1000 chars
            price=price,
            currency="INR",
            image_url=image_url[:1000] if image_url else None,
            category=category[:100],
            description=description,
            variants=variants,
        )
