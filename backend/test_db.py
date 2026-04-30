import asyncio
import logging
from database.db import async_session
from services.scrape_service import _upsert_product, _upsert_variants
from scrapers.base_scraper import ScrapedProduct, ScrapedVariant
from database.models import Brand
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)

async def test():
    async with async_session() as session:
        brand = (await session.execute(select(Brand).where(Brand.slug == 'alo-yoga'))).scalar_one_or_none()
        if not brand:
            print("Brand not found!")
            return
            
        p = ScrapedProduct(
            name="Test Product",
            url="https://www.aloyoga.com/test",
            price=10.0,
            currency="INR",
            category="Test",
            variants=[ScrapedVariant(size="M", in_stock=True)]
        )
        
        try:
            print("Upserting product...")
            db_p = await _upsert_product(session, brand.id, p)
            print(f"Product returned: {db_p}")
            if db_p:
                await _upsert_variants(session, db_p.id, p.variants)
                await session.commit()
                print("Commit successful!")
        except Exception as e:
            print(f"FAILED: {e}")

asyncio.run(test())
