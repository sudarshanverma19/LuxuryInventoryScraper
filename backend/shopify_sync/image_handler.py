"""
Image download and optional compression for Shopify upload.

Downloads product images via streaming HTTP, handles redirects/timeouts,
and optionally compresses images before upload.
"""

import io
import os
import logging
import mimetypes
from typing import Optional
from urllib.parse import urlparse, unquote

import httpx

logger = logging.getLogger(__name__)

# Common image content types
IMAGE_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

# Max image size: 20MB (Shopify limit)
MAX_IMAGE_SIZE = 20 * 1024 * 1024


def _extract_filename(url: str, content_type: Optional[str] = None) -> str:
    """Extract a filename from a URL, falling back to content type for extension."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    basename = os.path.basename(path)

    if basename and "." in basename:
        # Truncate overly long filenames
        name, ext = os.path.splitext(basename)
        return f"{name[:80]}{ext}"

    # Fallback: generate from content type
    ext = ".jpg"
    if content_type:
        guessed = mimetypes.guess_extension(content_type)
        if guessed:
            ext = guessed

    return f"image{ext}"


def _guess_content_type(url: str) -> str:
    """Guess content type from URL extension."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    for ext, ct in IMAGE_CONTENT_TYPES.items():
        if path.endswith(ext):
            return ct
    return "image/jpeg"


async def download_image(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 30.0,
) -> tuple[bytes, str, str]:
    """
    Download an image from a URL.

    Args:
        url: Image URL to download
        client: Optional reusable httpx client
        timeout: Request timeout in seconds

    Returns:
        (image_bytes, content_type, filename)

    Raises:
        httpx.HTTPError: On download failure
        ValueError: If response is not an image or exceeds size limit
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "image/*,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }

    # Add referer from the same domain to handle protected images
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
        )

    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

        data = response.content
        if len(data) > MAX_IMAGE_SIZE:
            raise ValueError(
                f"Image exceeds 20MB limit: {len(data) / 1024 / 1024:.1f}MB"
            )

        if len(data) < 100:
            raise ValueError(f"Image too small ({len(data)} bytes), likely invalid")

        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if not content_type or "image" not in content_type:
            content_type = _guess_content_type(url)

        filename = _extract_filename(url, content_type)

        logger.debug(
            f"[ShopifySync] Downloaded image: {filename} "
            f"({len(data) / 1024:.0f}KB, {content_type})"
        )

        return data, content_type, filename

    finally:
        if own_client:
            await client.aclose()


def compress_image(
    data: bytes,
    content_type: str,
    max_dimension: int = 4096,
    quality: int = 85,
) -> tuple[bytes, str, str]:
    """
    Optionally compress/resize an image before upload.

    Args:
        data: Raw image bytes
        content_type: Original content type
        max_dimension: Max width/height in pixels
        quality: JPEG quality (1-100)

    Returns:
        (compressed_bytes, new_content_type, new_extension)
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))

        # Convert palette/RGBA images for JPEG output
        if img.mode in ("RGBA", "P", "LA"):
            # Keep as PNG if it has transparency
            if img.mode in ("RGBA", "LA", "P"):
                has_alpha = False
                if img.mode == "RGBA" or img.mode == "LA":
                    has_alpha = True
                elif img.mode == "P" and "transparency" in img.info:
                    has_alpha = True

                if has_alpha:
                    # Resize if needed, keep as PNG
                    if max(img.size) > max_dimension:
                        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
                    output = io.BytesIO()
                    img.save(output, format="PNG", optimize=True)
                    return output.getvalue(), "image/png", ".png"

            img = img.convert("RGB")

        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if exceeds max dimensions
        if max(img.size) > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        compressed = output.getvalue()

        # Only use compressed version if it's actually smaller
        if len(compressed) < len(data):
            logger.debug(
                f"[ShopifySync] Compressed image: {len(data) / 1024:.0f}KB → "
                f"{len(compressed) / 1024:.0f}KB"
            )
            return compressed, "image/jpeg", ".jpg"

        return data, content_type, os.path.splitext("file" + mimetypes.guess_extension(content_type) or ".jpg")[1]

    except ImportError:
        logger.warning("[ShopifySync] Pillow not installed, skipping image compression")
        return data, content_type, ".jpg"
    except Exception as e:
        logger.warning(f"[ShopifySync] Image compression failed, using original: {e}")
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        return data, content_type, ext
