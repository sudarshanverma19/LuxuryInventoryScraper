import asyncio
from scrapers.anta_scraper import AntaScraper
import logging

logging.basicConfig(level=logging.INFO)

async def test():
    print("Testing ANTA scraper...")
    s = AntaScraper()
    products, health = await s.scrape()
    print(f"\nTotal scraped: {len(products)}")
    
    if products:
        p = products[0]
        print(f"\nSample product:")
        print(f"Name: {p.name}")
        print(f"URL: {p.url}")
        print(f"Price: {p.price} {p.currency}")
        print(f"Category: {p.category}")
        print(f"Image: {p.image_url}")
        print(f"Variant count: {len(p.variants)}")
        if p.variants:
            v = p.variants[0]
            print(f"First variant: size={v.size}, sku={v.sku}, in_stock={v.in_stock}, qty={v.quantity}")
        
    print("\nHealth check issues:")
    for issue in health.issues:
        print(f"[{issue['severity'].upper()}] {issue['check_type']}: {issue['details']}")

if __name__ == "__main__":
    asyncio.run(test())
