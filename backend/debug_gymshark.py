"""Debug script to extract Gymshark __NEXT_DATA__ and API structure."""
import aiohttp
import asyncio
import json
import re
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

async def main():
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # 1. Fetch a product page
        product_url = "https://row.gymshark.com/products/gymshark-running-short-6-shorts-black-aw25"
        print(f"Fetching product page: {product_url}")
        async with session.get(product_url) as resp:
            print(f"Status: {resp.status}")
            html = await resp.text()
            print(f"HTML length: {len(html)}")

            # Extract __NEXT_DATA__
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                page_props = data.get("props", {}).get("pageProps", {})
                print(f"\n=== pageProps keys: {list(page_props.keys())}")
                
                # Save full structure
                with open("gymshark_next_data.json", "w", encoding="utf-8") as f:
                    json.dump(page_props, f, indent=2, default=str)
                print("Full pageProps saved to gymshark_next_data.json")
                
                # Try to find product data
                for key in page_props:
                    val = page_props[key]
                    if isinstance(val, dict):
                        print(f"\n  [{key}] dict keys: {list(val.keys())[:20]}")
                    elif isinstance(val, list):
                        print(f"\n  [{key}] list len={len(val)}")
                        if val and isinstance(val[0], dict):
                            print(f"    first item keys: {list(val[0].keys())[:15]}")
                    else:
                        print(f"\n  [{key}] = {str(val)[:100]}")
            else:
                print("No __NEXT_DATA__ found!")
                # Check for other data patterns
                for pattern_name, pattern in [
                    ("window.__INITIAL_STATE__", r'window\.__INITIAL_STATE__\s*=\s*({.*?});'),
                    ("window.__data", r'window\.__data\s*=\s*({.*?});'),
                    ("application/ld+json", r'<script type="application/ld\+json">(.*?)</script>'),
                ]:
                    matches = re.findall(pattern, html, re.DOTALL)
                    if matches:
                        print(f"\nFound {pattern_name}: {len(matches)} matches")
                        for i, match in enumerate(matches[:2]):
                            try:
                                d = json.loads(match)
                                print(f"  Match {i} keys: {list(d.keys())[:15]}")
                            except:
                                print(f"  Match {i}: {match[:200]}")

        # 2. Fetch collection page
        print("\n\n=== COLLECTION PAGE ===")
        coll_url = "https://row.gymshark.com/collections/all-products"
        async with session.get(coll_url) as resp:
            print(f"Status: {resp.status}")
            html = await resp.text()
            
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                page_props = data.get("props", {}).get("pageProps", {})
                print(f"pageProps keys: {list(page_props.keys())}")
                
                with open("gymshark_collection_data.json", "w", encoding="utf-8") as f:
                    json.dump(page_props, f, indent=2, default=str)
                print("Full collection pageProps saved to gymshark_collection_data.json")
                
                # Look for products array
                for key in page_props:
                    val = page_props[key]
                    if isinstance(val, list) and len(val) > 0:
                        print(f"\n  [{key}] list len={len(val)}")
                        if isinstance(val[0], dict):
                            print(f"    first item keys: {list(val[0].keys())[:20]}")
                            # Print first product summary
                            item = val[0]
                            print(f"    name: {item.get('title', item.get('name', 'N/A'))}")
                            print(f"    url/handle: {item.get('handle', item.get('url', 'N/A'))}")
                    elif isinstance(val, dict):
                        print(f"\n  [{key}] dict keys: {list(val.keys())[:20]}")

        # 3. Try sitemap
        print("\n\n=== SITEMAP ===")
        for url in [
            "https://row.gymshark.com/sitemap.xml",
            "https://row.gymshark.com/sitemap_products_1.xml",
        ]:
            async with session.get(url) as resp:
                print(f"{url}: {resp.status}")
                if resp.status == 200:
                    text = await resp.text()
                    urls = re.findall(r'<loc>(.*?)</loc>', text)
                    print(f"  URLs found: {len(urls)}")
                    product_urls = [u for u in urls if '/products/' in u]
                    print(f"  Product URLs: {len(product_urls)}")
                    for u in product_urls[:5]:
                        print(f"    {u}")

if __name__ == "__main__":
    asyncio.run(main())
