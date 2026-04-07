"""
Alert service — generates stock alerts after scraping
and manages scraper health alerts.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Product, Variant, StockAlert, ScraperHealthAlert, AppSettings
)
from scrapers.base_scraper import HealthCheckResult
from config import LOW_STOCK_THRESHOLD

logger = logging.getLogger(__name__)


async def get_alert_threshold(session: AsyncSession) -> int:
    """Get the current low stock alert threshold from DB or config default."""
    result = await session.execute(
        select(AppSettings).where(AppSettings.key == "low_stock_threshold")
    )
    setting = result.scalar_one_or_none()
    if setting:
        return int(setting.value)
    return LOW_STOCK_THRESHOLD


async def set_alert_threshold(session: AsyncSession, threshold: int):
    """Update the low stock threshold in DB."""
    result = await session.execute(
        select(AppSettings).where(AppSettings.key == "low_stock_threshold")
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = str(threshold)
        setting.updated_at = datetime.now(timezone.utc)
    else:
        setting = AppSettings(key="low_stock_threshold", value=str(threshold))
        session.add(setting)

    await session.commit()


async def generate_stock_alerts(session: AsyncSession, brand_id: int):
    """
    Generate stock alerts for all variants of a brand.
    - quantity < threshold → low_stock
    - quantity == 0 or in_stock == False → out_of_stock
    Resolves alerts for variants that have recovered.
    """
    threshold = await get_alert_threshold(session)

    # Get all variants for this brand's products
    result = await session.execute(
        select(Variant)
        .join(Product, Variant.product_id == Product.id)
        .where(Product.brand_id == brand_id)
    )
    variants = result.scalars().all()

    for variant in variants:
        # Determine alert type
        alert_type = None

        if not variant.in_stock or (variant.quantity is not None and variant.quantity == 0):
            alert_type = "out_of_stock"
        elif variant.quantity is not None and variant.quantity < threshold:
            alert_type = "low_stock"

        # Check for existing active alert
        existing_result = await session.execute(
            select(StockAlert).where(
                and_(
                    StockAlert.variant_id == variant.id,
                    StockAlert.is_active == True,
                )
            )
        )
        existing_alert = existing_result.scalar_one_or_none()

        if alert_type:
            if existing_alert:
                # Update existing alert
                existing_alert.alert_type = alert_type
                existing_alert.quantity = variant.quantity
            else:
                # Create new alert
                alert = StockAlert(
                    variant_id=variant.id,
                    alert_type=alert_type,
                    quantity=variant.quantity,
                    is_active=True,
                )
                session.add(alert)
        else:
            # Stock recovered — resolve existing alert
            if existing_alert:
                existing_alert.is_active = False
                existing_alert.resolved_at = datetime.now(timezone.utc)

    await session.commit()
    logger.info(f"Stock alerts generated for brand_id={brand_id}")


async def create_health_alerts(
    session: AsyncSession,
    scrape_job_id: int,
    health: HealthCheckResult,
):
    """Create health alerts from health check results."""
    for issue in health.issues:
        alert = ScraperHealthAlert(
            scrape_job_id=scrape_job_id,
            check_type=issue["check_type"],
            details=issue["details"],
            severity=issue["severity"],
        )
        session.add(alert)

    await session.commit()
    logger.info(f"Created {len(health.issues)} health alerts for job {scrape_job_id}")


async def get_active_stock_alerts(
    session: AsyncSession,
    brand_slug: Optional[str] = None,
    alert_type: Optional[str] = None,
):
    """Get all active stock alerts with product and brand info."""
    from database.models import Brand

    query = (
        select(StockAlert, Variant, Product, Brand)
        .join(Variant, StockAlert.variant_id == Variant.id)
        .join(Product, Variant.product_id == Product.id)
        .join(Brand, Product.brand_id == Brand.id)
        .where(StockAlert.is_active == True)
    )

    if brand_slug:
        query = query.where(Brand.slug == brand_slug)
    if alert_type:
        query = query.where(StockAlert.alert_type == alert_type)

    query = query.order_by(StockAlert.created_at.desc())

    result = await session.execute(query)
    rows = result.all()

    alerts = []
    for alert, variant, product, brand in rows:
        alerts.append({
            "id": alert.id,
            "alert_type": alert.alert_type,
            "quantity": alert.quantity,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "variant": {
                "id": variant.id,
                "size": variant.size,
                "color": variant.color,
                "in_stock": variant.in_stock,
            },
            "product": {
                "id": product.id,
                "name": product.name,
                "url": product.url,
                "image_url": product.image_url,
                "price": product.price,
            },
            "brand": {
                "name": brand.name,
                "slug": brand.slug,
            },
        })

    return alerts


async def get_health_alerts(session: AsyncSession, resolved: bool = False):
    """Get scraper health alerts."""
    from database.models import Brand, ScrapeJob

    query = (
        select(ScraperHealthAlert, ScrapeJob, Brand)
        .join(ScrapeJob, ScraperHealthAlert.scrape_job_id == ScrapeJob.id)
        .join(Brand, ScrapeJob.brand_id == Brand.id)
        .where(ScraperHealthAlert.is_resolved == resolved)
        .order_by(ScraperHealthAlert.created_at.desc())
    )

    result = await session.execute(query)
    rows = result.all()

    alerts = []
    for health_alert, job, brand in rows:
        alerts.append({
            "id": health_alert.id,
            "check_type": health_alert.check_type,
            "details": health_alert.details,
            "severity": health_alert.severity,
            "is_resolved": health_alert.is_resolved,
            "created_at": health_alert.created_at.isoformat() if health_alert.created_at else None,
            "brand": {
                "name": brand.name,
                "slug": brand.slug,
            },
            "scrape_job_id": job.id,
        })

    return alerts
