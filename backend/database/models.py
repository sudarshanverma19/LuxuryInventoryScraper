"""
SQLAlchemy ORM models for the InventoryScraper database.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    base_url = Column(String(500), nullable=False)
    logo_url = Column(String(500), nullable=True)
    category = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    products = relationship("Product", back_populates="brand", cascade="all, delete-orphan")
    scrape_jobs = relationship("ScrapeJob", back_populates="brand", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Brand(name='{self.name}', slug='{self.slug}')>"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    url = Column(Text, nullable=False, unique=True)
    image_url = Column(Text, nullable=True)
    price = Column(Float, nullable=True)
    currency = Column(String(10), default="USD")
    category = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    last_scraped = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Shopify sync tracking
    shopify_sync_status = Column(String(20), default="pending", index=True)
    # Values: pending | processing | completed | failed
    shopify_product_id = Column(String(100), nullable=True)
    # Stores Shopify GID like "gid://shopify/Product/123456"
    shopify_synced_at = Column(DateTime, nullable=True)

    # Relationships
    brand = relationship("Brand", back_populates="products")
    variants = relationship("Variant", back_populates="product", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Product(name='{self.name}', brand_id={self.brand_id})>"


class Variant(Base):
    __tablename__ = "variants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    size = Column(Text, nullable=True)
    color = Column(Text, nullable=True)
    color_hex = Column(String(7), nullable=True)  # e.g., "#FF5733"
    in_stock = Column(Boolean, default=True)
    quantity = Column(Integer, nullable=True)  # Only if site exposes it
    sku = Column(Text, nullable=True)

    # Relationships
    product = relationship("Product", back_populates="variants")
    stock_alerts = relationship("StockAlert", back_populates="variant", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Variant(product_id={self.product_id}, size='{self.size}', color='{self.color}')>"


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending, running, completed, warning, failed
    products_found = Column(Integer, default=0)
    variants_found = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    brand = relationship("Brand", back_populates="scrape_jobs")
    health_alerts = relationship("ScraperHealthAlert", back_populates="scrape_job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ScrapeJob(brand_id={self.brand_id}, status='{self.status}')>"


class StockAlert(Base):
    __tablename__ = "stock_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(Integer, ForeignKey("variants.id"), nullable=False, index=True)
    alert_type = Column(String(20), nullable=False)  # low_stock, out_of_stock
    quantity = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    variant = relationship("Variant", back_populates="stock_alerts")

    def __repr__(self):
        return f"<StockAlert(variant_id={self.variant_id}, type='{self.alert_type}')>"


class ScraperHealthAlert(Base):
    __tablename__ = "scraper_health_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scrape_job_id = Column(Integer, ForeignKey("scrape_jobs.id"), nullable=False, index=True)
    check_type = Column(String(30), nullable=False)  # selector, count_anomaly, data_completeness, response
    details = Column(Text, nullable=False)  # What failed and expected vs actual
    severity = Column(String(10), nullable=False, default="warning")  # warning, critical
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    scrape_job = relationship("ScrapeJob", back_populates="health_alerts")

    def __repr__(self):
        return f"<ScraperHealthAlert(job_id={self.scrape_job_id}, type='{self.check_type}')>"


class AppSettings(Base):
    """Key-value store for app-wide settings like alert thresholds."""
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class ShopifySyncJob(Base):
    """Tracks a batch Shopify sync run."""
    __tablename__ = "shopify_sync_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), default="running")  # running, completed, failed
    total_products = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    error_summary = Column(Text, nullable=True)
    brand_filter = Column(String(100), nullable=True)  # null = all brands
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    logs = relationship("ShopifySyncLog", back_populates="sync_job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ShopifySyncJob(id={self.id}, status='{self.status}')>"


class ShopifySyncLog(Base):
    """Per-product sync log entry."""
    __tablename__ = "shopify_sync_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_job_id = Column(Integer, ForeignKey("shopify_sync_jobs.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False)  # completed, failed
    shopify_product_id = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    image_count = Column(Integer, default=0)
    images_uploaded = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    sync_job = relationship("ShopifySyncJob", back_populates="logs")
    product = relationship("Product")

    def __repr__(self):
        return f"<ShopifySyncLog(product_id={self.product_id}, status='{self.status}')>"
