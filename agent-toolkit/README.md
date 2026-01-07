# Agent Toolkit

A flexible agent framework built on Google ADK (Agent Development Kit) that allows you to define and execute workflow-based agents using YAML or JSON declarations.

## Features

- **Workflow-based Agents**: Define complex agent workflows using declarative YAML/JSON
- **Multiple Agent Support**: Create and manage multiple agent declarations
- **Google ADK Integration**: Built on top of Google's Agent Development Kit
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
│   └── agent_registry.py     # Agent registry and management
├── examples/
│   ├── simple_agent.yaml
│   ├── workflow_agent.yaml
│   └── multi_agent_workflow.json
├── configs/
│   └── default_config.yaml
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

# Load and execute agent
wrapper = AgentWrapper()
agent = wrapper.load_agent("examples/simple_agent.yaml")
result = wrapper.execute(agent)
print(result)
```

### 3. Execute from Command Line

```bash
python -m src.agent_wrapper --config examples/simple_agent.yaml
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

