"""Conversation and message endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import Annotated, List
from app.core.database import get_session
from app.models.conversation import Conversation, ConversationCreate, ConversationRead
from app.models.message import Message, MessageCreate, MessageRead
from app.api.auth import get_current_user
from app.services.websocket_manager import websocket_manager
import json

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=List[ConversationRead])
async def get_conversations(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """Get all conversations for the current user."""
    # TODO: Filter by user when user model is implemented
    statement = select(Conversation).order_by(Conversation.updated_at.desc())
    conversations = session.exec(statement).all()
    return conversations


@router.post("", response_model=ConversationRead)
async def create_conversation(
    conversation: ConversationCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """Create a new conversation."""
    db_conversation = Conversation(**conversation.model_dump())
    session.add(db_conversation)
    session.commit()
    session.refresh(db_conversation)
    return db_conversation


@router.post("/{conversation_id}/messages", response_model=MessageRead)
async def create_message(
    conversation_id: int,
    message: MessageCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Create a new message in a conversation.
    If user message, generates assistant response.
    Broadcasts message.new event via WebSocket.
    """
    # Verify conversation exists
    conversation = session.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    from datetime import datetime
    
    # Create user message
    db_message = Message(
        content=message.content,
        role=message.role,
        conversation_id=conversation_id
    )
    if message.blocks:
        db_message.set_blocks(message.blocks)
    
    session.add(db_message)
    conversation.updated_at = datetime.utcnow()
    session.add(conversation)
    session.commit()
    session.refresh(db_message)
    
    # Broadcast user message via WebSocket
    message_data = MessageRead(
        id=db_message.id,
        content=db_message.content,
        role=db_message.role,
        conversation_id=db_message.conversation_id,
        created_at=db_message.created_at,
        blocks=db_message.get_blocks()
    )
    await websocket_manager.broadcast({
        "type": "message.new",
        "data": message_data.model_dump()
    })
    
    # Generate assistant response if user sent a message
    if message.role == "user":
        # Get conversation history for context
        statement = select(Message).where(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.desc()).limit(10)
        recent_messages = session.exec(statement).all()
        recent_messages.reverse()  # Oldest first
        
        # Generate simple assistant response
        assistant_content = _generate_assistant_response(message.content, recent_messages)
        
        # Create assistant message
        assistant_message = Message(
            content=assistant_content,
            role="assistant",
            conversation_id=conversation_id
        )
        session.add(assistant_message)
        conversation.updated_at = datetime.utcnow()
        session.add(conversation)
        session.commit()
        session.refresh(assistant_message)
        
        # Broadcast assistant message
        assistant_data = MessageRead(
            id=assistant_message.id,
            content=assistant_message.content,
            role=assistant_message.role,
            conversation_id=assistant_message.conversation_id,
            created_at=assistant_message.created_at,
            blocks=assistant_message.get_blocks()
        )
        await websocket_manager.broadcast({
            "type": "message.new",
            "data": assistant_data.model_dump()
        })
    
    return message_data


def _generate_assistant_response(user_message: str, history: list) -> str:
    """Generate assistant response based on user message and history."""
    # Simple echo-based response for now
    # TODO: Integrate with LLM or more sophisticated response generation
    
    user_lower = user_message.lower()
    
    # Simple pattern matching responses
    if any(word in user_lower for word in ["hello", "hi", "hey"]):
        return "Hello! How can I help you today?"
    elif any(word in user_lower for word in ["help", "what can you do"]):
        return "I'm an AI assistant. I can help you with various tasks, answer questions, and generate charts. What would you like to do?"
    elif "chart" in user_lower or "graph" in user_lower:
        return "I can help you generate charts! Click the chart button or ask me to create a visualization."
    elif "?" in user_message:
        return f"That's an interesting question about '{user_message[:50]}...'. I'm here to help! Could you provide more details?"
    else:
        # Echo with acknowledgment
        return f"I understand you said: '{user_message}'. How can I assist you further?"


@router.get("/{conversation_id}/messages", response_model=List[MessageRead])
async def get_messages(
    conversation_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """Get all messages for a conversation."""
    conversation = session.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    statement = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    messages = session.exec(statement).all()
    
    return [
        MessageRead(
            id=msg.id,
            content=msg.content,
            role=msg.role,
            conversation_id=msg.conversation_id,
            created_at=msg.created_at,
            blocks=msg.get_blocks()
        )
        for msg in messages
    ]
