"""WebSocket endpoint for real-time updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from app.services.websocket_manager import websocket_manager
from app.core.auth import decode_access_token
from app.core.config import settings
from typing import Optional
import asyncio

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time updates.
    
    Accepts optional token query parameter for authentication.
    Broadcasts job.update and message.new events.
    
    When auth_enabled=False, authentication is optional and defaults to anonymous user.
    """
    # Accept the WebSocket connection first
    await websocket.accept()
    
    # Determine user_id after accepting connection
    # If authentication is disabled, use default user
    if not settings.auth_enabled:
        user_id = settings.default_user
    elif token:
        # Validate token if provided
        payload = decode_access_token(token)
        if not payload:
            # Close connection if token is invalid
            await websocket.close(code=1008, reason="Invalid token")
            return
        user_id = payload.get("sub") or settings.default_user
    else:
        # No token provided but auth is enabled - use anonymous
        user_id = settings.default_user
    
    # Register connection with manager (don't accept again - already accepted)
    await websocket_manager.connect(websocket, user_id)
    print(f"🔌 WebSocket connection established for user: {user_id}")
    
    try:
        # Keep connection alive - wait for either:
        # 1. Client sends a message (optional)
        # 2. Client disconnects
        # Server can send messages at any time via websocket_manager.broadcast()
        while True:
            try:
                # Wait for client message (with timeout to keep connection alive)
                # If client doesn't send anything, connection stays open for server to send
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo for now; can be extended for client->server commands
                await websocket.send_json({"type": "ack", "data": data})
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    # Connection might be closed, break to handle disconnect
                    break
    except WebSocketDisconnect:
        print(f"🔌 WebSocket disconnected for user: {user_id}")
        websocket_manager.disconnect(websocket, user_id)
    except Exception as e:
        print(f"❌ WebSocket error for user {user_id}: {e}")
        websocket_manager.disconnect(websocket, user_id)


