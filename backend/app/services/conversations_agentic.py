"""
Agentic conversation processing using Google ADK agents.

This module provides an alternative to LangGraph-based conversation processing,
using Google ADK agents defined in YAML/JSON declarations. Each agent execution
step includes activity status callbacks for real-time UI updates.

Usage:
    To use this instead of LangGraph-based processing in response_worker.py:
    
    Replace:
        from app.services.langgraph_service import process_conversation
        
        result = await process_conversation(...)
    
    With:
        from app.services.conversations_agentic import process_conversation_agentic
        
        result = await process_conversation_agentic(...)
    
    Both functions have the same signature and return format, making it a drop-in replacement.

Agent Mapping:
    - "ask" -> general_agent.yaml
    - "plan" -> general_agent.yaml
    - "observability_ag" -> splunk_agent.yaml
    - "analysis_ag" -> api_discovery_agent.yaml
    - Additional agents can be added to AGENT_MAP

Activity Callbacks:
    Every agent execution step automatically sends activity status updates via WebSocket:
    - Agent selection
    - Agent loading
    - Workflow execution
    - Individual step execution (start/completion)
    - Response extraction
    - Error handling

Configuration:
    Set environment variables for Google ADK:
    - GOOGLE_API_KEY or GEMINI_API_KEY: API key for Google Generative AI
    - GOOGLE_MODEL: Model name (default: "gemini-pro")
    - GOOGLE_TEMPERATURE: Temperature (default: 0.7)
    - GOOGLE_MAX_TOKENS: Max tokens (default: 2048)
    - GOOGLE_USE_VERTEX_AI: Use Vertex AI (default: false)
    - GOOGLE_PROJECT_ID: GCP project ID (for Vertex AI)
    - GOOGLE_LOCATION: GCP location (default: "us-central1")
    - GOOGLE_APPLICATION_CREDENTIALS: Path to credentials file (for Vertex AI)
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import asyncio

# Add agent-toolkit to path
AGENT_TOOLKIT_PATH = Path(__file__).parent.parent.parent.parent / "agent-toolkit" / "src"
if str(AGENT_TOOLKIT_PATH) not in sys.path:
    sys.path.insert(0, str(AGENT_TOOLKIT_PATH))

try:
    from agent_wrapper import AgentWrapper
    from declaration_parser import AgentDeclaration
    from google_adk_client import GoogleADKConfig
    AGENT_TOOLKIT_AVAILABLE = True
except ImportError as e:
    AGENT_TOOLKIT_AVAILABLE = False
    print(f"⚠️ Agent Toolkit not available: {e}")
    print(f"   Path checked: {AGENT_TOOLKIT_PATH}")

from app.services.websocket_manager import websocket_manager
from app.core.config import settings


# Map agent names to agent YAML files
AGENT_MAP = {
    "ask": "general_agent.yaml",
    "plan": "general_agent.yaml",  # Can be replaced with a dedicated plan agent
    "observability_ag": "splunk_agent.yaml",
    "analysis_ag": "api_discovery_agent.yaml",
    "splunk": "splunk_agent.yaml",
    "email_builder": "email_builder_agent.yaml",
    "api_discovery": "api_discovery_agent.yaml",
    "general": "general_agent.yaml",
    "selector": "selector_agent.yaml",
    "response_builder": "response_builder_agent.yaml",
}

# Base path for agent declarations
AGENT_DECLARATIONS_PATH = Path(__file__).parent.parent.parent.parent / "agent-toolkit" / "examples"


class AgenticConversationProcessor:
    """Process conversations using Google ADK agents with activity callbacks."""
    
    def __init__(self):
        """Initialize the agentic conversation processor."""
        if not AGENT_TOOLKIT_AVAILABLE:
            raise RuntimeError("Agent Toolkit not available. Please install required dependencies.")
        
        # Initialize Google ADK configuration
        google_adk_config = {
            "api_key": os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
            "model_name": os.getenv("GOOGLE_MODEL", "gemini-pro"),
            "temperature": float(os.getenv("GOOGLE_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("GOOGLE_MAX_TOKENS", "2048")),
            "use_vertex_ai": os.getenv("GOOGLE_USE_VERTEX_AI", "false").lower() == "true",
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "location": os.getenv("GOOGLE_LOCATION", "us-central1"),
            "credentials_path": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        }
        
        # Initialize agent wrapper with activity callback registry
        self.agent_wrapper = AgentWrapper(google_adk_config=google_adk_config)
        
        # Register custom action with activity callback wrapper
        self._register_activity_callbacks()
    
    def _register_activity_callbacks(self):
        """Register activity callbacks for all agent actions."""
        # Wrap existing actions to add activity callbacks
        original_actions = {
            "llm_generate": self.agent_wrapper._action_llm_generate,
            "llm_chat": self.agent_wrapper._action_llm_chat,
            "llm_stream": self.agent_wrapper._action_llm_stream,
        }
        
        # Create wrapped versions with activity callbacks
        async def wrapped_llm_generate(conversation_id: int, *args, **kwargs):
            """LLM generate with activity callback."""
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Generating response with LLM...",
                details={"step": "llm_generation", "action": "llm_generate"}
            )
            await asyncio.sleep(0.5)  # Brief delay for visibility
            return await original_actions["llm_generate"](*args, **kwargs)
        
        async def wrapped_llm_chat(conversation_id: int, *args, **kwargs):
            """LLM chat with activity callback."""
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Chatting with LLM...",
                details={"step": "llm_chat", "action": "llm_chat"}
            )
            await asyncio.sleep(0.5)
            return await original_actions["llm_chat"](*args, **kwargs)
        
        async def wrapped_llm_stream(conversation_id: int, *args, **kwargs):
            """LLM stream with activity callback."""
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Streaming LLM response...",
                details={"step": "llm_streaming", "action": "llm_stream"}
            )
            await asyncio.sleep(0.5)
            return await original_actions["llm_stream"](*args, **kwargs)
        
        # Store wrapped actions (we'll use these in the workflow execution)
        self.wrapped_actions = {
            "llm_generate": wrapped_llm_generate,
            "llm_chat": wrapped_llm_chat,
            "llm_stream": wrapped_llm_stream,
        }
    
    def _get_agent_file_path(self, agent_name: str) -> Optional[Path]:
        """Get the file path for an agent declaration."""
        agent_file = AGENT_MAP.get(agent_name.lower())
        if not agent_file:
            print(f"⚠️ Unknown agent: {agent_name}, using 'general'")
            agent_file = AGENT_MAP.get("general")
        
        if not agent_file:
            return None
        
        agent_path = AGENT_DECLARATIONS_PATH / agent_file
        if not agent_path.exists():
            print(f"⚠️ Agent file not found: {agent_path}")
            return None
        
        return agent_path
    
    async def process_conversation(
        self,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        thinking_mode: str = "thinking",
        agent: str = "ask"
    ) -> Dict[str, Any]:
        """
        Process a conversation turn using Google ADK agents.
        
        This is the main entry point that matches the signature and return format
        of the LangGraph-based `process_conversation` function.
        
        Args:
            user_message: Current user message
            conversation_id: ID of the conversation
            conversation_history: Previous messages in format:
                [{"role": "user|assistant", "content": "...", "blocks": [...]}, ...]
            thinking_mode: Thinking mode ("thinking" or "deep_thinking")
            agent: Agent name ("ask", "plan", "observability_ag", "analysis_ag", etc.)
        
        Returns:
            Dict[str, Any]: Response with same format as LangGraph version:
                {
                    "content": str,  # Response text
                    "blocks": List[Dict],  # UI blocks (charts, code, etc.)
                    "error": Optional[str],  # Error message if any
                    "thinking_mode": str,  # Thinking mode used
                    "agent": str  # Agent used
                }
        """
        try:
            # Broadcast activity: Agent selection
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity=f"Agent: {agent}",
                details={"agent": agent, "thinking_mode": thinking_mode, "step": "agent_selection"}
            )
            await asyncio.sleep(1.0)
            
            # Load agent declaration
            agent_path = self._get_agent_file_path(agent)
            if not agent_path:
                return {
                    "content": f"Error: Agent '{agent}' not found or not configured.",
                    "blocks": [],
                    "error": f"Agent '{agent}' not found",
                    "thinking_mode": thinking_mode,
                    "agent": agent
                }
            
            # Broadcast activity: Loading agent
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity=f"Loading {agent} agent...",
                details={"agent": agent, "step": "agent_loading", "file": str(agent_path)}
            )
            await asyncio.sleep(0.5)
            
            # Parse agent declaration
            agent_declaration = self.agent_wrapper.load_agent(agent_path)
            
            # Prepare context for agent execution
            # Convert conversation history to agent context format
            context = {
                "user_message": user_message,
                "user_prompt": user_message,  # Some agents use this key
                "conversation_history": conversation_history,
                "conversation_id": conversation_id,
                "thinking_mode": thinking_mode,
                "agent": agent,
            }
            
            # Add message history as context
            if conversation_history:
                context["messages"] = [
                    {"role": msg.get("role"), "content": msg.get("content", "")}
                    for msg in conversation_history[-5:]  # Last 5 messages for context
                ]
            
            # Broadcast activity: Executing agent workflow
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity=f"Executing {agent} workflow...",
                details={"agent": agent, "step": "workflow_execution"}
            )
            await asyncio.sleep(0.5)
            
            # Execute agent with activity callbacks
            result = await self._execute_agent_with_callbacks(
                agent_declaration=agent_declaration,
                context=context,
                conversation_id=conversation_id
            )
            
            # Extract response content and blocks from agent result
            # Also pass conversation_id for potential RAG/OpenSearch operations
            content, blocks = await self._extract_response_from_agent_result(
                result, agent, conversation_id, user_message, conversation_history
            )
            
            # Broadcast activity: Response ready
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Response ready",
                details={"agent": agent, "step": "response_complete"}
            )
            await asyncio.sleep(0.3)
            
            return {
                "content": content,
                "blocks": blocks,
                "error": result.get("error"),
                "thinking_mode": thinking_mode,
                "agent": agent
            }
            
        except Exception as e:
            print(f"❌ Error processing conversation with agent {agent}: {e}")
            import traceback
            print(traceback.format_exc())
            
            # Broadcast error activity
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity=f"Error in {agent} agent",
                details={"agent": agent, "step": "error", "error": str(e)}
            )
            
            return {
                "content": f"I encountered an error processing your request: {str(e)}",
                "blocks": [],
                "error": str(e),
                "thinking_mode": thinking_mode,
                "agent": agent
            }
    
    async def _execute_agent_with_callbacks(
        self,
        agent_declaration: AgentDeclaration,
        context: Dict[str, Any],
        conversation_id: int
    ) -> Dict[str, Any]:
        """
        Execute agent workflow with activity callbacks for each step.
        
        Wraps the workflow engine's execute method to inject activity status updates
        before and after each step execution.
        """
        try:
            # Store original execute_step method
            original_execute_step = self.agent_wrapper.engine._execute_step
            
            # Create wrapped version with activity callbacks
            async def execute_step_with_callbacks(step: Dict[str, Any], execution_context) -> Any:
                """Execute step with activity callbacks."""
                step_name = step.get("name", "unknown")
                step_type = step.get("type", "action")
                step_action = step.get("action", "")
                
                # Broadcast step start
                activity_name = f"Step: {step_name}"
                if step_action:
                    activity_name = f"{step_name} ({step_action})"
                
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity=activity_name,
                    details={
                        "step": step_name,
                        "type": step_type,
                        "action": step_action,
                        "agent": agent_declaration.name
                    }
                )
                await asyncio.sleep(0.3)
                
                # Execute the original step
                result = await original_execute_step(step, execution_context)
                
                # Broadcast step completion
                step_status = result.status.value if hasattr(result, 'status') else "completed"
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity=f"{step_name}: {step_status}",
                    details={
                        "step": step_name,
                        "status": step_status,
                        "action": step_action,
                        "agent": agent_declaration.name
                    }
                )
                await asyncio.sleep(0.2)
                
                return result
            
            # Replace execute_step temporarily
            self.agent_wrapper.engine._execute_step = execute_step_with_callbacks
            
            try:
                # Execute workflow with callbacks
                workflow_data = agent_declaration.workflow.dict()
                if context:
                    workflow_data.setdefault("variables", {}).update(context)
                
                result = await self.agent_wrapper.engine.execute(workflow_data, verbose=True)
                return result
            finally:
                # Restore original method
                self.agent_wrapper.engine._execute_step = original_execute_step
            
        except Exception as e:
            print(f"❌ Error executing agent with callbacks: {e}")
            import traceback
            print(traceback.format_exc())
            return {
                "status": "failed",
                "step_results": {},
                "error": str(e)
            }
    
    async def _extract_response_from_agent_result(
        self,
        result: Dict[str, Any],
        agent: str,
        conversation_id: int,
        user_message: str,
        conversation_history: List[Dict[str, Any]]
    ) -> tuple[str, List[Dict[str, Any]]]:
        """
        Extract response content and blocks from agent execution result.
        
        The agent result may have different structures depending on the agent type.
        This method normalizes it to match the expected format.
        
        For agents that use LLM, we extract the LLM response directly.
        For agents that do RAG/search, we format the results as blocks.
        
        Returns:
            tuple: (content: str, blocks: List[Dict])
        """
        content = ""
        blocks = []
        
        try:
            step_results = result.get("step_results", {})
            
            # Try to find response in step results
            # Look for LLM responses first (most common)
            for step_name, step_result in step_results.items():
                output = step_result.get("output", {})
                
                # Check if output is a dict with response/content
                if isinstance(output, dict):
                    # LLM responses typically have "response" key
                    if "response" in output and output["response"]:
                        content = output["response"] or content
                    elif "content" in output and output["content"]:
                        content = output["content"] or content
                    elif "message" in output and output["message"]:
                        content = output["message"] or content
                    
                    # Check for blocks
                    if "blocks" in output and output["blocks"]:
                        if isinstance(output["blocks"], list):
                            blocks.extend(output["blocks"])
                    elif "data" in output:
                        # Try to extract blocks from data
                        data = output["data"]
                        if isinstance(data, list):
                            blocks.extend(data)
                        elif isinstance(data, dict):
                            if "blocks" in data and isinstance(data["blocks"], list):
                                blocks.extend(data["blocks"])
                            # For RAG/search results, create blocks
                            elif agent in ["api_discovery", "analysis_ag"]:
                                blocks.append({
                                    "type": "code",
                                    "data": {
                                        "code": str(data),
                                        "language": "json",
                                        "title": f"Search Results from {agent}"
                                    }
                                })
                    
                    # For Splunk agents, check for query results
                    if agent in ["splunk", "observability_ag"] and "query" in output:
                        blocks.append({
                            "type": "query",
                            "data": {
                                "query": output["query"],
                                "language": "spl",
                                "title": "Splunk Query"
                            }
                        })
            
            # If no content found, check if we can generate from blocks
            if not content:
                # Check if any step generated useful output
                all_outputs = []
                for step_name, step_result in step_results.items():
                    output = step_result.get("output", {})
                    if isinstance(output, dict) and "response" in output:
                        all_outputs.append(output["response"])
                    elif isinstance(output, str):
                        all_outputs.append(output)
                
                if all_outputs:
                    content = "\n\n".join(filter(None, all_outputs))
                elif result.get("status") == "completed":
                    content = f"Agent '{agent}' completed successfully."
                elif result.get("status") == "partial":
                    content = f"Agent '{agent}' completed with some steps skipped."
                elif result.get("status") == "failed":
                    error = result.get("error", "Unknown error")
                    content = f"Agent '{agent}' encountered an error: {error}"
                else:
                    content = f"Agent '{agent}' execution completed."
            
            # Ensure blocks is a list
            if not isinstance(blocks, list):
                blocks = []
            
            # For agents that need to call external services (RAG, Splunk), 
            # we should handle them here if not already done in the agent
            if agent in ["api_discovery", "analysis_ag"] and not blocks:
                # These agents should have done RAG search, but if not, create placeholder
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity="No search results found",
                    details={"agent": agent, "step": "response_extraction"}
                )
            
            return content, blocks
            
        except Exception as e:
            print(f"⚠️ Error extracting response from agent result: {e}")
            import traceback
            print(traceback.format_exc())
            return content or "Response generated successfully.", blocks


# Global processor instance
_processor_instance: Optional[AgenticConversationProcessor] = None


async def process_conversation_agentic(
    user_message: str,
    conversation_id: int,
    conversation_history: List[Dict[str, Any]],
    thinking_mode: str = "thinking",
    agent: str = "ask"
) -> Dict[str, Any]:
    """
    Process a conversation using Google ADK agents (global function wrapper).
    
    This function has the same signature as the LangGraph-based `process_conversation`
    function, allowing it to be used as a drop-in replacement.
    
    Args:
        user_message: Current user message
        conversation_id: ID of the conversation
        conversation_history: Previous messages
        thinking_mode: Thinking mode ("thinking" or "deep_thinking")
        agent: Agent name ("ask", "plan", "observability_ag", "analysis_ag", etc.)
    
    Returns:
        Dict[str, Any]: Response with same format as LangGraph version
    """
    global _processor_instance
    
    if not AGENT_TOOLKIT_AVAILABLE:
        return {
            "content": "Agent Toolkit not available. Please install required dependencies.",
            "blocks": [],
            "error": "Agent Toolkit not available",
            "thinking_mode": thinking_mode,
            "agent": agent
        }
    
    if _processor_instance is None:
        try:
            _processor_instance = AgenticConversationProcessor()
        except Exception as e:
            print(f"❌ Failed to initialize AgenticConversationProcessor: {e}")
            return {
                "content": f"Failed to initialize agent processor: {str(e)}",
                "blocks": [],
                "error": str(e),
                "thinking_mode": thinking_mode,
                "agent": agent
            }
    
    return await _processor_instance.process_conversation(
        user_message=user_message,
        conversation_id=conversation_id,
        conversation_history=conversation_history,
        thinking_mode=thinking_mode,
        agent=agent
    )

