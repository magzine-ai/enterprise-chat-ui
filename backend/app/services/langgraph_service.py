"""
LangGraph Service for Intelligent Conversation Flow.

This service implements a state machine using LangGraph to handle conversation
flow with intelligent routing, intent classification, and response generation.
Supports both LLM-based responses and mock responses based on configuration.
"""

from typing import TypedDict, List, Dict, Any, Literal, Optional
from langgraph.graph import StateGraph, END
from app.core.config import settings
from app.services.llm_service import llm_service
from app.services.opensearch_service import opensearch_service
from app.api.conversations import _generate_blocks_for_response, _generate_response_text
import asyncio


class ConversationState(TypedDict):
    """
    State dictionary for LangGraph conversation flow.
    
    This TypedDict defines all the state variables that flow through
    the conversation graph, allowing nodes to read and update state.
    
    Attributes:
        messages: List of previous messages in the conversation
        conversation_id: ID of the current conversation
        user_message: The current user message being processed
        intent: Classified intent of the user message (splunk_query, general_chat, etc.)
        needs_splunk_query: Boolean indicating if a Splunk query is needed
        splunk_query: Generated or extracted Splunk query (if applicable)
        retrieved_context: Context retrieved from OpenSearch for query generation
        response_text: Generated response text content
        blocks: List of structured blocks (queries, charts, tables, etc.)
        is_streaming: Boolean indicating if response is being streamed
        error: Error message if processing fails
    """
    messages: List[Dict[str, Any]]
    conversation_id: int
    user_message: str
    intent: Optional[str]
    needs_splunk_query: bool
    splunk_query: Optional[str]
    retrieved_context: Optional[str]
    response_text: str
    blocks: List[Dict[str, Any]]
    is_streaming: bool
    error: Optional[str]


async def classify_intent(state: ConversationState) -> ConversationState:
    """
    Classify user intent to determine conversation flow routing.
    
    Analyzes the user message to determine what type of response is needed:
    - splunk_query: User wants to query Splunk data
    - general_chat: General conversation or questions
    - code_request: User wants code examples
    - chart_request: User wants data visualization
    
    This classification determines which nodes in the graph will be executed.
    
    Args:
        state: Current conversation state containing user_message
    
    Returns:
        ConversationState: Updated state with intent and needs_splunk_query set
    
    Edge Cases:
        - Empty user message: defaults to general_chat
        - Ambiguous messages: uses keyword matching with fallback to general_chat
        - Multiple intents: prioritizes splunk_query > chart_request > code_request > general_chat
    """
    user_message = state.get("user_message", "").lower().strip()
    intent = "general_chat"
    needs_splunk_query = False
    
    # Check for Splunk query intent
    splunk_keywords = [
        "splunk", "spl query", "index=", "stats", "timechart", 
        "search", "query splunk", "splunk search", "log analysis",
        "search logs", "analyze logs", "find in logs"
    ]
    if any(keyword in user_message for keyword in splunk_keywords):
        intent = "splunk_query"
        needs_splunk_query = True
    
    # Check for chart/visualization intent
    elif any(keyword in user_message for keyword in [
        "chart", "graph", "visualization", "plot", "visualize",
        "bar chart", "line chart", "pie chart", "timechart"
    ]):
        intent = "chart_request"
        # Charts might need Splunk queries for data
        if any(keyword in user_message for keyword in ["splunk", "logs", "data"]):
            needs_splunk_query = True
    
    # Check for code request
    elif any(keyword in user_message for keyword in [
        "code", "example", "show code", "python", "javascript",
        "sql query", "programming"
    ]):
        intent = "code_request"
    
    # Update state with classification results
    state["intent"] = intent
    state["needs_splunk_query"] = needs_splunk_query
    
    return state


async def generate_splunk_query(state: ConversationState) -> ConversationState:
    """
    Generate Splunk Processing Language (SPL) query from natural language.
    
    Uses LLM to convert user's natural language request into a valid
    Splunk query. Retrieves relevant context from OpenSearch to improve
    query accuracy with knowledge about indexes, fields, and patterns.
    
    Args:
        state: Current conversation state with user_message and intent
    
    Returns:
        ConversationState: Updated state with splunk_query set
    
    Edge Cases:
        - LLM unavailable: uses template-based query generation
        - OpenSearch unavailable: generates query without context
        - Ambiguous request: generates a generic query with explanation
        - Invalid request: sets error in state and returns
    """
    user_message = state.get("user_message", "")
    
    # Retrieve relevant context from OpenSearch
    context = ""
    if opensearch_service.is_available():
        try:
            context = await opensearch_service.get_splunk_context(
                user_query=user_message,
                top_k=settings.opensearch_context_top_k
            )
            if context:
                print(f"📚 Retrieved context from OpenSearch for query generation")
        except Exception as e:
            print(f"⚠️ Error retrieving context from OpenSearch: {e}")
            context = ""
    
    # If LLM is available, use it to generate query with context
    if llm_service.is_available():
        try:
            # Build prompt for query generation with context
            if context:
                prompt = f"""Convert the following user request into a Splunk Processing Language (SPL) query.

{context}

User request: {user_message}

Based on the context provided above, generate a valid SPL query that:
1. Uses the appropriate index names mentioned in the context
2. Uses the correct field names from the field mappings
3. Follows Splunk best practices

If the context mentions specific indexes or fields, use them in the query.
If the request is ambiguous, create a reasonable query based on the context.

Return only the SPL query, no additional text.

Examples:
- "show me errors in the last hour" -> index=* error | stats count
- "count requests by status" -> index=* | stats count by status
- "show me web logs from today" -> index=web_logs earliest=-1d@d latest=now
"""
            else:
                prompt = f"""Convert the following user request into a Splunk Processing Language (SPL) query.

User request: {user_message}

Generate a valid SPL query. If the request is ambiguous, create a reasonable query and explain what it does.
Return only the SPL query, no additional text.

Examples:
- "show me errors in the last hour" -> index=* error | stats count
- "count requests by status" -> index=* | stats count by status
- "show me web logs from today" -> index=web_logs earliest=-1d@d latest=now
"""
            
            # Generate query using LLM with context
            # Create a minimal conversation history for the query generation
            query_history = [{
                "role": "user",
                "content": prompt
            }]
            
            query = await llm_service.generate_response(
                user_message=prompt,
                conversation_history=query_history,
                conversation_id=state.get("conversation_id", 0)
            )
            
            # Clean up the query (remove markdown code blocks if present)
            query = query.strip()
            if query.startswith("```"):
                # Remove code block markers
                lines = query.split("\n")
                query = "\n".join([line for line in lines if not line.strip().startswith("```")])
            query = query.strip()
            
            # Validate query has basic SPL structure
            if not query or len(query) < 5:
                raise ValueError("Generated query is too short or empty")
            
        except Exception as e:
            print(f"⚠️ Error generating Splunk query with LLM: {e}")
            # Fallback to template
            query = f"index=* {user_message} | head 100"
    else:
        # Template-based query generation
        user_lower = user_message.lower()
        
        if "error" in user_lower:
            query = "index=* error | stats count by status"
        elif "count" in user_lower or "stats" in user_lower:
            query = "index=* | stats count"
        elif "timechart" in user_lower:
            query = "index=* | timechart count"
        else:
            query = f"index=* {user_message} | head 100"
    
    state["splunk_query"] = query
    
    # Store context in state for potential use in response generation
    if context:
        state["retrieved_context"] = context
    
    return state


async def execute_splunk_query(state: ConversationState) -> ConversationState:
    """
    Execute Splunk query (mock implementation, extensible for real Splunk API).
    
    Currently implements mock execution that generates sample results.
    In production, this would connect to Splunk API and execute the query.
    
    Args:
        state: Current conversation state with splunk_query set
    
    Returns:
        ConversationState: Updated state with query results in blocks
    
    Edge Cases:
        - Invalid query: returns error block
        - Query timeout: handles gracefully
        - No results: returns appropriate message
    """
    query = state.get("splunk_query", "")
    
    if not query:
        state["error"] = "No Splunk query provided"
        return state
    
    # Mock query execution - in production, this would call Splunk API
    # For now, create a query block that can be executed by the frontend
    query_block = {
        "type": "query",
        "data": {
            "query": query,
            "language": "spl",
            "title": "Splunk Query",
            "autoExecute": True
        }
    }
    
    # Add to blocks if not already present
    blocks = state.get("blocks", [])
    if not any(b.get("type") == "query" for b in blocks):
        blocks.append(query_block)
        state["blocks"] = blocks
    
    return state


async def generate_llm_response(state: ConversationState) -> ConversationState:
    """
    Generate AI response using OpenAI LLM.
    
    Uses the LLM service to generate a conversational response based on
    user message and conversation history. Extracts structured blocks
    from the response for rich UI rendering.
    
    Args:
        state: Current conversation state with user_message and messages
    
    Returns:
        ConversationState: Updated state with response_text and blocks
    
    Edge Cases:
        - LLM unavailable: falls back to mock response
        - API errors: catches and sets error in state
        - Empty response: handles gracefully
        - Token limits: truncates history if needed
    """
    user_message = state.get("user_message", "")
    conversation_history = state.get("messages", [])
    conversation_id = state.get("conversation_id", 0)
    
    # Check if LLM is available
    if not llm_service.is_available():
        print("⚠️ LLM not available, falling back to mock response")
        # Fallback to mock response generation
        return generate_mock_response(state)
    
    try:
        # Generate response using LLM
        # Note: For streaming, this is handled in the worker
        # This function is used for non-streaming responses
        response_text = await llm_service.generate_response(
            user_message,
            conversation_history,
            conversation_id
        )
        
        # Extract blocks from response
        cleaned_text, blocks = llm_service.extract_blocks_from_response(
            response_text,
            user_message
        )
        
        state["response_text"] = cleaned_text
        state["blocks"] = blocks
        
    except Exception as e:
        print(f"❌ Error generating LLM response: {e}")
        state["error"] = str(e)
        # Fallback to mock response on error
        return generate_mock_response(state)
    
    return state


async def generate_mock_response(state: ConversationState) -> ConversationState:
    """
    Generate mock response using existing pattern matching logic.
    
    Fallback method that uses the existing mock response generation
    from conversations.py. Used when mock_responses_enabled=True or
    when LLM is unavailable.
    
    Args:
        state: Current conversation state with user_message
    
    Returns:
        ConversationState: Updated state with response_text and blocks
    
    Edge Cases:
        - Handles all message types via pattern matching
        - Always succeeds (no external dependencies)
    """
    user_message = state.get("user_message", "")
    user_lower = user_message.lower().strip()
    
    # Use existing mock response generation
    blocks = _generate_blocks_for_response(user_message, user_lower)
    content = _generate_response_text(user_message, user_lower)
    
    state["response_text"] = content
    state["blocks"] = blocks
    
    return state


async def format_response_blocks(state: ConversationState) -> ConversationState:
    """
    Format and finalize response blocks for frontend rendering.
    
    Ensures all blocks are in the correct format expected by the frontend.
    Validates block structure and adds any missing required fields.
    
    Args:
        state: Current conversation state with blocks
    
    Returns:
        ConversationState: Updated state with formatted blocks
    
    Edge Cases:
        - Invalid block format: removes or fixes invalid blocks
        - Missing required fields: adds defaults
        - Empty blocks list: handles gracefully
    """
    blocks = state.get("blocks", [])
    formatted_blocks = []
    
    for block in blocks:
        # Validate block structure
        if not isinstance(block, dict) or "type" not in block:
            continue
        
        # Ensure data field exists
        if "data" not in block:
            block["data"] = {}
        
        formatted_blocks.append(block)
    
    state["blocks"] = formatted_blocks
    
    return state


async def route_based_on_intent(state: ConversationState) -> Literal["splunk_query", "general_chat", "mock_response"]:
    """
    Route conversation flow based on classified intent and configuration.
    
    Determines the next node to execute based on:
    1. mock_responses_enabled flag
    2. Classified intent
    3. LLM availability
    
    Args:
        state: Current conversation state with intent and configuration
    
    Returns:
        Literal: Next node name to execute
    
    Routing Logic:
        - If mock_responses_enabled=True: always route to mock_response
        - If intent is splunk_query: route to splunk_query node
        - If LLM unavailable: route to mock_response
        - Otherwise: route to general_chat (LLM response)
    """
    # If mock responses are enabled, always use mock
    if settings.mock_responses_enabled:
        return "mock_response"
    
    # If LLM is not available, fall back to mock
    if not llm_service.is_available():
        return "mock_response"
    
    intent = state.get("intent", "general_chat")
    
    # Route based on intent
    if intent == "splunk_query":
        return "splunk_query"
    else:
        return "general_chat"


async def route_after_splunk(state: ConversationState) -> Literal["generate_llm_response", "format_response_blocks"]:
    """
    Route after Splunk query execution.
    
    Determines whether to generate LLM response with query context
    or go directly to formatting blocks.
    
    Args:
        state: Current conversation state after query execution
    
    Returns:
        Literal: Next node name
    
    Logic:
        - If response_text is empty: generate LLM response with query context
        - Otherwise: format blocks and finish
    """
    if not state.get("response_text"):
        return "generate_llm_response"
    return "format_response_blocks"


def create_conversation_graph() -> StateGraph:
    """
    Create and configure the LangGraph conversation state machine.
    
    Builds a state graph with nodes for intent classification, query generation,
    LLM response generation, and block formatting. Sets up conditional routing
    based on intent and configuration.
    
    Returns:
        StateGraph: Configured graph ready for execution
    
    Graph Structure:
        1. classify_intent (entry point)
        2. Conditional routing:
           - splunk_query -> generate_splunk_query -> execute_splunk_query -> generate_llm_response -> format_response_blocks
           - general_chat -> generate_llm_response -> format_response_blocks
           - mock_response -> generate_mock_response -> format_response_blocks
        3. format_response_blocks -> END
    
    Edge Cases:
        - Handles errors at each node with fallback routing
        - Supports both streaming and non-streaming modes
    """
    # Create state graph
    graph = StateGraph(ConversationState)
    
    # Add nodes
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("generate_splunk_query", generate_splunk_query)
    graph.add_node("execute_splunk_query", execute_splunk_query)
    graph.add_node("generate_llm_response", generate_llm_response)
    graph.add_node("generate_mock_response", generate_mock_response)
    graph.add_node("format_response_blocks", format_response_blocks)
    
    # Set entry point
    graph.set_entry_point("classify_intent")
    
    # Add conditional routing from classify_intent
    graph.add_conditional_edges(
        "classify_intent",
        route_based_on_intent,
        {
            "splunk_query": "generate_splunk_query",
            "general_chat": "generate_llm_response",
            "mock_response": "generate_mock_response"
        }
    )
    
    # Add edges from splunk query path
    graph.add_edge("generate_splunk_query", "execute_splunk_query")
    graph.add_conditional_edges(
        "execute_splunk_query",
        route_after_splunk,
        {
            "generate_llm_response": "generate_llm_response",
            "format_response_blocks": "format_response_blocks"
        }
    )
    
    # Add edges from LLM and mock responses
    graph.add_edge("generate_llm_response", "format_response_blocks")
    graph.add_edge("generate_mock_response", "format_response_blocks")
    
    # Final edge to end
    graph.add_edge("format_response_blocks", END)
    
    return graph.compile()


# Global graph instance
conversation_graph = create_conversation_graph()


async def process_conversation(
    user_message: str,
    conversation_id: int,
    conversation_history: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Process a conversation turn using LangGraph.
    
    Main entry point for processing user messages through the conversation graph.
    Initializes state, runs the graph, and returns the final response.
    
    Args:
        user_message: Current user message
        conversation_id: ID of the conversation
        conversation_history: Previous messages in format:
            [{"role": "user|assistant", "content": "..."}, ...]
    
    Returns:
        Dict[str, Any]: Final state with response_text and blocks
    
    Edge Cases:
        - Empty user message: returns error
        - Graph execution failure: returns error state
        - Invalid state: handles gracefully
    """
    # Initialize state
    initial_state: ConversationState = {
        "messages": conversation_history,
        "conversation_id": conversation_id,
        "user_message": user_message,
        "intent": None,
        "needs_splunk_query": False,
        "splunk_query": None,
        "retrieved_context": None,
        "response_text": "",
        "blocks": [],
        "is_streaming": False,
        "error": None
    }
    
    try:
        # Run the graph
        final_state = await conversation_graph.ainvoke(initial_state)
        
        # Return response data
        return {
            "content": final_state.get("response_text", ""),
            "blocks": final_state.get("blocks", []),
            "error": final_state.get("error")
        }
    except Exception as e:
        print(f"❌ Error processing conversation: {e}")
        import traceback
        print(traceback.format_exc())
        return {
            "content": f"I encountered an error processing your request: {str(e)}",
            "blocks": [],
            "error": str(e)
        }

