"""
Hourglass Cosmetics (hourglasscosmetics.com) scraper.
Scrapes cosmetics products.
"""

import re
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant
from utils.anti_detect import random_delay, human_scroll, short_delay

logger = logging.getLogger(__name__)


class HourglassScraper(BaseScraper):
    BRAND_SLUG = "hourglass"
    BRAND_NAME = "Hourglass Cosmetics"
    BASE_URL = "https://www.hourglasscosmetics.com/"

    PRODUCT_LISTING_URLS = [
        "https://www.hourglasscosmetics.com/collections/makeup",
        "https://www.hourglasscosmetics.com/collections/equilibrium-skincare",
        "https://www.hourglasscosmetics.com/collections/brushes",
    ]

    HEALTH_SELECTORS = {
        "product_card": "a[href*='/products/']",
        "product_name": "h1",
        "price": ".price",
    }

    async def _start_browser(self):
        """Override to skip stealth plugin — causes blank pages on Hourglass."""
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,  # set True when confirmed working
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )

    async def _new_page(self):
        """Override to skip stealth_async — causes blank pages on Hourglass."""
        page = await self._context.new_page()
        return page

    async def get_product_links(self) -> list[str]:
        """Collect product URLs from collection pages."""
        links = set()
        page = await self._new_page()

        try:
            for listing_url in self.PRODUCT_LISTING_URLS:
                success = await self._navigate_with_retry(page, listing_url)
                if not success:
                    continue

                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await human_scroll(page, scroll_count=5)
                await short_delay()

                anchors = await page.query_selector_all('a[href*="/products/"]')
                for a in anchors:
                    href = await a.get_attribute("href")
                    if href and "/products/" in href:
                        slug = href.split("/products/")[-1].split("?")[0]
                        full_url = f"https://www.hourglasscosmetics.com/products/{slug}"
                        links.add(full_url)

                await random_delay()

        except Exception as e:
            logger.error(f"[Hourglass] Error collecting links: {e}")
        finally:
            await page.close()

        return list(links)[:100]

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        """Parse a single product page."""
        page = await self._new_page()

        try:
            success = await self._navigate_with_retry(page, url)
            if not success:
                return None

            await page.wait_for_load_state("domcontentloaded", timeout=15000)

            # Wait for product form to render before scraping variants
            try:
                await page.wait_for_selector(
                    '[class*="ProductForm__optionSwatchListAction"], [class*="ProductDetails-title"]',
                    timeout=8000
                )
            except Exception:
                pass  # continue anyway, may be a single-variant product

            await short_delay()

            # Product name — confirmed selector
            name = await self._get_text(page, '[class*="ProductDetails-title"], h1')
            if not name:
                return None
            name = name.strip()

            # Price — confirmed working
            price = None
            price_text = await self._get_text(page, '[class*="ProductDetails-price"], .price')
            if price_text:
                price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
                if price_match:
                    price = float(price_match.group())

            # Image — confirmed pattern
            image_url = await self._get_attribute(
                page,
                '[class*="ProductGallery"] img, picture img',
                "src"
            )
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

            # Description — confirmed selector gives clean product description
            description = await self._get_text(
                page,
                '[class*="ProductDetails-description"]'
            )

            # Variants — shade swatch buttons
            variants = []
            shade_buttons = await page.query_selector_all(
                '[class*="ProductForm__optionSwatchListAction"]'
            )

            seen_shades = set()
            for el in shade_buttons:
                class_name = await el.get_attribute("class") or ""
                # Skip child Hex dot and HexText label elements
                if "Hex" in class_name:
                    continue

                shade_name = (await el.inner_text()).strip()
                if not shade_name or shade_name in seen_shades:
                    continue
                seen_shades.add(shade_name)

                # Sold-out = disabled attribute or soldout in class name
                is_disabled = await el.get_attribute("disabled")
                in_stock = (
                    is_disabled is None
                    and "soldout" not in class_name.lower()
                    and "sold-out" not in class_name.lower()
                )

                variants.append(ScrapedVariant(
                    color=shade_name,
                    in_stock=in_stock,
                ))

            # Fallback — size variants (e.g. brushes with no shades)
            if not variants:
                size_elements = await page.query_selector_all(
                    "select[name='id'] option, .variant-selector option"
                )
                if size_elements:
                    for el in size_elements:
                        text = await el.text_content()
                        if text and text.strip():
                            text = text.strip()
                            in_stock = "sold out" not in text.lower()
                            variants.append(ScrapedVariant(
                                size=text.replace(" - Sold Out", "").strip(),
                                in_stock=in_stock,
                            ))
                else:
                    # Single variant fallback (e.g. brushes, single-sku products)
                    add_to_cart = await page.query_selector(
                        '[class*="addToCartButton"], [data-add-to-cart], button[type="submit"]'
                    )
                    in_stock = True
                    if add_to_cart:
                        btn_text = await add_to_cart.text_content() or ""
                        is_disabled = await add_to_cart.get_attribute("disabled")
                        if is_disabled is not None or "sold out" in btn_text.lower():
                            in_stock = False
                    variants.append(ScrapedVariant(in_stock=in_stock))

            return ScrapedProduct(
                name=name,
                url=url,
                price=price,
                image_url=image_url,
                category="Cosmetics",
                description=description,
                variants=variants,
            )

        except Exception as e:
            logger.error(f"[Hourglass] Error parsing {url}: {e}")
            return None
        finally:
            await page.close()