"""
HypeFly (hypefly.co.in) scraper.
Scrapes sneakers and streetwear from a custom React/Shopify store.

The /products.json API is DISABLED (returns 404).
Must use browser-based infinite scroll for link collection
and visit individual product pages for details.
"""

import re
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant
from utils.anti_detect import random_delay

logger = logging.getLogger(__name__)


class HypeFlyScraper(BaseScraper):
    BRAND_SLUG = "hypefly"
    BRAND_NAME = "HypeFly"
    BASE_URL = "https://hypefly.co.in/"

    # Main collection pages to scrape
    COLLECTION_URLS = [
        "https://hypefly.co.in/collections/all-sneakers",
    ]

    HEALTH_SELECTORS = {
        "product_card": "a[href*='/products/']",
        "product_name": "h1",
        "price": "₹",
    }

    async def _start_browser(self):
        """Standard Chromium — custom site, no heavy anti-bot."""
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
        return await self._context.new_page()

    async def get_product_links(self) -> list[str]:
        """
        Collect product URLs by infinite-scrolling through the collection page.
        The site loads more products as you scroll to the bottom.
        """
        all_links = set()
        page = await self._new_page()

        try:
            for collection_url in self.COLLECTION_URLS:
                logger.info(f"[HypeFly] Loading {collection_url}")

                success = await self._navigate_with_retry(page, collection_url)
                if not success:
                    continue

                await asyncio.sleep(3)

                # Scroll and collect products via infinite scroll
                prev_count = 0
                no_change_count = 0
                max_scrolls = 80  # safety limit

                for scroll_num in range(max_scrolls):
                    # Extract current product links
                    current_links = await page.evaluate("""
                        () => {
                            const links = new Set();
                            document.querySelectorAll('a[href*="/products/"]').forEach(a => {
                                const href = a.href || a.getAttribute('href') || '';
                                if (href.includes('/products/') &&
                                    !href.includes('/collections/') &&
                                    !href.includes('add-to-cart')) {
                                    // Normalize URL
                                    let url = href;
                                    if (url.startsWith('/')) url = 'https://hypefly.co.in' + url;
                                    links.add(url.split('?')[0].split('#')[0]);
                                }
                            });
                            return [...links];
                        }
                    """)

                    all_links.update(current_links)
                    current_count = len(all_links)

                    if current_count == prev_count:
                        no_change_count += 1
                        if no_change_count >= 5:
                            logger.info(f"[HypeFly] No new products after {scroll_num} scrolls, done.")
                            break
                    else:
                        no_change_count = 0
                        if scroll_num % 5 == 0:
                            logger.info(f"[HypeFly] Scroll {scroll_num}: {current_count} products found")

                    prev_count = current_count

                    # Scroll down
                    await page.evaluate("window.scrollBy({top: 1500, behavior: 'smooth'})")
                    await asyncio.sleep(2)

                    # Wait for any loading spinners to disappear
                    try:
                        await page.wait_for_function(
                            "() => !document.querySelector('.loading, [class*=\"spinner\"], [class*=\"loader\"]')",
                            timeout=3000,
                        )
                    except Exception:
                        pass

                logger.info(f"[HypeFly] Collection done: {len(all_links)} products")

        except Exception as e:
            logger.error(f"[HypeFly] Error collecting links: {e}")
        finally:
            await page.close()

        logger.info(f"[HypeFly] Total unique product links: {len(all_links)}")
        return list(all_links)

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        """Parse a single HypeFly product page."""
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
                    // Look for price with ₹ symbol
                    const allEls = document.querySelectorAll('h1 ~ *, [class*="price"], [class*="Price"]');
                    for (const el of allEls) {
                        const text = el.innerText || '';
                        if (text.includes('₹') && text.length < 30) return text;
                    }
                    // Broader search
                    const spans = document.querySelectorAll('span, p, div');
                    for (const el of spans) {
                        const text = el.innerText || '';
                        if (text.match(/^₹[\d,]+$/) && el.children.length === 0) return text;
                    }
                    return '';
                }
            """)
            if price_text:
                match = re.search(r'₹([\d,]+)', price_text)
                if match:
                    price = float(match.group(1).replace(",", ""))

            # ── Image ─────────────────────────────────────────────
            image_url = await page.evaluate("""
                () => {
                    // Shopify CDN image
                    const img = document.querySelector('img[src*="cdn.shopify"]');
                    if (img) return img.src;
                    // Fallback: first large image
                    const imgs = document.querySelectorAll('main img, img[alt]');
                    for (const i of imgs) {
                        const src = i.src || '';
                        if (src && (i.naturalWidth > 200 || src.includes('cdn'))) return src;
                    }
                    return '';
                }
            """)
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

            # ── Description ───────────────────────────────────────
            description = await page.evaluate("""
                () => {
                    const el = document.querySelector('[class*="description"], [class*="Description"], .product-details');
                    if (el) return el.innerText.slice(0, 500);
                    return '';
                }
            """)

            # ── Category from breadcrumb ──────────────────────────
            category = "Sneakers"
            breadcrumb = await self._get_text(page, "nav, [class*='breadcrumb']")
            if breadcrumb:
                bc_lower = breadcrumb.lower()
                if "apparel" in bc_lower:
                    category = "Apparel"
                elif "bag" in bc_lower:
                    category = "Bags"
                elif "watch" in bc_lower:
                    category = "Watches"
                elif "running" in bc_lower:
                    category = "Running"

            # ── Size variants ─────────────────────────────────────
            variants = []

            # Try to get sizes from the page
            size_data = await page.evaluate("""
                () => {
                    const sizes = [];

                    // Method 1: Look for size buttons/options
                    const sizeEls = document.querySelectorAll(
                        'button[data-size], [class*="size"] button, ' +
                        '[class*="variant"] button, li[class*="cursor"]'
                    );
                    for (const el of sizeEls) {
                        const text = (el.innerText || '').trim();
                        if (text && text.length < 20 && /UK|US|\d/.test(text)) {
                            const disabled = el.disabled ||
                                el.classList.contains('disabled') ||
                                el.classList.contains('line-through') ||
                                el.getAttribute('aria-disabled') === 'true';
                            sizes.push({ size: text, available: !disabled });
                        }
                    }

                    // Method 2: Check select dropdown
                    if (sizes.length === 0) {
                        const select = document.querySelector('select[name*="size"], select[name*="option"]');
                        if (select) {
                            for (const opt of select.options) {
                                if (opt.value && opt.text.trim()) {
                                    sizes.push({
                                        size: opt.text.trim(),
                                        available: !opt.disabled
                                    });
                                }
                            }
                        }
                    }

                    // Method 3: Look for size display text
                    if (sizes.length === 0) {
                        const sizeContainer = document.querySelector('[class*="Size"], [class*="size"]');
                        if (sizeContainer) {
                            const items = sizeContainer.querySelectorAll('li, button, span');
                            for (const item of items) {
                                const text = item.innerText.trim();
                                if (text && /UK|US|\d/.test(text) && text.length < 15) {
                                    sizes.push({ size: text, available: true });
                                }
                            }
                        }
                    }

                    return sizes;
                }
            """)

            if size_data and len(size_data) > 0:
                for s in size_data:
                    variants.append(ScrapedVariant(
                        size=s.get("size", ""),
                        in_stock=s.get("available", True),
                    ))
            else:
                # Check if sold out
                in_stock = True
                sold_out = await page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = (btn.innerText || '').toLowerCase();
                            if (text.includes('sold out') && btn.disabled) return true;
                        }
                        const body = document.body.innerText.toLowerCase();
                        if (body.includes('sold out') && !body.includes('add to cart')) return true;
                        return false;
                    }
                """)
                in_stock = not sold_out
                variants.append(ScrapedVariant(in_stock=in_stock))

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
            logger.error(f"[HypeFly] Error parsing {url}: {e}")
            return None
        finally:
            await page.close()
