# -*- coding: utf-8 -*-
"""
Publish-Subscribe Event Bus for decoupled module communication.
事件总线 - 模块间发布/订阅解耦通信机制.

Design:
    - Singleton pattern: single global bus instance.
    - Type-safe: subscribers filter by EventType.
    - Async-compatible: supports both sync and async handlers.
    - Thread-safe: uses asyncio.Lock for concurrent access.

Usage:
    # Subscribe
    async def on_target_found(event: TargetFoundEvent):
        print(f"Target found in {event.data['photo_id']}")

    bus = EventBus.get_instance()
    await bus.subscribe(
        EventType.RECOGNITION_TARGET_FOUND, on_target_found
    )

    # Publish
    await bus.publish(TargetFoundEvent(photo_id="abc", target_name="Baby", confidence=0.95))
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from app.core.events import Event, EventType

logger = logging.getLogger(__name__)

# Type alias for event handler functions
EventHandler = Callable[[Event], Any]


class EventBus:
    """
    Thread-safe, async-compatible publish-subscribe event bus.

    Responsibilities:
    - Manage subscriber registrations by event type.
    - Dispatch published events to matching subscribers.
    - Support both synchronous and asynchronous handlers.
    - Provide diagnostic info (subscriber counts, event history).
    """

    _instance: Optional["EventBus"] = None

    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[EventHandler]] = {}
        self._lock = asyncio.Lock()
        self._event_history: List[Event] = []
        self._history_max_size: int = 1000
        self._enabled: bool = True
        logger.info("EventBus initialized")

    @classmethod
    def get_instance(cls) -> "EventBus":
        """Get the singleton EventBus instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (mainly for testing)."""
        cls._instance = None

    async def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        """
        Register a handler for a specific event type.

        Args:
            event_type: The event type to listen for.
            handler: Callback function receiving an Event object.
                     Can be sync or async (async handlers are awaited).
        """
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            # Prevent duplicate subscriptions
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                logger.debug(
                    "Subscribed to %s: %s",
                    event_type.value,
                    getattr(handler, "__name__", repr(handler)),
                )

    async def unsubscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        """Remove a handler subscription."""
        async with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                    logger.debug(
                        "Unsubscribed from %s: %s",
                        event_type.value,
                        getattr(handler, "__name__", repr(handler)),
                    )
                except ValueError:
                    pass  # Not subscribed, ignore
                if not self._subscribers[event_type]:
                    del self._subscribers[event_type]

    async def publish(self, event: Event) -> int:
        """
        Publish an event to all matching subscribers.

        Args:
            event: The event to publish.

        Returns:
            Number of handlers that received this event.
        """
        if not self._enabled:
            return 0

        # Record in history
        self._record_event(event)

        event_type = event.event_type
        handlers = []

        async with self._lock:
            handlers = list(self._subscribers.get(event_type, []))

        if not handlers:
            logger.debug(
                "No subscribers for event type: %s",
                event_type.value,
            )
            return 0

        delivered = 0
        errors: List[str] = []

        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
                delivered += 1
            except Exception as exc:
                errors.append(str(exc))
                logger.error(
                    "Event handler error on %s [%s]: %s",
                    event_type.value,
                    getattr(handler, "__name__", repr(handler)),
                    exc,
                )

        if errors and logger.isEnabledFor(logging.WARNING):
            logger.warning(
                "Event %s had %d/%d handler errors",
                event_type.value,
                len(errors),
                len(handlers),
            )

        return delivered

    def publish_sync(self, event: Event) -> int:
        """
        Synchronous publish variant (for non-async contexts).

        Note: This only calls sync handlers; async handlers are skipped
        with a warning log.
        """
        if not self._enabled:
            return 0

        self._record_event(event)

        event_type = event.event_type
        handlers = self._subscribers.get(event_type, [])

        if not handlers:
            return 0

        delivered = 0
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    logger.warning(
                        "Sync publish skipping async handler "
                        "%s for event %s",
                        getattr(
                            handler, "__name__", repr(handler),
                        ),
                        event_type.value,
                    )
                    continue
                delivered += 1
            except Exception as exc:
                logger.error(
                    "Event handler error (sync): %s", exc,
                )

        return delivered

    async def publish_batch(self, events: List[Event]) -> Dict[str, int]:
        """
        Publish multiple events efficiently.

        Returns:
            Mapping of event_type -> delivery count.
        """
        results: Dict[str, int] = {}
        for event in events:
            count = await self.publish(event)
            results[event.event_type.value] = (
                results.get(event.event_type.value, 0) + count
            )
        return results

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info("EventBus enabled=%s", value)

    def get_subscriber_count(self, event_type: EventType) -> int:
        """Return number of subscribers for an event type."""
        return len(self._subscribers.get(event_type, []))

    def get_all_subscriptions(self) -> Dict[str, int]:
        """Return all event types and their subscriber counts."""
        return {
            et.value: len(handlers)
            for et, handlers in self._subscribers.items()
        }

    def get_recent_events(
        self, event_type: Optional[EventType] = None, limit: int = 50,
    ) -> List[Event]:
        """Get recent events from history, optionally filtered."""
        if event_type:
            events = [
                e for e in self._event_history
                if e.event_type == event_type
            ]
        else:
            events = self._event_history
        return events[-limit:]

    def clear_history(self) -> None:
        """Clear event history buffer."""
        self._event_history.clear()

    async def clear_all_subscriptions(self) -> None:
        """Remove all subscribers (useful for testing/reset)."""
        async with self._lock:
            self._subscribers.clear()
            logger.info("All EventBus subscriptions cleared")

    def _record_event(self, event: Event) -> None:
        """Append event to circular history buffer."""
        self._event_history.append(event)
        if len(self._event_history) > self._history_max_size:
            self._event_history = (
                self._event_history[-self._history_max_size:]
            )


# Module-level convenience accessor
def get_event_bus() -> EventBus:
    """Get the global EventBus instance."""
    return EventBus.get_instance()
