import asyncio
import logging
from scrapers.youngla_scraper import YoungLAScraper

logging.basicConfig(level=logging.INFO)

async def test():
    scraper = YoungLAScraper()
    products, health = await scraper.scrape()
    print(f"Got {len(products)} products from YoungLA.")
    if products:
        print(f"Sample: {products[0].name} - ${products[0].price}")

asyncio.run(test())
