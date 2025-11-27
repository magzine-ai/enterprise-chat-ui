"""Assistant response generation worker."""
from sqlmodel import Session, select
from app.models.job import Job, JobStatus
from app.models.message import Message, MessageRead
from app.models.conversation import Conversation
from app.core.database import engine
from app.services.websocket_manager import websocket_manager
from app.api.conversations import _generate_assistant_response
from app.services.langgraph_service import process_conversation
from app.services.llm_service import llm_service
from app.core.config import settings
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
                
                # Generate assistant response using LangGraph or mock based on configuration
                if settings.mock_responses_enabled:
                    # Use existing mock response generation
                    print(f"🔄 Using mock response generation for job {job_id}")
                    assistant_content, assistant_blocks = _generate_assistant_response(
                        user_message_content, 
                        recent_messages
                    )
                else:
                    # Use LangGraph for intelligent response generation
                    print(f"🔄 Using LangGraph for job {job_id}")
                    
                    # Convert message history to format expected by LangGraph
                    history = []
                    for msg in recent_messages:
                        history.append({
                            "role": msg.role,
                            "content": msg.content
                        })
                    
                    # Check if streaming is enabled and LLM is available
                    use_streaming = settings.streaming_enabled and llm_service.is_available()
                    
                    if use_streaming:
                        # Stream response tokens
                        await _generate_and_stream_response(
                            job_id=job_id,
                            conversation_id=conversation_id,
                            user_message=user_message_content,
                            conversation_history=history,
                            session=session
                        )
                        # Streaming handles message creation, so we can return early
                        return
                    else:
                        # Non-streaming: use LangGraph to generate complete response
                        result = await process_conversation(
                            user_message=user_message_content,
                            conversation_id=conversation_id,
                            conversation_history=history
                        )
                        
                        assistant_content = result.get("content", "")
                        assistant_blocks = result.get("blocks", [])
                        
                        if result.get("error"):
                            print(f"⚠️ Error in LangGraph processing: {result['error']}")
                
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


async def _generate_and_stream_response(
    job_id: str,
    conversation_id: int,
    user_message: str,
    conversation_history: list,
    session: Session
):
    """
    Generate and stream LLM response token by token.
    
    Creates a message placeholder, then streams tokens as they arrive from the LLM.
    Updates the message content incrementally and sends tokens via WebSocket.
    Finally extracts blocks and finalizes the message.
    
    Args:
        job_id: Job ID for tracking
        conversation_id: Conversation ID
        user_message: User's message
        conversation_history: Previous messages
        session: Database session
    
    Edge Cases:
        - Streaming failures: falls back to non-streaming
        - Connection errors: handles gracefully
        - Empty streams: creates message with empty content
    """
    try:
        print(f"🌊 Starting streaming response for job {job_id}")
        
        # Create placeholder message for streaming
        assistant_message = Message(
            content="",  # Will be updated as tokens arrive
            role="assistant",
            conversation_id=conversation_id
        )
        session.add(assistant_message)
        
        # Update conversation timestamp
        conversation = session.get(Conversation, conversation_id)
        if conversation:
            conversation.updated_at = datetime.utcnow()
            session.add(conversation)
        
        session.commit()
        session.refresh(assistant_message)
        
        # Signal streaming start
        await websocket_manager.send_stream_start(
            conversation_id=conversation_id,
            message_id=assistant_message.id
        )
        
        # Stream tokens from LLM
        accumulated_content = ""
        async for token in llm_service.generate_response_stream(
            user_message=user_message,
            conversation_history=conversation_history,
            conversation_id=conversation_id
        ):
            accumulated_content += token
            
            # Update message content incrementally
            assistant_message.content = accumulated_content
            session.add(assistant_message)
            session.commit()
            
            # Send token to frontend
            await websocket_manager.stream_token(
                conversation_id=conversation_id,
                token=token,
                message_id=assistant_message.id
            )
        
        # Extract blocks from final response
        cleaned_text, blocks = llm_service.extract_blocks_from_response(
            accumulated_content,
            user_message
        )
        
        # Update message with final content and blocks
        assistant_message.content = cleaned_text
        if blocks:
            assistant_message.set_blocks(blocks)
        session.add(assistant_message)
        
        # Update job status
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.set_result({
                "message_id": assistant_message.id,
                "content": cleaned_text,
                "blocks": blocks
            })
            session.add(job)
        
        session.commit()
        session.refresh(assistant_message)
        
        # Signal streaming end with blocks
        await websocket_manager.send_stream_end(
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            blocks=blocks
        )
        
        # Broadcast final message (for clients that missed streaming)
        assistant_data = MessageRead(
            id=assistant_message.id,
            content=assistant_message.content,
            role=assistant_message.role,
            conversation_id=assistant_message.conversation_id,
            created_at=assistant_message.created_at,
            blocks=assistant_message.get_blocks()
        )
        
        data_dict = assistant_data.model_dump()
        if isinstance(data_dict.get('created_at'), datetime):
            data_dict['created_at'] = data_dict['created_at'].isoformat()
        
        await websocket_manager.broadcast({
            "type": "message.new",
            "data": data_dict
        })
        
        print(f"✅ Completed streaming response for job {job_id}")
        
    except Exception as e:
        print(f"❌ Error in streaming response for job {job_id}: {e}")
        import traceback
        print(traceback.format_exc())
        
        # Fallback to non-streaming
        try:
            result = await process_conversation(
                user_message=user_message,
                conversation_id=conversation_id,
                conversation_history=conversation_history
            )
            
            # Create message with result
            assistant_message = Message(
                content=result.get("content", ""),
                role="assistant",
                conversation_id=conversation_id
            )
            if result.get("blocks"):
                assistant_message.set_blocks(result["blocks"])
            
            session.add(assistant_message)
            session.commit()
            session.refresh(assistant_message)
            
            # Broadcast message
            assistant_data = MessageRead(
                id=assistant_message.id,
                content=assistant_message.content,
                role=assistant_message.role,
                conversation_id=assistant_message.conversation_id,
                created_at=assistant_message.created_at,
                blocks=assistant_message.get_blocks()
            )
            
            data_dict = assistant_data.model_dump()
            if isinstance(data_dict.get('created_at'), datetime):
                data_dict['created_at'] = data_dict['created_at'].isoformat()
            
            await websocket_manager.broadcast({
                "type": "message.new",
                "data": data_dict
            })
        except Exception as fallback_error:
            print(f"❌ Fallback also failed: {fallback_error}")
            await websocket_manager.broadcast({
                "type": "job.update",
                "data": {
                    "job_id": job_id,
                    "status": "failed",
                    "error": str(e)
                }
            })
