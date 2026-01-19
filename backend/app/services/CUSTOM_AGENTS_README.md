# Custom Agents Documentation

## Overview

This module provides custom agents built using the `CustomAgent` pattern from `smart_sdk`. These agents use event-driven architecture with `InvocationContext` and `Event`-based flow control, following the same pattern as shown in the `ConditionChecker` example.

## Available Custom Agents

### 1. CustomSelectorAgent

**Purpose**: Analyzes user intent and selects appropriate specialized agents with workflow planning.

**Features**:
- Analyzes user messages using LLM
- Generates workflow plans with phases
- Supports parallel, sequential, conditional, and human approval phases
- Falls back to keyword-based selection if LLM fails
- Stores workflow plan in session state

**Usage**:
```python
from app.services.custom_agents import CustomSelectorAgent

# Initialize agent
selector = CustomSelectorAgent()

# Use in a workflow (requires InvocationContext from smart_sdk)
# The agent will:
# 1. Read user_message from context.session.state
# 2. Analyze intent and generate workflow plan
# 3. Store plan in context.session.state["workflow_plan"]
# 4. Yield Event with workflow plan
```

**Session State Requirements**:
- `user_message`: User's message to analyze
- `conversation_history`: Previous conversation messages
- `conversation_id`: ID of the conversation
- `model`: (Optional) Model instance, will use `get_model()` if not provided

**Session State Output**:
- `workflow_plan`: Generated workflow plan with phases
- `workflow_type`: "simple" or "complex"

### 2. CustomWorkflowAgent

**Purpose**: Orchestrates workflow execution with phase-based execution, human approval, and summarization.

**Features**:
- Executes workflow phases (parallel, sequential, human_approval, summarization)
- Manages phase dependencies and conditions
- Handles human-in-the-loop approvals
- Generates LLM-based summaries with structured UI blocks
- Uses ResponseBuilderAgent for final response formatting
- Stores all results in session state

**Usage**:
```python
from app.services.custom_agents import CustomWorkflowAgent

# Initialize agent
workflow = CustomWorkflowAgent()

# Use in a workflow (requires InvocationContext with workflow_plan in state)
# The agent will:
# 1. Read workflow_plan from context.session.state
# 2. Execute each phase sequentially
# 3. Yield Event for each phase completion
# 4. Yield final Event with complete result
```

**Session State Requirements**:
- `workflow_plan`: Workflow plan from CustomSelectorAgent
- `user_message`: User's message
- `conversation_id`: ID of the conversation
- `conversation_history`: Previous conversation messages
- `model`: (Optional) Model instance
- `agents`: (Optional) Dictionary of agent instances, will be created if not provided

**Session State Output**:
- `phase_results`: Dictionary of results from each phase
- `all_agent_results`: List of all AgentResult objects
- `final_result`: Final aggregated result
- `workflow_completed`: Boolean indicating completion

## Workflow Plan Structure

Both agents work with a workflow plan structure:

```json
{
  "workflow_type": "simple" or "complex",
  "phases": [
    {
      "phase": 1,
      "type": "parallel" or "sequential" or "human_approval" or "summarization",
      "agents": ["agent1", "agent2"],
      "condition": null or "condition_expression",
      "depends_on": ["phase_1"],
      "approval_type": "review" or "confirmation" (if type is human_approval)
    }
  ],
  "summarization": {
    "required": true or false,
    "agent": "general"
  },
  "human_approval": {
    "required": true or false,
    "steps": ["review", "confirmation"]
  },
  "reasoning": "Why this workflow structure was selected"
}
```

## Phase Types

1. **parallel**: Execute multiple agents concurrently
2. **sequential**: Execute agents one after another, passing results between them
3. **human_approval**: Pause workflow and request human approval
4. **summarization**: Generate LLM-based summary of previous phase results

## Event Flow

### CustomSelectorAgent Events

```python
# Success event
Event(
    author="custom_selector",
    content=json.dumps({
        "workflow_plan": {...},
        "selected_agents": ["agent1", "agent2"],
        "status": "completed"
    }),
    actions=EventActions(escalate=False)
)

# Error event (with fallback)
Event(
    author="custom_selector",
    content=json.dumps({
        "workflow_plan": {...},
        "status": "completed",
        "fallback": True,
        "error": "..."
    }),
    actions=EventActions(escalate=False)
)
```

### CustomWorkflowAgent Events

```python
# Phase completion event
Event(
    author="custom_workflow",
    content=json.dumps({
        "phase": 1,
        "type": "sequential",
        "status": "completed",
        "result": "Phase result content"
    }),
    actions=EventActions(escalate=False)
)

# Final result event
Event(
    author="custom_workflow",
    content=json.dumps({
        "status": "completed",
        "result": {
            "content": "Final response",
            "blocks": [...],
            "metadata": {...}
        }
    }),
    actions=EventActions(escalate=False)
)

# Error event
Event(
    author="custom_workflow",
    content=json.dumps({
        "error": "Error message",
        "status": "failed"
    }),
    actions=EventActions(escalate=True)
)
```

## Integration with Existing Code

The custom agents are designed to work alongside the existing `SelectorAgent` and `WorkflowOrchestrator` classes. They provide the same capabilities but use:

1. **Event-driven architecture** instead of direct method calls
2. **Session state management** via `InvocationContext`
3. **Event-based flow control** with `EventActions(escalate=True/False)`

## Requirements

- `smart_sdk` with `CustomAgent` support
- `smart_sdk.types` with `Event`, `EventActions`, `InvocationContext`
- All dependencies from `conversations_agentic_direct.py`

## Example Workflow

```python
# 1. Initialize context with user message
context.session.state = {
    "user_message": "Search for code that calls startDemo and generate a Splunk query",
    "conversation_id": 123,
    "conversation_history": [...]
}

# 2. Run CustomSelectorAgent
selector = CustomSelectorAgent()
async for event in selector.run(context):
    if event.author == "custom_selector":
        plan = json.loads(event.content)
        # Plan is also stored in context.session.state["workflow_plan"]

# 3. Run CustomWorkflowAgent
workflow = CustomWorkflowAgent()
async for event in workflow.run(context):
    if event.author == "custom_workflow":
        if "status" in json.loads(event.content) and json.loads(event.content)["status"] == "completed":
            final_result = json.loads(event.content)["result"]
            # Final result is also stored in context.session.state["final_result"]
```

## Differences from Existing Agents

| Feature | Existing Agents | Custom Agents |
|---------|----------------|---------------|
| Architecture | Direct method calls | Event-driven |
| State Management | Method parameters | Session state |
| Flow Control | Return values | Event escalation |
| Integration | Direct instantiation | LoopAgent/Workflow integration |
| Error Handling | Exceptions | Event-based errors |

Both approaches provide the same functionality but are optimized for different use cases:
- **Existing agents**: Direct, synchronous-style execution
- **Custom agents**: Event-driven, workflow-integrated execution

