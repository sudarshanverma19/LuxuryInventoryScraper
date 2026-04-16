"""
Drunk Elephant (drunkelephant.com) scraper.
Scrapes skincare, hair, and body products.
"""

import re
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant
from utils.anti_detect import random_delay, short_delay

logger = logging.getLogger(__name__)


class DrunkElephantScraper(BaseScraper):
    BRAND_SLUG = "drunk-elephant"          # ← fixed: matches config.py
    BRAND_NAME = "Drunk Elephant"
    BASE_URL = "https://www.drunkelephant.com/"

    # Comprehensive list of all collection pages
    PRODUCT_LISTING_URLS = [
        "https://www.drunkelephant.com/collections/skincare/",
        "https://www.drunkelephant.com/collections/moisturizers/",
        "https://www.drunkelephant.com/collections/serums/",
        "https://www.drunkelephant.com/collections/cleansers/",
        "https://www.drunkelephant.com/collections/masks/",
        "https://www.drunkelephant.com/collections/hair-collection/",
        "https://www.drunkelephant.com/collections/body-collection/",
        "https://www.drunkelephant.com/collections/best-sellers/",
        "https://www.drunkelephant.com/collections/kits-bundles/",
    ]

    HEALTH_SELECTORS = {
        "product_card": "a[href*='.html']",
        "product_name": "h1",
        "price": "[class*='price']",
    }

    # Regex: product URLs have a slug followed by a product ID and .html
    # e.g., protini-polypeptide-...-999DE00000103.html
    _PRODUCT_URL_RE = re.compile(
        r"drunkelephant\.com/.+/.+-[\w]+\.html",
        re.IGNORECASE,
    )

    # Numeric/alphanumeric product ID pattern (6+ chars at end before .html)
    _PRODUCT_ID_RE = re.compile(r"-(\w{6,})\.html$")

    async def _start_browser(self):
        """Override to skip stealth plugin — Drunk Elephant doesn't need it."""
        from playwright.async_api import async_playwright
        from config import HEADLESS

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        # Pre-set country cookie so popup never appears
        await self._context.add_cookies([
            {
                "name": "drunkelephant_us-preferredSite",
                "value": "USA",
                "domain": ".drunkelephant.com",
                "path": "/",
            },
        ])

    async def _new_page(self):
        """Override to skip stealth_async — not needed for this site."""
        page = await self._context.new_page()
        return page

    async def _dismiss_popups(self, page):
        """Handle location popup and cookie banner."""
        # Location popup
        try:
            btn = await page.query_selector("button.shopnow-button")
            if btn:
                await page.select_option("select.selectcountry", label="United States")
                await asyncio.sleep(0.5)
                await btn.click()
                await asyncio.sleep(1)
                logger.debug("[Drunk Elephant] Location popup dismissed")
        except Exception:
            pass

        # Cookie banner
        try:
            accept = await page.query_selector("button:has-text('Accept All Cookies')")
            if accept:
                await accept.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

    def _is_product_url(self, href: str) -> bool:
        """Check if a URL is a product page (not a collection/nav page)."""
        # Strip query params
        clean = href.split("?")[0]

        # Must end in .html
        if not clean.endswith(".html"):
            return False

        # Must be on drunkelephant.com
        if "drunkelephant.com" not in clean:
            return False

        # Skip known non-product pages
        skip_patterns = [
            "/gift-card", "/about-us", "/contact-us", "/delivery-and-returns",
            "/faqs", "/privacy", "/terms", "/press",
        ]
        for pattern in skip_patterns:
            if pattern in clean.lower():
                return False

        # Product URLs have a product ID before .html
        # e.g., -999DE00000103.html, -194249413797.html, -856556004036.html
        filename = clean.split("/")[-1]
        if self._PRODUCT_ID_RE.search(filename):
            return True

        # Also accept bundle-style IDs like CastinBronzeBundle
        if "bundle" in filename.lower() or "Bundle" in filename:
            return True

        return False

    def _normalize_product_url(self, href: str) -> str:
        """Clean and normalize a product URL."""
        clean = href.split("?")[0]
        if not clean.startswith("http"):
            clean = "https://www.drunkelephant.com" + clean
        return clean

    async def _collect_links_from_page(self, page) -> set[str]:
        """Extract all product links from the current page using JS for speed."""
        raw_links = await page.evaluate("""
        () => {
            const anchors = document.querySelectorAll('a[href*=".html"]');
            const links = [];
            for (const a of anchors) {
                links.push(a.href || '');
            }
            return links;
        }
        """)
        
        found = set()
        for href in raw_links:
            if self._is_product_url(href):
                found.add(self._normalize_product_url(href))
        return found

    async def get_product_links(self) -> list[str]:
        """Collect product URLs from all collection pages."""
        all_links = set()
        page = await self._new_page()

        try:
            first_page = True

            for listing_url in self.PRODUCT_LISTING_URLS:
                logger.info(f"[Drunk Elephant] Scraping {listing_url}")
                success = await self._navigate_with_retry(page, listing_url)
                if not success:
                    logger.warning(f"[Drunk Elephant] Failed to load {listing_url}")
                    continue

                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                # Handle popups on first page load
                if first_page:
                    await self._dismiss_popups(page)
                    first_page = False

                # Scroll to trigger lazy loading
                prev_count = 0
                stale_rounds = 0

                while True:
                    await page.evaluate(
                        "window.scrollBy({top: 400, behavior: 'smooth'})"
                    )
                    await asyncio.sleep(1.5)

                    # Collect links after each scroll
                    page_links = await self._collect_links_from_page(page)
                    all_links.update(page_links)

                    # Check if we're still finding new products
                    if len(all_links) == prev_count:
                        stale_rounds += 1
                        if stale_rounds >= 3:
                            break  # No new products after 3 scrolls
                    else:
                        stale_rounds = 0
                    prev_count = len(all_links)

                    # Check if we've reached the bottom
                    at_bottom = await page.evaluate("""
                        () => window.scrollY + window.innerHeight >= document.body.scrollHeight - 100
                    """)
                    if at_bottom and stale_rounds >= 1:
                        break

                logger.info(
                    f"[Drunk Elephant] {listing_url.split('/')[-2]}: "
                    f"found {len(page_links)} links on page, {len(all_links)} total unique"
                )
                await random_delay()

        except Exception as e:
            logger.error(f"[Drunk Elephant] Error collecting links: {e}")
        finally:
            await page.close()

        # Deduplicate: same product can appear under different collection paths
        # Normalize by extracting the product slug (filename before .html)
        unique_products = {}
        for url in all_links:
            filename = url.split("/")[-1]  # e.g., protini-...-999DE00000103.html
            if filename not in unique_products:
                unique_products[filename] = url

        logger.info(
            f"[Drunk Elephant] Total unique products: {len(unique_products)} "
            f"(from {len(all_links)} raw links)"
        )
        return list(unique_products.values())

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        """Parse a single product page."""
        page = await self._new_page()

        try:
            success = await self._navigate_with_retry(page, url)
            if not success:
                return None

            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await self._dismiss_popups(page)

            # Wait for product content
            try:
                await page.wait_for_selector("h1", timeout=8000)
            except Exception:
                pass

            await short_delay()

            # ── Product name ───────────────────────────────────────
            name = await self._get_text(page, "h1")
            if not name:
                return None
            name = name.strip()

            # ── Price ──────────────────────────────────────────────
            price = None
            price_text = await self._get_text(page, "[class*='price']")
            if price_text:
                # Handle range prices like "$18.00 - $36.00" → take the first
                price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(",", ""))
                if price_match:
                    price = float(price_match.group(1))

            # ── Image ─────────────────────────────────────────────
            image_url = None
            imgs = await page.query_selector_all("img")
            best_width = 0
            for img in imgs:
                src = await img.get_attribute("src") or ""
                try:
                    width = await img.evaluate("el => el.naturalWidth || el.width")
                except Exception:
                    width = 0
                if (
                    "Sites-itemmaster_drunkelephant" in src
                    and width > best_width
                    and not src.endswith(".svg")
                ):
                    best_width = width
                    image_url = src

            # Fallback: try og:image meta tag
            if not image_url:
                og_img = await page.query_selector("meta[property='og:image']")
                if og_img:
                    image_url = await og_img.get_attribute("content")

            # ── Description ───────────────────────────────────────
            description = await self._get_text(page, "div.product-description")

            # ── Category from URL path ────────────────────────────
            category = "Skincare"  # default
            url_lower = url.lower()
            if "/hair" in url_lower or "/shampoo" in url_lower or "/conditioner" in url_lower:
                category = "Hair Care"
            elif "/body" in url_lower or "/lotion" in url_lower or "/deodorant" in url_lower:
                category = "Body Care"
            elif "/kits" in url_lower or "/bundle" in url_lower:
                category = "Kits & Bundles"

            # ── Size variants ─────────────────────────────────────
            sizes = []
            size_elements = await page.query_selector_all(
                "[class*='size'] button, [class*='size'] a, .attribute.size li"
            )
            for el in size_elements:
                size_text = (await el.text_content() or "").strip()
                if size_text and len(size_text) < 50:
                    # Check if this size is disabled/unavailable
                    is_disabled = await el.get_attribute("disabled")
                    cls = await el.get_attribute("class") or ""
                    unavailable = is_disabled is not None or "unavailable" in cls.lower()
                    sizes.append((size_text, not unavailable))

            # ── Stock status ──────────────────────────────────────
            in_stock = True
            atc_btn = await page.query_selector(
                "button[class*='add-to-cart'], button[class*='add-to-bag'], "
                "button:has-text('ADD TO BAG'), button:has-text('Add to Bag')"
            )
            if atc_btn:
                is_disabled = await atc_btn.get_attribute("disabled")
                btn_text = await atc_btn.text_content() or ""
                if is_disabled is not None or "sold out" in btn_text.lower() or "out of stock" in btn_text.lower():
                    in_stock = False
            else:
                # No add-to-bag button found — might be sold out
                sold_out = await page.query_selector(
                    "[class*='sold-out'], [class*='out-of-stock']"
                )
                if sold_out:
                    in_stock = False

            # ── Build variants ────────────────────────────────────
            variants = []
            if sizes:
                for size_text, size_available in sizes:
                    variants.append(ScrapedVariant(
                        size=size_text,
                        in_stock=size_available and in_stock,
                    ))
            else:
                # Single variant (no size options)
                # Try to get size from page text
                single_size = await self._get_text(page, "div.attribute.size")
                if single_size:
                    single_size = single_size.strip()
                variants.append(ScrapedVariant(
                    size=single_size if single_size else None,
                    in_stock=in_stock,
                ))

            return ScrapedProduct(
                name=name,
                url=url,
                price=price,
                image_url=image_url,
                category=category,
                description=description,
                variants=variants,
            )

        except Exception as e:
            logger.error(f"[Drunk Elephant] Error parsing {url}: {e}")
            return None
        finally:
            await page.close()