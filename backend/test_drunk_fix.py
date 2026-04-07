"""
Quick test: Drunk Elephant scraper — link collection only.
Run: python test_drunk_fix.py
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


async def test():
    from scrapers.drunk_elephant_scraper import DrunkElephantScraper

    scraper = DrunkElephantScraper()
    print("Starting Drunk Elephant link collection...")
    print("(Browser will open and scroll through collection pages)\n")

    await scraper._start_browser()
    try:
        links = await scraper.get_product_links()
        print(f"\n{'='*60}")
        print(f"RESULT: Found {len(links)} unique products")
        print(f"{'='*60}")
        for i, link in enumerate(sorted(links), 1):
            name = link.split("/")[-1].replace(".html", "").rsplit("-", 1)[0]
            print(f"  {i:3d}. {name}")
    finally:
        await scraper._close_browser()


if __name__ == "__main__":
    try:
        asyncio.run(test())
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
