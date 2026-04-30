import os
import re

filepath = "scrapers/tcg_republic_scraper.py"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

scrape_match = re.search(r'        try:.*?health = await self\._run_health_checks\(products, len\(products\)\)', content, re.DOTALL)

replacement = '''        try:
            await self._start_browser()
            page = await self._new_page()

            page_num = 1
            while True:
                url = f"{self.PRODUCTS_API_URL}?per_page=100&page={page_num}"
                logger.info(f"[{self.BRAND_NAME}] Fetching page {page_num}...")
                
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                if not response or response.status != 200:
                    if response and response.status == 400:
                        break
                    logger.warning(f"[{self.BRAND_NAME}] API returned {response.status if response else 'None'}")
                    if response and response.status in (429, 403, 503):
                        if response.status == 403:
                            break
                
                try:
                    page_products = await response.json()
                except Exception as e:
                    logger.error(f"[{self.BRAND_NAME}] Failed to parse JSON on page {page_num}: {e}")
                    health.add_issue("api_error", f"Failed to parse JSON on page {page_num}", "critical")
                    break
                    
                if not page_products or not isinstance(page_products, list):
                    break
                    
                for item in page_products:
                    parsed = self._parse_wc_json(item)
                    products.append(parsed)
                    
                if len(page_products) < 100:
                    break
                    
                page_num += 1
                await asyncio.sleep(0.5)
                
            health = await self._run_health_checks(products, len(products))'''

content = content.replace(scrape_match.group(0), replacement)

if 'finally:' not in content:
    content = content.replace('''        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed with error: {str(e)}", "critical")''', 
            '''        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed with error: {str(e)}", "critical")
        finally:
            await self._close_browser()''')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"Refactored {filepath}")
