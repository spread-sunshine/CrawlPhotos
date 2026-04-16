# -*- coding: utf-8 -*-
"""
Trigger modes: scheduled, manual, event-based.
触发器模块 - 定时触发/CLI手动触发/事件触发骨架.

Supports three trigger modes:
A. Event trigger (real-time via bot/webhook listener)
B. Scheduled trigger (cron via APScheduler)
C. Manual trigger (CLI command or API call)
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config.logging_config import get_logger
from app.models.photo import TriggerType

logger = get_logger(__name__)

# Callback type for triggering the main pipeline
PipelineCallback = Callable[
    [TriggerType, Dict[str, Any]], Coroutine[Any, Any, None]
]


class BaseTrigger(ABC):
    """Abstract base class for all trigger mechanisms."""

    @abstractmethod
    def start(self, callback: PipelineCallback) -> None:
        """
        Register the pipeline execution callback and start listening.

        Args:
            callback: Async callable invoked when triggered.
                     Signature: callback(trigger_type, options)
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the trigger mechanism."""
        pass

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Whether this trigger is currently active."""


class ManualTrigger(BaseTrigger):
    """
    Mode C: Manual trigger via direct call.

    Simplest trigger - exposes a run() method for CLI or
    programmatic invocation.
    """

    def __init__(self):
        self._running = False
        self._callback: Optional[PipelineCallback] = None

    def start(self, callback: PipelineCallback) -> None:
        self._callback = callback
        self._running = True
        logger.info("ManualTrigger started")

    def stop(self) -> None:
        self._running = False
        self._callback = None
        logger.info("ManualTrigger stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def run(
        self,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Manually trigger one pipeline execution.

        Args:
            options: Optional parameters like scan_days_back.
        """
        if self._callback is None:
            raise RuntimeError("ManualTrigger not started")

        opts = options or {}
        logger.info(
            "Manual trigger invoked: options=%s", opts
        )
        await self._callback(TriggerType.MANUAL, opts)


class ScheduledTrigger(BaseTrigger):
    """
    Mode B: Scheduled trigger using APScheduler Cron.

    Executes at fixed intervals based on cron expression.
    Supports optional startup full-scan.
    """

    def __init__(
        self,
        cron_expression: str = "0 */30 * * * *",
        startup_scan: bool = True,
        scan_days_back: int = 7,
    ):
        self._cron_expression = cron_expression
        self._startup_scan = startup_scan
        self._scan_days_back = scan_days_back
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._callback: Optional[PipelineCallback] = None
        self._running = False

    def start(self, callback: PipelineCallback) -> None:
        self._callback = callback
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

        # Register periodic job from cron expression
        try:
            trigger = CronTrigger.from_crontab(
                self._cron_expression
            )
        except Exception:
            # Fallback: parse simple interval
            logger.warning(
                "Invalid cron expression '%s', falling back "
                "to default every 30 min",
                self._cron_expression,
            )
            trigger = CronTrigger(minute="*/30")

        self._scheduler.add_job(
            self._execute_pipeline,
            trigger=trigger,
            id="scheduled_crawl",
            name="Scheduled Photo Crawl",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True

        logger.info(
            "ScheduledTrigger started: cron='%s', "
            "startup_scan=%s",
            self._cron_expression,
            self._startup_scan,
        )

        # Optionally run startup scan
        if self._startup_scan:
            loop = asyncio.get_event_loop()
            loop.create_task(
                self._run_startup_scan()
            )

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("ScheduledTrigger stopped")

    @property
    def is_running(self) -> bool:
        return self._running and (
            self._scheduler.running if self._scheduler else False
        )

    async def _execute_pipeline(self) -> None:
        """Internal handler called by scheduler."""
        if self._callback:
            logger.info(
                "Scheduled trigger fired at %s",
                datetime.now().isoformat(),
            )
            await self._callback(
                TriggerType.SCHEDULED, {}
            )

    async def _run_startup_scan(self) -> None:
        """Run initial scan shortly after startup."""
        await asyncio.sleep(3)  # Brief delay for system init
        if self._callback:
            logger.info(
                "Running startup scan (last %d days)",
                self._scan_days_back,
            )
            await self._callback(
                TriggerType.SCHEDULED,
                {
                    "scan_days_back": self._scan_days_back,
                    "is_startup": True,
                },
            )


class EventTrigger(BaseTrigger):
    """
    Mode A: Event trigger (placeholder for future).

    Designed to listen for events such as:
    - QQ bot messages about photo uploads
    - Webhook callbacks
    - File system watches
    """

    DEBOUNCE_SECONDS = 60

    def __init__(
        self,
        debounce_seconds: int = DEBOUNCE_SECONDS,
    ):
        self._debounce_seconds = debounce_seconds
        self._callback: Optional[PipelineCallback] = None
        self._running = False
        self._last_trigger_time: Optional[datetime] = None
        self._pending_task: Optional[asyncio.Task] = None

    def start(self, callback: PipelineCallback) -> None:
        self._callback = callback
        self._running = True
        logger.info("EventTrigger started (debounce=%ds)",
                     self._debounce_seconds)

    def stop(self) -> None:
        self._running = False
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
        logger.info("EventTrigger stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def notify_event(
        self,
        event_type: str = "photo_upload",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Receive an external event notification.

        Implements debouncing: rapid successive events within
        the debounce window are coalesced into one trigger.

        Args:
            event_type: Type of event received.
            payload: Event-specific data.
        """
        if not self._running or self._callback is None:
            return

        now = datetime.now()
        payload = payload or {}

        # Debounce logic
        if (
            self._last_trigger_time is not None
            and (now - self._last_trigger_time).total_seconds()
            < self._debounce_seconds
        ):
            logger.debug(
                "Event throttled (debounce): type=%s",
                event_type,
            )
            return

        self._last_trigger_time = now

        # Schedule async execution
        self._pending_task = asyncio.create_task(
            self._fire_event(event_type, payload)
        )

    async def _fire_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """Execute the pipeline callback for an event."""
        logger.info(
            "Event trigger fired: type=%s", event_type
        )
        if self._callback:
            await self._callback(
                TriggerType.EVENT,
                {"event_type": event_type, **payload},
            )
