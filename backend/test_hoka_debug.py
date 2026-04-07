"""
Debug script — tests Hoka API endpoints to bypass Akamai bot protection.
Run from backend folder: python test_hoka_debug.py
"""
import asyncio
from playwright.async_api import async_playwright

URLS_TO_TEST = [
    "https://www.hoka.com/on/demandware.store/Sites-HOKA-US-Site/en_US/Search-Show?q=shoes&sz=48&format=ajax",
    "https://www.hoka.com/on/demandware.store/Sites-HOKA-US-Site/en_US/Search-Show?q=bondi&sz=12",
    "https://www.hoka.com/en/us/womens-shoes/?format=ajax",
]

async def debug():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-setuid-sandbox"],
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()

    for url in URLS_TO_TEST:
        print(f"\n{'='*60}")
        print(f"Testing: {url}")
        try:
            response = await page.goto(
                "https://www.hoka.com/on/demandware.store/Sites-HOKA-US-Site/en_US/Search-Show?q=shoes&sz=48&format=ajax",
                wait_until="domcontentloaded",
                timeout=30000
            )
            print(f"Status: {response.status}")
            print(f"Title: {await page.title()}")
            content = await page.content()
            print(f"Content preview: {content[:300]}")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Error: {e}")

    print(f"\n{'='*60}")
    print("Done testing all URLs. Waiting 5s before closing...")
    await asyncio.sleep(5)

    await browser.close()
    await playwright.stop()

asyncio.run(debug())