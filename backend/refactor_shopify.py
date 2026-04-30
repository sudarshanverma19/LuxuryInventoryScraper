import os
import re

def refactor_shopify_scraper(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the try block in scrape()
    scrape_match = re.search(r'        try:.*?health = await self\._run_health_checks\(products, len\(products\)\)', content, re.DOTALL)
    if not scrape_match:
        print(f"Skipping {filepath} (no scrape try block match)")
        return
        
    replacement = '''        try:
            await self._start_browser()
            page = await self._new_page()

            page_num = 1
            while True:
                url = f"{self.PRODUCTS_API_URL}?limit=250&page={page_num}"
                logger.info(f"[{self.BRAND_NAME}] Fetching page {page_num}...")

                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                if not response or response.status != 200:
                    if response and response.status in (429, 403, 503):
                        logger.warning(f"[{self.BRAND_NAME}] API returned {response.status}")
                        if response.status == 403:
                            break
                    
                try:
                    data = await response.json()
                except Exception as e:
                    logger.error(f"[{self.BRAND_NAME}] Failed to parse JSON on page {page_num}: {e}")
                    health.add_issue("api_error", f"Failed to parse JSON on page {page_num}", "critical")
                    break

                page_products = data.get("products", [])

                if not page_products:
                    break

                for item in page_products:
                    product_url = f"{self.BASE_URL}products/{item['handle']}"
                    parsed = self._parse_shopify_json(item, product_url)
                    products.append(parsed)

                logger.info(f"[{self.BRAND_NAME}] Page {page_num}: {len(page_products)} products")

                if len(page_products) < 250:
                    break

                page_num += 1
                await asyncio.sleep(0.5)

            health = await self._run_health_checks(products, len(products))'''
            
    content = content.replace(scrape_match.group(0), replacement)
    
    # Add finally block to close browser if not exists
    if 'finally:' not in content:
        content = content.replace('''        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")''', 
            '''        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")
        finally:
            await self._close_browser()''')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Refactored {filepath}")

scrapers = [
    'anta_scraper.py',
    'brooksrunning_scraper.py',
    'crepdogcrew_scraper.py',
    'fentybeauty_scraper.py',
    'hexbeautylab_scraper.py',
    'hourglass_scraper.py',
    'hustleculture_scraper.py',
    'hypeelixir_scraper.py',
    'hypefly_scraper.py',
    'magikart_scraper.py',
    'representclo_scraper.py',
    'youngla_scraper.py'
]

for s in scrapers:
    refactor_shopify_scraper(f"scrapers/{s}")
