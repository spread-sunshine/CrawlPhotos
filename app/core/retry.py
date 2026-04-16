# -*- coding: utf-8 -*-
"""
Exponential backoff retry handler with jitter.
指数退避重试器.

Usage:
    retryer = RetryHandler(max_retries=3, base_delay=1.0)
    result = await retryer.execute(async_func, arg1, arg2=arg2_val)
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetryResult:
    """Result of a retried operation."""

    success: bool
    result: Any = None
    error: Optional[Exception] = None
    attempts: int = 0
    total_delay_seconds: float = 0.0


class RetryHandler:
    """
    Exponential backoff retry handler with configurable params.

    Features:
    - Configurable max retries (default: 3)
    - Exponential backoff: delay * 2^attempt
    - Jitter: random +/-25% to avoid thundering herd
    - Retryable exception filtering
    - Per-attempt timeout support
    """

    DEFAULT_MAX_RETRIES: int = 3
    DEFAULT_BASE_DELAY_SECONDS: float = 1.0
    DEFAULT_MAX_DELAY_SECONDS: float = 30.0
    DEFAULT_JITTER_FACTOR: float = 0.25

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
        max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
        jitter_factor: float = DEFAULT_JITTER_FACTOR,
        retryable_exceptions: tuple = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
        self.retryable_exceptions = retryable_exceptions

    async def execute(
        self,
        func: Callable[..., Coroutine],
        *args: Any,
        **kwargs: Any,
    ) -> RetryResult:
        """
        Execute an async function with retry logic.

        Args:
            func: Async callable to execute.
            *args: Positional arguments passed to func.
            **kwargs: Keyword arguments passed to func.

        Returns:
            RetryResult with outcome details.
        """
        last_error: Optional[Exception] = None
        total_delay = 0.0

        for attempt in range(self.max_retries + 1):
            try:
                start = time.time()
                result = await func(*args, **kwargs)
                elapsed = time.time() - start

                if attempt > 0:
                    logger.info(
                        "Retry succeeded on attempt %d/%d "
                        "(%.1fs elapsed)",
                        attempt + 1,
                        self.max_retries + 1,
                        elapsed,
                    )

                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempt + 1,
                    total_delay_seconds=total_delay,
                )

            except Exception as exc:
                last_error = exc

                # Check if this exception type is retryable
                if not isinstance(exc, self.retryable_exceptions):
                    return RetryResult(
                        success=False,
                        error=exc,
                        attempts=attempt + 1,
                        total_delay_seconds=total_delay,
                    )

                # Last attempt - no more retries
                if attempt == self.max_retries:
                    logger.error(
                        "All %d retries failed. Last error: %s",
                        self.max_retries + 1,
                        exc,
                    )
                    return RetryResult(
                        success=False,
                        error=exc,
                        attempts=attempt + 1,
                        total_delay_seconds=total_delay,
                    )

                # Calculate delay
                delay = self._calculate_delay(attempt)
                total_delay += delay

                logger.warning(
                    "Attempt %d/%d failed: %s. "
                    "Retrying in %.1fs...",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        return RetryResult(
            success=False,
            error=last_error,
            attempts=self.max_retries + 1,
            total_delay_seconds=total_delay,
        )

    def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Formula: min(base_delay * 2^attempt, max_delay)
                 then apply jitter: delay * (1 +/- factor).
        """
        exp_delay = self.base_delay * (2 ** attempt)
        capped = min(exp_delay, self.max_delay)
        # Apply random jitter
        jitter_range = capped * self.jitter_factor
        delay = capped + random.uniform(
            -jitter_range, jitter_range,
        )
        return max(0.1, delay)


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    **handler_kwargs: Any,
):
    """
    Decorator factory that wraps async functions with retry logic.

    Usage:
        @with_retry(max_retries=3)
        async def fetch_data(url):
            ...
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            handler = RetryHandler(
                max_retries=max_retries,
                base_delay=base_delay,
                **handler_kwargs,
            )
            result = await handler.execute(func, *args, **kwargs)
            if result.success:
                return result.result
            raise result.error

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = getattr(func, "__doc__", "")
        return wrapper

    return decorator
