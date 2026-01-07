# Agent Toolkit Quick Start Guide

## Installation

```bash
cd agent-toolkit
pip install -r requirements.txt
```

## Basic Usage

### 1. Run a Simple Agent

```bash
python -m src.agent_wrapper --config examples/simple_agent.yaml --verbose
```

### 2. Run a Workflow Agent with Conditions

```bash
python -m src.agent_wrapper --config examples/workflow_agent.yaml --verbose
```

### 3. Run a Multi-Agent Workflow

```bash
python -m src.agent_wrapper --config examples/multi_agent_workflow.json --verbose
```

### 4. List All Registered Agents

```bash
python -m src.agent_wrapper --list --registry-dir examples
```

## Python API Usage

### Basic Execution

```python
from src.agent_wrapper import AgentWrapper

# Create wrapper
wrapper = AgentWrapper()

# Load and execute agent
agent = wrapper.load_agent("examples/simple_agent.yaml")
result = wrapper.execute_sync(agent, verbose=True)

print(result)
```

### Register Custom Actions

```python
from src.agent_wrapper import AgentWrapper

def my_custom_action(input_data: str) -> dict:
    """Custom action handler."""
    return {"result": f"Processed: {input_data}"}

# Create wrapper and register custom action
wrapper = AgentWrapper()
wrapper.register_action("my_custom_action", my_custom_action)

# Use in agent declaration
agent = wrapper.load_agent("my_agent.yaml")
result = wrapper.execute_sync(agent)
```

### Agent Registry

```python
from src.agent_wrapper import AgentWrapper

wrapper = AgentWrapper()

# Register multiple agents
wrapper.register_agent("examples/simple_agent.yaml")
wrapper.register_agent("examples/workflow_agent.yaml")

# List registered agents
wrapper.registry.display_registry()

# Execute registered agent
result = wrapper.execute_registered("SimpleAgent", verbose=True)
```

## Creating Your Own Agent

### 1. Create a YAML Declaration

```yaml
name: "MyCustomAgent"
description: "My custom agent workflow"
type: "workflow"
version: "1.0.0"

workflow:
  variables:
    my_var: "value"
  
  steps:
    - name: "step1"
      type: "action"
      action: "greet"
      parameters:
        message: "Hello from my agent!"
    
    - name: "step2"
      type: "action"
      action: "process"
      parameters:
        input: "{{my_var}}"
      depends_on:
        - "step1"
```

### 2. Execute Your Agent

```bash
python -m src.agent_wrapper --config my_agent.yaml --verbose
```

## Next Steps

- See `examples/` for more complex workflows
- Check `README.md` for detailed documentation
- Review `src/` for implementation details

