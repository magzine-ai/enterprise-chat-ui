"""
LLM Service for OpenAI integration with streaming support.

This service provides a wrapper around OpenAI's API for generating conversational
responses with support for streaming tokens and block extraction from responses.
"""

from typing import List, Dict, Any, AsyncIterator, Optional, Tuple
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from app.core.config import settings
import json
import re


class LLMService:
    """
    Service for interacting with OpenAI LLM for conversation generation.
    
    Handles both streaming and non-streaming response generation, with support
    for extracting structured blocks (queries, charts, tables) from responses.
    """
    
    def __init__(self):
        """
        Initialize the LLM service with OpenAI client configuration.
        
        Reads configuration from settings:
        - openai_api_key: API key for OpenAI (required if mock_responses_enabled=False)
        - openai_model: Model name to use (default: "gpt-4")
        - streaming_enabled: Whether to enable streaming by default
        
        Raises:
            ValueError: If API key is missing when mock responses are disabled
        """
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.streaming_enabled = settings.streaming_enabled
        
        # Initialize OpenAI client if API key is provided
        if self.api_key:
            self.client = AsyncOpenAI(api_key=self.api_key)
            # Initialize LangChain ChatOpenAI for compatibility
            self.langchain_llm = ChatOpenAI(
                model_name=self.model,
                temperature=0.7,
                streaming=True,
                openai_api_key=self.api_key
            )
        else:
            self.client = None
            self.langchain_llm = None
            if not settings.mock_responses_enabled:
                print("⚠️ Warning: OpenAI API key not set, but mock_responses_enabled=False")
    
    async def generate_response_stream(
        self,
        user_message: str,
        conversation_history: List[Dict[str, Any]],
        conversation_id: int
    ) -> AsyncIterator[str]:
        """
        Generate streaming response from OpenAI API.
        
        Streams tokens as they are generated, providing real-time feedback
        to the user interface.
        
        Args:
            user_message: The current user message to respond to
            conversation_history: List of previous messages in format:
                [{"role": "user|assistant", "content": "..."}, ...]
            conversation_id: ID of the conversation for context
        
        Yields:
            str: Individual tokens or chunks of text as they are generated
        
        Raises:
            ValueError: If OpenAI client is not initialized
            Exception: If API call fails
        """
        if not self.client:
            raise ValueError("OpenAI client not initialized. Check API key configuration.")
        
        # Build messages from conversation history
        messages = self._build_messages(user_message, conversation_history)
        
        try:
            # Create streaming completion
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=2000
            )
            
            # Stream tokens as they arrive
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                        
        except Exception as e:
            print(f"❌ Error in streaming response: {e}")
            raise
    
    async def generate_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, Any]],
        conversation_id: int
    ) -> str:
        """
        Generate non-streaming response from OpenAI API.
        
        Returns complete response after generation is finished.
        Use this when streaming is not needed or not supported.
        
        Args:
            user_message: The current user message to respond to
            conversation_history: List of previous messages
            conversation_id: ID of the conversation for context
        
        Returns:
            str: Complete response text
        
        Raises:
            ValueError: If OpenAI client is not initialized
            Exception: If API call fails
        """
        if not self.client:
            raise ValueError("OpenAI client not initialized. Check API key configuration.")
        
        # Build messages from conversation history
        messages = self._build_messages(user_message, conversation_history)
        
        try:
            # Create non-streaming completion
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                temperature=0.7,
                max_tokens=2000
            )
            
            # Extract content from response
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content or ""
            return ""
            
        except Exception as e:
            print(f"❌ Error generating response: {e}")
            raise
    
    def _format_blocks_for_context(self, blocks: List[Dict[str, Any]]) -> str:
        """
        Format message blocks (especially query results) into readable text for LLM context.
        
        Args:
            blocks: List of block objects from message
        
        Returns:
            str: Formatted text representation of blocks
        """
        if not blocks:
            return ""
        
        formatted_parts = []
        
        for block in blocks:
            block_type = block.get("type", "")
            block_data = block.get("data", {})
            
            if block_type == "query":
                # Format query and results
                query = block_data.get("query", "")
                language = block_data.get("language", "spl")
                result = block_data.get("result")
                
                formatted_parts.append(f"\n[Query ({language.upper()})]:")
                formatted_parts.append(query)
                
                if result:
                    # Include query execution results
                    row_count = result.get("rowCount", 0)
                    columns = result.get("columns", [])
                    rows = result.get("rows", [])
                    visualization_type = result.get("visualizationType")
                    
                    formatted_parts.append(f"\n[Query Results]: {row_count} row(s)")
                    
                    if columns and rows:
                        # Format as a simple table (limit rows to avoid token bloat)
                        max_rows_to_show = 10
                        formatted_parts.append(f"Columns: {', '.join(columns)}")
                        formatted_parts.append("Sample results:")
                        
                        for i, row in enumerate(rows[:max_rows_to_show]):
                            row_str = " | ".join(str(val) for val in row)
                            formatted_parts.append(f"  Row {i+1}: {row_str}")
                        
                        if len(rows) > max_rows_to_show:
                            formatted_parts.append(f"  ... ({len(rows) - max_rows_to_show} more rows)")
                    
                    if visualization_type:
                        formatted_parts.append(f"Visualization: {visualization_type}")
                        if visualization_type == "chart" and result.get("chartData"):
                            chart_data = result.get("chartData", [])
                            if chart_data:
                                formatted_parts.append(f"Chart data points: {len(chart_data)}")
                                # Show first few data points
                                for i, point in enumerate(chart_data[:3]):
                                    formatted_parts.append(f"  Point {i+1}: {point}")
                                if len(chart_data) > 3:
                                    formatted_parts.append(f"  ... ({len(chart_data) - 3} more points)")
                    
                    if result.get("error"):
                        formatted_parts.append(f"Error: {result.get('error')}")
            
            elif block_type == "table":
                # Format table data
                columns = block_data.get("columns", [])
                rows = block_data.get("rows", [])
                if columns and rows:
                    formatted_parts.append(f"\n[Table]: {len(rows)} row(s)")
                    formatted_parts.append(f"Columns: {', '.join(columns)}")
                    for i, row in enumerate(rows[:5]):  # Limit to 5 rows
                        row_str = " | ".join(str(val) for val in row)
                        formatted_parts.append(f"  Row {i+1}: {row_str}")
            
            elif block_type == "code":
                # Include code snippets
                code = block_data.get("code", "")
                language = block_data.get("language", "")
                if code:
                    formatted_parts.append(f"\n[Code ({language})]:")
                    formatted_parts.append(code[:500])  # Limit code length
                    if len(code) > 500:
                        formatted_parts.append("  ... (truncated)")
        
        return "\n".join(formatted_parts)
    
    def _build_messages(
        self,
        user_message: str,
        conversation_history: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """
        Build message list for OpenAI API from conversation history.
        
        Converts internal message format to OpenAI expected format,
        including system prompt for Splunk Genie context.
        Includes query execution results from message blocks in the context.
        
        Args:
            user_message: Current user message
            conversation_history: Previous messages in conversation (may include 'blocks' field)
        
        Returns:
            List[Dict[str, str]]: Messages in OpenAI format
        """
        messages = []
        
        # Add system message with context about Splunk Genie capabilities
        system_prompt = """You are Splunk Genie, an AI assistant specialized in helping users with Splunk queries, data analysis, and visualization.

Your capabilities include:
- Generating Splunk Processing Language (SPL) queries from natural language
- Explaining Splunk concepts and query syntax
- Creating data visualizations (charts, tables, graphs)
- Analyzing log data and metrics
- Answering questions about Splunk functionality

When users ask for data analysis or queries, you can:
1. Generate appropriate SPL queries
2. Explain what the query does
3. Suggest visualizations for the results

You have access to previous query execution results in the conversation history. Use these results to:
- Answer follow-up questions about the data
- Provide insights based on the query results
- Suggest refinements to queries based on results
- Explain patterns or trends in the data

Format your responses naturally, and when including code or queries, use clear formatting.
If you generate a Splunk query, you can indicate it should be executed by the system.
"""
        
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # Add conversation history (limit to last N messages to avoid token limits)
        max_history = settings.max_conversation_history
        recent_history = conversation_history[-max_history:] if len(conversation_history) > max_history else conversation_history
        
        for msg in recent_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            blocks = msg.get("blocks", [])
            
            if role in ["user", "assistant"] and content:
                # Build enhanced content with blocks information
                enhanced_content = content
                
                # Add formatted blocks (query results, tables, etc.) to context
                if blocks:
                    blocks_text = self._format_blocks_for_context(blocks)
                    if blocks_text:
                        enhanced_content = f"{content}\n{blocks_text}"
                
                messages.append({
                    "role": role,
                    "content": enhanced_content
                })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    def extract_blocks_from_response(
        self,
        response_text: str,
        user_message: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Extract structured blocks from LLM response text.
        
        Parses the response to identify and extract:
        - Splunk queries (SPL)
        - SQL queries
        - Code blocks
        - Chart requests
        - Table data
        
        Uses pattern matching and JSON parsing to identify structured content.
        
        Args:
            response_text: The complete response text from LLM
            user_message: Original user message for context
        
        Returns:
            Tuple[str, List[Dict[str, Any]]]: 
                - Cleaned response text (with block markers removed)
                - List of extracted blocks in the format expected by the frontend
        """
        blocks: List[Dict[str, Any]] = []
        cleaned_text = response_text
        
        # Try to extract JSON blocks if response contains structured data
        # Look for JSON code blocks
        json_pattern = r'```json\s*(\{.*?\})\s*```'
        json_matches = re.findall(json_pattern, response_text, re.DOTALL)
        
        for json_str in json_matches:
            try:
                block_data = json.loads(json_str)
                if isinstance(block_data, dict) and "type" in block_data:
                    blocks.append(block_data)
                    # Remove the JSON block from text
                    cleaned_text = re.sub(
                        f'```json\\s*{re.escape(json_str)}\\s*```',
                        '',
                        cleaned_text,
                        flags=re.DOTALL
                    )
            except json.JSONDecodeError:
                pass
        
        # Extract Splunk queries (SPL)
        # Look for patterns like: index=... | stats ...
        splunk_pattern = r'(index\s*=\s*[^\n\|]+(?:\s*\|\s*[^\n]+)*)'
        splunk_matches = re.findall(splunk_pattern, response_text, re.IGNORECASE | re.MULTILINE)
        
        for splunk_query in splunk_matches:
            # Clean up the query
            query = splunk_query.strip()
            if len(query) > 10:  # Only add if it's a substantial query
                blocks.append({
                    "type": "query",
                    "data": {
                        "query": query,
                        "language": "spl",
                        "title": "Splunk Query",
                        "autoExecute": False
                    }
                })
        
        # Extract SQL queries
        sql_pattern = r'(SELECT\s+.*?(?:;|$))'
        sql_matches = re.findall(sql_pattern, response_text, re.IGNORECASE | re.DOTALL)
        
        for sql_query in sql_matches:
            query = sql_query.strip().rstrip(';')
            if len(query) > 10:
                blocks.append({
                    "type": "query",
                    "data": {
                        "query": query,
                        "language": "sql",
                        "title": "SQL Query",
                        "autoExecute": False
                    }
                })
        
        # Extract code blocks (Python, JavaScript, etc.)
        code_pattern = r'```(\w+)?\s*\n(.*?)```'
        code_matches = re.findall(code_pattern, response_text, re.DOTALL)
        
        for language, code in code_matches:
            lang = language.lower() if language else "text"
            if lang not in ["json", "spl", "sql"]:  # Avoid duplicates
                blocks.append({
                    "type": "code",
                    "data": {
                        "code": code.strip(),
                        "language": lang,
                        "title": f"{lang.upper()} Code"
                    }
                })
        
        # Check for chart requests in user message or response
        user_lower = user_message.lower()
        response_lower = response_text.lower()
        
        if any(word in user_lower or word in response_lower for word in 
               ["chart", "graph", "visualization", "plot", "timechart", "bar chart", "line chart"]):
            # Determine chart type from context
            chart_type = "bar" if "bar" in user_lower or "bar" in response_lower else \
                        "pie" if "pie" in user_lower or "pie" in response_lower else \
                        "area" if "area" in user_lower or "area" in response_lower else \
                        "timechart" if "time" in user_lower or "time" in response_lower else "line"
            
            blocks.append({
                "type": "splunk-chart",
                "data": {
                    "type": chart_type,
                    "title": "Data Visualization",
                    "data": [],  # Will be populated by query execution
                    "xAxis": "time" if chart_type == "timechart" else "name",
                    "yAxis": "value",
                    "height": 300,
                    "isTimeSeries": chart_type == "timechart",
                    "allowChartTypeSwitch": chart_type != "pie"
                }
            })
        
        # Clean up the text: remove code block markers but keep content
        cleaned_text = re.sub(r'```\w*\s*\n.*?```', '', cleaned_text, flags=re.DOTALL)
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text, blocks
    
    def is_available(self) -> bool:
        """
        Check if LLM service is available and configured.
        
        Returns:
            bool: True if OpenAI client is initialized and ready to use
        """
        return self.client is not None and self.api_key is not None


# Global instance
llm_service = LLMService()



