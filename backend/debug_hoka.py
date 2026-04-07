"""
DEBUG: Hoka — saves output to debug_hoka_output.txt
Run from backend folder: python debug_hoka.py
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class Tee:
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

    print("=" * 70)
    print("TEST 1: Plain Chromium → Hoka womens shoes")
    print("=" * 70)

    browser = await pw.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    page = await ctx.new_page()

    try:
        resp = await page.goto(
            "https://www.hoka.com/en/us/womens-shoes/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        print(f"  Status: {resp.status}")
        print(f"  Title: {await page.title()}")

        # Check what we got
        await asyncio.sleep(5)
        body_text = await page.evaluate("document.body?.innerText?.slice(0, 500) || 'EMPTY'")
        print(f"  Body text (first 500 chars):")
        print(f"    {body_text[:500]}")

        # Check for Akamai challenge page
        akamai = await page.query_selector("#sec-cpt-if, #challenge-form, [id*='akamai']")
        if akamai:
            print("\n  ⚠️  AKAMAI CHALLENGE DETECTED!")
        else:
            # Try to count products
            import re
            anchors = await page.query_selector_all('a[href]')
            product_links = set()
            for a in anchors:
                href = await a.get_attribute("href") or ""
                if re.search(r'/en/us/.+/.+/\d+\.html$', href):
                    product_links.add(href.split("?")[0])
            print(f"\n  Product links found: {len(product_links)}")
            for l in list(product_links)[:5]:
                print(f"    {l}")

    except Exception as e:
        print(f"  ERROR: {e}")

    # Wait so user can see the browser
    print("\n  ⏳ Browser open for 8 seconds — take a screenshot of what you see!")
    await asyncio.sleep(8)
    await browser.close()

    # ── TEST 2: Try Hoka's Demandware AJAX API directly ──────────
    print("\n" + "=" * 70)
    print("TEST 2: Demandware Search API (JSON endpoint)")
    print("=" * 70)

    browser2 = await pw.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    ctx2 = await browser2.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    page2 = await ctx2.new_page()

    # First warm the session by visiting homepage
    print("  Warming session with homepage...")
    try:
        r1 = await page2.goto("https://www.hoka.com/", wait_until="domcontentloaded", timeout=30000)
        print(f"  Homepage status: {r1.status}")
        await asyncio.sleep(3)
    except Exception as e:
        print(f"  Homepage error: {e}")

    # Then try the AJAX API
    api_url = "https://www.hoka.com/on/demandware.store/Sites-HOKA-US-Site/en_US/Search-Show?q=shoes&sz=48&format=ajax"
    print(f"\n  Trying: {api_url}")
    try:
        r2 = await page2.goto(api_url, wait_until="domcontentloaded", timeout=30000)
        print(f"  API status: {r2.status}")
        content = await page2.content()
        print(f"  Content length: {len(content)} chars")
        # Check if it's HTML with products or a block page
        if "access" in content.lower() and "restrict" in content.lower():
            print("  ⚠️  BLOCKED — access restricted")
        elif "product" in content.lower():
            print("  ✅ Got product data!")
            # Count product links in response
            import re
            plinks = re.findall(r'/en/us/[^"]+/\d+\.html', content)
            print(f"  Product URLs in response: {len(set(plinks))}")
            for l in list(set(plinks))[:5]:
                print(f"    {l}")
        else:
            print(f"  Content preview: {content[:300]}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n  ⏳ Browser open for 5 seconds — take a screenshot!")
    await asyncio.sleep(5)
    await browser2.close()

    # ── TEST 3: Try Camoufox if installed ─────────────────────────
    print("\n" + "=" * 70)
    print("TEST 3: Camoufox (if installed)")
    print("=" * 70)
    try:
        from camoufox.async_api import AsyncCamoufox
        print("  Camoufox is installed ✅")

        async with AsyncCamoufox(headless=False) as browser3:
            page3 = await browser3.new_page()
            print("  Navigating to Hoka...")
            r3 = await page3.goto(
                "https://www.hoka.com/en/us/womens-shoes/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            print(f"  Status: {r3.status}")
            print(f"  Title: {await page3.title()}")
            await asyncio.sleep(5)

            body_text = await page3.evaluate("document.body?.innerText?.slice(0, 500) || 'EMPTY'")
            print(f"  Body text (first 500 chars):")
            print(f"    {body_text[:500]}")

            # Check for products
            import re
            anchors = await page3.query_selector_all('a[href]')
            product_links = set()
            for a in anchors:
                href = await a.get_attribute("href") or ""
                if re.search(r'/en/us/.+/.+/\d+\.html$', href):
                    product_links.add(href.split("?")[0])
            print(f"\n  Product links found: {len(product_links)}")
            for l in list(product_links)[:5]:
                print(f"    {l}")

            print("\n  ⏳ Browser open for 8 seconds — take a screenshot!")
            await asyncio.sleep(8)

    except ImportError:
        print("  Camoufox NOT installed.")
        print("  To install: pip install camoufox && python -m camoufox fetch")
    except Exception as e:
        print(f"  Camoufox error: {e}")

    await pw.stop()

    print("\n" + "=" * 70)
    print("DONE — Copy everything above and share it!")
    print("=" * 70)


if __name__ == "__main__":
    tee = Tee("debug_hoka_output.txt")
    sys.stdout = tee
    try:
        asyncio.run(debug())
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
    finally:
        sys.stdout = tee.stdout
        tee.close()
        print("Output saved to debug_hoka_output.txt")
