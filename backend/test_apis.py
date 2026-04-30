import asyncio
from playwright.async_api import async_playwright

async def check_api(name, url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            print(f"Testing {name} at {url}...")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if resp and resp.status == 200:
                text = await page.evaluate("document.body.innerText")
                if "{" in text and "}" in text:
                    print(f"✅ {name}: API exists and returns JSON (Status 200)!")
                else:
                    print(f"❌ {name}: Returns 200 but not JSON.")
            else:
                print(f"❌ {name}: Failed with status {resp.status if resp else 'None'}")
        except Exception as e:
            print(f"❌ {name}: Exception - {e}")
        finally:
            await browser.close()

async def main():
    await check_api("Skims Shopify API", "https://skims.com/products.json?limit=1")
    await check_api("Bored Game Co WooCommerce API", "https://boredgamecompany.com/wp-json/wc/store/products?per_page=1")

asyncio.run(main())
