"""WebSocket endpoint for real-time updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from app.services.websocket_manager import websocket_manager
from app.core.auth import decode_access_token
from typing import Optional

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
    """
    # TODO: Validate token properly
    if token:
        payload = decode_access_token(token)
        if not payload:
            await websocket.close(code=1008, reason="Invalid token")
            return
        user_id = payload.get("sub")
    else:
        user_id = "anonymous"
    
    await websocket_manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            # Echo for now; can be extended for client->server commands
            await websocket.send_json({"type": "ack", "data": data})
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket, user_id)


