"""In-memory event bus to replace Redis pubsub."""
import asyncio
from typing import Dict, List, Callable, Any
import json

class EventBus:
    """Simple in-memory event bus for local development."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()
    
    async def subscribe(self, channel: str, callback: Callable):
        """Subscribe to a channel."""
        async with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = []
            self._subscribers[channel].append(callback)
    
    async def publish(self, channel: str, message: Any):
        """Publish a message to a channel."""
        async with self._lock:
            if channel in self._subscribers:
                for callback in self._subscribers[channel]:
                    try:
                        await callback(message)
                    except Exception as e:
                        print(f"Error in event callback: {e}")
    
    async def publish_json(self, channel: str, data: dict):
        """Publish JSON message."""
        await self.publish(channel, json.dumps(data))

# Global event bus instance
event_bus = EventBus()


