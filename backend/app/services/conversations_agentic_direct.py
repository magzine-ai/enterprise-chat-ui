"""
Direct agent implementation using Google ADK (without agent-toolkit).

This module implements agents directly in Python code, using Google ADK for LLM
operations and supporting RAG integration with OpenSearch. Each agent sends
activity status updates via WebSocket for real-time UI feedback.

Shared Framework Support:
    This module now supports using the shared framework (smart_sdk) that wraps
    ADKLlmAgent from google.adk.agents. To enable:
    
    1. Set environment variable: USE_SHARED_FRAMEWORK=true
    2. Ensure smart_sdk is installed or available in the path
    3. Configure shared framework settings via SharedAgentConfig
    
    The shared framework provides:
    - Built-in memory support
    - Human-in-the-loop with ask_user tool
    - Advanced tool management (tool_choice)
    - Reflection on tool use
    - Structured output support
    - Sub-agent support
    
    If shared framework is not available, falls back to direct GoogleADKClient usage.
    
    Example: Using shared framework for an agent:
        from smart_sdk.agents.base_agent import Model, Tool
        
        # Create shared config
        shared_config = SharedAgentConfig(
            human_in_the_loop=True,
            use_memory=True,
            tool_choice="auto"
        )
        
        # Initialize agent with shared framework
        agent = EmailGeneratorAgent(
            use_shared_framework=True,
            shared_config=shared_config,
            system_message="You are an expert email writer.",
            model=Model(...),  # From smart_sdk
            tools=[...]  # List of Tool from smart_sdk
        )
"""

import os
import json
import re
import asyncio
import textwrap
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

# Google ADK imports
try:
    import sys
    from pathlib import Path
    
    # Add agent-toolkit to path for Google ADK client only
    # Path from: backend/app/services/conversations_agentic_direct.py
    # To: agent-toolkit/src/google_adk_client.py
    AGENT_TOOLKIT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "agent-toolkit" / "src"
    if str(AGENT_TOOLKIT_PATH.resolve()) not in [str(Path(p).resolve()) for p in sys.path]:
        sys.path.insert(0, str(AGENT_TOOLKIT_PATH.resolve()))
    
    from google_adk_client import GoogleADKClient, GoogleADKConfig
    GOOGLE_ADK_AVAILABLE = True
except ImportError as e:
    GOOGLE_ADK_AVAILABLE = False
    print(f"⚠️ Google ADK not available: {e}")
    import traceback
    print(traceback.format_exc())

# Shared Framework imports (smart_sdk with ADKLlmAgent)
try:
    import sys
    from pathlib import Path
    import textwrap
    
    # Try to import shared framework components
    # Adjust path based on where smart_sdk is located in your environment
    # Common locations: parent directory, installed package, or environment variable
    SHARED_FRAMEWORK_PATHS = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "smart_sdk",
        Path(__file__).resolve().parent.parent.parent.parent / "smart_sdk",
        Path(os.getenv("SMART_SDK_PATH", "")),
    ]
    
    SHARED_FRAMEWORK_AVAILABLE = False
    for framework_path in SHARED_FRAMEWORK_PATHS:
        if framework_path and framework_path.exists():
            if str(framework_path.resolve()) not in [str(Path(p).resolve()) for p in sys.path]:
                sys.path.insert(0, str(framework_path.resolve()))
            try:
                from google.adk.agents import LlmAgent as ADKLlmAgent
                from smart_sdk.agents.base_agent import BaseAgent as SharedBaseAgent
                from smart_sdk.agents.base_agent import AgentConfig, Model, Tool, ask_user, ToolContext
                SHARED_FRAMEWORK_AVAILABLE = True
                print(f"✅ Shared framework (smart_sdk) loaded from: {framework_path}")
                break
            except ImportError:
                continue
    
    if not SHARED_FRAMEWORK_AVAILABLE:
        # Try direct import (if smart_sdk is installed as package)
        try:
            from google.adk.agents import LlmAgent as ADKLlmAgent
            from smart_sdk.agents.base_agent import BaseAgent as SharedBaseAgent
            from smart_sdk.agents.base_agent import AgentConfig, Model, Tool, ask_user, ToolContext
            SHARED_FRAMEWORK_AVAILABLE = True
            print("✅ Shared framework (smart_sdk) loaded from installed package")
        except ImportError:
            SHARED_FRAMEWORK_AVAILABLE = False
            print("⚠️ Shared framework (smart_sdk) not available. Using direct GoogleADKClient.")
            
except Exception as e:
    SHARED_FRAMEWORK_AVAILABLE = False
    print(f"⚠️ Shared framework not available: {e}")
    ADKLlmAgent = None
    SharedBaseAgent = None
    AgentConfig = None
    Model = None
    Tool = None
    ask_user = None
    ToolContext = None

from app.services.websocket_manager import websocket_manager
from app.services.opensearch_service import opensearch_service
from app.services.approval_manager import approval_manager
from app.core.config import settings
import uuid

# Environment variable to enable shared framework
USE_SHARED_FRAMEWORK_ENV = os.getenv("USE_SHARED_FRAMEWORK", "false").lower() == "true"


class AgentStatus(Enum):
    """Agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Result from agent execution."""
    content: str
    blocks: List[Dict[str, Any]]
    status: AgentStatus
    metadata: Dict[str, Any]
    error: Optional[str] = None


@dataclass
class SharedAgentConfig:
    """Configuration for shared framework agent wrapper."""
    """Configuration matching AgentConfig from smart_sdk.agents.base_agent"""
    structure_output: bool = False
    reflect_on_tool_use: bool = True
    prompt_mode: bool = False
    tool_call_summary_format: str = "default"
    output_key: Optional[str] = None
    include_history: str = "default"  # 'default' or 'none'
    global_instructions: Optional[str] = None
    use_memory: bool = False
    memory_config: Optional[Dict[str, Any]] = None
    human_in_the_loop: bool = False
    tool_choice: str = "auto"  # 'required', 'auto', 'none', or tool name
    generation_config: Optional[Dict[str, Any]] = None


class SharedFrameworkAgentWrapper:
    """
    Wrapper around shared framework (smart_sdk) that uses ADKLlmAgent.
    
    This class bridges the shared framework with the current agent implementation,
    providing access to advanced features like memory, human-in-the-loop, tool management, etc.
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        system_message: str,
        model: Optional[Any] = None,
        tools: Optional[List[Any]] = None,
        config: Optional[SharedAgentConfig] = None
    ):
        """
        Initialize shared framework agent wrapper.
        
        Args:
            name: Agent name
            description: Agent description
            system_message: System message/instructions
            model: Model instance from smart_sdk
            tools: List of Tool instances from smart_sdk
            config: Shared agent configuration
        """
        if not SHARED_FRAMEWORK_AVAILABLE:
            raise RuntimeError(
                "Shared framework not available. Please ensure smart_sdk is installed."
            )
        
        self.name = name
        self.description = description
        self.system_message = system_message
        self.model = model
        self.tools = tools or []
        self.config = config or SharedAgentConfig()
        self._adk_agent: Optional[ADKLlmAgent] = None
        
        # Handle memory, human-in-the-loop, tool choice
        self._handle_memory()
        self._handle_human_in_the_loop()
        self._handle_tool_choice()
    
    def _create_adk_agent(self) -> ADKLlmAgent:
        """Create and return the underlying ADK LlmAgent instance."""
        if self._adk_agent:
            return self._adk_agent
        
        model_kwargs = {}
        if self.config.structure_output:
            model_kwargs["response_format"] = {"type": "json_object"}
        
        # Create model client if model is provided
        model_client = None
        if self.model:
            if hasattr(self.model, 'create_model_client'):
                model_client = self.model.create_model_client(**model_kwargs)
            else:
                model_client = self.model
        
        # Process tools
        processed_tools = self.tools
        if hasattr(self, 'process_tools'):
            processed_tools = self.process_tools(self.tools)
        
        self._adk_agent = ADKLlmAgent(
            name=self.name,
            description=self.description,
            instruction=self.system_message,
            model=model_client,
            tools=processed_tools,
            sub_agents=[],
            output_key=self.config.output_key,
            include_contents=self.config.include_history,
            global_instruction=self.config.global_instructions
        )
        
        # Handle reflection callback
        if not self.config.reflect_on_tool_use:
            self._adk_agent.after_tool_callback = self._disable_reflection_callback
        
        return self._adk_agent
    
    def _handle_memory(self):
        """Add memory tool to self.tools if configured to use global memory."""
        if self.config.memory_config and self.config.memory_config.get("use_global_memory"):
            try:
                from google.adk.tools import load_memory
                self.tools.append(load_memory)
            except ImportError:
                print("⚠️ Memory tool not available")
    
    def _handle_human_in_the_loop(self):
        """Add ask_user tool and update global instructions if human-in-the-loop is enabled."""
        if self.config.human_in_the_loop and ask_user:
            self.tools.append(ask_user)
            
            # Update global instructions
            hitl_instructions = textwrap.dedent("""
            CRITICALLY IMPORTANT INSTRUCTION:
            - call ask_user for any user interaction after providing response.
            - you should call `ask_user` when you want to ask for any clarification, confirmation or approval from user
            - you MUST call `ask_user` tool when you want to ask anything.
            """)
            
            if self.config.global_instructions:
                self.config.global_instructions = self.config.global_instructions + hitl_instructions
            else:
                self.config.global_instructions = hitl_instructions
    
    def _handle_tool_choice(self):
        """Handle the logic for setting the model's tool_choice completion argument."""
        if self.model and hasattr(self.model, 'completion_args'):
            tool_choice = self.config.tool_choice
            
            if self.tools:
                if tool_choice == "required":
                    if not self.tools:
                        raise ValueError("Tool choice is 'required' but no tools are available")
                    self.model.completion_args["tool_choice"] = "required"
                    self.config.reflect_on_tool_use = False
                elif tool_choice in (None, "auto"):
                    # Auto is default, not all models support tool_choice
                    self.model.completion_args.pop("tool_choice", None)
                elif tool_choice == "none":
                    self.model.completion_args["tool_choice"] = "none"
                elif isinstance(tool_choice, str):
                    # Specific tool name
                    tool_found = False
                    for tool in self.tools:
                        tool_name = getattr(tool, "tool_name", None) or \
                                   getattr(tool, "__name__", None) or \
                                   getattr(tool, "name", None)
                        if tool_name == tool_choice:
                            self.model.completion_args["tool_choice"] = {
                                "type": "function",
                                "function": {"name": tool_choice}
                            }
                            self.config.reflect_on_tool_use = False
                            tool_found = True
                            break
                    
                    if not tool_found:
                        raise ValueError(f"Tool '{tool_choice}' not found in available tools")
            else:
                # No tools available
                self.model.completion_args.pop("tool_choice", None)
    
    def _disable_reflection_callback(self, tool, args, tool_context: ToolContext, tool_response):
        """Callback function to disable reflection on tool use."""
        if hasattr(tool_context, 'actions'):
            tool_context.actions.skip_summarization = True
    
    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Generate text using shared framework ADK agent.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt/instructions
            context: Conversation context
            
        Returns:
            Generated text response
        """
        adk_agent = self._create_adk_agent()
        
        # Prepare messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": prompt})
        
        # Execute using shared framework
        try:
            response = await adk_agent.run(messages=messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            print(f"⚠️ Error in shared framework generate_text: {e}")
            raise
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Chat with shared framework ADK agent.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: System prompt/instructions
            
        Returns:
            Chat response
        """
        adk_agent = self._create_adk_agent()
        
        # Prepare messages
        chat_messages = messages.copy()
        if system_prompt:
            # Add system message at the beginning if not present
            if not any(msg.get("role") == "system" for msg in chat_messages):
                chat_messages.insert(0, {"role": "system", "content": system_prompt})
        
        # Execute using shared framework
        try:
            response = await adk_agent.run(messages=chat_messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            print(f"⚠️ Error in shared framework chat: {e}")
            raise


class BaseAgent:
    """
    Base class for all agents.
    
    Supports both direct GoogleADKClient usage and shared framework (smart_sdk) integration.
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        google_adk_client: Optional[GoogleADKClient] = None,
        use_shared_framework: bool = False,
        shared_config: Optional[SharedAgentConfig] = None,
        system_message: Optional[str] = None,
        model: Optional[Any] = None,  # Model from smart_sdk
        tools: Optional[List[Any]] = None  # List of Tool from smart_sdk
    ):
        """
        Initialize base agent.
        
        Args:
            name: Agent name
            description: Agent description
            google_adk_client: Google ADK client instance (for direct mode)
            use_shared_framework: Whether to use shared framework (smart_sdk)
            shared_config: Configuration for shared framework
            system_message: System message/instructions for shared framework
            model: Model instance from smart_sdk (for shared framework)
            tools: List of Tool instances from smart_sdk (for shared framework)
        """
        self.name = name
        self.description = description
        self.use_shared_framework = use_shared_framework and SHARED_FRAMEWORK_AVAILABLE
        self.shared_config = shared_config or SharedAgentConfig()
        self.system_message = system_message or description
        
        if self.use_shared_framework:
            # Initialize shared framework agent
            self._init_shared_framework(model, tools)
            self.adk_client = None  # Not used in shared framework mode
        else:
            # Use direct GoogleADKClient (existing approach)
            self.adk_client = google_adk_client
            self.shared_agent = None
            self._adk_agent = None
    
    def _init_shared_framework(self, model: Optional[Any], tools: Optional[List[Any]]):
        """Initialize shared framework agent wrapper."""
        if not SHARED_FRAMEWORK_AVAILABLE:
            raise RuntimeError(
                "Shared framework not available. Set use_shared_framework=False or install smart_sdk."
            )
        
        # Create shared framework agent instance
        self.shared_agent = SharedFrameworkAgentWrapper(
            name=self.name,
            description=self.description,
            system_message=self.system_message,
            model=model,
            tools=tools or [],
            config=self.shared_config
        )
        self._adk_agent = None  # Will be created on first use
    
    async def execute(
        self,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        **kwargs
    ) -> AgentResult:
        """
        Execute the agent.
        
        Args:
            user_message: User's message
            conversation_id: Conversation ID for activity updates
            conversation_history: Previous messages
            **kwargs: Additional context
            
        Returns:
            AgentResult with content, blocks, and metadata
        """
        raise NotImplementedError("Subclasses must implement execute()")
    
    async def _send_activity(
        self,
        conversation_id: int,
        activity: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Send activity status update."""
        await websocket_manager.send_activity_status(
            conversation_id=conversation_id,
            activity=activity,
            details={
                "agent": self.name,
                **(details or {})
            }
        )
        await asyncio.sleep(0.3)  # Brief delay for visibility
    
    async def _generate_with_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Generate text using either shared framework or direct Google ADK client.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt/instructions
            context: Conversation context (list of message dicts)
            
        Returns:
            Generated text response
        """
        if self.use_shared_framework and self.shared_agent:
            # Use shared framework
            return await self.shared_agent.generate_text(
                prompt=prompt,
                system_prompt=system_prompt or self.system_message,
                context=context or []
            )
        else:
            # Use direct GoogleADKClient (existing approach)
            if not self.adk_client:
                raise RuntimeError("Google ADK client not initialized")
            
            return await self.adk_client.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
                stream=False
            )
    
    async def _chat_with_llm(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Chat with LLM using either shared framework or direct Google ADK client.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: System prompt/instructions
            
        Returns:
            Chat response
        """
        if self.use_shared_framework and self.shared_agent:
            # Use shared framework
            return await self.shared_agent.chat(
                messages=messages,
                system_prompt=system_prompt or self.system_message
            )
        else:
            # Use direct GoogleADKClient
            if not self.adk_client:
                raise RuntimeError("Google ADK client not initialized")
            
            return await self.adk_client.chat(
                messages=messages,
                system_prompt=system_prompt,
                stream=False
            )


class CodeSearchRAGAgent(BaseAgent):
    """Agent that searches code repository using RAG and generates responses."""
    
    def __init__(self, google_adk_client: Optional[GoogleADKClient] = None):
        super().__init__(
            name="code_search_rag",
            description="Searches code repository using RAG with OpenSearch",
            google_adk_client=google_adk_client
        )
    
    async def execute(
        self,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        opensearch_index: Optional[str] = None,
        max_results: int = 10,
        **kwargs
    ) -> AgentResult:
        """Execute code search with RAG."""
        try:
            # Determine OpenSearch index to use
            if not opensearch_index:
                # Use Java code chunks index if available, otherwise fall back to general index
                opensearch_index = settings.java_opensearch_index if settings.java_opensearch_enabled else settings.opensearch_index
            
            if not opensearch_index:
                return AgentResult(
                    content="OpenSearch is not configured. Please configure OPENSEARCH_INDEX or JAVA_OPENSEARCH_INDEX.",
                    blocks=[],
                    status=AgentStatus.FAILED,
                    metadata={"agent": self.name},
                    error="OpenSearch index not configured"
                )
            
            # Step 1: Optimize search query
            await self._send_activity(
                conversation_id,
                "Optimizing search query...",
                {"step": "query_optimization"}
            )
            
            optimization_prompt = f"""
            Convert this user question into an optimized search query for code repository search:
            
            Question: "{user_message}"
            
            Generate search terms that would help find relevant code, methods, classes, or documentation.
            Focus on: method names, class names, functionality keywords, technical terms.
            Return only the search query, no explanations.
            """
            
            search_query = await self._generate_with_llm(
                prompt=optimization_prompt,
                system_prompt="You are a code search query optimizer."
            )
            
            # Step 2: RAG Search in OpenSearch
            await self._send_activity(
                conversation_id,
                "RAG: Searching code repository...",
                {"step": "rag_search", "query": search_query[:50], "index": opensearch_index}
            )
            
            rag_results = await self._search_code_rag(
                query=search_query,
                index=opensearch_index,
                max_results=max_results,
                conversation_id=conversation_id
            )
            
            # Step 3: Generate answer with context
            await self._send_activity(
                conversation_id,
                "Generating answer from code search...",
                {"step": "answer_generation", "results_count": len(rag_results.get("results", []))}
            )
            
            # Format RAG results for LLM context
            context_text = self._format_rag_results_for_llm(rag_results.get("results", []))
            
            answer_prompt = f"""
            Answer the user's question using the following code search results from the repository:
            
            User Question: {user_message}
            
            Relevant Code Found:
            {context_text}
            
            Provide a comprehensive answer that:
            1. Directly answers the question
            2. References specific code examples when helpful
            3. Includes file paths and method/class names
            4. Explains the code in context
            """
            
            answer = await self._generate_with_llm(
                prompt=answer_prompt,
                system_prompt="You are a code documentation expert. Provide clear, accurate answers with code examples and references."
            )
            
            # Step 4: Format response with blocks
            blocks = self._create_code_blocks(rag_results.get("results", []))
            
            await self._send_activity(
                conversation_id,
                "Code search complete",
                {"step": "complete", "blocks_count": len(blocks)}
            )
            
            return AgentResult(
                content=answer,
                blocks=blocks,
                status=AgentStatus.COMPLETED,
                metadata={
                    "agent": self.name,
                    "results_count": len(rag_results.get("results", [])),
                    "sources": rag_results.get("sources", [])
                }
            )
            
        except Exception as e:
            await self._send_activity(
                conversation_id,
                f"Error in code search: {str(e)[:50]}",
                {"step": "error", "error": str(e)}
            )
            return AgentResult(
                content=f"Error during code search: {str(e)}",
                blocks=[],
                status=AgentStatus.FAILED,
                metadata={"agent": self.name},
                error=str(e)
            )
    
    async def _search_code_rag(
        self,
        query: str,
        index: str,
        max_results: int,
        conversation_id: int
    ) -> Dict[str, Any]:
        """Search code in OpenSearch using RAG."""
        if not opensearch_service.is_available():
            return {"results": [], "sources": []}
        
        try:
            # Use OpenSearch service for code search
            if not opensearch_service.client:
                return {"results": [], "sources": []}
            
            search_body = {
                "size": max_results,
                "query": {
                    "bool": {
                        "should": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["code^2", "summary", "fqn", "file_path"],
                                    "type": "best_fields"
                                }
                            }
                        ]
                    }
                },
                "_source": [
                    "chunk_id", "type", "fqn", "file_path", "code", "summary",
                    "start_line", "end_line", "filetype", "module"
                ]
            }
            
            # Execute search
            response = opensearch_service.client.search(
                index=index,
                body=search_body
            )
            
            hits = response.get("hits", {}).get("hits", [])
            
            results = []
            sources = []
            
            for hit in hits:
                source = hit.get("_source", {})
                results.append({
                    "chunk_id": hit.get("_id"),
                    "type": source.get("type", "unknown"),
                    "fqn": source.get("fqn", ""),
                    "file_path": source.get("file_path", ""),
                    "code": source.get("code", ""),
                    "summary": source.get("summary", ""),
                    "start_line": source.get("start_line"),
                    "end_line": source.get("end_line"),
                    "filetype": source.get("filetype"),
                    "score": hit.get("_score", 0)
                })
                
                sources.append({
                    "chunk_id": hit.get("_id"),
                    "file_path": source.get("file_path", ""),
                    "fqn": source.get("fqn", ""),
                    "type": source.get("type", ""),
                    "score": hit.get("_score", 0)
                })
            
            return {"results": results, "sources": sources}
            
        except Exception as e:
            print(f"❌ Error in RAG code search: {e}")
            import traceback
            print(traceback.format_exc())
            return {"results": [], "sources": [], "error": str(e)}
    
    def _format_rag_results_for_llm(self, results: List[Dict[str, Any]]) -> str:
        """Format RAG results for LLM context."""
        if not results:
            return "No code results found."
        
        formatted = []
        for i, result in enumerate(results[:5], 1):  # Top 5 for context
            code_preview = result.get('code', '')[:500]  # Limit code length
            formatted.append(f"""
[{i}] {result.get('fqn', 'Unknown')}
File: {result.get('file_path', 'unknown')}
Type: {result.get('type', 'unknown')}
Code:
{code_preview}
""")
        
        return "\n".join(formatted)
    
    def _create_code_blocks(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create UI blocks from code search results."""
        blocks = []
        
        # Add code blocks for top results
        for result in results[:5]:
            if result.get("code"):
                filetype = result.get("filetype", "java").replace(".", "")
                blocks.append({
                    "type": "code",
                    "data": {
                        "code": result["code"],
                        "language": filetype,
                        "title": f"{result.get('fqn', 'Code')} ({result.get('file_path', 'unknown')})",
                        "metadata": {
                            "chunk_id": result.get("chunk_id"),
                            "type": result.get("type"),
                            "start_line": result.get("start_line"),
                            "end_line": result.get("end_line"),
                            "score": result.get("score")
                        }
                    }
                })
        
        # Add sources table
        if results:
            blocks.append({
                "type": "table",
                "data": {
                    "columns": ["File Path", "FQN", "Type", "Score"],
                    "rows": [
                        [
                            r.get("file_path", ""),
                            r.get("fqn", ""),
                            r.get("type", ""),
                            f"{r.get('score', 0):.2f}"
                        ]
                        for r in results[:10]
                    ],
                    "title": "Code Search Sources"
                }
            })
        
        return blocks


class SplunkAgent(BaseAgent):
    """Agent for Splunk queries and observability."""
    
    def __init__(self, google_adk_client: Optional[GoogleADKClient] = None):
        super().__init__(
            name="splunk",
            description="Handles Splunk queries, log analysis, and observability questions",
            google_adk_client=google_adk_client
        )
    
    async def execute(
        self,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        **kwargs
    ) -> AgentResult:
        """Execute Splunk agent."""
        try:
            # Step 1: Understand query
            await self._send_activity(
                conversation_id,
                "Analyzing Splunk query request...",
                {"step": "query_analysis"}
            )
            
            analysis_prompt = f"""
            Analyze this Splunk-related query and determine:
            1. What type of query is this? (search, dashboard, alert, etc.)
            2. What information is needed?
            3. What Splunk SPL (Search Processing Language) query would be appropriate?
            
            Query: "{user_message}"
            """
            
            analysis = await self._generate_with_llm(
                prompt=analysis_prompt,
                system_prompt="You are a Splunk expert. Help users with Splunk queries and observability questions."
            )
            
            # Step 2: Generate SPL query
            await self._send_activity(
                conversation_id,
                "Generating Splunk SPL query...",
                {"step": "spl_generation"}
            )
            
            spl_prompt = f"""
            Based on the analysis, generate a valid Splunk SPL query.
            
            Analysis: {analysis}
            Original Query: {user_message}
            
            Generate ONLY the SPL query, no explanations.
            """
            
            spl_query = await self._generate_with_llm(
                prompt=spl_prompt,
                system_prompt="You are a Splunk SPL query generator. Generate valid, optimized SPL queries."
            )
            
            # Step 3: Create response with query block
            blocks = [{
                "type": "query",
                "data": {
                    "query": spl_query.strip(),
                    "language": "spl",
                    "title": "Generated Splunk Query",
                    "autoExecute": False
                }
            }]
            
            content = f"I've generated a Splunk query for your request:\n\n{spl_query}\n\n{analysis}"
            
            await self._send_activity(
                conversation_id,
                "Splunk query generated",
                {"step": "complete"}
            )
            
            return AgentResult(
                content=content,
                blocks=blocks,
                status=AgentStatus.COMPLETED,
                metadata={
                    "agent": self.name,
                    "spl_query": spl_query.strip()
                }
            )
            
        except Exception as e:
            await self._send_activity(
                conversation_id,
                f"Error generating Splunk query: {str(e)[:50]}",
                {"step": "error", "error": str(e)}
            )
            return AgentResult(
                content=f"Error generating Splunk query: {str(e)}",
                blocks=[],
                status=AgentStatus.FAILED,
                metadata={"agent": self.name},
                error=str(e)
            )


class GeneralAgent(BaseAgent):
    """General purpose agent for conversations."""
    
    def __init__(self, google_adk_client: Optional[GoogleADKClient] = None):
        super().__init__(
            name="general",
            description="Handles general questions and conversations",
            google_adk_client=google_adk_client
        )
    
    async def execute(
        self,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        **kwargs
    ) -> AgentResult:
        """Execute general agent."""
        try:
            await self._send_activity(
                conversation_id,
                "Generating response...",
                {"step": "llm_generation"}
            )
            
            # Convert conversation history to context format
            context = [
                {"role": msg.get("role"), "content": msg.get("content", "")}
                for msg in conversation_history[-5:]  # Last 5 messages
            ]
            
            # Use _chat_with_llm which supports both shared framework and direct client
            response = await self._chat_with_llm(
                messages=context + [{"role": "user", "content": user_message}],
                system_prompt="You are a helpful AI assistant. Provide clear, accurate, and helpful responses."
            )
            
            await self._send_activity(
                conversation_id,
                "Response ready",
                {"step": "complete"}
            )
            
            return AgentResult(
                content=response if isinstance(response, str) else str(response),
                blocks=[],
                status=AgentStatus.COMPLETED,
                metadata={"agent": self.name}
            )
            
        except Exception as e:
            await self._send_activity(
                conversation_id,
                f"Error: {str(e)[:50]}",
                {"step": "error", "error": str(e)}
            )
            return AgentResult(
                content=f"Error: {str(e)}",
                blocks=[],
                status=AgentStatus.FAILED,
                metadata={"agent": self.name},
                error=str(e)
            )


class EmailGeneratorAgent(BaseAgent):
    """Agent for generating and sending emails with summarization capabilities."""
    
    def __init__(self, google_adk_client: Optional[GoogleADKClient] = None):
        super().__init__(
            name="email_generator",
            description="Generates and sends emails with summarization and content generation",
            google_adk_client=google_adk_client
        )
    
    async def execute(
        self,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        **kwargs
    ) -> AgentResult:
        """Execute email generator agent."""
        try:
            # Step 1: Extract email information from user message
            await self._send_activity(
                conversation_id,
                "Analyzing email request...",
                {"step": "email_analysis"}
            )
            
            # Check if there's context from previous agents (for summarization)
            intermediate_result = kwargs.get("intermediate_result")
            summarization_context = None
            if intermediate_result and isinstance(intermediate_result, AgentResult):
                summarization_context = intermediate_result.content
            
            # Extract email details
            extraction_prompt = f"""
            Extract email information from this user request:
            
            "{user_message}"
            
            {f'Previous context to summarize: {summarization_context}' if summarization_context else ''}
            
            Identify:
            1. Recipients (to, cc, bcc) - email addresses
            2. Subject line
            3. Purpose/type of email (summary, report, notification, request, etc.)
            4. Tone (formal, casual, professional)
            5. Any specific content requirements
            6. Priority level (high, medium, low)
            
            Return JSON format:
            {{
                "recipients": {{"to": ["email@example.com"], "cc": [], "bcc": []}},
                "subject": "Email subject line",
                "purpose": "summary|report|notification|request|other",
                "tone": "formal|casual|professional",
                "priority": "high|medium|low",
                "content_requirements": ["requirement1", "requirement2"],
                "should_summarize": true or false
            }}
            
            If email addresses are not explicitly mentioned, use placeholders like "recipient@example.com".
            Return ONLY valid JSON, no other text.
            """
            
            email_info_json = await self._generate_with_llm(
                prompt=extraction_prompt,
                system_prompt="You are an email information extraction expert. Extract email details accurately and return valid JSON only."
            )
            
            # Parse email info
            import re
            email_info_match = re.search(r'\{.*\}', email_info_json, re.DOTALL)
            if email_info_match:
                email_info = json.loads(email_info_match.group())
            else:
                email_info = json.loads(email_info_json.strip())
            
            # Step 2: Generate email content
            await self._send_activity(
                conversation_id,
                "Generating email content...",
                {"step": "content_generation"}
            )
            
            # Prepare context for email generation
            context_summary = ""
            if summarization_context:
                context_summary = f"\n\nContext to include in email:\n{summarization_context}"
            
            # Also include conversation history for context
            conversation_context = ""
            if conversation_history:
                recent_messages = conversation_history[-3:]  # Last 3 messages
                conversation_context = "\n\nConversation history:\n" + "\n".join([
                    f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
                    for msg in recent_messages
                ])
            
            # Generate email body
            email_prompt = f"""
            Generate a professional email based on the following requirements:
            
            Email Info:
            - To: {email_info.get('recipients', {}).get('to', [])}
            - CC: {email_info.get('recipients', {}).get('cc', [])}
            - Subject: {email_info.get('subject', 'No subject specified')}
            - Purpose: {email_info.get('purpose', 'general')}
            - Tone: {email_info.get('tone', 'professional')}
            - Priority: {email_info.get('priority', 'medium')}
            - Requirements: {email_info.get('content_requirements', [])}
            - Should summarize: {email_info.get('should_summarize', False)}
            
            Original Request: "{user_message}"
            {context_summary}
            {conversation_context}
            
            Generate a complete, well-structured email body that:
            1. {f'Summarizes the provided context concisely and clearly' if email_info.get('should_summarize') else 'Addresses the user\'s request'}
            2. Uses the specified tone ({email_info.get('tone', 'professional')})
            3. Includes all necessary information
            4. Is appropriate for the purpose ({email_info.get('purpose', 'general')})
            5. Has clear structure (greeting, body, closing)
            6. Is concise but complete
            
            Return the email body text only, no subject line, no formatting metadata.
            """
            
            email_body = await self._generate_with_llm(
                prompt=email_prompt,
                system_prompt=f"You are an expert email writer. Write clear, professional emails in {email_info.get('tone', 'professional')} tone."
            )
            
            # Clean up email body
            email_body = email_body.strip()
            
            # Step 3: Generate email subject if not provided or needs improvement
            subject = email_info.get("subject", "")
            if not subject or subject == "No subject specified" or len(subject) < 3:
                await self._send_activity(
                    conversation_id,
                    "Generating email subject...",
                    {"step": "subject_generation"}
                )
                
                subject_prompt = f"""
                Generate a concise, professional email subject line for this email:
                
                Purpose: {email_info.get('purpose', 'general')}
                Body: {email_body[:200]}...
                
                Return ONLY the subject line, no quotes, no labels, just the subject text.
                """
                
                subject = await self._generate_with_llm(
                    prompt=subject_prompt,
                    system_prompt="You are an expert at writing email subject lines. Generate concise, clear subject lines."
                )
                subject = subject.strip().strip('"').strip("'")
            
            # Step 4: Create email preview blocks
            recipients_to = email_info.get("recipients", {}).get("to", [])
            recipients_cc = email_info.get("recipients", {}).get("cc", [])
            recipients_bcc = email_info.get("recipients", {}).get("bcc", [])
            
            # Create email details table
            email_details_rows = [
                ["To", ", ".join(recipients_to) if recipients_to else "recipient@example.com"],
                ["Subject", subject],
                ["Priority", email_info.get("priority", "medium").upper()],
                ["Tone", email_info.get("tone", "professional").capitalize()]
            ]
            
            if recipients_cc:
                email_details_rows.insert(2, ["CC", ", ".join(recipients_cc)])
            if recipients_bcc:
                email_details_rows.insert(3 if recipients_cc else 2, ["BCC", ", ".join(recipients_bcc)])
            
            email_blocks = [
                {
                    "type": "table",
                    "data": {
                        "columns": ["Field", "Value"],
                        "rows": email_details_rows,
                        "title": "📧 Email Details"
                    }
                },
                {
                    "type": "collapsible",
                    "data": {
                        "title": "📝 Email Body",
                        "defaultExpanded": True,
                        "icon": "📝",
                        "children": [{
                            "type": "markdown",
                            "data": {
                                "content": f"## Email Content\n\n{email_body}"
                            }
                        }]
                    }
                }
            ]
            
            # Step 5: Optionally send email if explicitly requested and configured
            email_sent = False
            send_error = None
            
            # Check if sending was explicitly requested
            should_send = kwargs.get("send_email", False) or "send" in user_message.lower()
            
            if should_send:
                await self._send_activity(
                    conversation_id,
                    "Sending email...",
                    {"step": "email_sending"}
                )
                
                # Try to send email
                try:
                    email_sent = await self._send_email(
                        to_addresses=recipients_to,
                        cc_addresses=recipients_cc,
                        bcc_addresses=recipients_bcc,
                        subject=subject,
                        body=email_body
                    )
                    if email_sent:
                        await self._send_activity(
                            conversation_id,
                            "Email sent successfully",
                            {"step": "complete"}
                        )
                except Exception as e:
                    send_error = str(e)
                    print(f"⚠️ Error sending email: {e}")
                    await self._send_activity(
                        conversation_id,
                        f"Email generation complete (send failed: {str(e)[:50]})",
                        {"step": "complete", "send_error": str(e)}
                    )
            
            # Generate response content
            if email_sent:
                content = f"✅ Email sent successfully!\n\n**To:** {', '.join(recipients_to)}\n**Subject:** {subject}\n\n{email_body[:200]}..."
            elif send_error:
                content = f"📧 Email generated successfully, but sending failed.\n\n**Error:** {send_error}\n\n**To:** {', '.join(recipients_to)}\n**Subject:** {subject}\n\nYou can review the email preview below and send it manually."
            else:
                content = f"📧 Email generated successfully!\n\n**To:** {', '.join(recipients_to) if recipients_to else 'recipient@example.com'}\n**Subject:** {subject}\n\nReview the email preview below. The email can be sent after approval."
            
            return AgentResult(
                content=content,
                blocks=email_blocks,
                status=AgentStatus.COMPLETED,
                metadata={
                    "agent": self.name,
                    "email_subject": subject,
                    "email_recipients": {
                        "to": recipients_to,
                        "cc": recipients_cc,
                        "bcc": recipients_bcc
                    },
                    "email_sent": email_sent,
                    "send_error": send_error,
                    "priority": email_info.get("priority", "medium"),
                    "tone": email_info.get("tone", "professional")
                }
            )
            
        except Exception as e:
            await self._send_activity(
                conversation_id,
                f"Error generating email: {str(e)[:50]}",
                {"step": "error", "error": str(e)}
            )
            import traceback
            print(traceback.format_exc())
            return AgentResult(
                content=f"Error generating email: {str(e)}",
                blocks=[],
                status=AgentStatus.FAILED,
                metadata={"agent": self.name},
                error=str(e)
            )
    
    async def _send_email(
        self,
        to_addresses: List[str],
        cc_addresses: List[str],
        bcc_addresses: List[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Send email using SMTP.
        
        Requires environment variables:
        - SMTP_HOST: SMTP server hostname (e.g., smtp.gmail.com)
        - SMTP_PORT: SMTP server port (default: 587)
        - SMTP_USER: SMTP username/email
        - SMTP_PASSWORD: SMTP password or app password
        - SMTP_FROM_EMAIL: From email address (defaults to SMTP_USER)
        - SMTP_USE_TLS: Use TLS (default: True)
        
        Returns:
            True if email sent successfully, False otherwise
        """
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_user)
        smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        
        if not smtp_host or not smtp_user or not smtp_password:
            raise ValueError(
                "SMTP configuration missing. Please set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD environment variables."
            )
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = smtp_from
            msg['To'] = ', '.join(to_addresses)
            if cc_addresses:
                msg['Cc'] = ', '.join(cc_addresses)
            
            # Create email body
            if html_body:
                part1 = MIMEText(body, 'plain')
                part2 = MIMEText(html_body, 'html')
                msg.attach(part1)
                msg.attach(part2)
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # Get all recipients
            recipients = to_addresses + cc_addresses + bcc_addresses
            
            # Send email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_use_tls:
                    server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg, to_addrs=recipients)
            
            print(f"✅ Email sent successfully to {', '.join(to_addresses)}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
            import traceback
            print(traceback.format_exc())
            raise


class WorkflowOrchestrator:
    """
    Orchestrates workflow by selecting and executing appropriate agents.
    
    Supports both direct GoogleADKClient and shared framework (smart_sdk) modes.
    To enable shared framework for agents:
    1. Set USE_SHARED_FRAMEWORK=true environment variable
    2. Ensure smart_sdk is installed/available
    3. Agents will automatically use shared framework if available
    """
    
    def __init__(
        self,
        google_adk_client: Optional[GoogleADKClient] = None,
        use_shared_framework: Optional[bool] = None
    ):
        """
        Initialize orchestrator with available agents.
        
        Args:
            google_adk_client: Google ADK client instance (for direct mode)
            use_shared_framework: Whether to use shared framework (None = auto-detect from env)
        """
        self.adk_client = google_adk_client
        
        # Determine if shared framework should be used
        if use_shared_framework is None:
            use_shared_framework = USE_SHARED_FRAMEWORK_ENV and SHARED_FRAMEWORK_AVAILABLE
        
        # Initialize agents with optional shared framework support
        # For now, agents use direct client, but can be updated to use shared framework
        # by passing use_shared_framework=True and appropriate config
        self.agents = {
            "code_search_rag": CodeSearchRAGAgent(google_adk_client),
            "splunk": SplunkAgent(google_adk_client),
            "general": GeneralAgent(google_adk_client),
            "email_generator": EmailGeneratorAgent(google_adk_client),
        }
        
        # Log framework mode
        if use_shared_framework and SHARED_FRAMEWORK_AVAILABLE:
            print("✅ WorkflowOrchestrator: Shared framework (smart_sdk) available")
            print("   Note: Agents can be configured to use shared framework via BaseAgent.__init__")
        else:
            print("ℹ️  WorkflowOrchestrator: Using direct GoogleADKClient mode")
    
    async def orchestrate(
        self,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        **kwargs
    ) -> AgentResult:
        """
        Orchestrate workflow by selecting and executing agents with support for complex workflows.
        
        Supports:
        - Phase-based execution (parallel, sequential, conditional)
        - Human-in-the-loop approval steps
        - LLM-based summarization of multiple agent results
        - Conditional branching based on phase results
        
        Args:
            user_message: User's message
            conversation_id: Conversation ID
            conversation_history: Previous messages
            **kwargs: Additional context
            
        Returns:
            Aggregated AgentResult
        """
        try:
            # Step 1: Analyze intent and generate workflow plan
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Analyzing intent and creating workflow plan...",
                details={"step": "orchestration", "workflow": "planning"}
            )
            await asyncio.sleep(0.5)
            
            agent_plan = await self._select_agents(user_message, conversation_history)
            
            workflow_type = agent_plan.get("workflow_type", "simple")
            phases = agent_plan.get("phases", [])
            
            if not phases:
                # Fallback to simple workflow
                return await self._execute_simple_workflow(
                    user_message, conversation_id, conversation_history, agent_plan, **kwargs
                )
            
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity=f"Workflow plan created: {len(phases)} phase(s)",
                details={
                    "step": "orchestration",
                    "workflow_type": workflow_type,
                    "phases_count": len(phases),
                    "requires_approval": agent_plan.get("human_approval", {}).get("required", False),
                    "requires_summarization": agent_plan.get("summarization", {}).get("required", False)
                }
            )
            await asyncio.sleep(0.3)
            
            # Step 2: Execute workflow phases
            phase_results = {}
            all_agent_results = []
            
            for phase in phases:
                phase_num = phase.get("phase", 0)
                phase_type = phase.get("type", "sequential")
                
                # Check phase condition
                if phase.get("condition") and not self._evaluate_condition(
                    phase["condition"], phase_results, phase_num
                ):
                    print(f"⚠️ Phase {phase_num} skipped due to condition: {phase.get('condition')}")
                    continue
                
                # Check dependencies
                depends_on = phase.get("depends_on", [])
                if depends_on and not all(
                    dep in phase_results for dep in depends_on
                ):
                    print(f"⚠️ Phase {phase_num} skipped: dependencies not met")
                    continue
                
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity=f"Executing Phase {phase_num}: {phase_type}",
                    details={"step": "orchestration", "phase": phase_num, "type": phase_type}
                )
                await asyncio.sleep(0.2)
                
                if phase_type == "parallel":
                    results = await self._execute_parallel_phase(
                        phase, user_message, conversation_id, conversation_history,
                        phase_results, **kwargs
                    )
                    phase_results[f"phase_{phase_num}"] = results
                    all_agent_results.extend([r for r in results if isinstance(r, AgentResult)])
                    
                elif phase_type == "sequential":
                    results = await self._execute_sequential_phase(
                        phase, user_message, conversation_id, conversation_history,
                        phase_results, **kwargs
                    )
                    phase_results[f"phase_{phase_num}"] = results
                    all_agent_results.extend([r for r in results if isinstance(r, AgentResult)])
                    
                elif phase_type == "human_approval":
                    approval_result = await self._request_human_approval(
                        phase, conversation_id, phase_results, user_message
                    )
                    phase_results[f"phase_{phase_num}"] = approval_result
                    
                    if not approval_result.get("approved", False):
                        return AgentResult(
                            content="Workflow stopped: Human approval was denied or timed out.",
                            blocks=[],
                            status=AgentStatus.FAILED,
                            metadata={
                                "workflow": "orchestration",
                                "reason": "human_rejection",
                                "phase": phase_num
                            },
                            error="Human approval denied"
                        )
                    
                elif phase_type == "summarization":
                    summary_result = await self._generate_summary(
                        phase, phase_results, user_message, conversation_id
                    )
                    phase_results[f"phase_{phase_num}"] = summary_result
                    all_agent_results.append(summary_result)
            
            # Step 3: Final aggregation (with or without summarization)
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Aggregating final results...",
                details={"step": "orchestration", "workflow": "final_aggregation"}
            )
            await asyncio.sleep(0.3)
            
            # Check if summarization is already done in phases
            final_result = None
            if agent_plan.get("summarization", {}).get("required"):
                # Check if summarization was done in a phase
                summary_phase_results = [
                    r for k, r in phase_results.items()
                    if isinstance(r, AgentResult) and r.metadata.get("summarized")
                ]
                
                if summary_phase_results:
                    final_result = summary_phase_results[-1]  # Use latest summary
                else:
                    # Generate summary now
                    final_result = await self._generate_summary(
                        {"agents": [agent_plan.get("summarization", {}).get("agent", "general")]},
                        phase_results, user_message, conversation_id
                    )
            else:
                # Simple aggregation
                final_result = self._aggregate_results(all_agent_results, agent_plan)
            
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Workflow complete",
                details={"step": "orchestration", "workflow": "complete"}
            )
            
            return final_result
            
        except Exception as e:
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity=f"Orchestration error: {str(e)[:50]}",
                details={"step": "orchestration", "workflow": "error", "error": str(e)}
            )
            import traceback
            print(traceback.format_exc())
            return AgentResult(
                content=f"Error in workflow orchestration: {str(e)}",
                blocks=[],
                status=AgentStatus.FAILED,
                metadata={"workflow": "orchestration"},
                error=str(e)
            )
    
    async def _select_agents(
        self,
        user_message: str,
        conversation_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Select which agents to invoke based on user message - enhanced with complex workflow support."""
        if not self.adk_client:
            # Fallback: simple keyword matching
            return self._select_agents_keyword(user_message)
        
        try:
            prompt = f"""
            Analyze this user message and determine which specialized agents should be invoked and the workflow structure.
            
            User Message: "{user_message}"
            
            Available Agents:
            1. code_search_rag - For code repository search, API documentation, code questions (uses RAG)
            2. splunk - For Splunk queries, log analysis, observability
            3. general - For general questions, summarization, and conversations
            4. email_generator - For generating and sending emails with summarization capabilities
            
            Determine if the query requires:
            - Multiple agents (parallel or sequential)
            - Human approval/review (for sensitive operations, sending emails, executing queries)
            - Summarization of multiple agent responses
            - Conditional branching based on results
            
            Respond with JSON format:
            {{
                "workflow_type": "simple" or "complex",
                "phases": [
                    {{
                        "phase": 1,
                        "type": "parallel" or "sequential",
                        "agents": ["agent1", "agent2"],
                        "condition": null or "condition_expression"
                    }},
                    {{
                        "phase": 2,
                        "type": "human_approval" or "summarization" or "sequential",
                        "agents": ["agent_name"] or null,
                        "condition": "if phase1.completed",
                        "approval_type": "review" or "confirmation" (if type is human_approval)
                    }}
                ],
                "summarization": {{
                    "required": true or false,
                    "agent": "general"
                }},
                "human_approval": {{
                    "required": true or false,
                    "steps": ["review", "confirmation"]
                }},
                "reasoning": "Why this workflow structure was selected"
            }}
            
            Return ONLY valid JSON, no other text.
            """
            
            response = await self.adk_client.generate_text(
                prompt=prompt,
                system_prompt="You are an intelligent workflow orchestrator. Analyze user intent and create optimal workflow plans with phases, conditionals, and human-in-loop steps.",
                stream=False
            )
            
            # Parse JSON response
            import re
            json_match = re.search(r'\{.*"phases".*\}', response, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group())
            else:
                # Fallback: try to parse the whole response
                plan = json.loads(response)
            
            # Validate and normalize plan
            if "phases" not in plan:
                # Convert simple plan to phase-based
                agents = plan.get("agents", [])
                valid_agents = [a for a in agents if a in self.agents]
                if not valid_agents:
                    valid_agents = ["general"]
                
                plan = {
                    "workflow_type": "simple",
                    "phases": [{
                        "phase": 1,
                        "type": plan.get("order", "sequential"),
                        "agents": valid_agents,
                        "condition": None
                    }],
                    "summarization": {"required": len(valid_agents) > 1, "agent": "general"},
                    "human_approval": {"required": False, "steps": []},
                    "reasoning": plan.get("reasoning", "Simple workflow")
                }
            else:
                # Validate agents in phases
                for phase in plan.get("phases", []):
                    if phase.get("agents"):
                        valid_agents = [a for a in phase["agents"] if a in self.agents]
                        phase["agents"] = valid_agents if valid_agents else ["general"]
            
            return plan
            
        except Exception as e:
            print(f"⚠️ Error in agent selection: {e}, using keyword fallback")
            import traceback
            print(traceback.format_exc())
            return self._select_agents_keyword(user_message)
    
    def _select_agents_keyword(self, user_message: str) -> Dict[str, Any]:
        """Fallback keyword-based agent selection with workflow structure."""
        message_lower = user_message.lower()
        
        agents = []
        requires_approval = False
        
        # Check for code-related keywords
        if any(kw in message_lower for kw in ["code", "api", "method", "class", "function", "endpoint", "repository", "file", "java", "python"]):
            agents.append("code_search_rag")
        
        # Check for Splunk keywords
        if any(kw in message_lower for kw in ["splunk", "spl", "log", "query", "observability", "monitoring", "search index"]):
            agents.append("splunk")
            # Splunk queries often require approval
            if any(kw in message_lower for kw in ["execute", "run", "send", "delete"]):
                requires_approval = True
        
        # Check for email keywords
        if any(kw in message_lower for kw in ["email", "send email", "compose email", "mail", "email summary", "email report", "notify"]):
            agents.append("email_generator")
            # Email sending requires approval
            if any(kw in message_lower for kw in ["send", "send email", "send mail", "dispatch"]):
                requires_approval = True
        
        # Default to general if no specific agent matched
        if not agents:
            agents.append("general")
        
        # Build phase-based workflow
        phases = [{
            "phase": 1,
            "type": "parallel" if len(agents) > 1 else "sequential",
            "agents": agents,
            "condition": None
        }]
        
        # Add summarization phase if multiple agents
        if len(agents) > 1:
            phases.append({
                "phase": 2,
                "type": "summarization",
                "agents": ["general"],
                "condition": "if phase1.completed"
            })
        
        # Add approval phase if needed
        if requires_approval:
            phases.append({
                "phase": len(phases) + 1,
                "type": "human_approval",
                "approval_type": "confirmation",
                "condition": "if previous.completed"
            })
        
        return {
            "workflow_type": "complex" if len(phases) > 1 else "simple",
            "phases": phases,
            "summarization": {
                "required": len(agents) > 1,
                "agent": "general"
            },
            "human_approval": {
                "required": requires_approval,
                "steps": ["confirmation"] if requires_approval else []
            },
            "reasoning": "Keyword-based selection"
        }
    
    async def _execute_agent_with_activity(
        self,
        agent_name: str,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        intermediate_result: Optional[AgentResult] = None,
        **kwargs
    ) -> AgentResult:
        """Execute an agent with activity updates."""
        agent = self.agents.get(agent_name)
        if not agent:
            return AgentResult(
                content=f"Agent '{agent_name}' not found",
                blocks=[],
                status=AgentStatus.FAILED,
                metadata={"agent": agent_name},
                error="Agent not found"
            )
        
        # Prepare context
        context = kwargs.copy()
        if intermediate_result:
            context["intermediate_result"] = intermediate_result
            # Add previous response to user message for sequential execution
            if agent_name != "general":
                user_message = f"{user_message}\n\nPrevious context: {intermediate_result.content[:200]}"
        
        return await agent.execute(
            user_message=user_message,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
            **context
        )
    
    async def _execute_simple_workflow(
        self,
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        agent_plan: Dict[str, Any],
        **kwargs
    ) -> AgentResult:
        """Execute simple workflow (backward compatibility)."""
        # Extract agents from plan
        agents = []
        for phase in agent_plan.get("phases", []):
            agents.extend(phase.get("agents", []))
        
        if not agents:
            agents = ["general"]
        
        order = "parallel" if len(agents) > 1 else "sequential"
        
        # Execute agents
        agent_results = []
        if order == "parallel":
            tasks = []
            for agent_name in agents:
                if agent_name in self.agents:
                    tasks.append(
                        self._execute_agent_with_activity(
                            agent_name, user_message, conversation_id,
                            conversation_history, **kwargs
                        )
                    )
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                agent_results = [
                    r for r in results 
                    if isinstance(r, AgentResult) and not isinstance(r, Exception)
                ]
        else:
            intermediate_result = None
            for agent_name in agents:
                if agent_name in self.agents:
                    result = await self._execute_agent_with_activity(
                        agent_name, user_message, conversation_id,
                        conversation_history, intermediate_result=intermediate_result, **kwargs
                    )
                    agent_results.append(result)
                    intermediate_result = result
        
        return self._aggregate_results(agent_results, agent_plan)
    
    async def _execute_parallel_phase(
        self,
        phase: Dict[str, Any],
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        phase_results: Dict[str, Any],
        **kwargs
    ) -> List[AgentResult]:
        """Execute agents in parallel for a phase."""
        agents = phase.get("agents", [])
        results = []
        
        tasks = []
        for agent_name in agents:
            if agent_name in self.agents:
                tasks.append(
                    self._execute_agent_with_activity(
                        agent_name, user_message, conversation_id,
                        conversation_history, **kwargs
                    )
                )
        
        if tasks:
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)
            results = [
                r for r in parallel_results
                if isinstance(r, AgentResult) and not isinstance(r, Exception)
            ]
        
        return results
    
    async def _execute_sequential_phase(
        self,
        phase: Dict[str, Any],
        user_message: str,
        conversation_id: int,
        conversation_history: List[Dict[str, Any]],
        phase_results: Dict[str, Any],
        **kwargs
    ) -> List[AgentResult]:
        """Execute agents sequentially for a phase."""
        agents = phase.get("agents", [])
        results = []
        intermediate_result = None
        
        for agent_name in agents:
            if agent_name in self.agents:
                result = await self._execute_agent_with_activity(
                    agent_name, user_message, conversation_id,
                    conversation_history, intermediate_result=intermediate_result, **kwargs
                )
                results.append(result)
                intermediate_result = result
        
        return results
    
    async def _request_human_approval(
        self,
        phase: Dict[str, Any],
        conversation_id: int,
        phase_results: Dict[str, Any],
        user_message: str
    ) -> Dict[str, Any]:
        """Request human approval for a workflow step."""
        approval_type = phase.get("approval_type", "review")
        
        # Generate descriptive title based on approval type and context
        agents_used = []
        for phase_key, phase_result in phase_results.items():
            if isinstance(phase_result, AgentResult):
                agents_used.append(phase_result.metadata.get("agent", "agent"))
            elif isinstance(phase_result, list):
                for result in phase_result:
                    if isinstance(result, AgentResult):
                        agents_used.append(result.metadata.get("agent", "agent"))
        
        agents_list = ", ".join(set(agents_used)) if agents_used else "workflow"
        
        title = phase.get("title")
        if not title:
            if approval_type == "confirmation":
                title = f"Confirm Action from {agents_list}"
            elif approval_type == "feedback":
                title = f"Review and Provide Feedback for {agents_list}"
            else:
                title = f"Review Results from {agents_list}"
        
        # Gather content and blocks from previous phases
        content_parts = []
        all_blocks = []
        
        for phase_key, phase_result in phase_results.items():
            if isinstance(phase_result, AgentResult):
                if phase_result.content:
                    content_parts.append(f"[{phase_result.metadata.get('agent', 'agent')}]: {phase_result.content[:500]}")
                if phase_result.blocks:
                    all_blocks.extend(phase_result.blocks)
            elif isinstance(phase_result, list):
                for result in phase_result:
                    if isinstance(result, AgentResult):
                        if result.content:
                            content_parts.append(f"[{result.metadata.get('agent', 'agent')}]: {result.content[:500]}")
                        if result.blocks:
                            all_blocks.extend(result.blocks)
        
        content = "\n\n".join(content_parts) if content_parts else "Please review the workflow results and approve to continue."
        
        # Create approval request
        approval_id = await approval_manager.create_approval_request(
            conversation_id=conversation_id,
            approval_type=approval_type,
            title=title,
            content=content,
            blocks=all_blocks[:10],  # Limit blocks to avoid overwhelming UI
            options={
                "require_feedback": approval_type == "feedback",
                "can_reject": True
            },
            timeout=300  # 5 minutes
        )
        
        # Send approval request via WebSocket
        await websocket_manager.send_approval_request(
            conversation_id=conversation_id,
            approval_id=approval_id,
            approval_type=approval_type,
            title=title,
            content=content,
            blocks=all_blocks[:10],
            options={
                "require_feedback": approval_type == "feedback",
                "can_reject": True
            },
            timeout=300
        )
        
        # Wait for approval response
        try:
            approval_result = await approval_manager.wait_for_approval(approval_id, timeout=300)
            
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity=f"Approval {'approved' if approval_result.get('approved') else 'rejected'}",
                details={
                    "step": "human_approval",
                    "approved": approval_result.get("approved"),
                    "approval_id": approval_id
                }
            )
            
            return approval_result
            
        except asyncio.TimeoutError:
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Approval request timed out",
                details={"step": "human_approval", "approval_id": approval_id, "status": "timeout"}
            )
            return {
                "approved": False,
                "feedback": "Approval request timed out after 5 minutes",
                "response_data": {"timeout": True}
            }
    
    async def _generate_summary(
        self,
        phase: Dict[str, Any],
        phase_results: Dict[str, Any],
        user_message: str,
        conversation_id: int
    ) -> AgentResult:
        """Generate LLM-based summary with structured UI blocks from multiple agent results."""
        if not self.adk_client:
            # Fallback to simple aggregation
            all_results = []
            for pr in phase_results.values():
                if isinstance(pr, AgentResult):
                    all_results.append(pr)
                elif isinstance(pr, list):
                    all_results.extend([r for r in pr if isinstance(r, AgentResult)])
            return self._aggregate_results(all_results, {})
        
        await websocket_manager.send_activity_status(
            conversation_id=conversation_id,
            activity="Generating structured summary from multiple agents...",
            details={"step": "summarization"}
        )
        
        # Gather content from all phases
        context_parts = []
        all_blocks = []
        agents_used = []
        agent_summaries = {}
        
        for phase_key, phase_result in phase_results.items():
            if isinstance(phase_result, AgentResult):
                if phase_result.status == AgentStatus.COMPLETED:
                    agent_name = phase_result.metadata.get("agent", "unknown")
                    agents_used.append(agent_name)
                    agent_summaries[agent_name] = {
                        "content": phase_result.content,
                        "blocks": phase_result.blocks or []
                    }
                    context_parts.append(f"""
[{agent_name}]:
{phase_result.content}
""")
                    if phase_result.blocks:
                        all_blocks.extend(phase_result.blocks)
            elif isinstance(phase_result, list):
                for result in phase_result:
                    if isinstance(result, AgentResult) and result.status == AgentStatus.COMPLETED:
                        agent_name = result.metadata.get("agent", "unknown")
                        agents_used.append(agent_name)
                        agent_summaries[agent_name] = {
                            "content": result.content,
                            "blocks": result.blocks or []
                        }
                        context_parts.append(f"""
[{agent_name}]:
{result.content}
""")
                        if result.blocks:
                            all_blocks.extend(result.blocks)
        
        if not context_parts:
            return AgentResult(
                content="No results to summarize.",
                blocks=[],
                status=AgentStatus.FAILED,
                metadata={"summarization": "no_results"}
            )
        
        # Generate structured summary using LLM with JSON output
        summary_prompt = f"""
The user asked: "{user_message}"

Multiple specialized agents have provided responses:
{''.join(context_parts)}

Analyze and synthesize this information to create a comprehensive, structured summary. Generate a JSON response with the following structure:

{{
    "executive_summary": "A 2-3 sentence high-level answer to the user's question that synthesizes all key information",
    "key_findings": {{
        "code": ["finding from code search agent", "another finding"],
        "logs": ["finding from splunk/logs agent", "another finding"],
        "patterns": ["pattern or relationship identified", "another pattern"]
    }},
    "comparison": {{
        "alignments": ["point where code and logs agree", "another alignment"],
        "discrepancies": ["point where code and logs differ", "another discrepancy"],
        "correlations": ["relationship between findings", "another correlation"]
    }},
    "insights": [
        "Important insight #1",
        "Important insight #2",
        "Important insight #3"
    ],
    "recommendations": [
        "Actionable recommendation #1",
        "Actionable recommendation #2",
        "Actionable recommendation #3"
    ],
    "narrative_summary": "A complete narrative summary (3-5 paragraphs) that ties everything together, explains relationships, and provides context"
}}

Guidelines:
- Be specific and actionable
- Focus on what the user needs to know
- Highlight conflicts, alignments, and important patterns
- Recommendations should be concrete and actionable
- Keep insights concise but meaningful
- The narrative_summary should be comprehensive but well-organized

Return ONLY valid JSON, no markdown formatting, no code blocks, just the raw JSON object.
"""
        
        try:
            # Use _generate_with_llm which supports both shared framework and direct client
            # Note: We need to access the orchestrator's adk_client or use a helper
            # For now, we'll use the direct client approach but this should be refactored
            if not self.adk_client:
                raise RuntimeError("ADK client not available for summarization")
            
            summarized_response = await self.adk_client.generate_text(
                prompt=summary_prompt,
                system_prompt="You are an expert at synthesizing information from multiple sources. Always return valid JSON with structured, actionable summaries that integrate insights from different perspectives. Never include markdown or code blocks in your response, only pure JSON.",
                stream=False
            )
            
            # Handle None or empty response
            if not summarized_response:
                raise ValueError("LLM returned empty response")
            
            # Convert to string if needed
            summarized_response_str = str(summarized_response).strip()
            
            # Parse JSON response - Extract JSON from response (handle cases where LLM wraps it)
            try:
                json_match = re.search(r'\{.*\}', summarized_response_str, re.DOTALL)
                if json_match:
                    summary_data = json.loads(json_match.group())
                else:
                    # Try parsing the entire response
                    summary_data = json.loads(summarized_response_str)
            except json.JSONDecodeError as json_err:
                print(f"⚠️ Error parsing JSON summary response: {json_err}")
                print(f"Response was: {summarized_response_str[:500]}")
                # Fallback: use the response as plain text
                return AgentResult(
                    content=summarized_response_str,
                    blocks=all_blocks,
                    status=AgentStatus.COMPLETED,
                    metadata={
                        "workflow": "summarization",
                        "agents_used": list(set(agents_used)),
                        "summarized": True,
                        "structured": False,
                        "error": "JSON parsing failed, using plain text"
                    }
                )
            
            # Build enhanced UI blocks
            enhanced_blocks = []
            
            # 1. Executive Summary as Alert Block
            if summary_data.get("executive_summary"):
                enhanced_blocks.append({
                    "type": "alert",
                    "data": {
                        "type": "info",
                        "title": "Executive Summary",
                        "message": summary_data["executive_summary"],
                        "dismissible": False
                    }
                })
            
            # 2. Key Findings as Collapsible Section with Tables
            if summary_data.get("key_findings"):
                findings = summary_data["key_findings"]
                findings_blocks = []
                
                # Create a findings summary table
                findings_rows = []
                for category, items in findings.items():
                    if items:
                        for item in items:
                            findings_rows.append([category.capitalize(), item])
                
                if findings_rows:
                    findings_blocks.append({
                        "type": "table",
                        "data": {
                            "columns": ["Category", "Finding"],
                            "rows": findings_rows,
                            "title": "Key Findings Summary"
                        }
                    })
                
                # Add collapsible section for detailed findings
                if findings_blocks:
                    enhanced_blocks.append({
                        "type": "collapsible",
                        "data": {
                            "title": "📊 Key Findings",
                            "defaultExpanded": True,
                            "icon": "📊",
                            "children": findings_blocks
                        }
                    })
            
            # 3. Comparison/Analysis as Collapsible Section with Table
            if summary_data.get("comparison"):
                comparison = summary_data["comparison"]
                comparison_rows = []
                
                if comparison.get("alignments"):
                    for item in comparison["alignments"]:
                        comparison_rows.append(["✅ Alignment", item])
                
                if comparison.get("discrepancies"):
                    for item in comparison["discrepancies"]:
                        comparison_rows.append(["⚠️ Discrepancy", item])
                
                if comparison.get("correlations"):
                    for item in comparison["correlations"]:
                        comparison_rows.append(["🔗 Correlation", item])
                
                if comparison_rows:
                    enhanced_blocks.append({
                        "type": "collapsible",
                        "data": {
                            "title": "🔍 Comparison & Analysis",
                            "defaultExpanded": True,
                            "icon": "🔍",
                            "children": [{
                                "type": "table",
                                "data": {
                                    "columns": ["Type", "Details"],
                                    "rows": comparison_rows,
                                    "title": "Code vs Logs Analysis"
                                }
                            }]
                        }
                    })
            
            # 4. Key Insights as Markdown List Block
            if summary_data.get("insights"):
                insights = summary_data["insights"]
                insights_markdown = "## 💡 Key Insights\n\n" + "\n".join([f"- {insight}" for insight in insights])
                enhanced_blocks.append({
                    "type": "collapsible",
                    "data": {
                        "title": "💡 Key Insights",
                        "defaultExpanded": True,
                        "icon": "💡",
                        "children": [{
                            "type": "markdown",
                            "data": {
                                "content": insights_markdown
                            }
                        }]
                    }
                })
            
            # 5. Recommendations as Checklist Block
            if summary_data.get("recommendations"):
                recommendations = summary_data["recommendations"]
                enhanced_blocks.append({
                    "type": "checklist",
                    "data": {
                        "title": "✅ Recommendations & Next Steps",
                        "items": [
                            {
                                "id": str(i),
                                "text": rec,
                                "checked": False,
                                "priority": "medium"
                            }
                            for i, rec in enumerate(recommendations, 1)
                        ],
                        "showProgress": True,
                        "showPriority": True,
                        "allowEdit": False,
                        "collapsible": False
                    }
                })
            
            # 6. Narrative Summary as Markdown Block (collapsible for detailed view)
            if summary_data.get("narrative_summary"):
                enhanced_blocks.append({
                    "type": "collapsible",
                    "data": {
                        "title": "📝 Detailed Summary",
                        "defaultExpanded": False,
                        "icon": "📝",
                        "children": [{
                            "type": "markdown",
                            "data": {
                                "content": f"## Comprehensive Analysis\n\n{summary_data['narrative_summary']}"
                            }
                        }]
                    }
                })
            
            # 7. Append original blocks from agents at the end (for reference)
            if all_blocks:
                enhanced_blocks.append({
                    "type": "collapsible",
                    "data": {
                        "title": "🔧 Source Details",
                        "defaultExpanded": False,
                        "icon": "🔧",
                        "children": all_blocks[:10]  # Limit to avoid overwhelming UI
                    }
                })
            
            # Use executive summary as main content, with narrative as fallback
            main_content = summary_data.get("executive_summary") or summary_data.get("narrative_summary", "Summary generated successfully.")
            
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Structured summary generated",
                details={"step": "summarization", "blocks_count": len(enhanced_blocks)}
            )
            
            return AgentResult(
                content=main_content,
                blocks=enhanced_blocks,
                status=AgentStatus.COMPLETED,
                metadata={
                    "workflow": "summarization",
                    "agents_used": list(set(agents_used)),
                    "summarized": True,
                    "structured": True,
                    "phase_results_count": len(phase_results),
                    "blocks_generated": len(enhanced_blocks)
                }
            )
        except Exception as e:
            print(f"⚠️ Error generating summary: {e}")
            import traceback
            print(traceback.format_exc())
            # Fallback to simple aggregation
            all_results = []
            for pr in phase_results.values():
                if isinstance(pr, AgentResult):
                    all_results.append(pr)
                elif isinstance(pr, list):
                    all_results.extend([r for r in pr if isinstance(r, AgentResult)])
            return self._aggregate_results(all_results, {})
    
    def _evaluate_condition(
        self,
        condition: str,
        phase_results: Dict[str, Any],
        current_phase: int
    ) -> bool:
        """Evaluate a phase condition."""
        if not condition:
            return True
        
        # Simple condition evaluation
        # Support conditions like: "if phase1.completed", "if previous.completed"
        condition_lower = condition.lower()
        
        if "phase1.completed" in condition_lower or "phase_1" in condition_lower:
            return "phase_1" in phase_results
        elif "previous.completed" in condition_lower or "previous" in condition_lower:
            # Check if any previous phase exists
            for i in range(1, current_phase):
                if f"phase_{i}" in phase_results:
                    return True
            return False
        elif "all.completed" in condition_lower:
            # Check if all previous phases are completed
            for i in range(1, current_phase):
                if f"phase_{i}" not in phase_results:
                    return False
            return True
        
        # Default: condition is met if any previous phase exists
        return len(phase_results) > 0
    
    def _aggregate_results(
        self,
        agent_results: List[AgentResult],
        agent_plan: Dict[str, Any]
    ) -> AgentResult:
        """Aggregate results from multiple agents."""
        if not agent_results:
            return AgentResult(
                content="No agent results to aggregate",
                blocks=[],
                status=AgentStatus.FAILED,
                metadata={"workflow": "orchestration"}
            )
        
        # Combine content
        contents = []
        all_blocks = []
        agents_used = []
        
        for result in agent_results:
            if result.status == AgentStatus.COMPLETED:
                agents_used.append(result.metadata.get("agent", "unknown"))
                if result.content:
                    contents.append(f"[{result.metadata.get('agent', 'agent')}]: {result.content}")
                if result.blocks:
                    all_blocks.extend(result.blocks)
        
        aggregated_content = "\n\n".join(contents) if contents else "Workflow execution completed."
        
        return AgentResult(
            content=aggregated_content,
            blocks=all_blocks,
            status=AgentStatus.COMPLETED if all(r.status == AgentStatus.COMPLETED for r in agent_results) else AgentStatus.FAILED,
            metadata={
                "workflow": "orchestration",
                "agents_used": agents_used,
                "reasoning": agent_plan.get("reasoning", ""),
                "order": agent_plan.get("order", "sequential")
            }
        )


# Global instances
_orchestrator_instance: Optional[WorkflowOrchestrator] = None
_adk_client_instance: Optional[GoogleADKClient] = None


def _initialize_google_adk() -> Optional[GoogleADKClient]:
    """Initialize Google ADK client."""
    global _adk_client_instance
    
    if _adk_client_instance:
        return _adk_client_instance
    
    if not GOOGLE_ADK_AVAILABLE:
        return None
    
    try:
        config = GoogleADKConfig(
            api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
            model_name=os.getenv("GOOGLE_MODEL", "gemini-pro"),
            temperature=float(os.getenv("GOOGLE_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("GOOGLE_MAX_TOKENS", "2048")),
            use_vertex_ai=os.getenv("GOOGLE_USE_VERTEX_AI", "false").lower() == "true",
            project_id=os.getenv("GOOGLE_PROJECT_ID"),
            location=os.getenv("GOOGLE_LOCATION", "us-central1"),
            credentials_path=os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        
        _adk_client_instance = GoogleADKClient(config=config)
        print("✅ Google ADK client initialized for direct agents")
        return _adk_client_instance
    except Exception as e:
        print(f"⚠️ Failed to initialize Google ADK: {e}")
        import traceback
        print(traceback.format_exc())
        return None


async def process_conversation_agentic_direct(
    user_message: str,
    conversation_id: int,
    conversation_history: List[Dict[str, Any]],
    thinking_mode: str = "thinking",
    agent: str = "orchestrator"  # Default to orchestrator
) -> Dict[str, Any]:
    """
    Process conversation using direct code-based agents (no agent-toolkit).
    
    Args:
        user_message: Current user message
        conversation_id: Conversation ID
        conversation_history: Previous messages
        thinking_mode: Thinking mode (not used in direct agents, kept for compatibility)
        agent: Agent name or "orchestrator" to use workflow orchestration
        
    Returns:
        Dict with same format as LangGraph version:
        {
            "content": str,
            "blocks": List[Dict],
            "error": Optional[str],
            "thinking_mode": str,
            "agent": str
        }
    """
    global _orchestrator_instance
    
    try:
        # Initialize Google ADK
        adk_client = _initialize_google_adk()
        if not adk_client:
            return {
                "content": "Google ADK not available. Please configure GOOGLE_API_KEY.",
                "blocks": [],
                "error": "Google ADK not available",
                "thinking_mode": thinking_mode,
                "agent": agent
            }
        
        # Initialize orchestrator if needed
        if _orchestrator_instance is None:
            _orchestrator_instance = WorkflowOrchestrator(google_adk_client=adk_client)
        
        # Broadcast activity: Starting
        await websocket_manager.send_activity_status(
            conversation_id=conversation_id,
            activity=f"Agent: {agent}",
            details={"agent": agent, "step": "agent_selection"}
        )
        await asyncio.sleep(0.5)
        
        # Execute based on agent selection
        if agent == "orchestrator" or agent == "workflow":
            # Use orchestrator to select and execute agents
            result = await _orchestrator_instance.orchestrate(
                user_message=user_message,
                conversation_id=conversation_id,
                conversation_history=conversation_history
            )
        else:
            # Execute specific agent directly
            specific_agent = _orchestrator_instance.agents.get(agent)
            if not specific_agent:
                return {
                    "content": f"Agent '{agent}' not found. Available: {list(_orchestrator_instance.agents.keys())}",
                    "blocks": [],
                    "error": f"Agent '{agent}' not found",
                    "thinking_mode": thinking_mode,
                    "agent": agent
                }
            
            result = await specific_agent.execute(
                user_message=user_message,
                conversation_id=conversation_id,
                conversation_history=conversation_history
            )
        
        # Convert AgentResult to expected format
        return {
            "content": result.content,
            "blocks": result.blocks,
            "error": result.error,
            "thinking_mode": thinking_mode,
            "agent": agent,
            "metadata": result.metadata
        }
        
    except Exception as e:
        print(f"❌ Error in direct agentic processing: {e}")
        import traceback
        print(traceback.format_exc())
        
        await websocket_manager.send_activity_status(
            conversation_id=conversation_id,
            activity=f"Error: {str(e)[:50]}",
            details={"step": "error", "error": str(e)}
        )
        
        return {
            "content": f"I encountered an error: {str(e)}",
            "blocks": [],
            "error": str(e),
            "thinking_mode": thinking_mode,
            "agent": agent
        }
```

Updating the API endpoint to use direct agents:
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
read_file
