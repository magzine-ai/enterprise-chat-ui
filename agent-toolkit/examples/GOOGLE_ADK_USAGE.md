# Google ADK Integration Usage Guide

This guide shows how to use Google ADK (Agent Development Kit) with the Agent Toolkit.

## Setup

### Option 1: Environment Variable (Recommended)

```bash
export GOOGLE_API_KEY=your-api-key-here
```

### Option 2: Command Line

```bash
python -m src.agent_wrapper \
  --config examples/llm_agent.yaml \
  --google-api-key your-api-key-here \
  --model gemini-pro \
  --temperature 0.7 \
  --verbose
```

### Option 3: Python Code

```python
from src.agent_wrapper import AgentWrapper

# Configure Google ADK
adk_config = {
    "api_key": "your-api-key",
    "model_name": "gemini-pro",
    "temperature": 0.7,
    "max_tokens": 2048
}

# Create wrapper with ADK config
wrapper = AgentWrapper(google_adk_config=adk_config)

# Load and execute agent
agent = wrapper.load_agent("examples/llm_agent.yaml")
result = wrapper.execute_sync(agent, verbose=True)
```

## Example Agents

### 1. LLM Generation Agent

```yaml
name: "LLMAgent"
workflow:
  variables:
    user_query: "Explain machine learning"
    system_prompt: "You are a helpful teacher"
  
  steps:
    - name: "generate"
      type: "action"
      action: "llm_generate"
      parameters:
        prompt: "{{user_query}}"
        system_prompt: "{{system_prompt}}"
```

**Run:**
```bash
python -m src.agent_wrapper --config examples/llm_agent.yaml --verbose
```

### 2. Chat Agent

```yaml
name: "ChatAgent"
workflow:
  variables:
    messages:
      - role: "user"
        content: "Hello!"
      - role: "assistant"
        content: "Hi! How can I help?"
    current_message: "Tell me about Python"
  
  steps:
    - name: "chat"
      type: "action"
      action: "llm_chat"
      parameters:
        messages: "{{messages}}"
        system_prompt: "You are a helpful assistant"
```

**Run:**
```bash
python -m src.agent_wrapper --config examples/chat_agent.yaml --verbose
```

### 3. Streaming Agent

```yaml
name: "StreamingAgent"
workflow:
  variables:
    prompt: "Write a short story"
  
  steps:
    - name: "stream"
      type: "action"
      action: "llm_stream"
      parameters:
        prompt: "{{prompt}}"
```

**Run:**
```bash
python -m src.agent_wrapper --config examples/streaming_agent.yaml --verbose
```

## Available Actions

### `llm_generate`
Generate text using Google ADK.

**Parameters:**
- `prompt` (required): The user prompt
- `system_prompt` (optional): System instructions
- `context` (optional): Conversation context

**Returns:**
```json
{
  "response": "Generated text...",
  "status": "success"
}
```

### `llm_chat`
Chat conversation with Google ADK.

**Parameters:**
- `messages` (required): List of messages with "role" and "content"
- `system_prompt` (optional): System instructions

**Returns:**
```json
{
  "response": "Chat response...",
  "status": "success"
}
```

### `llm_stream`
Stream text generation.

**Parameters:**
- `prompt` (required): The user prompt
- `system_prompt` (optional): System instructions
- `context` (optional): Conversation context

**Returns:**
```json
{
  "response": "Full generated text...",
  "chunks": ["chunk1", "chunk2", ...],
  "status": "success"
}
```

## Vertex AI Setup (Enterprise)

For Vertex AI integration:

```python
adk_config = {
    "use_vertex_ai": True,
    "project_id": "your-gcp-project-id",
    "location": "us-central1",
    "credentials_path": "/path/to/service-account.json",
    "model_name": "gemini-pro"
}

wrapper = AgentWrapper(google_adk_config=adk_config)
```

## Troubleshooting

1. **API Key Not Found**: Set `GOOGLE_API_KEY` environment variable
2. **Import Errors**: Install dependencies: `pip install google-generativeai langchain-google-genai`
3. **Model Not Available**: Check available models in Google AI Studio
4. **Rate Limits**: Implement retry logic or use Vertex AI for higher limits

## Next Steps

- See `examples/` for more agent examples
- Check `configs/google_adk_config.yaml` for configuration options
- Read the main README.md for workflow patterns

