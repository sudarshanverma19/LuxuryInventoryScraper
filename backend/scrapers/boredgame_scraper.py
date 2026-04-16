"""
Bored Game Company (boredgamecompany.com) scraper.
Scrapes board games, card sleeves, and hobby supplies.

Custom React/Next.js site — all products load on a single listing page.
No anti-bot, no pagination needed. ~125 total products.
"""

import re
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant
from utils.anti_detect import random_delay

logger = logging.getLogger(__name__)


class BoredGameScraper(BaseScraper):
    BRAND_SLUG = "bored-game-company"
    BRAND_NAME = "Bored Game Company"
    BASE_URL = "https://boredgamecompany.com/in/en/"

    # Category listing pages
    PRODUCT_LISTING_URLS = [
        "https://boredgamecompany.com/in/en/products/board-games",
        "https://boredgamecompany.com/in/en/products/card-sleeves-accessories",
        "https://boredgamecompany.com/in/en/products/hobby-supplies",
    ]

    HEALTH_SELECTORS = {
        "product_card": "a[href*='/product/']",
        "product_name": "h1",
        "price": "₹",
    }

    async def _start_browser(self):
        """Standard Chromium — no anti-bot needed."""
        from playwright.async_api import async_playwright
        from config import HEADLESS

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

    async def _new_page(self):
        """Simple page — no stealth needed."""
        return await self._context.new_page()

    async def get_product_links(self) -> list[str]:
        """
        Collect product URLs from all category pages.
        All products load on a single page (no pagination needed).
        """
        all_links = set()
        page = await self._new_page()

        try:
            for listing_url in self.PRODUCT_LISTING_URLS:
                logger.info(f"[Bored Game] Loading {listing_url}")

                try:
                    resp = await page.goto(
                        listing_url, wait_until="networkidle", timeout=30000
                    )
                except Exception as e:
                    logger.error(f"[Bored Game] Navigation failed for {listing_url}: {e}")
                    continue

                if not resp or resp.status != 200:
                    logger.warning(f"[Bored Game] {listing_url} returned {resp.status if resp else 'none'}")
                    continue

                await asyncio.sleep(2)

                # Scroll down to load any lazy content
                for _ in range(5):
                    await page.evaluate("window.scrollBy({top: 600, behavior: 'smooth'})")
                    await asyncio.sleep(1)

                # Extract product links
                page_links = await page.evaluate("""
                    () => {
                        const links = new Set();
                        // Match /in/en/product/[slug] pattern
                        document.querySelectorAll('a[href*="/product/"]').forEach(a => {
                            const href = a.href || '';
                            if (href.includes('/in/en/product/') && !href.includes('/products/')) {
                                links.add(href.split('?')[0].split('#')[0]);
                            }
                        });
                        return [...links];
                    }
                """)

                all_links.update(page_links)
                logger.info(f"[Bored Game] {listing_url.split('/')[-1]}: {len(page_links)} products, {len(all_links)} total")

                await random_delay()

        except Exception as e:
            logger.error(f"[Bored Game] Error collecting links: {e}")
        finally:
            await page.close()

        logger.info(f"[Bored Game] Total unique product links: {len(all_links)}")
        return list(all_links)

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        """Parse a single product page."""
        page = await self._new_page()

        try:
            resp = await page.goto(
                url, wait_until="domcontentloaded", timeout=20000
            )
            if not resp or resp.status != 200:
                return None

            await asyncio.sleep(2)

            # ── Product name ───────────────────────────────────────
            name = await self._get_text(page, "h1")
            if not name:
                return None
            name = name.strip()

            # ── Price (₹ INR) ──────────────────────────────────────
            price = None
            price_text = await page.evaluate("""
                () => {
                    // Look for price text with ₹ symbol
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        const text = el.innerText || '';
                        // Match ₹X,XXX.XX format, skip if element has many children (nav, etc)
                        if (text.match(/^₹[\d,]+\.?\d*$/) && el.children.length === 0) {
                            return text;
                        }
                    }
                    // Fallback: look for price in common patterns
                    const priceEls = document.querySelectorAll('[class*="price"], [class*="Price"]');
                    for (const el of priceEls) {
                        const text = el.innerText || '';
                        if (text.includes('₹')) return text;
                    }
                    return '';
                }
            """)
            if price_text:
                match = re.search(r'₹([\d,]+\.?\d*)', price_text.replace(",", ""))
                if match:
                    price = float(match.group(1))

            # ── Image ─────────────────────────────────────────────
            image_url = await page.evaluate("""
                () => {
                    // Look for main product image
                    const img = document.querySelector('img[alt][src*="cdn"], img[src*="product"]');
                    if (img) return img.src;
                    // Fallback: first large image on page
                    const imgs = document.querySelectorAll('main img, [class*="product"] img');
                    for (const i of imgs) {
                        if (i.naturalWidth > 200 || i.width > 200) return i.src;
                    }
                    return '';
                }
            """)
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

            # ── Description ───────────────────────────────────────
            description = await page.evaluate("""
                () => {
                    const descEl = document.querySelector('[class*="description"], [class*="Description"], [class*="detail"] p');
                    if (descEl) return descEl.innerText.slice(0, 500);
                    return '';
                }
            """)

            # ── Category ──────────────────────────────────────────
            category = "Board Games"  # default
            breadcrumb = await self._get_text(page, "nav[aria-label='breadcrumb'], [class*='breadcrumb']")
            if breadcrumb:
                bc_lower = breadcrumb.lower()
                if "sleeve" in bc_lower or "accessor" in bc_lower:
                    category = "Card Sleeves & Accessories"
                elif "hobby" in bc_lower or "suppli" in bc_lower:
                    category = "Hobby Supplies"

            # ── Stock status ──────────────────────────────────────
            in_stock = True
            stock_check = await page.evaluate("""
                () => {
                    const body = document.body.innerText.toLowerCase();
                    // Check for "out of stock" text near buy/add to cart area
                    const stockEls = document.querySelectorAll('[class*="stock"], button[disabled], [class*="sold"]');
                    for (const el of stockEls) {
                        const text = el.innerText.toLowerCase();
                        if (text.includes('out of stock') || text.includes('sold out')) return 'out';
                    }
                    // Check if add to cart button is disabled
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = (btn.innerText || '').toLowerCase();
                        if ((text.includes('add to cart') || text.includes('buy')) && btn.disabled) return 'out';
                    }
                    // Check for stock indicator
                    const checkmark = document.querySelector('[class*="stock"]');
                    if (checkmark && checkmark.innerText.includes('✓')) return 'in';
                    // Look for "Out of Stock" text anywhere near price
                    if (body.includes('out of stock')) return 'out';
                    return 'in';
                }
            """)
            in_stock = stock_check != "out"

            # ── Build variant ─────────────────────────────────────
            variants = [ScrapedVariant(in_stock=in_stock)]

            return ScrapedProduct(
                name=name,
                url=url,
                price=price,
                currency="INR",
                image_url=image_url,
                category=category,
                description=description or None,
                variants=variants,
            )

        except Exception as e:
            logger.error(f"[Bored Game] Error parsing {url}: {e}")
            return None
        finally:
            await page.close()
