"""
Debug script to investigate issues with HypeFly, CrepDog Crew, Hex Beauty Lab, and Skims.
Run: venv\Scripts\python.exe test_debug.py > debug_log.txt 2>&1
"""
import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # ═══════════════════════════════════════════════════
        # 1. HypeFly — confirm no JSON API
        # ═══════════════════════════════════════════════════
        print("=" * 60)
        print("1. HYPEFLY — Checking JSON API")
        print("=" * 60)
        try:
            r = await page.goto("https://hypefly.co.in/products.json?limit=1", wait_until="domcontentloaded", timeout=15000)
            print(f"   Status: {r.status}")
            if r.status == 200:
                data = await r.json()
                print(f"   Products found: {len(data.get('products', []))}")
            else:
                print(f"   CONFIRMED: No JSON API (status {r.status})")
        except Exception as e:
            print(f"   ERROR: {e}")

        # ═══════════════════════════════════════════════════
        # 2. CrepDog Crew — check schema
        # ═══════════════════════════════════════════════════
        print()
        print("=" * 60)
        print("2. CREPDOG CREW — Checking schema")
        print("=" * 60)
        try:
            r = await page.goto("https://crepdogcrew.com/products.json?limit=1", wait_until="domcontentloaded", timeout=15000)
            print(f"   Status: {r.status}")
            if r.status == 200:
                data = await r.json()
                prods = data.get("products", [])
                print(f"   Products on page: {len(prods)}")
                if prods:
                    p0 = prods[0]
                    print(f"   Product keys: {list(p0.keys())}")
                    v0 = p0.get("variants", [{}])[0] if p0.get("variants") else {}
                    print(f"   Variant keys: {list(v0.keys())}")
                    print(f"   Sample title: {p0.get('title', '')[:80]}")
                    print(f"   Sample price: {v0.get('price')}")
                    print(f"   Sample available: {v0.get('available')}")
        except Exception as e:
            print(f"   ERROR: {e}")

        # ═══════════════════════════════════════════════════
        # 3. Hex Beauty Lab — check all pages
        # ═══════════════════════════════════════════════════
        print()
        print("=" * 60)
        print("3. HEX BEAUTY LAB — Checking all pages")
        print("=" * 60)
        total = 0
        try:
            for pg in range(1, 20):
                r = await page.goto(f"https://hexbeautylab.com/products.json?limit=250&page={pg}", wait_until="domcontentloaded", timeout=15000)
                data = await r.json()
                count = len(data.get("products", []))
                total += count
                print(f"   Page {pg}: {count} products (total so far: {total})")
                if count < 250:
                    break
            print(f"   TOTAL products available: {total}")
        except Exception as e:
            print(f"   ERROR: {e}")

        # ═══════════════════════════════════════════════════
        # 4. Skims — check sitemap availability
        # ═══════════════════════════════════════════════════
        print()
        print("=" * 60)
        print("4. SKIMS — Checking sitemaps")
        print("=" * 60)
        sitemap_urls = [
            "https://skims.com/sitemap-products.xml",
            "https://skims.com/sitemap.xml",
            "https://skims.com/sitemap_products_1.xml",
            "https://skims.com/en-in/sitemap.xml",
        ]
        for url in sitemap_urls:
            try:
                r = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
                text = await page.evaluate("document.body.innerText")
                has_products = "/products/" in text
                print(f"   {url}")
                print(f"      Status: {r.status}, Length: {len(text)}, Has /products/: {has_products}")
            except Exception as e:
                print(f"   {url}")
                print(f"      ERROR: {e}")

        # Also check if Skims has a Shopify JSON API
        print()
        print("   Checking Skims JSON API...")
        for url in ["https://skims.com/products.json?limit=1", "https://skims.com/en-in/products.json?limit=1"]:
            try:
                r = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
                print(f"   {url} -> Status: {r.status}")
            except Exception as e:
                print(f"   {url} -> ERROR: {e}")

        await browser.close()
        print()
        print("=" * 60)
        print("DEBUG COMPLETE")
        print("=" * 60)

asyncio.run(main())
