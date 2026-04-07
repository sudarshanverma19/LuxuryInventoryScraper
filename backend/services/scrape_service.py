"""
Scrape service — orchestrates scraping jobs, upserts products into DB,
and triggers alert generation after each scrape.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Brand, Product, Variant, ScrapeJob
from scrapers.base_scraper import ScrapedProduct, HealthCheckResult
from services.alert_service import generate_stock_alerts, create_health_alerts

logger = logging.getLogger(__name__)


async def create_scrape_job(session: AsyncSession, brand_id: int) -> ScrapeJob:
    """Create a new scrape job record."""
    job = ScrapeJob(
        brand_id=brand_id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def complete_scrape_job(
    session: AsyncSession,
    job: ScrapeJob,
    products: list[ScrapedProduct],
    health: HealthCheckResult,
):
    """
    Save scraped products to DB, generate alerts, and mark job complete.
    """
    try:
        # Upsert products and variants
        products_count = 0
        variants_count = 0

        for scraped in products:
            product = await _upsert_product(session, job.brand_id, scraped)
            if product:
                products_count += 1
                variants_count += await _upsert_variants(session, product.id, scraped.variants)

        # Update job
        job.products_found = products_count
        job.variants_found = variants_count
        job.completed_at = datetime.now(timezone.utc)

        # Set status based on health check
        if health.has_critical:
            job.status = "failed"
            job.error_message = "; ".join(
                i["details"] for i in health.issues if i["severity"] == "critical"
            )
        elif health.has_issues:
            job.status = "warning"
            job.error_message = "; ".join(i["details"] for i in health.issues)
        else:
            job.status = "completed"

        await session.commit()

        # Generate stock alerts for this brand
        await generate_stock_alerts(session, job.brand_id)

        # Create health alerts if any
        if health.has_issues:
            await create_health_alerts(session, job.id, health)

        logger.info(
            f"Scrape job {job.id} completed: {products_count} products, "
            f"{variants_count} variants, status={job.status}"
        )

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()
        logger.error(f"Scrape job {job.id} failed: {e}")
        raise


async def fail_scrape_job(session: AsyncSession, job: ScrapeJob, error: str):
    """Mark a scrape job as failed."""
    job.status = "failed"
    job.error_message = error
    job.completed_at = datetime.now(timezone.utc)
    await session.commit()


async def _upsert_product(
    session: AsyncSession,
    brand_id: int,
    scraped: ScrapedProduct,
) -> Optional[Product]:
    """Insert or update a product by URL."""
    try:
        result = await session.execute(
            select(Product).where(Product.url == scraped.url)
        )
        product = result.scalar_one_or_none()

        if product:
            # Update existing
            product.name = scraped.name
            product.price = scraped.price
            product.currency = scraped.currency
            product.image_url = scraped.image_url
            product.category = scraped.category
            product.description = scraped.description
            product.last_scraped = datetime.now(timezone.utc)
        else:
            # Insert new
            product = Product(
                brand_id=brand_id,
                name=scraped.name,
                url=scraped.url,
                price=scraped.price,
                currency=scraped.currency,
                image_url=scraped.image_url,
                category=scraped.category,
                description=scraped.description,
                last_scraped=datetime.now(timezone.utc),
            )
            session.add(product)

        await session.flush()
        return product

    except Exception as e:
        logger.error(f"Error upserting product '{scraped.name}': {e}")
        return None


async def _upsert_variants(
    session: AsyncSession,
    product_id: int,
    scraped_variants: list,
) -> int:
    """Replace all variants for a product with freshly scraped data."""
    # Delete existing variants for this product
    result = await session.execute(
        select(Variant).where(Variant.product_id == product_id)
    )
    existing = result.scalars().all()
    for v in existing:
        await session.delete(v)

    # Insert new variants
    count = 0
    for sv in scraped_variants:
        variant = Variant(
            product_id=product_id,
            size=sv.size,
            color=sv.color,
            color_hex=sv.color_hex,
            in_stock=sv.in_stock,
            quantity=sv.quantity,
            sku=sv.sku,
        )
        session.add(variant)
        count += 1

    await session.flush()
    return count


async def get_last_scrape_job(session: AsyncSession, brand_id: int) -> Optional[ScrapeJob]:
    """Get the most recent completed scrape job for a brand."""
    result = await session.execute(
        select(ScrapeJob)
        .where(
            and_(
                ScrapeJob.brand_id == brand_id,
                ScrapeJob.status.in_(["completed", "warning"]),
            )
        )
        .order_by(ScrapeJob.completed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
