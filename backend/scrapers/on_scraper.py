"""
On Running (on.com) scraper.
On Running detects playwright-stealth and serves blank pages.
Solution: override _start_browser() with a clean context + real Chrome UA,
patch navigator.webdriver via init script, and simulate human behavior.
"""

import re
import logging
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright
from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant
from utils.anti_detect import random_delay, short_delay, human_mouse_move

logger = logging.getLogger(__name__)

# JavaScript to remove Playwright/automation fingerprints
_ANTI_DETECT_JS = """
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Fake plugins array (real Chrome has plugins)
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Fake languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Fix chrome object (Playwright/headful Chromium sometimes lacks this)
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {},
};

// Fix permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
"""


class OnScraper(BaseScraper):
    BRAND_SLUG = "on-running"
    BRAND_NAME = "On Running"
    BASE_URL = "https://www.on.com/en-us/"

    PRODUCT_LISTING_URLS = [
        "https://www.on.com/en-us/shop/womens/shoes",
        "https://www.on.com/en-us/shop/mens/shoes",
    ]

    HEALTH_SELECTORS = {
        "product_card": "a[href*='/en-us/products/']",
        "product_name": "h1",
        "price": "span",
    }

    async def _start_browser(self):
        """
        Override base _start_browser completely.
        On Running detects stealth plugin and heavy stealth args.
        Use a clean launch with modern UA + webdriver patching.
        """
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ],
        )

        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Patch navigator.webdriver on every new page BEFORE any scripts run
        await self._context.add_init_script(_ANTI_DETECT_JS)

    async def _new_on_page(self):
        """Create a plain page — no playwright-stealth plugin (triggers detection)."""
        return await self._context.new_page()

    async def get_product_links(self) -> list[str]:
        links = set()
        page = await self._new_on_page()

        try:
            for listing_url in self.PRODUCT_LISTING_URLS:
                logger.info(f"[On Running] Loading listing: {listing_url}")
                success = await self._navigate_with_retry(page, listing_url)
                if not success:
                    logger.warning(f"[On Running] Failed to navigate to {listing_url}")
                    continue

                # Wait for the page to fully render (SPA hydration)
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    logger.debug("[On Running] networkidle timeout, continuing anyway")

                # Simulate human: move mouse before interacting
                try:
                    await human_mouse_move(page)
                except Exception:
                    pass
                await short_delay()

                # Wait for product links to appear
                try:
                    await page.wait_for_selector(
                        'a[href*="/en-us/products/"]',
                        timeout=25000,
                    )
                except Exception:
                    logger.warning(
                        f"[On Running] No product links found on {listing_url}, "
                        "trying fallback with aria-label selector..."
                    )
                    # Fallback: try finding product links via aria-label
                    try:
                        await page.wait_for_selector(
                            'a[aria-label]',
                            timeout=10000,
                        )
                    except Exception:
                        logger.error(f"[On Running] Page appears empty for {listing_url}")
                        continue

                # Scroll to trigger lazy loading — human-like with pauses
                prev_height = 0
                stale_rounds = 0
                while True:
                    await page.evaluate("window.scrollBy(0, 800)")
                    await short_delay()
                    
                    try:
                        await human_mouse_move(page)
                    except Exception:
                        pass
                    await random_delay(0.5, 1.5)
                        
                    curr_height = await page.evaluate("document.body.scrollHeight")
                    if curr_height == prev_height:
                        stale_rounds += 1
                        if stale_rounds >= 3:
                            break
                    else:
                        stale_rounds = 0
                    prev_height = curr_height

                # Collect all product links
                anchors = await page.query_selector_all('a[href*="/en-us/products/"]')
                for a in anchors:
                    href = await a.get_attribute("href")
                    if href and "/en-us/products/" in href:
                        full_url = urljoin("https://www.on.com", href).split("?")[0]
                        links.add(full_url)

                logger.info(
                    f"[On Running] Found {len(anchors)} anchors, "
                    f"{len(links)} unique links so far from {listing_url}"
                )
                await random_delay()

        except Exception as e:
            logger.error(f"[On Running] Error collecting links: {e}")
        finally:
            await page.close()

        deduped = self._deduplicate_by_slug(list(links))
        logger.info(f"[On Running] {len(links)} links → {len(deduped)} after dedup")
        return deduped

    def _deduplicate_by_slug(self, links: list[str]) -> list[str]:
        """Keep one color variant per product slug."""
        seen_slugs = set()
        deduped = []
        for url in links:
            match = re.search(r'/products/([^/]+)/', url)
            if match:
                slug = match.group(1)
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    deduped.append(url)
            else:
                deduped.append(url)
        return deduped

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        page = await self._new_on_page()

        try:
            success = await self._navigate_with_retry(page, url)
            if not success:
                return None

            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await short_delay()

            # Simulate human presence
            try:
                await human_mouse_move(page)
            except Exception:
                pass

            # Name — try h1 first (has gender / model / color lines)
            name = None
            name_el = await page.query_selector("h1")
            if name_el:
                name_text = await name_el.inner_text()
                if name_text:
                    name_lines = [l.strip() for l in name_text.strip().splitlines() if l.strip()]
                    name = name_lines[1] if len(name_lines) >= 2 else name_lines[0]

            if not name:
                # Fallback: try meta title
                meta_title = await self._get_attribute(page, "meta[property='og:title']", "content")
                if meta_title:
                    name = meta_title.split("|")[0].strip()

            if not name:
                logger.warning(f"[On Running] Could not extract name from {url}")
                return None

            # Price — look for dollar amounts in various containers
            price = None
            # Try aria-label on product links which contains price
            price_el = await page.query_selector("[class*='price']")
            if price_el:
                price_text = await price_el.text_content()
                if price_text:
                    price_match = re.search(r'\$[\d]+\.?\d*', price_text.replace(",", ""))
                    if price_match:
                        price = float(price_match.group().replace("$", ""))

            if price is None:
                # Fallback: look for any span containing a dollar price
                spans = await page.query_selector_all("span")
                for span in spans:
                    text = await span.text_content()
                    if text and "$" in text:
                        m = re.search(r'\$(\d+(?:\.\d{2})?)', text.strip())
                        if m:
                            price = float(m.group(1))
                            break

            # Image
            image_url = (
                await self._get_attribute(page, "meta[property='og:image']", "content")
                or await self._get_attribute(page, "picture img", "src")
                or await self._get_attribute(page, "img[srcset]", "src")
            )

            # Description
            description = (
                await self._get_attribute(page, "meta[property='og:description']", "content")
                or await self._get_text(page, "[class*='description']")
            )

            # Color from URL path
            color = None
            color_match = re.search(r'/(?:womens|mens)/([^/]+)-shoes', url)
            if color_match:
                color = color_match.group(1).replace("-", " ").title()
            else:
                # Fallback: try older URL pattern
                color_match = re.search(r'/([^/]+)-shoes-[A-Z0-9]+$', url)
                if color_match:
                    color = color_match.group(1).replace("-", " ").title()

            # Sizes — try multiple selector patterns (CSS modules change)
            variants = []

            # Pattern 1: button with sizeButton class
            size_buttons = await page.query_selector_all("button[class*='size' i]")
            if not size_buttons:
                # Pattern 2: button inside a size container
                size_buttons = await page.query_selector_all(
                    "[class*='sizeSelector' i] button, [class*='size-selector' i] button"
                )
            if not size_buttons:
                # Pattern 3: any button with a numeric label in size area
                size_buttons = await page.query_selector_all(
                    "[class*='Size' i] button"
                )

            for btn in size_buttons:
                # Get size text from span child or button text
                size_text = None
                size_span = await btn.query_selector("span")
                if size_span:
                    size_text = await size_span.text_content()
                if not size_text:
                    size_text = await btn.text_content()
                if not size_text:
                    continue
                size_text = size_text.strip()
                # Skip non-size text (e.g. "Add to cart", "Notify me")
                if not re.match(r'^[\d]', size_text):
                    continue

                btn_class = await btn.get_attribute("class") or ""
                aria_disabled = await btn.get_attribute("aria-disabled")
                disabled = await btn.get_attribute("disabled")

                # Determine stock: check class, aria-disabled, or disabled attr
                in_stock = (
                    "_sizeOutOfStock_" not in btn_class
                    and "out-of-stock" not in btn_class.lower()
                    and "unavailable" not in btn_class.lower()
                    and aria_disabled != "true"
                    and disabled is None
                )

                variants.append(ScrapedVariant(
                    size=size_text,
                    color=color,
                    in_stock=in_stock,
                ))

            if not variants:
                variants.append(ScrapedVariant(color=color, in_stock=True))

            return ScrapedProduct(
                name=name,
                url=url,
                price=price,
                image_url=image_url,
                category="Shoes",
                description=description,
                variants=variants,
            )

        except Exception as e:
            logger.error(f"[On Running] Error parsing {url}: {e}")
            return None
        finally:
            await page.close()