import os

filepath = "scrapers/skims_scraper.py"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

replacement = '''    async def scrape(self) -> tuple[list[ScrapedProduct], HealthCheckResult]:
        health = HealthCheckResult()
        products = []

        logger.info(f"[{self.BRAND_NAME}] Starting API-based scrape via Playwright...")

        try:
            await self._start_browser()
            page = await self._new_page()

            # Step 1: Get product URLs from sitemap
            logger.info(f"[{self.BRAND_NAME}] Fetching sitemap...")
            response = await page.goto(self.SITEMAP_URL, wait_until="domcontentloaded", timeout=30000)
            if not response or response.status != 200:
                health.add_issue("sitemap", f"Sitemap returned {response.status if response else 'None'}", "critical")
                return products, health

            xml_text = await response.text()
            
            import xml.etree.ElementTree as ElementTree
            root = ElementTree.fromstring(xml_text)
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            product_urls = []
            for loc in root.findall(".//s:loc", ns):
                url = loc.text.strip() if loc.text else ""
                if "/products/" in url:
                    product_urls.append(url)

            if not product_urls:
                health.add_issue("sitemap", "No product URLs found in sitemap", "critical")
                return products, health

            logger.info(f"[{self.BRAND_NAME}] Found {len(product_urls)} products in sitemap")
            if MAX_PRODUCTS:
                product_urls = product_urls[:MAX_PRODUCTS]

            # Step 2: Fetch each product page
            for i, url in enumerate(product_urls):
                try:
                    await asyncio.sleep(0.5)
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    if not resp or resp.status != 200:
                        continue
                        
                    html = await resp.text()
                    product = self._parse_ld_json(html, url)
                    if product:
                        products.append(product)
                        
                    if (i + 1) % 50 == 0:
                        logger.info(f"[{self.BRAND_NAME}] Processed {i + 1}/{len(product_urls)} products")
                except Exception as e:
                    logger.debug(f"[{self.BRAND_NAME}] Fetch error for {url}: {e}")
                    
            health = await self._run_health_checks(products, len(product_urls))

        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")
        finally:
            await self._close_browser()

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")
        return products, health'''

import re
scrape_match = re.search(r'    async def scrape\(self\).*?return products, health', content, re.DOTALL)
content = content.replace(scrape_match.group(0), replacement)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"Refactored {filepath}")
