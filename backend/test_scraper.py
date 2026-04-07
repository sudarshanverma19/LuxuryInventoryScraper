"""
Quick test — only scrapes 3 products to verify Hoka scraper works.
Run from backend folder: python test_hoka.py
"""
import asyncio
from scrapers.hoka_scraper import HokaScraper


async def test():
    print("Testing Hoka scraper (quick — 3 products only)...")
    s = HokaScraper()

    await s._start_browser()
    links = await s.get_product_links()
    print(f"Total links found: {len(links)}")

    if not links:
        print("No links found!")
        await s._close_browser()
        return

    print("\nSample links:")
    for link in links[:5]:
        print(f"  {link}")

    products = []
    for url in links[:3]:
        print(f"\nScraping: {url}")
        product = await s.parse_product(url)
        if product:
            products.append(product)
            print(f"  Name        : {product.name}")
            print(f"  Price       : {product.price}")
            print(f"  Image URL   : {product.image_url}")
            print(f"  Description : {(product.description or '')[:80]}...")
            print(f"  Variants    : {len(product.variants)}")
            if product.variants:
                for v in product.variants[:5]:
                    print(f"  Variant     : size={v.size}, color={v.color}, in_stock={v.in_stock}")
                if len(product.variants) > 5:
                    print(f"  ... and {len(product.variants) - 5} more variants")
            else:
                print("  WARNING: No variants found!")
        else:
            print("  FAILED to parse — check selectors")

    await s._close_browser()
    print(f"\n--- DONE: {len(products)}/3 products scraped successfully ---")

    if len(products) < 3:
        print("\nTROUBLESHOOT: Open a product URL above in Chrome DevTools and run:")
        print('  console.log("NAME:", document.querySelector("h1")?.innerText)')
        print('  console.log("PRICE:", document.querySelector("span.accessible-price-summary")?.innerText)')
        print('  document.querySelectorAll("button.options-select").forEach(el =>')
        print('    console.log("SIZE:", el.innerText?.trim(), "| disabled:", el.disabled))')


asyncio.run(test())