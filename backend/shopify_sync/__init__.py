"""
shopify_sync — Automated Shopify product upload module.

Processes stored products, downloads images, uploads them to Shopify
via staged uploads (GraphQL), and creates products with attached media.
"""

from shopify_sync.sync_orchestrator import run_sync, get_sync_status

__all__ = ["run_sync", "get_sync_status"]
