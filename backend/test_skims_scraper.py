"""Quick test for the Skims scraper — scrapes 10 products to verify it works."""
import sys
import asyncio
import logging

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("skims_test")


async def main():
    import scrapers.skims_scraper as ss
    ss.MAX_PRODUCTS = 10

    from scrapers.skims_scraper import SkimsScraper
    scraper = SkimsScraper()

    logger.info("Starting Skims scraper test (10 products)...")
    products, health = await scraper.scrape()

    logger.info(f"\n{'='*60}")
    logger.info(f"Products scraped: {len(products)}")
    logger.info(f"Health issues: {health.issues}")
    logger.info(f"{'='*60}")

    for i, p in enumerate(products):
        logger.info(f"\n[{i+1}] {p.name}")
        logger.info(f"    URL: {p.url}")
        logger.info(f"    Price: {p.price} {p.currency}")
        logger.info(f"    Category: {p.category}")
        logger.info(f"    Image: {p.image_url[:80] if p.image_url else 'None'}...")
        logger.info(f"    Variants: {len(p.variants)}")
        for v in p.variants[:5]:
            stock = "IN STOCK" if v.in_stock else "OUT"
            logger.info(f"      {stock} | {v.size or 'OS'} | {v.color or '-'} | SKU: {v.sku or '-'}")
        if len(p.variants) > 5:
            logger.info(f"      ... and {len(p.variants) - 5} more")


if __name__ == "__main__":
    asyncio.run(main())
