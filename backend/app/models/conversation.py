"""Conversation model."""
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from app.models.message import Message


class ConversationBase(SQLModel):
    """Base conversation schema."""
    title: Optional[str] = None


class Conversation(ConversationBase, table=True):
    """Conversation database model."""
    __tablename__ = "conversations"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationship
    messages: list["Message"] = Relationship(back_populates="conversation")


class ConversationCreate(ConversationBase):
    """Conversation creation schema."""
    pass


class ConversationRead(ConversationBase):
    """Conversation read schema."""
    id: int
    created_at: datetime
    updated_at: datetime

