"""WebSocket connection manager."""
from fastapi import WebSocket
from typing import Dict, List
import json


class WebSocketManager:
    """Manages WebSocket connections and broadcasts."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Register WebSocket connection (connection should already be accepted)."""
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"✅ WebSocket registered for user: {user_id} (total connections: {len(self.active_connections[user_id])})")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove WebSocket connection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to a specific connection."""
        await websocket.send_json(message)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        total_connections = sum(len(conns) for conns in self.active_connections.values())
        print(f"📡 Broadcasting {message.get('type', 'unknown')} to {total_connections} connection(s)")
        
        if total_connections == 0:
            print("⚠️ No active WebSocket connections to broadcast to!")
            return
        
        disconnected = []
        sent_count = 0
        for user_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(message)
                    sent_count += 1
                    print(f"✅ Sent {message.get('type', 'unknown')} to user {user_id}")
                except Exception as e:
                    print(f"❌ Failed to send to user {user_id}: {e}")
                    disconnected.append((user_id, connection))
        
        print(f"📤 Broadcast complete: {sent_count} sent, {len(disconnected)} failed")
        
        # Clean up disconnected connections
        for user_id, connection in disconnected:
            self.disconnect(connection, user_id)


websocket_manager = WebSocketManager()


