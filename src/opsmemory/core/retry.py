"""Async retry helper for independently retryable pipeline stages."""

import asyncio
from collections.abc import Awaitable, Callable

from opsmemory.core.logging import get_logger

logger = get_logger(__name__)


async def retry_async[T](
    fn: Callable[[], Awaitable[T]],
    *,
    label: str,
    attempts: int = 3,
    base_delay: float = 0.5,
) -> T:
    """Run an async operation with exponential backoff.

    Args:
        fn: Zero-argument coroutine factory for the operation.
        label: Stage name used in log lines.
        attempts: Total attempts before giving up.
        base_delay: Delay before the second attempt; doubles each retry.

    Returns:
        The operation's result.

    Raises:
        Exception: The last failure, if all attempts are exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                delay = base_delay * 2 ** (attempt - 1)
                logger.warning(
                    "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                    label,
                    attempt,
                    attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
    assert last_error is not None
    logger.error("%s failed after %d attempts: %s", label, attempts, last_error)
    raise last_error
