"""
TCG Republic (tcgrepublic.in) scraper.
Scrapes Pokemon TCG singles from a WooCommerce store using the Store API.
This bypasses browser rendering entirely for maximum speed and reliability.
"""

import re
import aiohttp
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant, HealthCheckResult

logger = logging.getLogger(__name__)


class TCGRepublicScraper(BaseScraper):
    BRAND_SLUG = "tcg-republic"
    BRAND_NAME = "TCG Republic"
    BASE_URL = "https://tcgrepublic.in/"
    PRODUCTS_API_URL = "https://tcgrepublic.in/wp-json/wc/store/products"

    HEALTH_SELECTORS = {}

    async def scrape(self) -> tuple[list[ScrapedProduct], HealthCheckResult]:
        """
        Main entry point overriden to use WooCommerce Store API directly.
        """
        health = HealthCheckResult()
        products = []

        logger.info(f"[{self.BRAND_NAME}] Starting scrape using Store API...")

        try:
            async with aiohttp.ClientSession() as session:
                page_num = 1
                while True:
                    url = f"{self.PRODUCTS_API_URL}?per_page=100&page={page_num}"
                    logger.info(f"[{self.BRAND_NAME}] Fetching page {page_num}...")
                    
                    async with session.get(url) as response:
                        if response.status == 400:
                            # 400 usually indicates out of bounds pagination in WP
                            break
                        if response.status != 200:
                            logger.error(f"[{self.BRAND_NAME}] API returned {response.status}")
                            health.add_issue("api_error", f"API returned {response.status} on page {page_num}", "critical")
                            break
                            
                        page_products = await response.json()
                        
                        if not page_products or not isinstance(page_products, list):
                            break
                            
                        for item in page_products:
                            parsed = self._parse_wc_json(item)
                            products.append(parsed)
                            
                        if len(page_products) < 100:
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
    
    def _parse_wc_json(self, data: dict) -> ScrapedProduct:
        """Parse WooCommerce product JSON into ScrapedProduct."""
        name = data.get("name", "")
        url = data.get("permalink", "")
        
        description = data.get("short_description", "") or data.get("description", "")
        # Strip HTML from description
        if description:
            description = re.sub(r'<[^>]+>', ' ', description).strip()
            description = re.sub(r'\s+', ' ', description)[:500]

        # Price
        price = None
        prices = data.get("prices", {})
        raw_price = prices.get("price")
        currency = prices.get("currency_code", "INR")
        minor_unit = prices.get("currency_minor_unit", 2)
        
        if raw_price:
            try:
                price = float(raw_price) / (10 ** minor_unit)
            except (ValueError, TypeError):
                pass
                
        # Image
        image_url = None
        images = data.get("images", [])
        if images:
            image_url = images[0].get("src")

        # Category
        category = "Pokemon TCG"
        categories = data.get("categories", [])
        if categories:
            cat_list = [c.get("name", "").lower() for c in categories]
            if any("one piece" in c for c in cat_list):
                category = "One Piece TCG"
            elif any("dragon ball" in c for c in cat_list):
                category = "Dragon Ball Z"
            elif any("yu gi oh" in c for c in cat_list) or any("yugioh" in c for c in cat_list):
                category = "Yu-Gi-Oh"
            elif any("digimon" in c for c in cat_list):
                category = "Digimon"

        # Stock
        in_stock = data.get("is_in_stock", True)
        
        # ── Parse card details from name ───────────────────────
        card_number = None
        card_match = re.search(r'#(\d+/\d+)', name)
        if card_match:
            card_number = card_match.group(1)
            
        sku = data.get("sku", "")

        variants = []
        # Support WooCommerce variations if any, otherwise single product
        variations = data.get("variations", [])
        if variations:
            for v in variations:
                v_in_stock = v.get("is_in_stock", True)
                # In basic WooCommerce store API, variation details might be limited
                variants.append(ScrapedVariant(
                    size=card_number,
                    in_stock=v_in_stock,
                    sku=sku
                ))
        else:
            variants.append(ScrapedVariant(
                size=card_number,
                in_stock=in_stock,
                sku=sku
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
