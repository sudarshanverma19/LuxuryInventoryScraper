"""
Test camoufox against Hoka's Akamai bot protection.
Run from backend folder: python test_hoka_camoufox.py
"""
import asyncio
from camoufox.async_api import AsyncCamoufox

async def debug():
    print("Launching camoufox...")
    async with AsyncCamoufox(headless=False) as browser:
        page = await browser.new_page()

        print("Navigating to Hoka womens shoes...")
        response = await page.goto(
            "https://www.hoka.com/en/us/womens-shoes/",
            wait_until="domcontentloaded",
            timeout=30000
        )
        print(f"Status: {response.status}")
        print(f"Title: {await page.title()}")

        # Wait to see what loads
        print("Waiting 10s — watch the browser window...")
        await asyncio.sleep(10)

        # Check for product links
        import re
        anchors = await page.query_selector_all('a[href]')
        product_links = []
        for a in anchors:
            href = await a.get_attribute("href") or ""
            if re.search(r'/en/us/.+/.+/\d+\.html$', href):
                product_links.append(href)

        print(f"Product links found: {len(product_links)}")
        for l in product_links[:5]:
            print(f"  {l}")

        await asyncio.sleep(3)

asyncio.run(debug())