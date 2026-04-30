import asyncio
from playwright.async_api import async_playwright
import json

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = "https://www.aloyoga.com/en-in/products.json?limit=1"
        print(f"Loading {url}...")
        response = await page.goto(url)
        print(f"Status: {response.status}")
        
        content = await page.content()
        if "Just a moment" in content or "Cloudflare" in content or response.status == 403:
            print("Blocked by anti-bot.")
        else:
            text = await page.evaluate("document.body.innerText")
            try:
                data = json.loads(text)
                print(f"Success! Products: {len(data.get('products', []))}")
            except Exception as e:
                print(f"Failed to parse JSON: {e}")
                
        await browser.close()

asyncio.run(test())
