"""
Database engine and async session management.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database.models import Base
from config import DATABASE_URL, BRANDS

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)

# Session factory
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables and seed brands if empty."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed brands from config
    await seed_brands()


async def seed_brands():
    """Insert configured brands if they don't exist yet."""
    from database.models import Brand
    from sqlalchemy import select

    async with async_session() as session:
        for brand_cfg in BRANDS:
            result = await session.execute(
                select(Brand).where(Brand.slug == brand_cfg["slug"])
            )
            existing = result.scalar_one_or_none()

            if not existing:
                brand = Brand(
                    name=brand_cfg["name"],
                    slug=brand_cfg["slug"],
                    base_url=brand_cfg["base_url"],
                    category=brand_cfg.get("category"),
                )
                session.add(brand)

        await session.commit()


async def get_session() -> AsyncSession:
    """Dependency for FastAPI endpoints."""
    async with async_session() as session:
        yield session


async def shutdown_db():
    """Dispose engine on app shutdown."""
    await engine.dispose()
