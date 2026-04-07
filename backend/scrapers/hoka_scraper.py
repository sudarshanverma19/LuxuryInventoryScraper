"""
Hoka (hoka.com) scraper.
Scrapes running and lifestyle shoes.

Uses Camoufox (Firefox-based) to bypass Akamai Bot Manager.
Falls back gracefully if Camoufox is not installed.
"""

import re
import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant
from utils.anti_detect import random_delay, short_delay

logger = logging.getLogger(__name__)


class HokaScraper(BaseScraper):
    BRAND_SLUG = "hoka"
    BRAND_NAME = "Hoka"
    BASE_URL = "https://www.hoka.com/en/us/"

    PRODUCT_LISTING_URLS = [
        "https://www.hoka.com/en/us/womens-shoes/",
        "https://www.hoka.com/en/us/mens-shoes/",
    ]

    HEALTH_SELECTORS = {
        "product_card": "a[href*='/en/us/']",
        "product_name": "h1",
        "price": "span.accessible-price-summary",
    }

    _camoufox_available = None  # cached check

    @classmethod
    def _check_camoufox(cls) -> bool:
        """Check if Camoufox is installed (cached)."""
        if cls._camoufox_available is None:
            try:
                import camoufox  # noqa: F401
                cls._camoufox_available = True
            except ImportError:
                cls._camoufox_available = False
        return cls._camoufox_available

    async def _start_browser(self):
        """
        Use Camoufox (Firefox-based) if available — Hoka's Akamai blocks
        Chromium's TLS fingerprint with HTTP 406.
        Falls back to Chromium if Camoufox is not installed.
        """
        from config import HEADLESS

        if self._check_camoufox():
            logger.info("[Hoka] Using Camoufox (Firefox) to bypass Akamai")
            from camoufox.async_api import AsyncCamoufox

            # Camoufox manages its own browser instance
            # We store the context manager so we can clean up later
            self._camoufox_cm = AsyncCamoufox(
                headless=HEADLESS,
                geoip=True,  # Use GeoIP for locale consistency
            )
            self._browser = await self._camoufox_cm.__aenter__()
            self._context = self._browser  # Camoufox browser acts as context
            self._playwright = None  # Not used with Camoufox
            self._using_camoufox = True
        else:
            logger.warning(
                "[Hoka] Camoufox not installed — falling back to Chromium. "
                "Install with: pip install camoufox && python -m camoufox fetch"
            )
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            self._using_camoufox = False

    async def _close_browser(self):
        """Override to handle Camoufox cleanup."""
        if getattr(self, "_using_camoufox", False) and hasattr(self, "_camoufox_cm"):
            try:
                await self._camoufox_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._browser = None
            self._context = None
        else:
            await super()._close_browser()

    async def _new_page(self):
        """Create a new page — works with both Camoufox and Chromium."""
        if getattr(self, "_using_camoufox", False):
            page = await self._browser.new_page()
        else:
            page = await self._context.new_page()
        return page

    async def _warm_session(self, page):
        """
        Visit the homepage first to establish cookies/session,
        like a real user would.
        """
        try:
            logger.info("[Hoka] Warming session via homepage...")
            resp = await page.goto(
                "https://www.hoka.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            if resp and resp.status == 200:
                logger.info("[Hoka] Homepage loaded successfully")
                await asyncio.sleep(3)
                # Scroll a bit like a real user
                await page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'})")
                await asyncio.sleep(2)
                return True
            else:
                status = resp.status if resp else "no response"
                logger.warning(f"[Hoka] Homepage returned status {status}")

                # Check if blocked
                body = await page.evaluate("document.body?.innerText?.slice(0, 200) || ''")
                if "block" in body.lower() or "restricted" in body.lower():
                    logger.error(
                        "[Hoka] IP is blocked by Akamai. You need a proxy or VPN. "
                        "Try: (1) Wait 30+ minutes, (2) Use a VPN, or "
                        "(3) Configure residential proxies in config.py"
                    )
                return False
        except Exception as e:
            logger.error(f"[Hoka] Session warmup failed: {e}")
            return False

    async def get_product_links(self) -> list[str]:
        """Collect product URLs from listing pages."""
        links = set()
        page = await self._new_page()

        try:
            # Warm session first
            session_ok = await self._warm_session(page)
            if not session_ok:
                logger.error("[Hoka] Cannot proceed — blocked by anti-bot")
                return []

            for listing_url in self.PRODUCT_LISTING_URLS:
                logger.info(f"[Hoka] Loading {listing_url}")

                try:
                    resp = await page.goto(
                        listing_url,
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                except Exception as e:
                    logger.error(f"[Hoka] Navigation failed for {listing_url}: {e}")
                    continue

                if not resp or resp.status != 200:
                    status = resp.status if resp else "no response"
                    logger.warning(f"[Hoka] {listing_url} returned status {status}")
                    # Check for block
                    body = await page.evaluate(
                        "document.body?.innerText?.slice(0, 200) || ''"
                    )
                    if "block" in body.lower() or "restricted" in body.lower():
                        logger.error("[Hoka] Blocked by Akamai — stopping")
                        break
                    continue

                await asyncio.sleep(3)

                # Scroll slowly to load products
                for _ in range(10):
                    await page.evaluate(
                        "window.scrollBy({top: 500, behavior: 'smooth'})"
                    )
                    await asyncio.sleep(2)

                # Extract product links
                anchors = await page.query_selector_all("a[href]")
                for a in anchors:
                    href = await a.get_attribute("href") or ""
                    if re.search(r"/en/us/.+/.+/\d+\.html", href):
                        full_url = href.split("?")[0]
                        if not full_url.startswith("http"):
                            full_url = "https://www.hoka.com" + full_url
                        # Skip non-shoe pages
                        skip = [
                            "coming-soon", "gift-card", "egift",
                            "apparel", "tops", "bottoms", "shorts",
                            "socks", "hats", "accessories", "tights",
                            "outerwear", "bras",
                        ]
                        if not any(k in full_url.lower() for k in skip):
                            links.add(full_url)

                logger.info(f"[Hoka] {listing_url}: {len(links)} total links so far")
                await random_delay()

        except Exception as e:
            logger.error(f"[Hoka] Error collecting links: {e}")
        finally:
            await page.close()

        logger.info(f"[Hoka] Total unique product links: {len(links)}")
        return list(links)

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        """Parse a single product page."""
        page = await self._new_page()

        try:
            resp = await page.goto(
                url, wait_until="domcontentloaded", timeout=30000
            )
            if not resp or resp.status != 200:
                logger.warning(f"[Hoka] Product page returned {resp.status if resp else 'no response'}: {url}")
                return None

            await asyncio.sleep(2)

            # Wait for size buttons to render
            try:
                await page.wait_for_selector("button.options-select", timeout=8000)
            except Exception:
                pass

            await short_delay()

            # Product name
            name = await self._get_text(page, "h1")
            if not name:
                return None
            name = name.strip()

            # Price
            price = None
            price_text = await self._get_text(page, "span.accessible-price-summary")
            if price_text:
                price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
                if price_match:
                    price = float(price_match.group())

            # Image
            image_url = await self._get_attribute(
                page, ".primary-image, .js-pdp-main-image", "src"
            )
            if not image_url:
                el = await page.query_selector("picture source[srcset]")
                if el:
                    srcset = await el.get_attribute("srcset") or ""
                    image_url = srcset.split(",")[0].strip().split(" ")[0]

            # Description
            description = await self._get_text(
                page,
                ".description__info, .short-description-expander__preview"
            )

            # Color
            color = await self._get_text(
                page, "span.color-attr-value, span.swatch-group-label"
            )
            if color:
                color = color.strip()

            # Size variants
            variants = []
            size_buttons = await page.query_selector_all("button.options-select")

            seen_sizes = set()
            for el in size_buttons:
                size_text = (await el.inner_text()).strip()
                if not size_text or size_text in seen_sizes:
                    continue
                seen_sizes.add(size_text)

                class_name = await el.get_attribute("class") or ""
                is_disabled = await el.get_attribute("disabled")
                aria_disabled = await el.get_attribute("aria-disabled")

                in_stock = (
                    is_disabled is None
                    and aria_disabled != "true"
                    and "unavailable" not in class_name.lower()
                    and "sold-out" not in class_name.lower()
                    and "out-of-stock" not in class_name.lower()
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
            logger.error(f"[Hoka] Error parsing {url}: {e}")
            return None
        finally:
            await page.close()