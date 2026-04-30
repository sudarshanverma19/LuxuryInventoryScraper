"""
Retry utilities with exponential backoff for transient failures.
"""

import asyncio
import logging
import functools
from typing import TypeVar, Callable, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, last_error: Exception, attempts: int):
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(f"Failed after {attempts} attempts: {last_error}")


async def async_retry(
    func: Callable,
    *args,
    max_retries: int = 2,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (Exception,),
    description: str = "operation",
    **kwargs,
) -> Any:
    """
    Execute an async function with retry logic and exponential backoff.

    Args:
        func: Async function to execute
        max_retries: Maximum number of retry attempts (total attempts = max_retries + 1)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        retryable_exceptions: Tuple of exception types that trigger a retry
        description: Human-readable description for logging
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as e:
            last_error = e

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    f"[ShopifySync] {description} failed (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e} — retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"[ShopifySync] {description} failed after {max_retries + 1} attempts: "
                    f"{type(e).__name__}: {e}"
                )

    raise RetryExhausted(last_error, max_retries + 1)
