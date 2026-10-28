import asyncio
import json
from typing import Any

_subscribers: set[asyncio.Queue[str]] = set()


def subscribe() -> asyncio.Queue[str]:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue[str]) -> None:
    _subscribers.discard(queue)


def publish(event: dict[str, Any]) -> None:
    payload = json.dumps(event, default=str)
    for queue in list(_subscribers):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            continue
