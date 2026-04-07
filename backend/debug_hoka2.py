"""
DEBUG: Hoka — test using installed Chrome (not Chromium) + Camoufox tuning
Run: python debug_hoka2.py
"""
import asyncio
import sys
import re

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class Tee:
    def __init__(self, fp):
        self.file = open(fp, "w", encoding="utf-8")
        self.stdout = sys.stdout
    def write(self, d):
        self.stdout.write(d)
        self.file.write(d)
    def flush(self):
        self.stdout.flush()
        self.file.flush()
    def close(self):
        self.file.close()


async def debug():
    from playwright.async_api import async_playwright

    # ── TEST 1: Use INSTALLED Chrome (channel="chrome") ──────────
    # This uses your real Chrome browser, which has the genuine TLS fingerprint
    print("=" * 70)
    print("TEST 1: Installed Chrome (channel='chrome') — real TLS fingerprint")
    print("=" * 70)

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(
            channel="chrome",       # <-- Uses YOUR installed Chrome
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

        # Remove webdriver flag
        page = await ctx.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete navigator.__proto__.webdriver;
        """)

        print("  Navigating to Hoka homepage first...")
        resp = await page.goto("https://www.hoka.com/", wait_until="domcontentloaded", timeout=30000)
        print(f"  Homepage status: {resp.status if resp else 'none'}")
        await asyncio.sleep(4)

        body = await page.evaluate("document.body?.innerText?.slice(0, 300) || 'EMPTY'")
        if "block" in body.lower() or "restricted" in body.lower():
            print(f"  ⚠️ BLOCKED: {body[:200]}")
        else:
            print(f"  ✅ Homepage loaded! Title: {await page.title()}")

            # Now try listing page
            print("\n  Navigating to womens-shoes...")
            resp2 = await page.goto(
                "https://www.hoka.com/en/us/womens-shoes/",
                wait_until="domcontentloaded", timeout=30000
            )
            print(f"  Listing status: {resp2.status if resp2 else 'none'}")
            await asyncio.sleep(4)

            body2 = await page.evaluate("document.body?.innerText?.slice(0, 300) || 'EMPTY'")
            if "block" in body2.lower() or "restricted" in body2.lower():
                print(f"  ⚠️ BLOCKED: {body2[:200]}")
            else:
                print(f"  ✅ Listing loaded! Title: {await page.title()}")
                # Count products
                anchors = await page.query_selector_all("a[href]")
                plinks = set()
                for a in anchors:
                    href = await a.get_attribute("href") or ""
                    if re.search(r'/en/us/.+/.+/\d+\.html', href):
                        plinks.add(href.split("?")[0])
                print(f"  Product links: {len(plinks)}")
                for l in list(plinks)[:5]:
                    print(f"    {l}")

        print("\n  ⏳ 5 sec pause...")
        await asyncio.sleep(5)
        await browser.close()

    except Exception as e:
        print(f"  ERROR: {e}")

    # ── TEST 2: Camoufox with addons + human behavior ─────────────
    print("\n" + "=" * 70)
    print("TEST 2: Camoufox with humanized behavior")
    print("=" * 70)
    try:
        from camoufox.async_api import AsyncCamoufox
        print("  Camoufox available ✅")

        async with AsyncCamoufox(
            headless=False,
            geoip=True,
            humanize=True,     # Enable human-like interactions
        ) as browser3:
            page3 = await browser3.new_page()

            # Warm with homepage — slow and human-like
            print("  Warming: homepage...")
            r3 = await page3.goto("https://www.hoka.com/", wait_until="domcontentloaded", timeout=30000)
            print(f"  Homepage status: {r3.status if r3 else 'none'}")
            await asyncio.sleep(5)

            body3 = await page3.evaluate("document.body?.innerText?.slice(0, 300) || 'EMPTY'")
            if "block" in body3.lower() or "restricted" in body3.lower():
                print(f"  ⚠️ BLOCKED: {body3[:200]}")
            else:
                print(f"  ✅ Homepage OK! Scrolling like a human...")
                # Human-like scrolling
                for _ in range(3):
                    await page3.evaluate("window.scrollBy({top: 200, behavior: 'smooth'})")
                    await asyncio.sleep(2)

                # Now navigate to listing
                print("  Navigating to womens-shoes...")
                r4 = await page3.goto(
                    "https://www.hoka.com/en/us/womens-shoes/",
                    wait_until="domcontentloaded", timeout=30000
                )
                print(f"  Listing status: {r4.status if r4 else 'none'}")
                await asyncio.sleep(5)

                body4 = await page3.evaluate("document.body?.innerText?.slice(0, 300) || 'EMPTY'")
                if "block" in body4.lower() or "restricted" in body4.lower():
                    print(f"  ⚠️ BLOCKED: {body4[:200]}")
                else:
                    print(f"  ✅ Listing loaded!")
                    anchors = await page3.query_selector_all("a[href]")
                    plinks = set()
                    for a in anchors:
                        href = await a.get_attribute("href") or ""
                        if re.search(r'/en/us/.+/.+/\d+\.html', href):
                            plinks.add(href.split("?")[0])
                    print(f"  Product links: {len(plinks)}")
                    for l in list(plinks)[:5]:
                        print(f"    {l}")

            print("\n  ⏳ 5 sec pause...")
            await asyncio.sleep(5)

    except ImportError:
        print("  Camoufox not installed, skipping")
    except Exception as e:
        print(f"  Camoufox error: {e}")

    await pw.stop()
    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    tee = Tee("debug_hoka2_output.txt")
    sys.stdout = tee
    try:
        asyncio.run(debug())
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
    finally:
        sys.stdout = tee.stdout
        tee.close()
        print("Output saved to debug_hoka2_output.txt")
