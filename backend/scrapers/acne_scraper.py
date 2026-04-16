"""
Acne Studios (acnestudios.com) scraper.
Scrapes fashion clothing, shoes, and accessories.

Platform: Salesforce Commerce Cloud (SFCC / Demandware)
Anti-bot: OneTrust cookie consent + Location popup.
           stealth_async should be skipped — same pattern as other scrapers.

URL structure (confirmed from live console inspection):
  - Base (US):      https://www.acnestudios.com/us/en/
  - Listing pages:  /us/en/woman/new-arrivals/
                    /us/en/man/new-arrivals/
  - Product pages:  /us/en/{product-slug}/{SKU-CODE}.html?g=woman
      e.g. /us/en/hooded-denim-jacket-mid-blue/C90219-863.html
      e.g. /us/en/nylon-logo-jacket-black/A90681-900.html
  - SKU pattern:    {LETTERS+DIGITS}-{LETTERS+DIGITS} like C90219-863, A90681-CXX

Selector notes (from live console inspection):
  - Product name:   h1
  - Price:          .price (inside .pdp__price container)
  - Sizes:          button.variations__grid-item (inside .variations__grid)
  - Out of stock:   text-decoration: line-through on size buttons (checked via JS)
  - Color:          h2 containing "Current colour:" text
  - Add to cart:    button.action--primary.action--color-blue ("ADD TO BAG")
  - Image:          img from Demandware CDN (dw/image/v2/AAXV_PRD/)
  - Description:    .description__giftwrapping or accordion content (minimal)

Popup handling:
  - Cookie consent: OneTrust — #onetrust-accept-btn-handler
  - Location popup: button with class action--primary containing "UNITED STATES"
  - Pre-set cookies: OptanonAlertBoxClosed + prefered_locale for US
"""

import re
import logging
import asyncio
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright
from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant
from utils.anti_detect import random_delay, human_scroll, short_delay

logger = logging.getLogger(__name__)

# Regex matching Acne product URLs: /{locale-path}/{slug}/{SKU}.html
# SKU = uppercase letters + digits, dash, then more letters + digits
_PRODUCT_URL_RE = re.compile(r'/[a-z0-9-]+/[A-Z0-9]+-[A-Z0-9]+\.html')


class AcneScraper(BaseScraper):
    BRAND_SLUG = "acne-studios"
    BRAND_NAME = "Acne Studios"
    BASE_URL = "https://www.acnestudios.com/us/en/"

    PRODUCT_LISTING_URLS = [
        "https://www.acnestudios.com/us/en/woman/new-arrivals/",
        "https://www.acnestudios.com/us/en/man/new-arrivals/",
    ]

    HEALTH_SELECTORS = {
        "product_card": "a[href*='.html']",
        "product_name": "h1",
        "price": ".price",
    }

    # ── Browser override ────────────────────────────────────────────────────

    async def _start_browser(self):
        """
        Clean launch — no stealth plugin (triggers bot detection on SFCC).
        Pre-sets cookies for:
          1. OneTrust cookie consent (suppresses banner)
          2. US locale preference (suppresses location popup)
        """
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        # Pre-set cookies to suppress popups
        await self._context.add_cookies([
            # OneTrust cookie consent — prevents cookie banner
            {
                "name": "OptanonAlertBoxClosed",
                "value": "2026-01-01T00:00:00.000Z",
                "domain": ".acnestudios.com",
                "path": "/",
            },
            {
                "name": "OptanonConsent",
                "value": (
                    "isGpcEnabled=0&datestamp=Mon+Jan+01+2026+00%3A00%3A00+GMT"
                    "&version=202601.1.0&browserGpcFlag=0&isIABGlobal=false"
                    "&consentId=scraper-consent&interactionCount=1"
                    "&isAnonUser=1&landingPath=NotLandingPage"
                    "&groups=C0002%3A1%2CC0004%3A1%2CC0001%3A1%2CC0003%3A1"
                    "&intType=1"
                ),
                "domain": ".acnestudios.com",
                "path": "/",
            },
            # US locale preference — prevents location redirect popup
            {
                "name": "prefered_locale",
                "value": '{"localeId":"en_US","countryCode":"US"}',
                "domain": ".acnestudios.com",
                "path": "/",
            },
        ])

        # Also load any previously saved cookies (session cookies, etc.)
        await self._load_cookies()

    async def _new_page(self):
        """Override to skip stealth_async — triggers bot detection on SFCC."""
        page = await self._context.new_page()
        return page

    # ── Popup Handlers ──────────────────────────────────────────────────────

    async def _dismiss_cookie_popup(self, page):
        """Click 'ACCEPT ALL COOKIES' if OneTrust banner appears."""
        try:
            btn = await page.query_selector("#onetrust-accept-btn-handler")
            if btn and await btn.is_visible():
                await btn.click()
                logger.info("[Acne Studios] Cookie popup dismissed")
                await page.wait_for_timeout(1000)
                await self._save_cookies()
        except Exception:
            pass

    async def _dismiss_location_popup(self, page):
        """Click 'UNITED STATES' if location modal appears."""
        try:
            # The US button has these classes (confirmed from console)
            us_btn = await page.query_selector(
                "button.margin-top--micro.action--primary"
            )
            if us_btn and await us_btn.is_visible():
                text = await us_btn.text_content() or ""
                if "UNITED STATES" in text.upper():
                    await us_btn.click()
                    logger.info("[Acne Studios] Location popup dismissed — US selected")
                    await page.wait_for_timeout(2000)
                    await self._save_cookies()
                    return

            # Fallback: find by text content
            buttons = await page.query_selector_all("button.action--primary")
            for btn in buttons:
                text = await btn.text_content() or ""
                if "UNITED STATES" in text.upper():
                    await btn.click()
                    logger.info("[Acne Studios] Location popup dismissed (fallback)")
                    await page.wait_for_timeout(2000)
                    await self._save_cookies()
                    return
        except Exception:
            pass

    async def _dismiss_popups(self, page):
        """Dismiss both popups in order."""
        await self._dismiss_cookie_popup(page)
        await asyncio.sleep(1)
        await self._dismiss_location_popup(page)

    # ── Link collection ─────────────────────────────────────────────────────

    async def get_product_links(self) -> list[str]:
        """Collect product URLs from new arrivals listing pages."""
        links = set()
        page = await self._new_page()

        try:
            for listing_url in self.PRODUCT_LISTING_URLS:
                success = await self._navigate_with_retry(page, listing_url)
                if not success:
                    logger.warning(f"[Acne Studios] Could not load: {listing_url}")
                    continue

                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                # Dismiss popups on first page load
                await self._dismiss_popups(page)

                # Scroll to trigger lazy loading completely
                prev_height = 0
                stale_rounds = 0
                while True:
                    await page.evaluate("window.scrollBy(0, 800)")
                    await short_delay()
                    
                    curr_height = await page.evaluate("document.body.scrollHeight")
                    if curr_height == prev_height:
                        stale_rounds += 1
                        if stale_rounds >= 3:
                            break
                    else:
                        stale_rounds = 0
                    prev_height = curr_height

                # Collect product links
                # Pattern: /us/en/{slug}/{SKU}.html where SKU = e.g. C90219-863
                anchors = await page.query_selector_all("a[href*='.html']")
                for a in anchors:
                    href = await a.get_attribute("href")
                    if not href:
                        continue

                    full_url = urljoin("https://www.acnestudios.com", href).split("?")[0]

                    # Must match product URL pattern
                    if not _PRODUCT_URL_RE.search(full_url):
                        continue

                    # Skip non-product pages
                    skip = ["help", "client-services", "about", "company",
                            "gift-card", "legal", "size-guide", "shopping-help"]
                    if any(s in full_url for s in skip):
                        continue

                    links.add(full_url)

                logger.info(
                    f"[Acne Studios] {len(links)} product links so far "
                    f"after {listing_url.split('/en/')[-1]}"
                )
                await random_delay()

        except Exception as e:
            logger.error(f"[Acne Studios] Error collecting links: {e}")
        finally:
            await page.close()

        result = list(links)
        logger.info(f"[Acne Studios] Collected {len(result)} product links")
        return result

    # ── Product page parser ─────────────────────────────────────────────────

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        """Parse a single Acne Studios product page."""
        page = await self._new_page()

        try:
            success = await self._navigate_with_retry(page, url)
            if not success:
                return None

            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            # Dismiss any popups
            await self._dismiss_popups(page)
            await short_delay()

            # ── Name ──────────────────────────────────────────────────────
            name = await self._get_text(page, "h1")
            if not name:
                return None
            name = name.strip()

            # ── Price ─────────────────────────────────────────────────────
            # Confirmed: .price class inside .pdp__price container
            price = None
            price_text = await self._get_text(page, ".pdp__price .price, .price")
            if price_text:
                # Handle both USD ($750) and EUR (€750) formats
                price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
                if price_match:
                    price = float(price_match.group())

            # ── Image ─────────────────────────────────────────────────────
            # Demandware CDN images from acnestudios.com/dw/image
            image_url = await page.evaluate("""
                () => {
                    const imgs = document.querySelectorAll('img');
                    let best = null, bestW = 0;
                    for (const img of imgs) {
                        const src = img.currentSrc || img.src || '';
                        const w = img.naturalWidth || 0;
                        if (src.includes('dw/image') && w > bestW && !src.endsWith('.svg')) {
                            best = src;
                            bestW = w;
                        }
                    }
                    return best;
                }
            """)

            # ── Color ─────────────────────────────────────────────────────
            # Confirmed: h2 with text "Current colour: Mid Blue"
            color = None
            color_el = await page.query_selector("h2[class*='color']")
            if color_el:
                color_text = await color_el.text_content() or ""
                # Extract color name after "Current colour:" prefix
                match = re.search(r'(?:Current\s+colou?r:\s*)(.+)', color_text, re.IGNORECASE)
                if match:
                    color = match.group(1).strip()
                elif color_text.strip():
                    color = color_text.strip()

            # ── Description ───────────────────────────────────────────────
            # Acne doesn't have a prominent description block — try accordion
            description = await self._get_text(
                page, ".description__giftwrapping, .pdp-description, .product-description"
            )

            # ── Size Variants ─────────────────────────────────────────────
            # Confirmed: button.variations__grid-item inside .variations__grid
            # Out of stock = text-decoration: line-through (visual strikethrough)
            variants = []

            size_data = await page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button.variations__grid-item');
                    const sizes = [];
                    for (const btn of buttons) {
                        const text = btn.innerText?.trim();
                        if (!text) continue;

                        // Check if out of stock via:
                        // 1. text-decoration line-through
                        // 2. disabled attribute
                        // 3. class containing unavailable/sold-out
                        const style = window.getComputedStyle(btn);
                        const isStrikethrough = style.textDecorationLine?.includes('line-through')
                                             || style.textDecoration?.includes('line-through');
                        const isDisabled = btn.disabled || btn.getAttribute('aria-disabled') === 'true';
                        const cls = btn.className.toLowerCase();
                        const hasOOSClass = cls.includes('unavailable') || cls.includes('sold-out')
                                         || cls.includes('out-of-stock') || cls.includes('unselectable');

                        sizes.push({
                            size: text,
                            in_stock: !isStrikethrough && !isDisabled && !hasOOSClass,
                        });
                    }
                    return sizes;
                }
            """)

            if size_data:
                for s in size_data:
                    variants.append(ScrapedVariant(
                        size=s["size"],
                        color=color,
                        in_stock=s["in_stock"],
                    ))

            # Fallback: no size buttons found — check add-to-bag button
            if not variants:
                atc_btn = await page.query_selector(
                    "button.action--primary.action--color-blue"
                )
                in_stock = True
                if atc_btn:
                    btn_text = await atc_btn.text_content() or ""
                    is_disabled = await atc_btn.get_attribute("disabled")
                    if is_disabled is not None or "sold out" in btn_text.lower():
                        in_stock = False
                variants.append(ScrapedVariant(color=color, in_stock=in_stock))

            # ── Determine category from URL ───────────────────────────────
            category = "Fashion"
            url_lower = url.lower()
            if any(k in url_lower for k in ["shoe", "boot", "sandal", "sneaker"]):
                category = "Shoes"
            elif any(k in url_lower for k in ["bag", "musubi", "tote"]):
                category = "Bags"
            elif any(k in url_lower for k in ["cap", "hat", "scarf", "belt"]):
                category = "Accessories"

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
            logger.error(f"[Acne Studios] Error parsing {url}: {e}")
            return None
        finally:
            await page.close()
