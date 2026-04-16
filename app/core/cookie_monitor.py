# -*- coding: utf-8 -*-
"""
QQ Cookie validity checker with expiry warning.
QQ Cookie有效期检测与到期预警模块.

Monitors QQ cookie file for expiration indicators:
- File modification time (stale cookies > 24h need refresh)
- Cookie content patterns indicating session expiry
- Proactive warning before cookies expire
"""

import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.config.logging_config import get_logger
from app.core.events import (
    EventBus,
    EventType,
    CookieExpiringEvent,
    get_event_bus,
)
from app.models.photo import TriggerType

logger = get_logger(__name__)

# Warning thresholds (in days/hours)
COOKIE_STALE_HOURS: float = 24.0
COOKIE_WARNING_DAYS: int = 3
COOKIE_CRITICAL_DAYS: int = 1


class CookieMonitor:
    """
    Monitor QQ cookie file health and emit warning events.

    Responsibilities:
    - Check cookie file existence and recency
    - Parse cookie content for expiration clues
    - Emit CookieExpiringEvent through EventBus
    """

    def __init__(
        self,
        cookie_file: str = "data/qq_cookies.txt",
    ):
        self._cookie_path = Path(cookie_file)
        self._bus: Optional[EventBus] = None

    def set_event_bus(self, bus: EventBus) -> None:
        """Set EventBus for emitting warning events."""
        self._bus = bus

    def check_health(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Comprehensive cookie health check.

        Returns:
            Tuple of (is_healthy, message, details dict).

        Details contains:
            - exists: Whether file exists
            - age_hours: Hours since last modification
            - size_bytes: File size
            - expires_in_days: Estimated days until expiry (-1 if unknown)
        """
        details: Dict[str, Any] = {}

        # Check existence
        if not self._cookie_path.exists():
            details["exists"] = False
            return (
                False,
                "Cookie file does not exist",
                details,
            )

        details["exists"] = True
        details["size_bytes"] = self._cookie_path.stat().st_size

        # Check staleness by mtime
        mtime = datetime.fromtimestamp(
            self._cookie_path.stat().st_mtime,
        )
        age_hours = (
            datetime.now() - mtime
        ).total_seconds() / 3600
        details["age_hours"] = round(age_hours, 1)

        # Check file content
        try:
            content = self._cookie_path.read_text(
                encoding="utf-8", errors="ignore",
            ).strip()

            if not content or len(content) < 20:
                details["expires_in_days"] = -1
                return (
                    False,
                    "Cookie file appears empty",
                    details,
                )

            # Parse for expiration hints
            expires_in = self._parse_expiry(content)
            details["expires_in_days"] = expires_in

            if expires_in <= COOKIE_CRITICAL_DAYS:
                msg = (
                    f"Cookie CRITICAL: expires in "
                    f"~{expires_in} day(s)"
                )
                healthy = False
                self._emit_warning(
                    max(expires_in, 0),
                    level="critical",
                )
            elif expires_in <= COOKIE_WARNING_DAYS:
                msg = (
                    f"Cookie WARNING: expires in ~{expires_in} "
                    f"day(s)"
                )
                healthy = True  # Still works but warn
                self._emit_warning(
                    expires_in, level="warning",
                )
            elif age_hours > COOKIE_STALE_HOURS:
                msg = (
                    f"Cookie stale: not updated in "
                    f"{age_hours:.0f}h"
                )
                healthy = True
                self._emit_warning_from_age(age_hours)
            else:
                msg = "Cookie OK"
                healthy = True

            return (healthy, msg, details)

        except Exception as exc:
            details["error"] = str(exc)
            return (False, f"Cookie read error: {exc}", details)

    def _parse_expiry(
        self, cookie_content: str,
    ) -> int:
        """
        Parse estimated cookie expiry from content.

        Looks for patterns like:
        - 'expires=...date...'
        - 'p_uin' field presence
        - 'qzone_token' presence
        """
        # Look for explicit expires header
        expire_patterns = [
            r"expires=(?:Wed|Thu|Fri|Sat|Sun|Mon|Tue)",
            r"Expires=(?:Wed|Thu|Fri|Sat|Sun|Mon|Tue)",
        ]

        for pattern in expire_patterns:
            match = re.search(pattern, cookie_content, re.I)
            if match:
                # Try to parse date after match
                date_str = cookie_content[
                    match.end():match.end() + 40
                ]
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(date_str.strip())
                    delta = dt.replace(tzinfo=None) - datetime.now()
                    return max(0, delta.days)
                except Exception:
                    continue

        # Fallback: estimate from key fields presence
        has_uin = "p_uin=" in cookie_content
        has_skey = "skey=" in cookie_content or "p_skey=" in cookie_content
        has_qz = "qzone_token" in cookie_content

        if not has_uin or not has_skey:
            return 0  # Likely expired or broken
        if has_qz:
            return 30  # Rough estimate: fresh cookies have this
        return 14  # Conservative estimate

    async def check_async(self) -> Tuple[bool, str]:
        """Async-friendly health check wrapper."""
        healthy, message, _details = self.check_health()
        return (healthy, message)

    def _emit_warning(
        self, days_remaining: float, level: str = "warning",
    ) -> None:
        """Emit CookieExpiringEvent to EventBus."""
        if self._bus is None:
            self._bus = get_event_bus()

        event = CookieExpiringEvent(
            days_remaining=int(days_remaining),
            cookie_file=str(self._cookie_path),
        )
        self._bus.publish_sync(event)
        logger.warning(
            "Cookie %s: %d days remaining (file=%s)",
            level.upper(),
            days_remaining,
            self._cookie_path.name,
        )

    def _emit_warning_from_age(self, age_hours: float) -> None:
        """Emit warning based on cookie file age alone."""
        if self._bus is None:
            self._bus = get_event_bus()

        event = CookieExpiringEvent(
            days_remaining=max(-int(age_hours // 24), -99),
            cookie_file=str(self._cookie_path),
        )
        self._bus.publish_sync(event)


async def check_cookie_and_warn(
    cookie_file: str = "",
    event_bus: Optional[EventBus] = None,
) -> bool:
    """
    Convenience function: check cookie and warn if issues.

    Returns:
        True if cookie is healthy, False otherwise.
    """
    monitor = CookieMonitor(cookie_file)
    if event_bus:
        monitor.set_event_bus(event_bus)

    healthy, message = await monitor.check_async()

    if not healthy:
        logger.warning("Cookie issue detected: %s", message)

    return healthy
