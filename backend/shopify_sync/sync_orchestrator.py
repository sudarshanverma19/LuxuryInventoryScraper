"""
Shopify Sync Orchestrator.

Main engine that processes stored products in batches, downloads images,
uploads them to Shopify via staged uploads, and creates products with
attached media. Handles concurrency, batching, and status management.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    SHOPIFY_SYNC_BATCH_SIZE,
    SHOPIFY_SYNC_CONCURRENCY,
    SHOPIFY_SYNC_BATCH_DELAY,
    SHOPIFY_IMAGE_COMPRESSION,
    SHOPIFY_STORE_URL,
    SHOPIFY_ACCESS_TOKEN,
)
from database.db import async_session
from database.models import Product, Brand, Variant, ShopifySyncJob, ShopifySyncLog
from shopify_sync.shopify_client import ShopifyClient, VariantInput
from shopify_sync.image_handler import download_image, compress_image
from shopify_sync.retry import RetryExhausted

logger = logging.getLogger(__name__)

# Module-level flag to track running sync
_running_sync: Optional[int] = None  # job_id if running


def is_sync_running() -> bool:
    """Check if a sync job is currently running."""
    return _running_sync is not None


async def get_sync_status() -> dict:
    """Get current sync status and latest job info."""
    async with async_session() as session:
        # Get the latest job
        result = await session.execute(
            select(ShopifySyncJob)
            .order_by(ShopifySyncJob.started_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()

        # Count pending products
        pending_count = (await session.execute(
            select(func.count(Product.id))
            .where(Product.shopify_sync_status == "pending")
        )).scalar() or 0

        # Count completed products
        completed_count = (await session.execute(
            select(func.count(Product.id))
            .where(Product.shopify_sync_status == "completed")
        )).scalar() or 0

        # Count failed products
        failed_count = (await session.execute(
            select(func.count(Product.id))
            .where(Product.shopify_sync_status == "failed")
        )).scalar() or 0

        status = {
            "is_running": is_sync_running(),
            "pending_products": pending_count,
            "completed_products": completed_count,
            "failed_products": failed_count,
            "is_configured": bool(SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN),
        }

        if job:
            status["latest_job"] = {
                "id": job.id,
                "status": job.status,
                "total_products": job.total_products,
                "completed": job.completed_count,
                "failed": job.failed_count,
                "skipped": job.skipped_count,
                "brand_filter": job.brand_filter,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "error_summary": job.error_summary,
            }

        return status


async def get_sync_history(limit: int = 20) -> list[dict]:
    """Get sync job history."""
    async with async_session() as session:
        result = await session.execute(
            select(ShopifySyncJob)
            .order_by(ShopifySyncJob.started_at.desc())
            .limit(limit)
        )
        jobs = result.scalars().all()

        return [
            {
                "id": job.id,
                "status": job.status,
                "total_products": job.total_products,
                "completed": job.completed_count,
                "failed": job.failed_count,
                "skipped": job.skipped_count,
                "brand_filter": job.brand_filter,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "error_summary": job.error_summary,
            }
            for job in jobs
        ]


async def get_sync_logs(job_id: int) -> list[dict]:
    """Get per-product sync logs for a specific job."""
    async with async_session() as session:
        result = await session.execute(
            select(ShopifySyncLog, Product, Brand)
            .join(Product, ShopifySyncLog.product_id == Product.id)
            .join(Brand, Product.brand_id == Brand.id)
            .where(ShopifySyncLog.sync_job_id == job_id)
            .order_by(ShopifySyncLog.created_at.desc())
        )
        rows = result.all()

        return [
            {
                "id": log.id,
                "product_id": log.product_id,
                "product_name": product.name,
                "brand_name": brand.name,
                "status": log.status,
                "shopify_product_id": log.shopify_product_id,
                "error_message": log.error_message,
                "image_count": log.image_count,
                "images_uploaded": log.images_uploaded,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log, product, brand in rows
        ]


async def retry_failed_products() -> int:
    """Re-queue all failed products back to pending. Returns count."""
    async with async_session() as session:
        result = await session.execute(
            select(Product).where(Product.shopify_sync_status == "failed")
        )
        products = result.scalars().all()

        count = 0
        for product in products:
            product.shopify_sync_status = "pending"
            count += 1

        await session.commit()
        logger.info(f"[ShopifySync] Re-queued {count} failed products to pending")
        return count


# ── Main Sync Entry Point ─────────────────────────────────────────────────

async def run_sync(brand_slug: Optional[str] = None, publish_mode: str = "DRAFT") -> dict:
    """
    Run the Shopify sync process.

    Args:
        brand_slug: Optional brand slug to filter products. None = all brands.
        publish_mode: "DRAFT" or "ACTIVE". Controls Shopify product visibility.

    Returns:
        Summary dict with job results
    """
    global _running_sync

    if _running_sync is not None:
        return {"error": "A sync job is already running", "job_id": _running_sync}

    # Validate configuration
    if not SHOPIFY_STORE_URL or not SHOPIFY_ACCESS_TOKEN:
        return {"error": "Shopify credentials not configured. Set SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN in .env"}

    async with async_session() as session:
        # Create the sync job
        job = ShopifySyncJob(
            status="running",
            brand_filter=brand_slug,
            started_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

        _running_sync = job.id
        logger.info(f"[ShopifySync] Starting sync job #{job.id} (brand={brand_slug or 'all'}, mode={publish_mode})")

    try:
        result = await _execute_sync(job.id, brand_slug, publish_mode)
        return result
    except Exception as e:
        logger.error(f"[ShopifySync] Sync job #{job.id} crashed: {e}")
        async with async_session() as session:
            job = await session.get(ShopifySyncJob, job.id)
            if job:
                job.status = "failed"
                job.error_summary = str(e)[:2000]
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
        return {"error": str(e), "job_id": job.id}
    finally:
        _running_sync = None


async def _execute_sync(job_id: int, brand_slug: Optional[str] = None, publish_mode: str = "DRAFT") -> dict:
    """Core sync execution logic."""
    total_processed = 0
    total_completed = 0
    total_failed = 0
    total_skipped = 0
    error_messages = []

    async with ShopifyClient() as shopify_client:
        # Process in batches
        offset = 0
        batch_num = 0

        while True:
            batch_num += 1

            # Fetch a batch of pending products
            async with async_session() as session:
                query = (
                    select(Product, Brand)
                    .join(Brand, Product.brand_id == Brand.id)
                    .where(Product.shopify_sync_status == "pending")
                )

                if brand_slug:
                    query = query.where(Brand.slug == brand_slug)

                query = query.order_by(Product.id).limit(SHOPIFY_SYNC_BATCH_SIZE)
                result = await session.execute(query)
                batch = result.all()

            if not batch:
                logger.info(f"[ShopifySync] No more pending products to process")
                break

            logger.info(
                f"[ShopifySync] Processing batch #{batch_num}: "
                f"{len(batch)} products"
            )

            # Process batch with concurrency limiter
            semaphore = asyncio.Semaphore(SHOPIFY_SYNC_CONCURRENCY)
            tasks = []

            for product, brand in batch:
                task = asyncio.create_task(
                    _process_product_with_semaphore(
                        semaphore, job_id, product.id, brand.id,
                        shopify_client, publish_mode,
                    )
                )
                tasks.append(task)

            # Wait for all tasks in the batch to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                total_processed += 1
                if isinstance(r, Exception):
                    total_failed += 1
                    error_messages.append(str(r)[:200])
                elif r == "completed":
                    total_completed += 1
                elif r == "skipped":
                    total_skipped += 1
                elif r == "failed":
                    total_failed += 1

            # Update job progress
            async with async_session() as session:
                job = await session.get(ShopifySyncJob, job_id)
                if job:
                    job.total_products = total_processed
                    job.completed_count = total_completed
                    job.failed_count = total_failed
                    job.skipped_count = total_skipped
                    await session.commit()

            # Delay between batches to respect rate limits
            if batch and len(batch) == SHOPIFY_SYNC_BATCH_SIZE:
                logger.info(
                    f"[ShopifySync] Batch #{batch_num} done. "
                    f"Waiting {SHOPIFY_SYNC_BATCH_DELAY}s before next batch..."
                )
                await asyncio.sleep(SHOPIFY_SYNC_BATCH_DELAY)

    # Finalize job
    async with async_session() as session:
        job = await session.get(ShopifySyncJob, job_id)
        if job:
            job.total_products = total_processed
            job.completed_count = total_completed
            job.failed_count = total_failed
            job.skipped_count = total_skipped
            job.status = "completed" if total_failed == 0 else "completed"
            if total_failed > 0 and total_completed == 0:
                job.status = "failed"
            if error_messages:
                job.error_summary = "; ".join(error_messages[:10])
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()

    summary = {
        "job_id": job_id,
        "status": "completed",
        "total_processed": total_processed,
        "completed": total_completed,
        "failed": total_failed,
        "skipped": total_skipped,
    }

    logger.info(
        f"[ShopifySync] Sync job #{job_id} finished: "
        f"{total_completed} completed, {total_failed} failed, "
        f"{total_skipped} skipped out of {total_processed} total"
    )

    return summary


async def _process_product_with_semaphore(
    semaphore: asyncio.Semaphore,
    job_id: int,
    product_id: int,
    brand_id: int,
    shopify_client: ShopifyClient,
    publish_mode: str = "DRAFT",
) -> str:
    """Wrapper to limit concurrency via semaphore."""
    async with semaphore:
        return await _process_single_product(
            job_id, product_id, brand_id, shopify_client, publish_mode
        )


async def _process_single_product(
    job_id: int,
    product_id: int,
    brand_id: int,
    shopify_client: ShopifyClient,
    publish_mode: str = "DRAFT",
) -> str:
    """
    Full pipeline for a single product:
    1. Mark as processing
    2. Download images
    3. Stage upload images to Shopify
    4. Create product with media
    5. Optionally create variants
    6. Update status

    Returns: "completed", "failed", or "skipped"
    """
    product_name = ""
    image_count = 0
    images_uploaded = 0

    try:
        # 1. Load product data and mark as processing
        async with async_session() as session:
            product = await session.get(Product, product_id)
            if not product:
                return "skipped"

            # Skip if already completed (race condition guard)
            if product.shopify_sync_status == "completed":
                return "skipped"

            product_name = product.name
            product.shopify_sync_status = "processing"
            await session.commit()

            # Gather product data
            brand = await session.get(Brand, brand_id)
            brand_name = brand.name if brand else "Unknown"
            brand_category = brand.category if brand else None

            # Get variants
            var_result = await session.execute(
                select(Variant).where(Variant.product_id == product_id)
            )
            variants = var_result.scalars().all()

            # Collect all image URLs (main + any from variants if applicable)
            image_urls = []
            if product.image_url:
                image_urls.append(product.image_url)

            image_count = len(image_urls)

            product_data = {
                "name": product.name,
                "url": product.url,
                "price": product.price,
                "currency": product.currency,
                "category": product.category,
                "description": product.description,
                "image_urls": image_urls,
                "variants": [
                    {
                        "size": v.size,
                        "color": v.color,
                        "sku": v.sku,
                        "in_stock": v.in_stock,
                        "quantity": v.quantity,
                    }
                    for v in variants
                ],
            }

        logger.info(f"[ShopifySync] Processing: {product_name} ({image_count} images)")

        # 2. Download and upload images
        media_sources = []
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        ) as http_client:
            for img_url in product_data["image_urls"]:
                try:
                    # Download
                    img_data, content_type, filename = await download_image(
                        img_url, client=http_client
                    )

                    # Optional compression
                    if SHOPIFY_IMAGE_COMPRESSION:
                        img_data, content_type, _ = compress_image(
                            img_data, content_type
                        )

                    # Staged upload
                    target = await shopify_client.staged_upload(
                        filename, content_type, len(img_data)
                    )

                    # Upload file
                    resource_url = await shopify_client.upload_file(
                        target, img_data, filename, content_type
                    )

                    media_sources.append(resource_url)
                    images_uploaded += 1

                except Exception as e:
                    logger.warning(
                        f"[ShopifySync] Image failed for '{product_name}': "
                        f"{img_url[:80]} — {e}"
                    )
                    # Continue with remaining images

        # 3. Create product on Shopify
        description = product_data.get("description") or ""
        if product_data.get("url"):
            description += f'\n<p><a href="{product_data["url"]}">Original product page</a></p>'

        tags = []
        if brand_category:
            tags.append(brand_category)
        if product_data.get("category"):
            tags.append(product_data["category"])

        result = await shopify_client.create_product(
            title=product_data["name"],
            description_html=description if description.strip() else None,
            vendor=brand_name,
            product_type=product_data.get("category"),
            tags=tags if tags else None,
            media_sources=media_sources if media_sources else None,
            status=publish_mode,
        )

        shopify_product_id = result.product_id

        # 4. Create variants if available
        variant_inputs = []
        for v in product_data["variants"]:
            option_values = []
            if v.get("size"):
                option_values.append(v["size"])
            if v.get("color"):
                option_values.append(v["color"])

            if option_values:
                variant_inputs.append(VariantInput(
                    sku=v.get("sku"),
                    price=product_data.get("price"),
                    option_values=option_values,
                ))

        if variant_inputs:
            try:
                await shopify_client.create_variants(
                    shopify_product_id, variant_inputs
                )
            except Exception as e:
                # Variant creation failure is non-fatal
                logger.warning(
                    f"[ShopifySync] Variant creation failed for '{product_name}': {e}"
                )

        # 5. Update product status in DB
        async with async_session() as session:
            product = await session.get(Product, product_id)
            if product:
                product.shopify_sync_status = "completed"
                product.shopify_product_id = shopify_product_id
                product.shopify_synced_at = datetime.now(timezone.utc)
                await session.commit()

        # 6. Create success log
        async with async_session() as session:
            log = ShopifySyncLog(
                sync_job_id=job_id,
                product_id=product_id,
                status="completed",
                shopify_product_id=shopify_product_id,
                image_count=image_count,
                images_uploaded=images_uploaded,
            )
            session.add(log)
            await session.commit()

        logger.info(
            f"[ShopifySync] ✓ {product_name} → {shopify_product_id} "
            f"({images_uploaded}/{image_count} images)"
        )
        return "completed"

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:500]}"
        logger.error(f"[ShopifySync] ✗ {product_name}: {error_msg}")

        # Mark product as failed
        try:
            async with async_session() as session:
                product = await session.get(Product, product_id)
                if product:
                    product.shopify_sync_status = "failed"
                    await session.commit()

                # Create failure log
                log = ShopifySyncLog(
                    sync_job_id=job_id,
                    product_id=product_id,
                    status="failed",
                    error_message=error_msg[:2000],
                    image_count=image_count,
                    images_uploaded=images_uploaded,
                )
                session.add(log)
                await session.commit()
        except Exception as db_err:
            logger.error(f"[ShopifySync] Failed to log error for product {product_id}: {db_err}")

        return "failed"
