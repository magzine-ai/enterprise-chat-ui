"""Message model."""
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, Any
from datetime import datetime
import json


class MessageBase(SQLModel):
    """Base message schema."""
    content: str
    role: str  # "user" or "assistant"
    conversation_id: int
    blocks: Optional[str] = None  # JSON string of block array


class Message(MessageBase, table=True):
    """Message database model."""
    __tablename__ = "messages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    conversation_id: int = Field(foreign_key="conversations.id")
    
    # Relationship
    conversation: Optional["Conversation"] = Relationship(back_populates="messages")
    
    def get_blocks(self) -> list[dict[str, Any]]:
        """Parse blocks JSON."""
        if not self.blocks:
            return []
        return json.loads(self.blocks)
    
    def set_blocks(self, blocks: list[dict[str, Any]]):
        """Serialize blocks to JSON."""
        self.blocks = json.dumps(blocks)


class MessageCreate(SQLModel):
    """Message creation schema."""
    content: str
    role: str = "user"
    blocks: Optional[list[dict[str, Any]]] = None


class MessageRead(MessageBase):
    """Message read schema."""
    id: int
    created_at: datetime
    blocks: Optional[list[dict[str, Any]]] = None


