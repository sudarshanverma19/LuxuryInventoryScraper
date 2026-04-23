"""
Quick test script to find Gymshark's Algolia credentials and test API access.
"""
import aiohttp
import asyncio
import re
import json


async def find_algolia_config():
    """Fetch Gymshark page and extract Algolia config from page source."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get("https://row.gymshark.com/collections/all-products/womens") as resp:
            html = await resp.text()
            print(f"Page length: {len(html)} chars")

            # Search for algolia references
            for pattern_name, pattern in [
                ("algolia app id", r'(?:algoliaAppId|algolia_app_id|appId|applicationId|ALGOLIA_APP_ID)["\s:=]+["\']([a-zA-Z0-9]{8,14})["\']'),
                ("algolia api key", r'(?:algoliaApiKey|algolia_api_key|apiKey|searchKey|ALGOLIA_API_KEY|ALGOLIA_SEARCH_KEY)["\s:=]+["\']([a-zA-Z0-9]{20,40})["\']'),
                ("algolia index", r'(?:algoliaIndex|indexName|ALGOLIA_INDEX)["\s:=]+["\']([a-zA-Z0-9_\-]+)["\']'),
            ]:
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    print(f"  {pattern_name}: {matches}")

            # Look for any occurrence of 'algolia' in the text
            algolia_positions = [m.start() for m in re.finditer(r'algolia', html, re.IGNORECASE)]
            print(f"\n'algolia' found at {len(algolia_positions)} positions")
            for pos in algolia_positions[:5]:
                context = html[max(0, pos-50):pos+150]
                context = re.sub(r'\s+', ' ', context)
                print(f"  ...{context}...")

            # Look for script tags with configuration
            script_contents = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            print(f"\nFound {len(script_contents)} script blocks")
            for i, script in enumerate(script_contents):
                if 'algolia' in script.lower() or 'appId' in script or 'apiKey' in script:
                    print(f"\n  Script #{i} contains algolia config ({len(script)} chars):")
                    # Try to extract the relevant part
                    for line in script.split('\n'):
                        line = line.strip()
                        if any(k in line.lower() for k in ['algolia', 'appid', 'apikey', 'indexname', 'search']):
                            print(f"    {line[:200]}")


async def test_gymshark_sitemap():
    """Try the sitemap approach."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        # Try sitemap
        for url in [
            "https://row.gymshark.com/sitemap.xml",
            "https://row.gymshark.com/sitemap_products_1.xml",
        ]:
            try:
                async with session.get(url) as resp:
                    print(f"\n{url}: {resp.status}")
                    if resp.status == 200:
                        text = await resp.text()
                        print(f"  Length: {len(text)} chars")
                        # Show first few URLs
                        urls = re.findall(r'<loc>(.*?)</loc>', text)
                        print(f"  URLs found: {len(urls)}")
                        for u in urls[:5]:
                            print(f"    {u}")
            except Exception as e:
                print(f"  Error: {e}")


async def main():
    print("=== FINDING ALGOLIA CONFIG ===")
    await find_algolia_config()
    print("\n=== TRYING SITEMAPS ===")
    await test_gymshark_sitemap()


if __name__ == "__main__":
    asyncio.run(main())
