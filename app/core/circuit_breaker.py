# -*- coding: utf-8 -*-
"""
Circuit Breaker + Rate Limiter + Fallback (Three-tier Protection).
熔断器+限流+降级 - 三级防护体系保护外部API调用.

Architecture:

  Level 1: RateLimiter (Token Bucket)
      Controls request rate to avoid overwhelming downstream APIs.
      Prevents QPS violations and throttling errors.

  Level 2: CircuitBreaker (State Machine: CLOSED/OPEN/HALF_OPEN)
      Detects sustained failures and stops calling failing services.
      Allows recovery without flooding the broken service.

  Level 3: Fallback / Degradation Handler
      When circuit opens or rate limit triggers, gracefully degrade:
      - Return cached/stale results
      - Switch to alternative provider
      - Return safe defaults
      - Skip operation entirely
"""

import asyncio
import functools
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

from app.config.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# ==================== Rate Limiter ====================


class RateLimiter:
    """
    Token bucket rate limiter.

    Controls how many requests can pass through per second.
    Supports both synchronous and async contexts.
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: int = 20,
    ):
        self._rps = requests_per_second
        self._burst = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def tokens_available(self) -> float:
        return self._tokens

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._burst,
            self._tokens + elapsed * self._rps,
        )
        self._last_refill = now

    def acquire(self) -> bool:
        """Try to acquire one token synchronously."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    async def acquire_async(self) -> bool:
        """Acquire one token asynchronously (with lock)."""
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    async def wait_for_token(self, timeout: float = 10.0) -> bool:
        """Wait until a token becomes available."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.acquire_async():
                return True
            await asyncio.sleep(min(0.05, timeout * 0.01))
        return False

    def stats(self) -> Dict[str, Any]:
        return {
            "rps": self._rps,
            "burst": self._burst,
            "tokens": round(self._tokens, 2),
        }


# ==================== Circuit Breaker ====================


class CircuitState(Enum):
    CLOSED = "closed"       # Normal: requests flow through
    OPEN = "open"           # Blocking: service considered down
    HALF_OPEN = "half_open"  # Testing: allow one probe request


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5       # Failures to trip OPEN
    success_threshold: int = 3       # Successes to close from HALF_OPEN
    reset_timeout_seconds: float = 30.0  # How long OPEN lasts
    half_open_max_probes: int = 1    # Probes allowed in HALF_OPEN


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation.

    State transitions:
        CLOSED --(failures >= threshold)--> OPEN
        OPEN --(timeout elapsed)--> HALF_OPEN
        HALF_OPEN --(success >= threshold)--> CLOSED
        HALF_OPEN --(any failure)--> OPEN
    """

    def __init__(
        self,
        name: str = "",
        config: Optional[CircuitBreakerConfig] = None,
    ):
        self._name = name or "default"
        self._cfg = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._probe_count = 0
        # History window for diagnostics
        self._history: deque = deque(maxlen=100)

    @property
    def state(self) -> CircuitState:
        """Check and potentially transition state based on time."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._cfg.reset_timeout_seconds:
                self._transition(CircuitState.HALF_OPEN)
                logger.info(
                    "Circuit '%s' OPEN->HALF_OPEN "
                    "(%.1fs passed)",
                    self._name, elapsed,
                )
        return self._state

    def can_execute(self) -> bool:
        """Check if a request should be allowed through."""
        current_state = self.state
        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.OPEN:
            return False
        else:  # HALF_OPEN
            if self._probe_count < self._cfg.half_open_max_probes:
                self._probe_count += 1
                return True
            return False

    def record_success(self) -> None:
        """Record a successful execution."""
        self._history.append(True)
        self._success_count += 1

        if self._state == CircuitState.HALF_OPEN:
            if self._success_count >= self._cfg.success_threshold:
                self._transition(CircuitState.CLOSED)
                logger.info(
                    "Circuit '%s' HALF_OPEN->CLOSED",
                    self._name,
                )
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success streak
            if self._success_count >= 3:
                self._failure_count = max(
                    0, self._failure_count - 1,
                )

    def record_failure(self, exc: Optional[Exception] = None) -> None:
        """Record a failed execution."""
        self._history.append(False)
        self._failure_count += 1
        self._success_count = 0
        self._last_failure_time = time.monotonic()
        self._probe_count = 0

        err_info = str(exc)[:100] if exc else ""

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
            logger.warning(
                "Circuit '%s' HALF_OPEN->OPEN (probe failed: %s)",
                self._name, err_info,
            )
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._cfg.failure_threshold:
                self._transition(CircuitState.OPEN)
                logger.warning(
                    "Circuit '%s' CLOSED->OPEN "
                    "(%d failures): %s",
                    self._name,
                    self._failure_count,
                    err_info,
                )

    def _transition(self, new_state: CircuitState) -> None:
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0

    def stats(self) -> Dict[str, Any]:
        total = len(self._history)
        failures = sum(1 for h in self._history if not h)
        return {
            "name": self._name,
            "state": self._state.value,
            "failures": self._failure_count,
            "successes": self._success_count,
            "history_total": total,
            "history_failure_rate": (
                failures / total if total > 0 else 0
            ),
        }


# ==================== Combined API Guard ====================


@dataclass
class ApiGuardConfig:
    """Combined configuration for API guard."""
    rate_limit_rps: float = 10.0
    rate_limit_burst: int = 20
    cb_failure_threshold: int = 5
    cb_reset_timeout: float = 30.0


class ApiGuard:
    """
    Three-tier protection guard combining RateLimiter +
    CircuitBreaker.

    Usage:
        guard = ApiGuard("face_api", config)
        result = await guard.call(recognizer.recognize, image_path)
    """

    def __init__(
        self,
        name: str = "default",
        config: Optional[ApiGuardConfig] = None,
    ):
        self._name = name
        self._config = config or ApiGuardConfig()

        self._limiter = RateLimiter(
            requests_per_second=self._config.rate_limit_rps,
            burst_size=self._config.rate_limit_burst,
        )
        self._breaker = CircuitBreaker(
            name=name,
            config=CircuitBreakerConfig(
                failure_threshold=self._config.cb_failure_threshold,
                reset_timeout_seconds=self._config.cb_reset_timeout,
            ),
        )
        # Fallback registry: exception_type -> fallback_fn
        self._fallbacks: Dict[type, Callable] = {}

    def register_fallback(
        self,
        exc_type: type,
        fallback_fn: Callable[..., T],
    ) -> None:
        """Register a fallback for a specific exception type."""
        self._fallbacks[exc_type] = fallback_fn

    async def call(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute a function through the three-tier guard.

        1. Rate limiter check
        2. Circuit breaker check
        3. Execute with failure recording
        4. Fallback on exception
        """
        # Tier 1: Rate Limiting
        if not await self._limiter.wait_for_token(timeout=5.0):
            raise RateLimitExceededError(
                f"[{self._name}] Rate limit exceeded"
            )

        # Tier 2: Circuit Breaker
        if not self._breaker.can_execute():
            raise CircuitOpenError(
                f"[{self._name}] Circuit is open, blocking call"
            )

        # Execute
        try:
            result = await fn(*args, **kwargs)
            self._breaker.record_success()
            return result
        except Exception as exc:
            self._breaker.record_failure(exc)

            # Tier 3: Fallback / Degradation
            for exc_type, fallback_fn in self._fallbacks.items():
                if isinstance(exc, exc_type):
                    logger.info(
                        "[%s] Using fallback for %s",
                        self._name, exc.__class__.__name__,
                    )
                    try:
                        return await fallback_fn(
                            *args, **kwargs,
                        )
                    except Exception as fb_err:
                        logger.error(
                            "[%s] Fallback also failed: %s",
                            self._name, fb_err,
                        )
            raise

    def stats(self) -> Dict[str, Any]:
        return {
            "guard": self._name,
            "rate_limiter": self._limiter.stats(),
            "circuit_breaker": self._breaker.stats(),
        }


# ==================== Custom Exceptions ====================


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class CircuitOpenError(Exception):
    """Raised when circuit breaker blocks execution."""
    pass
