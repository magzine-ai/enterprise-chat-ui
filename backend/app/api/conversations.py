"""Conversation and message endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel import Session, select
from typing import Annotated, List, Dict, Any, Tuple
from app.core.database import get_session
from app.models.conversation import Conversation, ConversationCreate, ConversationRead
from app.models.message import Message, MessageCreate, MessageRead
from app.api.auth import get_current_user
from app.services.websocket_manager import websocket_manager
from app.core.config import settings
import json
import random

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


@router.post("/{conversation_id}/messages")
async def create_message(
    conversation_id: int,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Create a new message in a conversation.
    If user message, creates async job for assistant response generation.
    Returns message data and job_id (if user message).
    Broadcasts user message via WebSocket immediately.
    """
    # Verify conversation exists
    conversation = session.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    from datetime import datetime
    import uuid
    from app.models.job import Job, JobStatus
    from app.workers.response_worker import generate_assistant_response_async
    
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
    
    # Prepare message data for API response
    # Note: We don't broadcast user messages via WebSocket - frontend already has them from API response
    # Only assistant messages are broadcast via WebSocket (handled in response_worker.py)
    message_data = MessageRead(
        id=db_message.id,
        content=db_message.content,
        role=db_message.role,
        conversation_id=db_message.conversation_id,
        created_at=db_message.created_at,
        blocks=db_message.get_blocks()
    )
    
    # Create async job for assistant response if user sent a message
    job_id = None
    if message.role == "user":
        job_id = str(uuid.uuid4())
        
        # Create job record
        db_job = Job(
            job_id=job_id,
            type="assistant_response",
            conversation_id=conversation_id,
            status=JobStatus.QUEUED
        )
        db_job.set_params({
            "user_message": message.content,
            "conversation_id": conversation_id
        })
        session.add(db_job)
        session.commit()
        session.refresh(db_job)
        
        # Start async worker to generate response
        # Use asyncio.create_task to properly run async function in background
        # This ensures the task runs independently and doesn't block the response
        import asyncio
        try:
            # Get the current event loop (should exist since we're in an async endpoint)
            loop = asyncio.get_event_loop()
            loop.create_task(generate_assistant_response_async(job_id))
            print(f"🚀 Started background task for job {job_id}")
        except RuntimeError:
            # If no event loop, create a new one (shouldn't happen in FastAPI)
            print(f"⚠️ No event loop found, using BackgroundTasks fallback for job {job_id}")
            background_tasks.add_task(generate_assistant_response_async, job_id)
        except Exception as e:
            print(f"❌ Failed to start background task for job {job_id}: {e}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")
            # Fallback: use BackgroundTasks as backup
            background_tasks.add_task(generate_assistant_response_async, job_id)
    
    # Return message data and job_id
    return {
        "message": message_data.model_dump(),
        "job_id": job_id
    }


def _generate_assistant_response(user_message: str, history: list) -> Tuple[str, list[Dict[str, Any]]]:
    """
    Generate assistant response based on user message and history.
    Returns tuple of (content, blocks).
    """
    user_lower = user_message.lower().strip()
    blocks: list[Dict[str, Any]] = []
    content: str = ""
    
    # If mock responses are enabled, generate rich responses with blocks
    if settings.mock_responses_enabled:
        blocks = _generate_blocks_for_response(user_message, user_lower)
        content = _generate_response_text(user_message, user_lower)
    else:
        # Simple pattern matching responses (original behavior)
        if any(word in user_lower for word in ["hello", "hi", "hey"]):
            content = "Hello! How can I help you today?"
        elif any(word in user_lower for word in ["help", "what can you do"]):
            content = "I'm an AI assistant. I can help you with various tasks, answer questions, and generate charts. What would you like to do?"
        elif "chart" in user_lower or "graph" in user_lower:
            content = "I can help you generate charts! Click the chart button or ask me to create a visualization."
        elif "?" in user_message:
            content = f"That's an interesting question about '{user_message[:50]}...'. I'm here to help! Could you provide more details?"
        else:
            content = f"I understand you said: '{user_message}'. How can I assist you further?"
    
    return content, blocks


def _generate_blocks_for_response(user_message: str, user_lower: str) -> list[Dict[str, Any]]:
    """Generate blocks based on user message patterns."""
    blocks: list[Dict[str, Any]] = []
    
    # SQL queries
    if any(pattern in user_lower for pattern in ["show sql", "sql query", "select from", "create table", "insert into"]):
        blocks.append({
            "type": "code",
            "data": {
                "code": "SELECT \n  user_id,\n  username,\n  email,\n  created_at,\n  last_login\nFROM users\nWHERE active = true\nORDER BY created_at DESC\nLIMIT 100;",
                "language": "sql",
                "title": "SQL Query Example",
            },
        })
        blocks.append({
            "type": "table",
            "data": {
                "columns": ["user_id", "username", "email", "created_at", "last_login"],
                "rows": [
                    ["1", "john_doe", "john@example.com", "2024-01-15 10:30:00", "2024-11-20 14:22:00"],
                    ["2", "jane_smith", "jane@example.com", "2024-01-16 11:00:00", "2024-11-21 09:15:00"],
                    ["3", "bob_wilson", "bob@example.com", "2024-01-17 12:30:00", "2024-11-19 16:45:00"],
                ],
            },
        })
    
    # Splunk queries
    if any(pattern in user_lower for pattern in ["splunk", "spl query", "index=", "stats count", "timechart"]):
        blocks.append({
            "type": "query",
            "data": {
                "query": "index=cfs_digital_profilecore_hec_105961 \n| stats count by status\n| sort -count",
                "language": "spl",
                "title": "Splunk Query: Status Counts",
                "autoExecute": True,
            },
        })
    
    # Chart requests
    if any(pattern in user_lower for pattern in ["chart", "graph", "visualization", "plot", "timechart", "bar chart", "line chart", "show chart", "create chart", "visualize data"]):
        chart_type = "bar" if "bar" in user_lower else "pie" if "pie" in user_lower else "area" if "area" in user_lower else "timechart" if "time" in user_lower else "line"
        
        chart_data = []
        if chart_type == "timechart":
            chart_data = [
                {"time": f"{i:02d}:00", "requests": random.randint(500, 1500), "errors": random.randint(10, 60)}
                for i in range(24)
            ]
        elif chart_type == "pie":
            chart_data = [
                {"name": "Success", "value": 1250},
                {"name": "Warning", "value": 150},
                {"name": "Error", "value": 75},
                {"name": "Info", "value": 200},
            ]
        else:
            chart_data = [
                {"name": "Mon", "value": 1200},
                {"name": "Tue", "value": 1350},
                {"name": "Wed", "value": 1100},
                {"name": "Thu", "value": 1450},
                {"name": "Fri", "value": 1300},
                {"name": "Sat", "value": 980},
                {"name": "Sun", "value": 1050},
            ]
        
        blocks.append({
            "type": "splunk-chart",
            "data": {
                "type": chart_type,
                "title": "Sample Data Visualization",
                "data": chart_data,
                "xAxis": "time" if chart_type == "timechart" else "name",
                "yAxis": "value" if chart_type == "pie" else None,
                "series": ["requests", "errors"] if chart_type == "timechart" else None,
                "height": 300,
                "isTimeSeries": chart_type == "timechart",
                "allowChartTypeSwitch": chart_type != "pie",
            },
        })
    
    # Code examples
    if any(pattern in user_lower for pattern in ["show code", "code example", "python code", "javascript code", "example code"]):
        code_examples = [
            {
                "code": "def process_data(data):\n    \"\"\"Process and analyze data.\"\"\"\n    results = []\n    for item in data:\n        if item['status'] == 'active':\n            results.append(item)\n    return results",
                "language": "python",
                "title": "Python Example",
            },
            {
                "code": "function analyzeData(data) {\n  return data\n    .filter(item => item.status === 'active')\n    .map(item => ({\n      ...item,\n      processed: true\n    }));\n}",
                "language": "javascript",
                "title": "JavaScript Example",
            },
        ]
        blocks.append({
            "type": "code",
            "data": random.choice(code_examples),
        })
    
    # Data table requests
    if any(pattern in user_lower for pattern in ["show table", "display data", "list data", "table data"]):
        blocks.append({
            "type": "table",
            "data": {
                "columns": ["ID", "Name", "Status", "Value", "Timestamp"],
                "rows": [
                    ["1", "Item A", "Active", "1250", "2024-11-21 10:00:00"],
                    ["2", "Item B", "Active", "980", "2024-11-21 11:00:00"],
                    ["3", "Item C", "Inactive", "750", "2024-11-21 12:00:00"],
                    ["4", "Item D", "Active", "2100", "2024-11-21 13:00:00"],
                    ["5", "Item E", "Pending", "450", "2024-11-21 14:00:00"],
                ],
            },
        })
    
    # JSON explorer requests
    if any(pattern in user_lower for pattern in ["json", "show json", "explore data", "view json", "json data"]):
        blocks.append({
            "type": "json-explorer",
            "data": {
                "title": "JSON Data Explorer",
                "data": {
                    "user": {
                        "id": 1,
                        "name": "John Doe",
                        "email": "john@example.com",
                        "preferences": {
                            "theme": "dark",
                            "notifications": True,
                        },
                        "tags": ["admin", "developer"],
                    },
                    "metadata": {
                        "created": "2024-01-15",
                        "updated": "2024-11-21",
                    },
                },
                "collapsed": False,
                "maxDepth": 3,
            },
        })
    
    # Timeline requests
    if any(pattern in user_lower for pattern in ["timeline", "events", "log view", "event history", "show events"]):
        blocks.append({
            "type": "timeline",
            "data": {
                "title": "Event Timeline",
                "events": [
                    {
                        "time": "10:00:00",
                        "title": "System Started",
                        "description": "Application initialized successfully",
                        "type": "success",
                    },
                    {
                        "time": "10:15:30",
                        "title": "User Login",
                        "description": "User authenticated",
                        "type": "info",
                    },
                    {
                        "time": "10:30:45",
                        "title": "Warning",
                        "description": "High memory usage detected",
                        "type": "warning",
                    },
                    {
                        "time": "10:45:12",
                        "title": "Error Occurred",
                        "description": "Failed to process request",
                        "type": "error",
                        "metadata": {"errorCode": "ERR_500", "details": "Internal server error"},
                    },
                ],
                "showTime": True,
                "orientation": "vertical",
            },
        })
    
    # Search/filter requests
    if any(pattern in user_lower for pattern in ["search", "filter", "find data", "lookup"]):
        blocks.append({
            "type": "search-filter",
            "data": {
                "data": [
                    {"id": 1, "name": "Item A", "category": "Type 1", "status": "Active"},
                    {"id": 2, "name": "Item B", "category": "Type 2", "status": "Inactive"},
                    {"id": 3, "name": "Item C", "category": "Type 1", "status": "Active"},
                    {"id": 4, "name": "Item D", "category": "Type 3", "status": "Pending"},
                ],
                "placeholder": "Search items...",
                "showResultsCount": True,
            },
        })
    
    # Alert/notification requests
    if any(pattern in user_lower for pattern in ["alert", "warning", "error", "notification", "important"]):
        alert_type = "error" if "error" in user_lower else "warning" if "warning" in user_lower else "success" if "success" in user_lower else "info"
        blocks.append({
            "type": "alert",
            "data": {
                "type": alert_type,
                "title": "Error" if alert_type == "error" else "Warning" if alert_type == "warning" else "Information",
                "message": f"This is a {alert_type} message. Important information or notifications can be displayed here.",
                "dismissible": True,
            },
        })
    
    # Form viewer / ServiceNow change request
    if any(pattern in user_lower for pattern in ["change request", "servicenow", "ticket", "form", "cr", "inc", "show form", "display form"]):
        is_change_request = "change" in user_lower or "cr" in user_lower
        form_title = "Change Request CR12345" if is_change_request else "ServiceNow Ticket INC67890"
        
        blocks.append({
            "type": "form-viewer",
            "data": {
                "title": form_title,
                "fields": [
                    {"name": "number", "label": "Number", "value": "CR12345" if is_change_request else "INC67890", "type": "text", "icon": "📋"},
                    {"name": "state", "label": "State", "value": "In Progress", "type": "badge", "badgeType": "info"},
                    {"name": "priority", "label": "Priority", "value": "High", "type": "badge", "badgeType": "warning"},
                    {"name": "category", "label": "Category", "value": "Standard" if is_change_request else "Incident", "type": "text"},
                    {"name": "assigned_to", "label": "Assigned To", "value": "John Doe", "type": "text", "icon": "👤"},
                    {"name": "short_description", "label": "Short Description", "value": "Deploy new application version to production" if is_change_request else "Application server experiencing high CPU usage", "type": "text"},
                    {"name": "description", "label": "Description", "value": "This change request involves deploying version 2.1.0 of the application to the production environment. All tests have passed and approval has been obtained." if is_change_request else "Users are reporting slow response times. Monitoring shows CPU usage at 95%. Investigation needed.", "type": "multiline"},
                    {"name": "risk", "label": "Risk", "value": "Medium", "type": "badge", "badgeType": "warning"},
                    {"name": "impact", "label": "Impact", "value": "High", "type": "badge", "badgeType": "error"},
                    {"name": "planned_start", "label": "Planned Start", "value": "2024-11-22T02:00:00Z", "type": "date"},
                    {"name": "planned_end", "label": "Planned End", "value": "2024-11-22T04:00:00Z", "type": "date"},
                    {"name": "approval_status", "label": "Approval Status", "value": "Approved", "type": "badge", "badgeType": "success"},
                    {"name": "sys_id", "label": "System ID", "value": "a1b2c3d4e5f6g7h8i9j0", "type": "text"},
                    {"name": "link", "label": "View in ServiceNow", "value": "Open Ticket", "type": "link", "link": "https://servicenow.example.com/nav_to.do?uri=change_request.do?sys_id=a1b2c3d4"},
                ],
                "sections": [
                    {"title": "Basic Information", "fields": ["number", "state", "priority", "category"]},
                    {"title": "Assignment", "fields": ["assigned_to"]},
                    {"title": "Description", "fields": ["short_description", "description"]},
                    {"title": "Risk & Impact", "fields": ["risk", "impact"]},
                    {"title": "Schedule", "fields": ["planned_start", "planned_end"]},
                    {"title": "Approval", "fields": ["approval_status"]},
                    {"title": "System Information", "fields": ["sys_id", "link"], "collapsed": True},
                ],
                "metadata": {
                    "created": "2024-11-20T10:30:00Z",
                    "updated": "2024-11-21T14:45:00Z",
                    "createdBy": "System Administrator",
                    "updatedBy": "Change Manager",
                },
                "actions": [
                    {"label": "Approve", "actionId": "approve", "variant": "primary"},
                    {"label": "Reject", "actionId": "reject", "variant": "danger"},
                ],
            },
        })
    
    # File upload/download
    if any(pattern in user_lower for pattern in ["upload file", "download file", "file upload", "file download", "share file", "attach file"]):
        blocks.append({
            "type": "file-upload-download",
            "data": {
                "title": "File Manager",
                "mode": "both",
                "files": [
                    {
                        "name": "application.log",
                        "size": 1048576,
                        "url": "/files/application.log",
                        "type": "text/plain",
                        "uploadedAt": "2024-11-20T00:00:00Z",
                        "description": "Application logs from yesterday",
                    },
                    {
                        "name": "config.json",
                        "size": 2048,
                        "url": "/files/config.json",
                        "type": "application/json",
                        "uploadedAt": "2024-11-21T14:00:00Z",
                        "description": "Application configuration file",
                    },
                    {
                        "name": "report.pdf",
                        "size": 5242880,
                        "url": "/files/report.pdf",
                        "type": "application/pdf",
                        "uploadedAt": "2024-11-21T12:00:00Z",
                        "description": "Monthly report document",
                    },
                ],
                "accept": ".log,.txt,.json,.pdf,.csv",
                "maxSize": 10485760,
                "multiple": True,
            },
        })
    
    # Checklist
    if any(pattern in user_lower for pattern in ["checklist", "task list", "todo list", "deployment checklist", "action items", "steps to complete"]):
        blocks.append({
            "type": "checklist",
            "data": {
                "title": "Deployment Checklist",
                "items": [
                    {"id": "1", "text": "Backup production database", "checked": True, "priority": "high", "assignee": "devops-team"},
                    {"id": "2", "text": "Run automated test suite", "checked": True, "priority": "high", "assignee": "qa-team"},
                    {"id": "3", "text": "Update configuration files", "checked": False, "priority": "medium", "assignee": "dev-team", "dueDate": "2024-11-22"},
                    {"id": "4", "text": "Deploy to staging environment", "checked": False, "priority": "high", "assignee": "devops-team", "dueDate": "2024-11-23"},
                    {"id": "5", "text": "Perform smoke tests", "checked": False, "priority": "medium", "assignee": "qa-team", "notes": "Focus on critical user flows"},
                    {"id": "6", "text": "Deploy to production", "checked": False, "priority": "critical", "assignee": "devops-team", "subItems": [
                        {"id": "6-1", "text": "Schedule maintenance window", "checked": False},
                        {"id": "6-2", "text": "Notify stakeholders", "checked": True},
                        {"id": "6-3", "text": "Execute deployment script", "checked": False},
                    ]},
                    {"id": "7", "text": "Monitor application metrics", "checked": False, "priority": "high", "assignee": "monitoring-team"},
                ],
                "showProgress": True,
                "showPriority": True,
                "showDueDate": True,
                "collapsible": True,
            },
        })
    
    # Diagram/Architecture
    if any(pattern in user_lower for pattern in ["diagram", "architecture", "workflow", "aws architecture", "system design", "flowchart", "sequence diagram"]):
        diagram_type = "aws" if "aws" in user_lower else "flowchart" if ("workflow" in user_lower or "flowchart" in user_lower) else "sequence" if "sequence" in user_lower else "architecture" if "architecture" in user_lower else "mermaid"
        
        if diagram_type == "mermaid":
            blocks.append({
                "type": "diagram",
                "data": {
                    "type": "mermaid",
                    "title": "System Workflow Diagram",
                    "description": "High-level system workflow",
                    "diagram": "graph TD\n    A[User Request] --> B{Authentication}\n    B -->|Valid| C[Process Request]\n    B -->|Invalid| D[Return Error]\n    C --> E[Query Database]\n    E --> F[Generate Response]\n    F --> G[Return to User]\n    D --> H[Log Error]",
                    "interactive": True,
                    "showControls": True,
                },
            })
        elif diagram_type == "aws":
            blocks.append({
                "type": "diagram",
                "data": {
                    "type": "aws",
                    "title": "AWS Architecture",
                    "description": "Cloud infrastructure architecture",
                    "diagram": "Load Balancer\nApplication Server\nDatabase\nS3 Storage\nCloudWatch",
                    "interactive": True,
                    "showControls": True,
                },
            })
        else:
            # Handle other diagram types (flowchart, sequence, architecture)
            blocks.append({
                "type": "diagram",
                "data": {
                    "type": diagram_type,
                    "title": f"{diagram_type.title()} Diagram",
                    "description": f"{diagram_type.title()} representation",
                    "diagram": f"Start Process\nValidate Input\nProcess Data\nGenerate Output\nEnd Process",
                    "interactive": True,
                    "showControls": True,
                },
            })
    
    return blocks


def _generate_response_text(user_message: str, user_lower: str) -> str:
    """Generate response text content based on user message."""
    # Greetings
    if any(word in user_lower for word in ["hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening"]):
        greetings = [
            "Hello! 👋 I'm your AI assistant. How can I help you today?",
            "Hi there! Nice to meet you. What can I do for you?",
            "Hey! I'm here to help. What would you like to know?",
            "Greetings! I'm ready to assist you. How can I help?",
        ]
        return random.choice(greetings)
    
    # Help requests
    if any(word in user_lower for word in ["help", "what can you do", "capabilities"]):
        return """I can help you with various tasks:

📊 **Data & Analytics**
- Generate charts and visualizations
- Analyze data and provide insights
- Process and transform data

💬 **Conversation**
- Answer questions
- Provide explanations
- Assist with problem-solving

🔧 **Tools & Features**
- Create async jobs for long-running tasks
- Generate reports and summaries
- Much more!

What would you like to try first?"""
    
    # Chart/visualization requests
    if any(word in user_lower for word in ["chart", "graph", "visualization", "plot"]):
        return "Here's a sample chart visualization for you! 📊"
    
    # Questions
    if "?" in user_message:
        question_responses = [
            f"That's a great question! Let me help you with that. Based on what you're asking about \"{user_message[:40]}{'...' if len(user_message) > 40 else ''}\", I'd suggest exploring this topic further. Would you like me to provide more details?",
            f"Interesting question! I understand you're asking about \"{user_message[:40]}{'...' if len(user_message) > 40 else ''}\". Let me think about this... Could you provide a bit more context so I can give you a more accurate answer?",
            f"Good question! To give you the best answer about \"{user_message[:40]}{'...' if len(user_message) > 40 else ''}\", I'd need a bit more information. What specific aspect would you like to know more about?",
        ]
        return random.choice(question_responses)
    
    # Default contextual responses
    default_responses = [
        f"I understand you're talking about \"{user_message[:50]}{'...' if len(user_message) > 50 else ''}\". That's interesting! How can I help you with this?",
        f"Thanks for sharing that! Regarding \"{user_message[:50]}{'...' if len(user_message) > 50 else ''}\", I'm here to assist. What would you like to know more about?",
        f"Got it! You mentioned \"{user_message[:50]}{'...' if len(user_message) > 50 else ''}\". I can help you with this. What specific aspect would you like to explore?",
        f"I see! About \"{user_message[:50]}{'...' if len(user_message) > 50 else ''}\" - that's something I can help with. What would you like to do next?",
        f"Interesting! You're asking about \"{user_message[:50]}{'...' if len(user_message) > 50 else ''}\". Let me help you with that. Could you provide a bit more detail?",
    ]
    
    return random.choice(default_responses)


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """Delete a conversation and all its messages."""
    conversation = session.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Delete all messages in the conversation
    statement = select(Message).where(Message.conversation_id == conversation_id)
    messages = session.exec(statement).all()
    for message in messages:
        session.delete(message)
    
    # Delete the conversation
    session.delete(conversation)
    session.commit()
    
    return {"message": "Conversation deleted successfully"}


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
