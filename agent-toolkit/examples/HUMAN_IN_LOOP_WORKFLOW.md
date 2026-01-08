# Human-in-the-Loop Multi-Agent Workflow

This document describes the human-in-the-loop workflow system with multiple specialized agents.

## Architecture

```
User Prompt
    ↓
Selector Agent (routes to appropriate agent)
    ↓
┌─────────────────────────────────────────┐
│  Specialized Agents:                    │
│  - Splunk Agent                         │
│  - Email Builder Agent                  │
│  - API Discovery Agent (RAG)            │
│  - General Agent                        │
└─────────────────────────────────────────┘
    ↓
Human Review (optional)
    ↓
Response Builder Agent (formats for UI)
    ↓
Human Confirmation (for actions like sending emails)
    ↓
Final Response
```

## Agents

### 1. Selector Agent (`selector_agent.yaml`)
- **Purpose**: Analyzes user prompts and routes to appropriate specialized agent
- **Input**: User prompt
- **Output**: Selected agent name
- **Uses**: LLM to analyze prompt and match to agent capabilities

### 2. Splunk Agent (`splunk_agent.yaml`)
- **Purpose**: Handles Splunk queries, log analysis, and observability
- **Features**:
  - Understands Splunk queries
  - Generates SPL (Search Processing Language) queries
  - Executes queries via Splunk REST API
  - Human approval step for query execution
- **Human-in-Loop**: Query approval before execution

### 3. Email Builder Agent (`email_builder_agent.yaml`)
- **Purpose**: Composes and builds email content
- **Features**:
  - Generates email content using LLM
  - Human review step for email content
  - Applies feedback and revisions
- **Human-in-Loop**: Email content review and feedback

### 4. Email Sending Tool (`email_sending_tool.yaml`)
- **Purpose**: Sends emails via SMTP
- **Features**:
  - Validates email data
  - Human confirmation before sending
  - SMTP integration
- **Human-in-Loop**: Final confirmation before sending

### 5. API Discovery Agent (`api_discovery_agent.yaml`)
- **Purpose**: Answers API questions using RAG (Retrieval Augmented Generation)
- **Features**:
  - Searches OpenSearch index for API documentation
  - Uses embeddings for semantic search
  - Generates answers with code examples
- **Human-in-Loop**: Optional review of API answers

### 6. General Agent (`general_agent.yaml`)
- **Purpose**: Handles general questions and conversations
- **Features**:
  - Conversational LLM interface
  - Maintains conversation history
- **Human-in-Loop**: None (direct responses)

### 7. Response Builder Agent (`response_builder_agent.yaml`)
- **Purpose**: Formats responses in UI-expected format
- **Features**:
  - Standardizes response structure
  - Adds metadata (timestamp, agent name, etc.)
  - Validates format
- **Output Format**:
  ```json
  {
    "success": true,
    "data": {...},
    "metadata": {
      "agent": "agent_name",
      "timestamp": "2024-01-01T00:00:00",
      "response_type": "standard"
    }
  }
  ```

## Main Workflow (`human_in_loop_workflow.yaml`)

The main workflow orchestrates all agents with human-in-the-loop steps:

1. **Agent Selection**: Selector agent routes prompt
2. **Agent Execution**: Execute selected specialized agent
3. **Human Review**: Optional review step (if `require_approval=true`)
4. **Response Building**: Format response for UI
5. **Final Confirmation**: Human confirmation for actions (e.g., sending emails)

## Usage

### Basic Execution

```python
from src.agent_wrapper import AgentWrapper

# Initialize with Google ADK
adk_config = {
    "api_key": os.getenv("GOOGLE_API_KEY"),
    "model_name": "gemini-pro"
}

wrapper = AgentWrapper(google_adk_config=adk_config)

# Load and execute main workflow
agent = wrapper.load_agent("examples/human_in_loop_workflow.yaml")
result = wrapper.execute_sync(
    agent,
    context={
        "user_prompt": "Send an email to john@example.com about the API documentation",
        "require_approval": True,
        "require_confirmation": True
    },
    verbose=True
)
```

### Command Line

```bash
# Set required environment variables
export GOOGLE_API_KEY=your-key
export SPLUNK_ENDPOINT=https://splunk.example.com:8089
export SPLUNK_TOKEN=your-token
export OPENSEARCH_ENDPOINT=https://opensearch.example.com
export OPENSEARCH_INDEX=api-docs
export SMTP_SERVER=smtp.example.com
export SMTP_USER=user@example.com
export SMTP_PASSWORD=password

# Execute workflow
python -m src.agent_wrapper \
  --config examples/human_in_loop_workflow.yaml \
  --google-api-key $GOOGLE_API_KEY \
  --verbose
```

## Human-in-the-Loop Steps

### 1. Query Approval (Splunk Agent)
- **When**: Before executing Splunk queries
- **Action**: Review generated SPL query
- **Timeout**: Configurable (default: 5 minutes)
- **Control**: Set `require_approval=true` in workflow variables

### 2. Email Content Review (Email Builder)
- **When**: After generating email content
- **Action**: Review and provide feedback
- **Timeout**: 30 seconds
- **Control**: Automatic for email builder agent

### 3. Email Sending Confirmation
- **When**: Before sending emails
- **Action**: Final confirmation
- **Timeout**: 60 seconds
- **Control**: Set `require_confirmation=true`

### 4. General Response Review
- **When**: After agent execution (optional)
- **Action**: Review agent response
- **Timeout**: 5 minutes
- **Control**: Set `require_approval=true` in workflow

## Configuration

### Environment Variables

```bash
# Google ADK
GOOGLE_API_KEY=your-api-key

# Splunk
SPLUNK_ENDPOINT=https://splunk.example.com:8089
SPLUNK_TOKEN=your-splunk-token

# OpenSearch (for RAG)
OPENSEARCH_ENDPOINT=https://opensearch.example.com
OPENSEARCH_INDEX=api-docs

# SMTP (for email sending)
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USER=user@example.com
SMTP_PASSWORD=password
```

### Workflow Variables

```yaml
workflow:
  variables:
    user_prompt: "Your user prompt here"
    require_approval: true      # Enable human review
    require_confirmation: true   # Enable confirmation for actions
    approval_timeout: 300       # Timeout in seconds
```

## Customization

### Adding New Agents

1. Create agent YAML file in `examples/`
2. Add action handler in `src/custom_actions.py`
3. Register action in `AgentWrapper._register_custom_actions()`
4. Update selector agent keywords

### Modifying Human-in-Loop Steps

Edit the workflow YAML to:
- Add/remove review steps
- Change timeout values
- Modify approval conditions
- Add custom confirmation logic

## Example Scenarios

### Scenario 1: Splunk Query
```
User: "Show me errors from the last hour"
→ Selector: Routes to Splunk Agent
→ Splunk Agent: Generates SPL query
→ Human Review: Approve query
→ Execute: Runs query
→ Response Builder: Formats results
```

### Scenario 2: Email Composition
```
User: "Send email to team about API changes"
→ Selector: Routes to Email Builder
→ Email Builder: Generates email content
→ Human Review: Review and provide feedback
→ Email Builder: Revises based on feedback
→ Response Builder: Formats email
→ Human Confirmation: Confirm sending
→ Email Tool: Sends email
```

### Scenario 3: API Discovery
```
User: "How do I authenticate with the API?"
→ Selector: Routes to API Discovery Agent
→ API Discovery: Searches RAG index
→ API Discovery: Generates answer with examples
→ Response Builder: Formats response
```

## Troubleshooting

1. **Agent not selected correctly**: Update selector agent keywords
2. **Human review timeout**: Increase timeout in workflow variables
3. **Email not sending**: Check SMTP configuration
4. **RAG not finding results**: Verify OpenSearch index and endpoint
5. **Splunk query fails**: Check Splunk endpoint and token

