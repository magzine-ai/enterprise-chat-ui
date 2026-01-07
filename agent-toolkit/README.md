# Agent Toolkit

A flexible agent framework built on Google ADK (Agent Development Kit) that allows you to define and execute workflow-based agents using YAML or JSON declarations.

## Features

- **Workflow-based Agents**: Define complex agent workflows using declarative YAML/JSON
- **Multiple Agent Support**: Create and manage multiple agent declarations
- **Google ADK Integration**: Full integration with Google Generative AI (Gemini) and Vertex AI
- **LLM Actions**: Built-in actions for text generation, chat, and streaming
- **Flexible Execution**: Execute agents individually or as part of a workflow
- **Extensible**: Easy to add new agent types and capabilities

## Project Structure

```
agent-toolkit/
├── src/
│   ├── __init__.py
│   ├── agent_wrapper.py      # Main agent wrapper
│   ├── workflow_engine.py    # Workflow execution engine
│   ├── declaration_parser.py # YAML/JSON parser
│   ├── agent_registry.py     # Agent registry and management
│   └── google_adk_client.py  # Google ADK integration client
├── examples/
│   ├── simple_agent.yaml
│   ├── workflow_agent.yaml
│   ├── multi_agent_workflow.json
│   ├── llm_agent.yaml        # LLM generation example
│   ├── chat_agent.yaml       # Chat conversation example
│   └── streaming_agent.yaml  # Streaming generation example
├── configs/
│   ├── default_config.yaml
│   └── google_adk_config.yaml  # Google ADK configuration
├── tests/
│   └── test_agent_wrapper.py
├── requirements.txt
└── README.md
```

## Installation

```bash
cd agent-toolkit
pip install -r requirements.txt
```

### Google ADK Setup

1. **Get Google API Key** (for Gemini API):
   - Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Create an API key
   - Set environment variable: `export GOOGLE_API_KEY=your-api-key`

2. **Or use Vertex AI** (for enterprise):
   - Set up GCP project and credentials
   - Configure in `configs/google_adk_config.yaml`

3. **Test the integration**:
   ```bash
   export GOOGLE_API_KEY=your-api-key
   python -m src.agent_wrapper --config examples/llm_agent.yaml --verbose
   ```

## Quick Start

### 1. Define an Agent (YAML)

```yaml
# examples/simple_agent.yaml
name: "SimpleAgent"
description: "A simple demonstration agent"
type: "workflow"

workflow:
  steps:
    - name: "step1"
      type: "action"
      action: "greet"
      parameters:
        message: "Hello from Agent!"
    
    - name: "step2"
      type: "action"
      action: "process"
      parameters:
        input: "{{step1.output}}"
    
    - name: "step3"
      type: "condition"
      condition: "{{step2.result}} > 0"
      on_true:
        - name: "success_action"
          type: "action"
          action: "notify"
          parameters:
            status: "success"
      on_false:
        - name: "failure_action"
          type: "action"
          action: "notify"
          parameters:
            status: "failure"
```

### 2. Execute an Agent

```python
from src.agent_wrapper import AgentWrapper

# Basic usage
wrapper = AgentWrapper()
agent = wrapper.load_agent("examples/simple_agent.yaml")
result = wrapper.execute_sync(agent)
print(result)

# With Google ADK configuration
from src.google_adk_client import GoogleADKConfig

adk_config = {
    "api_key": "your-google-api-key",
    "model_name": "gemini-pro",
    "temperature": 0.7
}
wrapper = AgentWrapper(google_adk_config=adk_config)
agent = wrapper.load_agent("examples/llm_agent.yaml")
result = wrapper.execute_sync(agent, verbose=True)
```

### 3. Use LLM Actions in Workflows

```yaml
name: "LLMAgent"
workflow:
  steps:
    - name: "generate_text"
      type: "action"
      action: "llm_generate"
      parameters:
        prompt: "Explain quantum computing"
        system_prompt: "You are a helpful science teacher"
    
    - name: "stream_response"
      type: "action"
      action: "llm_stream"
      parameters:
        prompt: "Write a poem about AI"
      depends_on:
        - "generate_text"
```

### 4. Execute from Command Line

```bash
# Basic execution
python -m src.agent_wrapper --config examples/simple_agent.yaml

# With verbose output
python -m src.agent_wrapper --config examples/llm_agent.yaml --verbose

# List all registered agents
python -m src.agent_wrapper --list --registry-dir examples
```

## Agent Declaration Format

### YAML Format

```yaml
name: string              # Agent name
description: string       # Agent description
type: string              # Agent type (workflow, sequential, parallel)
version: string           # Agent version

workflow:
  steps:                  # List of workflow steps
    - name: string        # Step name
      type: string        # Step type (action, condition, loop, parallel)
      action: string      # Action to execute
      parameters: {}      # Action parameters
      condition: string   # Condition expression (for condition type)
      on_true: []         # Steps to execute if condition is true
      on_false: []        # Steps to execute if condition is false
      loop: {}            # Loop configuration
      parallel: []         # Parallel steps
```

### JSON Format

```json
{
  "name": "AgentName",
  "description": "Agent description",
  "type": "workflow",
  "workflow": {
    "steps": [...]
  }
}
```

## Supported Step Types

- **action**: Execute a single action
- **condition**: Conditional branching
- **loop**: Iterate over a collection
- **parallel**: Execute steps in parallel
- **wait**: Wait for a condition or time
- **call**: Call another agent

## Built-in Actions

### Default Actions
- `greet`: Display a greeting message
- `process`: Process input data
- `notify`: Send a notification
- `log`: Log a message with level
- `transform`: Transform data (uppercase, lowercase, etc.)

### Google ADK Actions
- `llm_generate`: Generate text using Google ADK
- `llm_chat`: Chat conversation with Google ADK
- `llm_stream`: Stream text generation from Google ADK

## Examples

See the `examples/` directory for:
- Simple agent workflows
- Complex multi-step workflows
- Conditional logic examples
- Parallel execution examples
- Agent composition examples

## Development

```bash
# Run tests
pytest tests/

# Run with verbose output
python -m src.agent_wrapper --config examples/simple_agent.yaml --verbose
```

## License

MIT

