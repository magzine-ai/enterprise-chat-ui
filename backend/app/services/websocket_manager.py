"""WebSocket connection manager."""
from fastapi import WebSocket
from typing import Dict, List, Optional
import json


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts.
    
    Supports both regular message broadcasting and streaming responses
    for real-time token delivery during LLM generation.
    """
    
    def __init__(self):
        """
        Initialize WebSocket manager.
        
        Maintains a dictionary of active connections organized by user_id
        to support multiple connections per user.
        """
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """
        Register WebSocket connection (connection should already be accepted).
        
        Adds the websocket to the active connections for the given user.
        Supports multiple connections per user (e.g., multiple browser tabs).
        
        Args:
            websocket: The WebSocket connection object
            user_id: Identifier for the user (from authentication or default)
        """
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"✅ WebSocket registered for user: {user_id} (total connections: {len(self.active_connections[user_id])})")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """
        Remove WebSocket connection.
        
        Removes the websocket from active connections and cleans up
        empty user entries.
        
        Args:
            websocket: The WebSocket connection to remove
            user_id: Identifier for the user
        """
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        Send message to a specific connection.
        
        Sends a JSON message to a single WebSocket connection.
        Used for targeted messages or error handling.
        
        Args:
            message: Dictionary to send as JSON
            websocket: Target WebSocket connection
        
        Raises:
            Exception: If sending fails (connection may be closed)
        """
        await websocket.send_json(message)
    
    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected clients.
        
        Sends a message to all active WebSocket connections.
        Handles disconnections gracefully and cleans up failed connections.
        
        Args:
            message: Dictionary to broadcast as JSON
        
        Edge Cases:
            - No active connections: logs warning and returns
            - Failed sends: removes connection from active list
            - Partial failures: continues sending to other connections
        """
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
    
    async def send_stream_start(
        self,
        conversation_id: int,
        message_id: Optional[int] = None
    ):
        """
        Signal the start of a streaming response.
        
        Sends a message to all clients indicating that a streaming response
        is beginning. This allows the frontend to initialize UI for streaming.
        
        Args:
            conversation_id: ID of the conversation receiving the stream
            message_id: Optional message ID if message was pre-created
        
        Message Format:
            {
                "type": "message.stream.start",
                "data": {
                    "conversation_id": int,
                    "message_id": int (optional)
                }
            }
        """
        message = {
            "type": "message.stream.start",
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id
            }
        }
        await self.broadcast(message)
    
    async def stream_token(
        self,
        conversation_id: int,
        token: str,
        message_id: Optional[int] = None
    ):
        """
        Send a single token during streaming.
        
        Broadcasts a token chunk to all clients. Tokens are accumulated
        on the frontend to build the complete message.
        
        Args:
            conversation_id: ID of the conversation receiving the stream
            token: Text token to send
            message_id: Optional message ID for tracking
        
        Message Format:
            {
                "type": "message.stream.token",
                "data": {
                    "conversation_id": int,
                    "token": str,
                    "message_id": int (optional)
                }
            }
        
        Performance:
            - Sends individual tokens for real-time feel
            - Consider batching for high-frequency streams
        """
        message = {
            "type": "message.stream.token",
            "data": {
                "conversation_id": conversation_id,
                "token": token,
                "message_id": message_id
            }
        }
        await self.broadcast(message)
    
    async def stream_chunk(
        self,
        conversation_id: int,
        chunk: str,
        message_id: Optional[int] = None
    ):
        """
        Send a chunk of tokens during streaming.
        
        More efficient than stream_token for sending multiple tokens at once.
        Use this when you have accumulated tokens to send in batches.
        
        Args:
            conversation_id: ID of the conversation receiving the stream
            chunk: Text chunk containing multiple tokens
            message_id: Optional message ID for tracking
        
        Message Format:
            {
                "type": "message.stream.chunk",
                "data": {
                    "conversation_id": int,
                    "chunk": str,
                    "message_id": int (optional)
                }
            }
        
        Use Cases:
            - Batching tokens for better performance
            - Sending complete words/phrases
            - Reducing WebSocket message frequency
        """
        message = {
            "type": "message.stream.chunk",
            "data": {
                "conversation_id": conversation_id,
                "chunk": chunk,
                "message_id": message_id
            }
        }
        await self.broadcast(message)
    
    async def send_stream_end(
        self,
        conversation_id: int,
        message_id: Optional[int] = None,
        blocks: Optional[List[Dict]] = None
    ):
        """
        Signal the end of a streaming response.
        
        Sends a message indicating streaming is complete. Optionally includes
        structured blocks extracted from the response.
        
        Args:
            conversation_id: ID of the conversation
            message_id: Optional message ID
            blocks: Optional list of structured blocks (queries, charts, etc.)
        
        Message Format:
            {
                "type": "message.stream.end",
                "data": {
                    "conversation_id": int,
                    "message_id": int (optional),
                    "blocks": List[Dict] (optional)
                }
            }
        
        Edge Cases:
            - Handles missing blocks gracefully
            - Ensures frontend can finalize message rendering
        """
        message = {
            "type": "message.stream.end",
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "blocks": blocks or []
            }
        }
        await self.broadcast(message)


websocket_manager = WebSocketManager()


