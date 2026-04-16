import asyncio
from scrapers.acne_scraper import AcneScraper

async def main():
    s = AcneScraper()
    await s._start_browser()
    links = await s.get_product_links()
    print("Acne links:", len(links))

if __name__ == "__main__":
    asyncio.run(main())
