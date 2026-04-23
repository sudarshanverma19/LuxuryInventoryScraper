"""Debug script to understand Skims website structure."""
import aiohttp
import asyncio
import json
import re
import sys
from xml.etree import ElementTree

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
        # 1. Check product sitemap
        print("=== PRODUCT SITEMAP ===")
        async with session.get("https://skims.com/sitemap-products.xml") as resp:
            print(f"Status: {resp.status}")
            if resp.status == 200:
                text = await resp.text()
                # Parse XML
                root = ElementTree.fromstring(text)
                ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                urls = [loc.text.strip() for loc in root.findall(".//s:loc", ns) if loc.text]
                print(f"Total URLs: {len(urls)}")
                product_urls = [u for u in urls if "/products/" in u]
                print(f"Product URLs: {len(product_urls)}")
                for u in product_urls[:10]:
                    print(f"  {u}")
                # Save all product URLs
                with open("skims_product_urls.txt", "w") as f:
                    for u in product_urls:
                        f.write(u + "\n")

        # 2. Fetch a product page and look for data
        if product_urls:
            test_url = product_urls[0]
            print(f"\n=== PRODUCT PAGE: {test_url} ===")
            async with session.get(test_url) as resp:
                print(f"Status: {resp.status}")
                html = await resp.text()
                print(f"HTML length: {len(html)}")
                
                # Check for __NEXT_DATA__
                m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
                if m:
                    data = json.loads(m.group(1))
                    pp = data.get("props", {}).get("pageProps", {})
                    print(f"\n__NEXT_DATA__ pageProps keys: {list(pp.keys())}")
                    with open("skims_next_data.json", "w", encoding="utf-8") as f:
                        json.dump(pp, f, indent=2, default=str)
                    print("Saved to skims_next_data.json")
                    
                    for key in pp:
                        val = pp[key]
                        if isinstance(val, dict):
                            print(f"  [{key}] dict keys: {list(val.keys())[:20]}")
                        elif isinstance(val, list):
                            print(f"  [{key}] list len={len(val)}")
                            if val and isinstance(val[0], dict):
                                print(f"    first keys: {list(val[0].keys())[:15]}")
                        else:
                            print(f"  [{key}] = {str(val)[:100]}")
                else:
                    print("No __NEXT_DATA__ found")
                
                # Check for application/ld+json
                ld_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
                if ld_matches:
                    print(f"\napplication/ld+json blocks: {len(ld_matches)}")
                    for i, match in enumerate(ld_matches):
                        try:
                            d = json.loads(match)
                            print(f"  Block {i}: @type={d.get('@type')} keys={list(d.keys())[:10]}")
                            if d.get('@type') == 'Product':
                                print(f"    name: {d.get('name')}")
                                print(f"    offers: {str(d.get('offers', {}))[:200]}")
                                with open("skims_ld_json.json", "w", encoding="utf-8") as f:
                                    json.dump(d, f, indent=2)
                                print("    Saved to skims_ld_json.json")
                        except:
                            print(f"  Block {i}: parse error")
                
                # Check for window.__INITIAL_DATA__ or similar
                for pattern_name, pattern in [
                    ("window.__INITIAL", r'window\.__INITIAL[_A-Z]*\s*=\s*({.*?});'),
                    ("window.__data", r'window\.__data\s*=\s*({.*?});'),
                    ("window.ShopifyAnalytics", r'window\.ShopifyAnalytics'),
                    ("Shopify.theme", r'Shopify\.theme'),
                    ("product JSON in script", r'var\s+product\s*=\s*({.*?});'),
                ]:
                    matches = re.findall(pattern, html, re.DOTALL)
                    if matches:
                        print(f"\n  Found {pattern_name}: {len(matches)} matches")

        # 3. Try common API endpoints
        print("\n=== API ENDPOINTS ===")
        for api_url in [
            "https://skims.com/api/products",
            "https://skims.com/api/v1/products",
            "https://skims.com/en-in/collections/all.json",
            "https://skims.com/collections/all.json",
        ]:
            try:
                async with session.get(api_url) as resp:
                    print(f"  {api_url}: {resp.status}")
                    if resp.status == 200:
                        text = await resp.text()
                        print(f"    Length: {len(text)}")
                        try:
                            data = json.loads(text)
                            print(f"    Keys: {list(data.keys())[:10]}")
                        except:
                            print(f"    Not JSON")
            except Exception as e:
                print(f"  {api_url}: Error - {e}")


if __name__ == "__main__":
    asyncio.run(main())
