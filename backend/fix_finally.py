"""Fix missing finally blocks in all refactored scrapers."""
import os, re

scrapers_needing_finally = [
    'anta_scraper.py',
    'brooksrunning_scraper.py',
    'crepdogcrew_scraper.py',
    'fentybeauty_scraper.py',
    'hexbeautylab_scraper.py',
    'hourglass_scraper.py',
    'hustleculture_scraper.py',
    'hypeelixir_scraper.py',
    'magikart_scraper.py',
    'representclo_scraper.py',
]

for fname in scrapers_needing_finally:
    filepath = f"scrapers/{fname}"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if '_close_browser' in content:
        print(f"SKIP {fname}: already has _close_browser")
        continue
    
    # Find the except block pattern and add finally after it
    # Pattern: except block followed by the scrape complete log line
    old = '''        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed with error: {str(e)}", "critical")

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")'''
    
    new = '''        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed with error: {str(e)}", "critical")
        finally:
            await self._close_browser()

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")'''
    
    if old in content:
        content = content.replace(old, new)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"FIXED {fname}")
    else:
        # Try alternate pattern without "with error:"
        old2 = '''        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")'''
        new2 = '''        except Exception as e:
            logger.error(f"[{self.BRAND_NAME}] Scrape failed: {e}")
            health.add_issue("exception", f"Scrape failed: {str(e)}", "critical")
        finally:
            await self._close_browser()

        logger.info(f"[{self.BRAND_NAME}] Scrape complete: {len(products)} products")'''
        if old2 in content:
            content = content.replace(old2, new2)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"FIXED {fname} (alt pattern)")
        else:
            print(f"MANUAL FIX NEEDED: {fname}")
