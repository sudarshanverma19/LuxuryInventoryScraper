"""
Maison Margiela (maisonmargiela.com/wx/) scraper.
Scrapes luxury fashion items.

Anti-bot notes:
  - High anti-bot (403 on plain HTTP). stealth_async likely triggers detection.
  - Fix: override _start_browser() with clean context, headless=False, no stealth.
  - Same pattern as the working On Running fix.

URL structure (confirmed from live console inspection):
  - Base:         https://www.maisonmargiela.com/wx/
  - Listing pages: /wx/maison-margiela/women/featured/new-arrivals/
                   /wx/maison-margiela/men/featured/new-arrivals/
  - Product pages: /wx/{product-slug}-{SKU_CODE}.html
      e.g. /wx/anatomic-numeric-slingback-S59WP0212P3628T2259.html
      e.g. /wx/tabi-new-ballerina-S58WZ0127P3753T6317.html
  - SKU pattern:  ends in an uppercase alphanumeric code like S59WP0212P3628T2259

Selector notes (Margiela custom SPA — not SFCC):
  - Product name:  h1, or first prominent text block on PDP
  - Price:         typically [class*="price"], .price, or a data attribute
  - Sizes:         look for [class*="size"] buttons or list items
  - Out of stock:  disabled attribute or class containing "unavailable"/"soldout"
  - Color:         [class*="color"] label or active swatch aria-label

  NOTE: Margiela's SPA renders content client-side. Always wait for networkidle
  before querying selectors. If selectors return None on first run, open a product
  page in browser DevTools and run:
    console.log("NAME:", document.querySelector('h1')?.innerText)
    console.log("PRICE:", document.querySelector('[class*="price"]')?.innerText)
    document.querySelectorAll('[class*="size"]').forEach(el =>
      console.log("SIZE:", el.tagName, el.className, el.innerText?.slice(0,20)))
  Then update the selectors below accordingly.
"""

import re
import logging
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright
from scrapers.base_scraper import BaseScraper, ScrapedProduct, ScrapedVariant
from utils.anti_detect import random_delay, short_delay

logger = logging.getLogger(__name__)

# Regex that matches confirmed Margiela product URL pattern:
# anything ending in -{UPPERCASE_ALPHANUMERIC}.html
# e.g. tabi-new-ballerina-S58WZ0127P3753T6317.html
_PRODUCT_URL_RE = re.compile(r'/wx/[a-z0-9-]+-[A-Z0-9]{8,}\.html$')


class MargielaScraper(BaseScraper):
    BRAND_SLUG = "maison-margiela"
    BRAND_NAME = "Maison Margiela"
    BASE_URL = "https://www.maisonmargiela.com/wx/"

    # Confirmed listing URLs from live console inspection
    PRODUCT_LISTING_URLS = [
        "https://www.maisonmargiela.com/wx/maison-margiela/women/featured/new-arrivals/",
        "https://www.maisonmargiela.com/wx/maison-margiela/men/featured/new-arrivals/",
        # Broader category pages as fallback for more products
        "https://www.maisonmargiela.com/wx/maison-margiela/women/shoes/",
        "https://www.maisonmargiela.com/wx/maison-margiela/men/shoes/",
        "https://www.maisonmargiela.com/wx/maison-margiela/women/bags/",
        "https://www.maisonmargiela.com/wx/maison-margiela/men/bags/",
        "https://www.maisonmargiela.com/wx/maison-margiela/women/ready-to-wear/",
        "https://www.maisonmargiela.com/wx/maison-margiela/men/ready-to-wear/",
    ]

    HEALTH_SELECTORS = {
        "product_card": "a[href$='.html']",
        "product_name": "h1",
        "price": "[class*='price']",
    }

    # ── Browser override (same pattern as OnScraper) ────────────────────────

    async def _start_browser(self):
        """
        Margiela blocks stealth_async and headless Chrome (returns 403).
        Use a clean, minimal launch — identical to the working On Running fix.
        Also loads saved cookies so the consent popup is not shown on repeat runs.
        """
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=False,  # Margiela blocks headless
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

        # Restore saved cookies — this suppresses the consent popup on repeat runs
        await self._load_cookies()

    # ── Link collection ─────────────────────────────────────────────────────

    async def _dismiss_cookie_popup(self, page) -> None:
        """
        Accept the Margiela cookie/consent popup if it appears.
        Confirmed selector from live DOM inspection:
          <button class="mm-button -xl -block -solid mt-0.5"
                  onclick="window.callBack_cookie_banner()">Accept All</button>
        Saves cookies immediately after so the popup won't reappear next run.
        """
        selectors = [
            # Exact confirmed selector — onclick is unique and style-change-proof
            "button[onclick='window.callBack_cookie_banner()']",
            # Fallback: the specific class combo seen in the DOM
            "button.mm-button.-xl.-block.-solid",
        ]
        for sel in selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    logger.info("[Margiela] Cookie popup dismissed")
                    await page.wait_for_timeout(1000)  # let page settle
                    await self._save_cookies()          # persist — won't show next run
                    return
            except Exception:
                continue

    async def get_product_links(self) -> list[str]:
        links: set[str] = set()
        page = await self._context.new_page()  # clean page — no stealth

        try:
            for listing_url in self.PRODUCT_LISTING_URLS:
                success = await self._navigate_with_retry(page, listing_url)
                if not success:
                    logger.warning(f"[Margiela] Could not load listing: {listing_url}")
                    continue

                # Wait for initial HTML — avoid networkidle which times out due
                # to the cookie banner keeping background requests alive
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)   # let SPA hydrate

                # Dismiss cookie popup on first run (saves cookies for next run)
                await self._dismiss_cookie_popup(page)

                # Brief extra wait for product grid to render after consent
                await page.wait_for_timeout(2000)

                # Scroll to trigger lazy loading — dynamic until page bottom
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

                # Product URLs confirmed pattern: /wx/{slug}-{SKU}.html
                # The SKU portion is all-uppercase alphanumeric, 8+ chars
                anchors = await page.query_selector_all("a[href]")
                for a in anchors:
                    href = await a.get_attribute("href")
                    if not href:
                        continue
                    full_url = urljoin("https://www.maisonmargiela.com", href).split("?")[0]
                    if _PRODUCT_URL_RE.search(full_url):
                        links.add(full_url)

                logger.info(
                    f"[Margiela] {len(links)} product links so far "
                    f"after {listing_url.split('/wx/')[-1]}"
                )
                await random_delay()

        except Exception as e:
            logger.error(f"[Margiela] Error collecting links: {e}")
        finally:
            await page.close()

        result = list(links)
        logger.info(f"[Margiela] Collected {len(result)} product links")
        return result

    # ── Product page parser ─────────────────────────────────────────────────

    async def parse_product(self, url: str) -> Optional[ScrapedProduct]:
        page = await self._context.new_page()  # clean page — no stealth

        try:
            success = await self._navigate_with_retry(page, url)
            if not success:
                return None

            # SPA — domcontentloaded is reliable; networkidle times out due to
            # background requests (consent banner, analytics, etc.)
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)   # let SPA render product content
            await self._dismiss_cookie_popup(page)
            await short_delay()

            # ── Name ──────────────────────────────────────────────────────
            name = await self._get_text(page, "h1")
            if not name:
                return None
            name = name.strip()

            # ── Price ─────────────────────────────────────────────────────
            # Confirmed from console: span.value inside .product-detail.product-wrapper
            # holds the price. European format: "725,00" or "1.175,00"
            # (dot = thousands separator, comma = decimal separator).
            # Must scope to main product wrapper to avoid carousel prices.
            price = None
            price_text = await page.evaluate("""
                () => {
                    const main = document.querySelector(
                        '.product-detail.product-wrapper'
                    );
                    if (!main) return null;
                    const span = main.querySelector('span.value');
                    return span ? span.innerText.trim() : null;
                }
            """)
            if price_text:
                # European format: "1.175,00" → remove thousands dot → replace decimal comma
                clean = price_text.strip()
                if re.search(r'\d\.\d{3},\d{2}$', clean):        # e.g. 1.175,00
                    clean = clean.replace(".", "").replace(",", ".")
                elif "," in clean:                                  # e.g. 725,00
                    clean = clean.replace(",", ".")
                try:
                    price = float(clean)
                except ValueError:
                    pass

            # ── Image ─────────────────────────────────────────────────────
            # Console shows all imgs have class "single-image-product js-product-image"
            # with lazyload — src stays as SVG placeholder, real URL never in data-src.
            # Use evaluate() to read currentSrc (set by browser after lazy load)
            # or fall back to the img element's src after forcing a scroll trigger.
            image_url = await page.evaluate("""
                () => {
                    const selectors = [
                        'img.single-image-product.js-product-image',
                        'img.js-product-image',
                        '.product-primary-image img',
                        '.pdp-images img',
                    ];
                    for (const sel of selectors) {
                        const img = document.querySelector(sel);
                        if (!img) continue;
                        // currentSrc is set after lazy load fires
                        const src = img.currentSrc || img.src || img.getAttribute('data-src')
                                    || img.getAttribute('data-lazysrc');
                        if (src && !src.startsWith('data:')) return src;
                    }
                    return null;
                }
            """)
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

            # ── Description ───────────────────────────────────────────────
            # Console confirmed: class="product-description product-description-box"
            # contains the real product description text.
            description = await self._get_text(
                page, ".product-description.product-description-box"
            )
            if not description:
                # Fallback to the content box without the second class
                description = await self._get_text(page, ".product-description-content")

            # ── Color ─────────────────────────────────────────────────────
            # Console confirmed: class="product-color-variant value-XXX selected-description"
            # contains the color name e.g. "Polished Palladio"
            color = await self._get_text(
                page, "[class*='selected-description'][class*='product-color']"
            )
            if not color:
                color = await self._get_text(
                    page,
                    "[class*='color-variant'][class*='selected']",
                )
            if color:
                color = color.strip()

            # ── Sizes / Variants ──────────────────────────────────────────
            # Console confirmed structure:
            #   Single-size products: <p class="attribute-label-value single-val single-val-size selected">UNI</p>
            #   Multi-size products:  <li> inside .attribute.variation-attribute.attribute-size
            # ── Sizes / Variants ──────────────────────────────────────────
            # Confirmed from console: sizes live in <select> <option> elements.
            # Structure:
            #   <option class="default-attr-option">Size</option>  ← skip this
            #   <option class="disabled" data-value="39">39\n Out of Stock</option>
            #   <option class="" data-value="40">40</option>       ← in stock
            # class="disabled" = out of stock (confusingly named — it's a style class,
            # not the HTML disabled attribute; the HTML disabled attr is always false)
            variants: list[ScrapedVariant] = []

            # Scope to main product wrapper to avoid any duplicate selects
            main = await page.query_selector(".product-detail.product-wrapper")
            scope = main if main else page

            size_options = await scope.query_selector_all("select option")
            for opt in size_options:
                opt_class = await opt.get_attribute("class") or ""

                # Skip the placeholder "Size" option
                if "default-attr-option" in opt_class:
                    continue

                # Get size text — strip "Out of Stock" suffix
                raw_text = await opt.text_content() or ""
                size_text = raw_text.split("\n")[0].strip()
                if not size_text:
                    continue

                # class="disabled" means out of stock on Margiela
                in_stock = "disabled" not in opt_class

                variants.append(ScrapedVariant(
                    size=size_text,
                    color=color,
                    in_stock=in_stock,
                ))

            # Single-size / UNI products (no select dropdown)
            if not variants:
                uni_el = await page.query_selector(
                    "p.attribute-label-value.single-val.selected, "
                    "p.single-val-size.selected"
                )
                if uni_el:
                    size_text = (await uni_el.text_content() or "").strip()
                    if size_text:
                        variants.append(ScrapedVariant(
                            size=size_text,
                            color=color,
                            in_stock=True,
                        ))

            # Last resort — no size info at all
            if not variants:
                add_btn = await page.query_selector("button.mm-button.-solid.add-to-cart")
                in_stock = True
                if add_btn:
                    btn_text = await add_btn.text_content() or ""
                    is_disabled = await add_btn.get_attribute("disabled")
                    if is_disabled or "sold out" in btn_text.lower():
                        in_stock = False
                variants.append(ScrapedVariant(color=color, in_stock=in_stock))

            return ScrapedProduct(
                name=name,
                url=url,
                price=price,
                image_url=image_url,
                category="Fashion",
                description=description,
                variants=variants,
            )

        except Exception as e:
            logger.error(f"[Margiela] Error parsing {url}: {e}")
            return None
        finally:
            await page.close()