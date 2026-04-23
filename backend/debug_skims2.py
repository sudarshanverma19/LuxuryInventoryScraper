"""Extract Skims product LD+JSON data for analysis."""
import aiohttp, asyncio, json, re, sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get("https://skims.com/products/cotton-rib-long-sleeve-t-shirt-marble") as resp:
            html = await resp.text()
            ld_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            for i, match in enumerate(ld_matches):
                d = json.loads(match)
                if d.get("@type") == "ProductGroup":
                    with open("skims_product_data.json", "w", encoding="utf-8") as f:
                        json.dump(d, f, indent=2)
                    print(f"name: {d.get('name')}")
                    print(f"variesBy: {d.get('variesBy')}")
                    variants = d.get("hasVariant", [])
                    print(f"variants: {len(variants)}")
                    if variants:
                        v = variants[0]
                        print(f"variant keys: {list(v.keys())}")
                        print(f"variant 0: {json.dumps(v, default=str)[:600]}")
                        if len(variants) > 1:
                            print(f"\nvariant 1: {json.dumps(variants[1], default=str)[:600]}")

asyncio.run(main())
