"""
DEBUG: Drunk Elephant — saves output to debug_drunk_output.txt
Run from backend folder: python debug_drunk.py
"""
import asyncio
import sys
import re

# Windows: Playwright needs ProactorEventLoop (the default).
# The "Event loop is closed" error on cleanup is harmless — suppress it.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class Tee:
    """Write to both console and file."""
    def __init__(self, filepath):
        self.file = open(filepath, "w", encoding="utf-8")
        self.stdout = sys.stdout
    def write(self, data):
        self.stdout.write(data)
        self.file.write(data)
    def flush(self):
        self.stdout.flush()
        self.file.flush()
    def close(self):
        self.file.close()


async def debug():
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    await ctx.add_cookies([
        {"name": "drunkelephant_us-preferredSite", "value": "USA",
         "domain": ".drunkelephant.com", "path": "/"},
    ])

    page = await ctx.new_page()

    # ── TEST 1: Skincare collection page ──────────────────────────
    print("=" * 70)
    print("TEST 1: Loading /collections/skincare/")
    print("=" * 70)
    await page.goto("https://www.drunkelephant.com/collections/skincare/",
                    wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    # Dismiss popup
    try:
        btn = await page.query_selector("button.shopnow-button")
        if btn:
            await page.select_option("select.selectcountry", label="United States")
            await btn.click()
            await asyncio.sleep(2)
            print("  Popup dismissed")
    except Exception:
        pass

    # Accept cookies
    try:
        accept = await page.query_selector("button:has-text('Accept All Cookies')")
        if accept:
            await accept.click()
            await asyncio.sleep(1)
            print("  Cookies accepted")
    except Exception:
        pass

    # Scroll to load products
    print("  Scrolling...")
    for i in range(20):
        await page.evaluate("window.scrollBy(0, 400)")
        await asyncio.sleep(1)
    print("  Done scrolling")

    # ── Extract ALL links ──────────────────────────────────────────
    result = await page.evaluate("""
    () => {
        const allAnchors = document.querySelectorAll('a[href]');
        const htmlLinks = [];
        for (const a of allAnchors) {
            const href = a.href || '';
            if (href.includes('.html')) {
                htmlLinks.push(href.split('?')[0]);
            }
        }
        return [...new Set(htmlLinks)];
    }
    """)

    print(f"\n  Total unique .html links on page: {len(result)}")

    # Classify
    product_links = []
    nav_links = []
    for link in result:
        slug = link.split('/')[-1]
        # Product pages have numeric IDs like -194249413797.html
        if re.search(r'\d{6,}', slug):
            product_links.append(link)
        else:
            nav_links.append(link)

    product_links = sorted(set(product_links))
    print(f"\n  PRODUCT links (with numeric IDs): {len(product_links)}")
    for l in product_links:
        print(f"    {l}")

    print(f"\n  NON-PRODUCT .html links: {len(set(nav_links))}")
    for l in sorted(set(nav_links)):
        print(f"    {l}")

    # ── Check product card DOM ────────────────────────────────────
    card_info = await page.evaluate("""
    () => {
        const anchors = document.querySelectorAll('a[href*=".html"]');
        const samples = [];
        for (const a of anchors) {
            const href = a.href || '';
            if (href.includes('/collections/') && /\\d{6,}/.test(href)) {
                const parent = a.parentElement;
                const grandparent = parent?.parentElement;
                samples.push({
                    href: href.split('?')[0],
                    aClass: a.className?.slice(0, 120) || '',
                    parentTag: parent?.tagName || '',
                    parentClass: parent?.className?.slice(0, 120) || '',
                    gpTag: grandparent?.tagName || '',
                    gpClass: grandparent?.className?.slice(0, 120) || '',
                });
                if (samples.length >= 3) break;
            }
        }
        return samples;
    }
    """)

    print(f"\n  Product card DOM samples:")
    for s in card_info:
        print(f"    <a> href: {s['href']}")
        print(f"    <a> class: {s['aClass']}")
        print(f"    parent: <{s['parentTag']}> class=\"{s['parentClass']}\"")
        print(f"    grandparent: <{s['gpTag']}> class=\"{s['gpClass']}\"")
        print()

    # ── TEST 2: Check subcategory pages ───────────────────────────
    print("=" * 70)
    print("TEST 2: Checking subcategory pages")
    print("=" * 70)

    sub_pages = [
        "/collections/moisturizers/",
        "/collections/serums/",
        "/collections/cleansers/",
        "/collections/masks/",
        "/collections/hair-collection/",
        "/collections/body-collection/",
        "/collections/best-sellers/",
        "/collections/kits-bundles/",
    ]

    for sub in sub_pages:
        url = f"https://www.drunkelephant.com{sub}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 400)")
                await asyncio.sleep(0.5)

            count = await page.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href*=".html"]');
                const products = new Set();
                for (const a of links) {
                    const href = (a.href || '').split('?')[0];
                    if (/\\d{6,}/.test(href)) {
                        products.add(href);
                    }
                }
                return products.size;
            }
            """)
            print(f"  {sub:40s} -> {count} products")
        except Exception as e:
            print(f"  {sub:40s} -> ERROR: {e}")

    print("\n" + "=" * 70)
    print("DONE — output also saved to debug_drunk_output.txt")
    print("=" * 70)

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    tee = Tee("debug_drunk_output.txt")
    sys.stdout = tee
    try:
        asyncio.run(debug())
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
    finally:
        sys.stdout = tee.stdout
        tee.close()
        print("Output saved to debug_drunk_output.txt")
