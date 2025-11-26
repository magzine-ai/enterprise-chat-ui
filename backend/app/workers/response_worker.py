"""Assistant response generation worker."""
from sqlmodel import Session, select
from app.models.job import Job, JobStatus
from app.models.message import Message, MessageRead
from app.models.conversation import Conversation
from app.core.database import engine
from app.services.websocket_manager import websocket_manager
from app.api.conversations import _generate_assistant_response
from datetime import datetime
import asyncio


async def generate_assistant_response_async(job_id: str):
    """
    Generate assistant response asynchronously.
    
    Reads job params to get message content and conversation_id,
    generates response, saves it, and broadcasts via WebSocket.
    """
    try:
        print(f"🔄 Starting response generation for job {job_id}")
        
        # No delay - generate response immediately for fast feedback
        # Database transaction should be committed by the time this runs
        
        with Session(engine) as session:
            # Get job
            statement = select(Job).where(Job.job_id == job_id)
            job = session.exec(statement).first()
            if not job:
                print(f"Job {job_id} not found")
                return
            
            try:
                # Update status to started
                job.status = JobStatus.STARTED
                job.progress = 0
                session.add(job)
                session.commit()
                
                # Get job params
                params = job.get_params()
                user_message_content = params.get("user_message")
                conversation_id = job.conversation_id
                
                if not user_message_content or not conversation_id:
                    raise ValueError("Missing user_message or conversation_id in job params")
                
                # Get conversation history for context
                statement = select(Message).where(
                    Message.conversation_id == conversation_id
                ).order_by(Message.created_at.desc()).limit(10)
                recent_messages = session.exec(statement).all()
                recent_messages.reverse()  # Oldest first
                
                # Update progress
                job.progress = 50
                job.status = JobStatus.PROGRESS
                session.add(job)
                session.commit()
                
                # Generate assistant response (with blocks if mock mode enabled)
                # For faster response, generate immediately (no artificial delay)
                assistant_content, assistant_blocks = _generate_assistant_response(
                    user_message_content, 
                    recent_messages
                )
                
                print(f"🔄 Generated response for job {job_id}: {assistant_content[:50]}...")
                
                # Create assistant message
                assistant_message = Message(
                    content=assistant_content,
                    role="assistant",
                    conversation_id=conversation_id
                )
                if assistant_blocks:
                    assistant_message.set_blocks(assistant_blocks)
                session.add(assistant_message)
                
                # Update conversation timestamp
                conversation = session.get(Conversation, conversation_id)
                if conversation:
                    conversation.updated_at = datetime.utcnow()
                    session.add(conversation)
                
                session.commit()
                session.refresh(assistant_message)
                
                # Update job with result
                job.status = JobStatus.COMPLETED
                job.progress = 100
                job.set_result({
                    "message_id": assistant_message.id,
                    "content": assistant_content,
                    "blocks": assistant_blocks
                })
                session.add(job)
                session.commit()
                
                # Broadcast assistant message via WebSocket
                assistant_data = MessageRead(
                    id=assistant_message.id,
                    content=assistant_message.content,
                    role=assistant_message.role,
                    conversation_id=assistant_message.conversation_id,
                    created_at=assistant_message.created_at,
                    blocks=assistant_message.get_blocks()
                )
                
                # Convert to dict and serialize datetime to ISO format string
                # FastAPI's send_json can't handle datetime objects directly
                data_dict = assistant_data.model_dump()
                if isinstance(data_dict.get('created_at'), datetime):
                    data_dict['created_at'] = data_dict['created_at'].isoformat()
                
                broadcast_message = {
                    "type": "message.new",
                    "data": data_dict
                }
                
                print(f"📤 Broadcasting assistant message for job {job_id}:")
                print(f"   Message ID: {assistant_message.id}")
                print(f"   Conversation ID: {assistant_message.conversation_id}")
                print(f"   Content: {assistant_message.content[:50]}...")
                print(f"   Blocks: {len(assistant_blocks)}")
                
                await websocket_manager.broadcast(broadcast_message)
                
                print(f"✅ Generated and broadcast assistant response for job {job_id}")
                
            except Exception as e:
                # Mark job as failed
                job.status = JobStatus.FAILED
                job.error = str(e)
                session.add(job)
                session.commit()
                print(f"❌ Error generating assistant response for job {job_id}: {e}")
                import traceback
                print(f"❌ Traceback: {traceback.format_exc()}")
                
                # Broadcast error via WebSocket
                try:
                    await websocket_manager.broadcast({
                        "type": "job.update",
                        "data": {
                            "job_id": job_id,
                            "status": "failed",
                            "error": str(e)
                        }
                    })
                except Exception as broadcast_error:
                    print(f"❌ Failed to broadcast error: {broadcast_error}")
    except Exception as outer_error:
        # Catch any errors outside the try block (e.g., database connection issues)
        print(f"❌ Critical error in generate_assistant_response_async for job {job_id}: {outer_error}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
