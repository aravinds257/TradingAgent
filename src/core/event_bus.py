"""Async event bus for decoupled communication between components."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger("event_bus")


class EventBus:
    """Simple pub/sub event bus using asyncio.Queue.

    Components subscribe to event types. When an event is published,
    all subscribers for that event type receive a copy in their queue.
    """

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, event_type: str, queue: asyncio.Queue | None = None) -> asyncio.Queue:
        """Subscribe to an event type. Returns the queue that will receive events."""
        if queue is None:
            queue = asyncio.Queue()
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(queue)
        return queue

    async def publish(self, event_type: str, data: Any) -> None:
        """Publish an event to all subscribers of that type."""
        if event_type in self._subscribers:
            for queue in self._subscribers[event_type]:
                await queue.put(data)

    def subscriber_count(self, event_type: str) -> int:
        return len(self._subscribers.get(event_type, []))
