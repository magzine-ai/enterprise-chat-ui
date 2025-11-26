"""Event bus listener for job updates (runs in FastAPI process)."""
import json
import asyncio
from app.core.event_bus import event_bus
from app.services.websocket_manager import websocket_manager


async def handle_job_update(message: str):
    """Handle job update event."""
    try:
        data = json.loads(message)
        await websocket_manager.broadcast(data)
    except Exception as e:
        print(f"Error broadcasting job update: {e}")


async def listen_for_job_updates():
    """Listen to event bus and broadcast job updates via WebSocket."""
    await event_bus.subscribe("job_updates", handle_job_update)
    # Keep the subscription alive
    while True:
        await asyncio.sleep(1)


