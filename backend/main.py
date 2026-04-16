"""
InventoryScraper — FastAPI Application
Main entry point with all API endpoints and static file serving.
"""

import sys
import asyncio

# Fix for Windows: Playwright requires ProactorEventLoop to spawn subprocesses.
# The default SelectorEventLoop on Windows does not support this.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Depends, Query, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import HOST, PORT, BRANDS
from database.db import init_db, shutdown_db, get_session
from database.models import (
    Brand, Product, Variant, ScrapeJob, StockAlert, ScraperHealthAlert
)
from services.scrape_service import create_scrape_job, complete_scrape_job, fail_scrape_job
from services.alert_service import (
    get_active_stock_alerts, get_health_alerts,
    get_alert_threshold, set_alert_threshold,
)
from services.export_service import export_products

# ── Logging Setup ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("inventory_scraper")

# ── App Setup ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="InventoryScraper",
    description="Luxury brand inventory scraper dashboard",
    version="1.0.0",
)

# Track running scrape tasks
_running_jobs: dict[str, int] = {}  # brand_slug -> job_id


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("Database initialized and brands seeded")


@app.on_event("shutdown")
async def shutdown():
    await shutdown_db()


# ── Scraper Registry ───────────────────────────────────────────────────────

def _get_scraper(brand_slug: str):
    """Get the scraper instance for a brand."""
    from scrapers.on_scraper import OnScraper
    from scrapers.hoka_scraper import HokaScraper
    from scrapers.acne_scraper import AcneScraper
    from scrapers.margiela_scraper import MargielaScraper
    from scrapers.hourglass_scraper import HourglassScraper
    from scrapers.drunk_elephant_scraper import DrunkElephantScraper
    from scrapers.tcg_republic_scraper import TCGRepublicScraper
    from scrapers.magikart_scraper import MagikartScraper
    from scrapers.boredgame_scraper import BoredGameScraper
    from scrapers.hypefly_scraper import HypeFlyScraper
    from scrapers.hypeelixir_scraper import HypeElixirScraper
    from scrapers.crepdogcrew_scraper import CrepDogCrewScraper
    from scrapers.hustleculture_scraper import HustleCultureScraper

    scrapers = {
        "on-running": OnScraper,
        # "hoka": HokaScraper,  # Disabled — Akamai blocks automation
        "acne-studios": AcneScraper,
        "maison-margiela": MargielaScraper,
        "hourglass": HourglassScraper,
        "drunk-elephant": DrunkElephantScraper,
        "tcg-republic": TCGRepublicScraper,
        "magikart": MagikartScraper,
        "bored-game-company": BoredGameScraper,
        "hypefly": HypeFlyScraper,
        "hype-elixir": HypeElixirScraper,
        "crepdog-crew": CrepDogCrewScraper,
        "hustle-culture": HustleCultureScraper,
    }

    scraper_class = scrapers.get(brand_slug)
    if not scraper_class:
        return None
    return scraper_class()


# ── Background Scrape Task ─────────────────────────────────────────────────

async def _run_scrape(brand_slug: str, job_id: int):
    """Background task to run a scrape job."""
    from database.db import async_session

    scraper = _get_scraper(brand_slug)
    if not scraper:
        return

    async with async_session() as session:
        try:
            job = await session.get(ScrapeJob, job_id)
            if not job:
                return

            # Run the scraper
            products, health = await scraper.scrape()

            # Save results
            await complete_scrape_job(session, job, products, health)

        except Exception as e:
            logger.error(f"Scrape task failed for {brand_slug}: {e}")
            job = await session.get(ScrapeJob, job_id)
            if job:
                await fail_scrape_job(session, job, str(e))
        finally:
            _running_jobs.pop(brand_slug, None)


# ══════════════════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

# ── Brands ─────────────────────────────────────────────────────────────────

@app.get("/api/brands")
async def list_brands(session: AsyncSession = Depends(get_session)):
    """List all configured brands with last scrape info."""
    result = await session.execute(
        select(Brand).order_by(Brand.name)
    )
    brands = result.scalars().all()

    response = []
    for brand in brands:
        # Get last scrape job
        job_result = await session.execute(
            select(ScrapeJob)
            .where(ScrapeJob.brand_id == brand.id)
            .order_by(ScrapeJob.started_at.desc())
            .limit(1)
        )
        last_job = job_result.scalar_one_or_none()

        # Get product count
        prod_count = await session.execute(
            select(func.count(Product.id)).where(Product.brand_id == brand.id)
        )
        product_count = prod_count.scalar() or 0

        # Get active alert count
        alert_count_result = await session.execute(
            select(func.count(StockAlert.id))
            .join(Variant, StockAlert.variant_id == Variant.id)
            .join(Product, Variant.product_id == Product.id)
            .where(and_(Product.brand_id == brand.id, StockAlert.is_active == True))
        )
        alert_count = alert_count_result.scalar() or 0

        response.append({
            "id": brand.id,
            "name": brand.name,
            "slug": brand.slug,
            "base_url": brand.base_url,
            "logo_url": brand.logo_url,
            "category": brand.category,
            "product_count": product_count,
            "alert_count": alert_count,
            "is_scraping": brand.slug in _running_jobs,
            "last_scrape": {
                "id": last_job.id,
                "status": last_job.status,
                "products_found": last_job.products_found,
                "started_at": last_job.started_at.isoformat() if last_job.started_at else None,
                "completed_at": last_job.completed_at.isoformat() if last_job.completed_at else None,
            } if last_job else None,
        })

    return response


# ── Scraping ───────────────────────────────────────────────────────────────

@app.post("/api/scrape/all")
async def start_scrape_all(
    session: AsyncSession = Depends(get_session),
):
    """Start scraping all brands in parallel."""
    result = await session.execute(select(Brand))
    brands = result.scalars().all()

    started = []
    skipped = []

    for brand in brands:
        if brand.slug in _running_jobs:
            skipped.append(brand.slug)
            continue

        scraper = _get_scraper(brand.slug)
        if not scraper:
            skipped.append(brand.slug)
            continue

        job = await create_scrape_job(session, brand.id)
        _running_jobs[brand.slug] = job.id
        # Fire-and-forget async task — runs in parallel
        asyncio.create_task(_run_scrape(brand.slug, job.id))
        started.append(brand.slug)

    return {"started": started, "skipped": skipped}


@app.post("/api/scrape/{brand_slug}")
async def start_scrape(
    brand_slug: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Start scraping a specific brand."""
    # Check if already running
    if brand_slug in _running_jobs:
        raise HTTPException(400, f"Scrape already running for {brand_slug}")

    # Validate brand
    result = await session.execute(
        select(Brand).where(Brand.slug == brand_slug)
    )
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(404, f"Brand '{brand_slug}' not found")

    # Validate scraper exists
    scraper = _get_scraper(brand_slug)
    if not scraper:
        raise HTTPException(501, f"Scraper not yet implemented for '{brand_slug}'")

    # Create job
    job = await create_scrape_job(session, brand.id)
    _running_jobs[brand_slug] = job.id

    # Run in background
    background_tasks.add_task(_run_scrape, brand_slug, job.id)

    return {
        "message": f"Scrape started for {brand.name}",
        "job_id": job.id,
        "brand_slug": brand_slug,
    }


@app.get("/api/scrape/status/{job_id}")
async def scrape_status(job_id: int, session: AsyncSession = Depends(get_session)):
    """Check scrape job status."""
    job = await session.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    brand = await session.get(Brand, job.brand_id)

    return {
        "id": job.id,
        "brand": brand.name if brand else "Unknown",
        "status": job.status,
        "products_found": job.products_found,
        "variants_found": job.variants_found,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.get("/api/scrape/history")
async def scrape_history(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Get scrape job history."""
    result = await session.execute(
        select(ScrapeJob, Brand)
        .join(Brand, ScrapeJob.brand_id == Brand.id)
        .order_by(ScrapeJob.started_at.desc())
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "id": job.id,
            "brand_name": brand.name,
            "brand_slug": brand.slug,
            "status": job.status,
            "products_found": job.products_found,
            "variants_found": job.variants_found,
            "error_message": job.error_message,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
        for job, brand in rows
    ]


# ── Products ───────────────────────────────────────────────────────────────

@app.get("/api/products")
async def list_products(
    brand: Optional[str] = Query(None, description="Filter by brand slug"),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    in_stock: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """List products with filtering and pagination."""
    query = (
        select(Product, Brand)
        .join(Brand, Product.brand_id == Brand.id)
    )

    if brand:
        query = query.where(Brand.slug == brand)
    if category:
        query = query.where(Product.category == category)
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Brand.name, Product.name)
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await session.execute(query)
    rows = result.all()

    products = []
    for product, brand_obj in rows:
        # Get variants
        var_result = await session.execute(
            select(Variant).where(Variant.product_id == product.id)
        )
        variants = var_result.scalars().all()

        # Check stock filter
        if in_stock is not None:
            has_stock = any(v.in_stock for v in variants)
            if in_stock != has_stock:
                continue

        # Collect colors and sizes
        colors = list(set(v.color for v in variants if v.color))
        sizes = list(set(v.size for v in variants if v.size))
        all_in_stock = any(v.in_stock for v in variants)

        products.append({
            "id": product.id,
            "name": product.name,
            "url": product.url,
            "image_url": product.image_url,
            "price": product.price,
            "currency": product.currency,
            "category": product.category,
            "description": product.description,
            "last_scraped": product.last_scraped.isoformat() if product.last_scraped else None,
            "brand": {
                "name": brand_obj.name,
                "slug": brand_obj.slug,
            },
            "colors": colors,
            "sizes": sizes,
            "in_stock": all_in_stock,
            "variant_count": len(variants),
            "variants": [
                {
                    "id": v.id,
                    "size": v.size,
                    "color": v.color,
                    "color_hex": v.color_hex,
                    "in_stock": v.in_stock,
                    "quantity": v.quantity,
                    "sku": v.sku,
                }
                for v in variants
            ],
        })

    return {
        "products": products,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@app.get("/api/products/{product_id}")
async def get_product(product_id: int, session: AsyncSession = Depends(get_session)):
    """Get a single product with all variants."""
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    brand = await session.get(Brand, product.brand_id)

    var_result = await session.execute(
        select(Variant).where(Variant.product_id == product.id)
    )
    variants = var_result.scalars().all()

    return {
        "id": product.id,
        "name": product.name,
        "url": product.url,
        "image_url": product.image_url,
        "price": product.price,
        "currency": product.currency,
        "category": product.category,
        "description": product.description,
        "last_scraped": product.last_scraped.isoformat() if product.last_scraped else None,
        "brand": {
            "name": brand.name,
            "slug": brand.slug,
        },
        "variants": [
            {
                "id": v.id,
                "size": v.size,
                "color": v.color,
                "color_hex": v.color_hex,
                "in_stock": v.in_stock,
                "quantity": v.quantity,
                "sku": v.sku,
            }
            for v in variants
        ],
    }


# ── Alerts ─────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
async def list_alerts(
    brand: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get all active stock alerts."""
    return await get_active_stock_alerts(session, brand, alert_type)


class AlertSettingsRequest(BaseModel):
    threshold: int


@app.get("/api/alerts/settings")
async def get_alert_settings(session: AsyncSession = Depends(get_session)):
    """Get current alert threshold."""
    threshold = await get_alert_threshold(session)
    return {"low_stock_threshold": threshold}


@app.put("/api/alerts/settings")
async def update_alert_settings(
    req: AlertSettingsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update alert threshold."""
    await set_alert_threshold(session, req.threshold)
    return {"low_stock_threshold": req.threshold}


@app.get("/api/health-alerts")
async def list_health_alerts(
    resolved: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    """Get scraper health alerts."""
    return await get_health_alerts(session, resolved)


# ── Export ──────────────────────────────────────────────────────────────────

@app.get("/api/export")
async def export_data(
    format: str = Query("csv", regex="^(csv|xlsx)$"),
    brand: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Export product data as CSV or Excel."""
    file_bytes, filename, content_type = await export_products(session, format, brand)

    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Stats ──────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def dashboard_stats(session: AsyncSession = Depends(get_session)):
    """Dashboard summary stats."""
    # Total products
    total_products = (await session.execute(
        select(func.count(Product.id))
    )).scalar() or 0

    # Total brands with products
    active_brands = (await session.execute(
        select(func.count(func.distinct(Product.brand_id)))
    )).scalar() or 0

    # Items in stock (products with at least one variant in stock)
    in_stock_products = (await session.execute(
        select(func.count(func.distinct(Variant.product_id)))
        .where(Variant.in_stock == True)
    )).scalar() or 0

    # Active stock alerts
    active_alerts = (await session.execute(
        select(func.count(StockAlert.id)).where(StockAlert.is_active == True)
    )).scalar() or 0

    # Active health alerts
    active_health_alerts = (await session.execute(
        select(func.count(ScraperHealthAlert.id))
        .where(ScraperHealthAlert.is_resolved == False)
    )).scalar() or 0

    # Last scrape time
    last_scrape = (await session.execute(
        select(ScrapeJob.completed_at)
        .where(ScrapeJob.status.in_(["completed", "warning"]))
        .order_by(ScrapeJob.completed_at.desc())
        .limit(1)
    )).scalar()

    return {
        "total_products": total_products,
        "active_brands": active_brands,
        "in_stock_products": in_stock_products,
        "active_alerts": active_alerts,
        "active_health_alerts": active_health_alerts,
        "last_scrape": last_scrape.isoformat() if last_scrape else None,
    }


# ── Static Files (Frontend) ───────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard page."""
    return FileResponse(FRONTEND_DIR / "index.html")


# Mount static files for CSS and JS
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


# ── Run ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False, loop="asyncio")
