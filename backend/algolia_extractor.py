"""
Algolia product extractor.
Paginates through all products from an Algolia-powered e-commerce site.
"""

import httpx
import json
import time

ALGOLIA_URL = "https://k1n6gb06ip-dsn.algolia.net/1/indexes/*/queries"

HEADERS = {
    "x-algolia-application-id": "K1N6GB06IP",
    "x-algolia-api-key": "Y2MwMDA1OTA2MTc3MjY1MWYxMzhiOGQ0OTdlMjk5MmY1MWY2NGI2MmQyOWZlN2NlNGRhYzgzMWQwYTI5YjI4",
    "content-type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Origin": "https://www.gymshark.com",
    "Referer": "https://www.gymshark.com/",
}

INDEX_NAME = "prod_en-US_products"
HITS_PER_PAGE = 100


def fetch_page(client: httpx.Client, page: int) -> dict:
    """Fetch a single page of results from Algolia."""
    body = {
        "requests": [
            {
                "indexName": INDEX_NAME,
                "hitsPerPage": HITS_PER_PAGE,
                "page": page,
            }
        ]
    }
    resp = client.post(ALGOLIA_URL, json=body)
    resp.raise_for_status()
    return resp.json()


def extract_all_products() -> list[dict]:
    """Paginate through all Algolia pages and collect every product hit."""
    all_products = []
    page = 0

    with httpx.Client(headers=HEADERS, timeout=30) as client:
        while True:
            print(f"Fetching page {page}...", end=" ")
            data = fetch_page(client, page)

            results = data.get("results", [])
            if not results:
                print("No results block — stopping.")
                break

            hits = results[0].get("hits", [])
            nb_pages = results[0].get("nbPages", 0)
            nb_hits = results[0].get("nbHits", 0)
            current_page = results[0].get("page", page)

            print(f"got {len(hits)} hits (page {current_page + 1}/{nb_pages}, total: {nb_hits})")

            if not hits:
                break

            all_products.extend(hits)

            # Stop if we've reached the last page
            if current_page + 1 >= nb_pages:
                break

            page += 1
            time.sleep(0.3)  # polite delay

    return all_products


def main():
    print("=" * 60)
    print("Algolia Product Extractor")
    print("=" * 60)

    products = extract_all_products()

    print(f"\n{'=' * 60}")
    print(f"Total products extracted: {len(products)}")
    print("=" * 60)

    # Show structure of first product
    if products:
        first = products[0]
        print(f"\nProduct keys: {list(first.keys())}")
        print(f"\nSample product:")
        print(f"  Name:  {first.get('title', first.get('name', 'N/A'))}")
        print(f"  Price: {first.get('price', 'N/A')}")
        print(f"  URL:   {first.get('url', first.get('handle', 'N/A'))}")
        print(f"  Type:  {first.get('product_type', first.get('type', 'N/A'))}")
        print(f"  Color: {first.get('colour', 'N/A')}")
        print(f"  Stock: {first.get('inStock', 'N/A')}")

        # Show sizes if available
        sizes = first.get("availableSizes", first.get("sizes", []))
        if sizes and isinstance(sizes, list):
            print(f"  Sizes: {len(sizes)} variants")
            for s in sizes[:3]:
                if isinstance(s, dict):
                    print(f"    - {s.get('size', '?')} | stock={s.get('inStock', '?')} | qty={s.get('inventoryQuantity', '?')}")

    # Save all products to JSON
    output_file = "algolia_products.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, default=str)
    print(f"\nAll products saved to {output_file}")


if __name__ == "__main__":
    main()
