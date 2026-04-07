"""Quick debug script for OnScraper — logs everything to on_scraper_debug.txt"""
import sys
import asyncio
import logging
import traceback

# Fix for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Log everything to file
log_file = open("on_scraper_debug.txt", "w", encoding="utf-8")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("on_debug")


async def main():
    logger.info("Importing OnScraper...")
    from scrapers.on_scraper import OnScraper

    scraper = OnScraper()
    logger.info("OnScraper imported OK, starting scrape...")

    products, health = await scraper.scrape()

    logger.info(f"=== RESULTS ===")
    logger.info(f"Products found: {len(products)}")
    logger.info(f"Health issues: {health.issues}")

    for i, p in enumerate(products[:5]):
        logger.info(f"  [{i+1}] {p.name} | ${p.price} | {len(p.variants)} variants")
        for v in p.variants[:3]:
            logger.info(f"       size={v.size} color={v.color} in_stock={v.in_stock}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"FATAL: {e}")
        traceback.print_exc(file=log_file)
        traceback.print_exc()
    finally:
        log_file.close()
        print("\n>>> Output saved to on_scraper_debug.txt")
