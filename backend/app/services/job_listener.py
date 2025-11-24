"""Redis pubsub listener for job updates (runs in FastAPI process)."""
import json
import asyncio
from app.core.redis_client import redis_client
from app.services.websocket_manager import websocket_manager


async def listen_for_job_updates():
    """Listen to Redis pubsub and broadcast job updates via WebSocket."""
    pubsub = redis_client.pubsub()
    pubsub.subscribe("job_updates")
    
    for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                await websocket_manager.broadcast(data)
            except Exception as e:
                print(f"Error broadcasting job update: {e}")


def start_job_listener():
    """Start job update listener in background task."""
    # This will be started in main.py startup event
    pass


