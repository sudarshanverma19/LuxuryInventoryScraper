"""
Anti-detection utilities for web scraping.
Implements user-agent rotation, random delays, browser fingerprint spoofing,
request interception, and human-like behavior simulation.
"""

import random
import math
import asyncio
from typing import Optional
from fake_useragent import UserAgent
from playwright.async_api import Page, BrowserContext

# ── User-Agent Rotation ───────────────────────────────────────────────────

# Initialize with fallback
try:
    _ua = UserAgent(browsers=["Chrome", "Firefox", "Edge"], os=["Windows", "Mac OS X"])
except Exception:
    _ua = None

# Fallback pool of real, modern user agents
_FALLBACK_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
]


def get_random_user_agent() -> str:
    """Get a random, realistic user agent string."""
    if _ua:
        try:
            return _ua.random
        except Exception:
            pass
    return random.choice(_FALLBACK_UAS)


# ── Random Delays (Gaussian Distribution) ─────────────────────────────────

async def random_delay(min_sec: float = 2.0, max_sec: float = 6.0):
    """
    Sleep for a random duration using gaussian distribution.
    More human-like than uniform random — clusters around the mean.
    """
    mean = (min_sec + max_sec) / 2
    std_dev = (max_sec - min_sec) / 4  # ~95% of values within min-max
    delay = max(min_sec, min(max_sec, random.gauss(mean, std_dev)))
    await asyncio.sleep(delay)


async def short_delay():
    """Short pause for between micro-actions (0.3-1.2 seconds)."""
    await asyncio.sleep(random.uniform(0.3, 1.2))


# ── Random Viewport ───────────────────────────────────────────────────────

_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
    {"width": 1600, "height": 900},
    {"width": 2560, "height": 1440},
    {"width": 1680, "height": 1050},
]


def get_random_viewport() -> dict:
    """Get a random realistic viewport size."""
    return random.choice(_VIEWPORTS)


# ── Browser Fingerprint Spoofing ──────────────────────────────────────────

_LANGUAGES = [
    ["en-US", "en"],
    ["en-US", "en", "es"],
    ["en-GB", "en"],
    ["en-US", "en", "fr"],
    ["en-US", "en", "de"],
]

_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
]


def get_random_fingerprint() -> dict:
    """Get random browser fingerprint settings."""
    return {
        "locale": random.choice(["en-US", "en-GB"]),
        "timezone_id": random.choice(_TIMEZONES),
        "languages": random.choice(_LANGUAGES),
    }


# ── Human-like Behavior Simulation ───────────────────────────────────────

async def human_scroll(page: Page, scroll_count: int = 3):
    """Simulate human-like scrolling with random pauses."""
    for _ in range(scroll_count):
        # Random scroll distance
        distance = random.randint(200, 600)
        await page.mouse.wheel(0, distance)
        await asyncio.sleep(random.uniform(0.5, 2.0))


async def human_mouse_move(page: Page):
    """Move mouse to a random position to simulate human presence."""
    viewport = page.viewport_size
    if viewport:
        x = random.randint(100, viewport["width"] - 100)
        y = random.randint(100, viewport["height"] - 100)
        # Move in small steps
        steps = random.randint(3, 8)
        await page.mouse.move(x, y, steps=steps)


async def smooth_scroll_to_bottom(page: Page, pause_every: int = 3):
    """Scroll to the bottom of the page like a human browsing."""
    previous_height = 0
    scroll_count = 0

    while True:
        # Get current page height
        current_height = await page.evaluate("document.body.scrollHeight")

        if current_height == previous_height:
            break  # Reached the bottom

        # Scroll down by a random amount
        scroll_amount = random.randint(300, 700)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        scroll_count += 1

        # Pause occasionally to "read" the page
        if scroll_count % pause_every == 0:
            await asyncio.sleep(random.uniform(1.0, 3.0))
            await human_mouse_move(page)
        else:
            await asyncio.sleep(random.uniform(0.3, 0.8))

        previous_height = current_height

        # Safety limit
        if scroll_count > 100:
            break


# ── Request Interception (Block Tracking Scripts) ─────────────────────────

# Patterns to block — analytics/tracking that could flag the session
_BLOCKED_PATTERNS = [
    "*google-analytics.com*",
    "*googletagmanager.com*",
    "*facebook.net*",
    "*facebook.com/tr*",
    "*doubleclick.net*",
    "*hotjar.com*",
    "*segment.io*",
    "*segment.com*",
    "*mixpanel.com*",
    "*amplitude.com*",
    "*fullstory.com*",
    "*optimizely.com*",
    "*newrelic.com*",
    "*nr-data.net*",
    "*sentry.io*",
    "*datadoghq.com*",
]


async def setup_request_interception(page: Page):
    """Block tracking/analytics requests to avoid detection."""
    async def handle_route(route):
        await route.abort()

    for pattern in _BLOCKED_PATTERNS:
        await page.route(pattern, handle_route)


# ── Chrome Launch Arguments ───────────────────────────────────────────────

def get_stealth_launch_args() -> list[str]:
    """Get Chrome launch arguments that reduce detectability."""
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--no-first-run",
        "--no-zygote",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--window-position=0,0",
        "--ignore-certifcate-errors",
        "--ignore-certifcate-errors-spki-list",
    ]
