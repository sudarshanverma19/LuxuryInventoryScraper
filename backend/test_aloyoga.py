import asyncio
import logging
from scrapers.aloyoga_scraper import AloYogaScraper
from database.db import async_session
from services.scrape_service import _upsert_product, _upsert_variants
from database.models import Brand
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)

async def test():
    scraper = AloYogaScraper()
    print("Scraping...")
    products, health = await scraper.scrape()
    print(f"Scraped {len(products)} products.")
    
    if not products:
        return
        
    print(products[0])
    
    async with async_session() as session:
        brand = (await session.execute(select(Brand).where(Brand.slug == 'alo-yoga'))).scalar_one_or_none()
        print(f"Brand ID: {brand.id}")
        
        # Test upserting the first 5 products
        for p in products[:5]:
            try:
                db_p = await _upsert_product(session, brand.id, p)
                if db_p:
                    print(f"Successfully upserted product: {p.name}")
                    count = await _upsert_variants(session, db_p.id, p.variants)
                    print(f"Successfully upserted {count} variants.")
                    await session.commit()
                else:
                    print(f"Failed to upsert product (returned None): {p.name}")
            except Exception as e:
                print(f"Exception during upsert: {e}")
                await session.rollback()

asyncio.run(test())
