# cURL Examples for Agentic-Direct API

## Endpoint
`POST /conversations/{conversation_id}/messages/agentic-direct`

## Request Body Schema
```json
{
  "content": "string (required)",
  "role": "string (default: 'user')",
  "blocks": "array (optional)"
}
```

## Basic cURL Command (No Authentication)

If authentication is disabled (`auth_enabled: false`):

```bash
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Search for code that calls startDemo and generate a Splunk query",
    "role": "user"
  }'
```

## With Authentication Token

If authentication is enabled, include the Bearer token:

```bash
# First, get a token (if using OAuth2)
TOKEN=$(curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=dev&password=dev" | jq -r '.access_token')

# Then use the token
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "content": "Search for code that calls startDemo and generate a Splunk query",
    "role": "user"
  }'
```

## Complete Example with All Fields

```bash
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Search for code that calls startDemo and generate a Splunk query",
    "role": "user",
    "blocks": [
      {
        "type": "markdown",
        "content": "Additional context"
      }
    ]
  }'
```

## Pretty Print Response (using jq)

```bash
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Search for code that calls startDemo and generate a Splunk query",
    "role": "user"
  }' | jq '.'
```

## Save Response to File

```bash
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Search for code that calls startDemo and generate a Splunk query",
    "role": "user"
  }' > response.json
```

## With Verbose Output (for debugging)

```bash
curl -v -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Search for code that calls startDemo and generate a Splunk query",
    "role": "user"
  }'
```

## Example Responses

### Success Response
```json
{
  "user_message": {
    "id": 123,
    "content": "Search for code that calls startDemo and generate a Splunk query",
    "role": "user",
    "conversation_id": 1,
    "created_at": "2024-01-15T10:30:00Z",
    "blocks": null
  },
  "assistant_message": {
    "id": 124,
    "content": "I found the following code...",
    "role": "assistant",
    "conversation_id": 1,
    "created_at": "2024-01-15T10:30:05Z",
    "blocks": [
      {
        "type": "code",
        "language": "java",
        "content": "public void startDemo() { ... }"
      },
      {
        "type": "code",
        "language": "spl",
        "content": "index=main | search startDemo"
      }
    ]
  }
}
```

### Error Response (Conversation Not Found)
```json
{
  "detail": "Conversation not found"
}
```

## Create Conversation First

If you don't have a conversation ID yet:

```bash
# Create a new conversation
CONVERSATION_ID=$(curl -X POST "http://localhost:8000/conversations" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Code Search Query",
    "thinking_mode": "thinking",
    "agent": "orchestrator"
  }' | jq -r '.id')

# Then use the conversation ID
curl -X POST "http://localhost:8000/conversations/$CONVERSATION_ID/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Search for code that calls startDemo and generate a Splunk query",
    "role": "user"
  }'
```

## One-Liner Script

```bash
#!/bin/bash
# Send a message to agentic-direct endpoint

CONVERSATION_ID=${1:-1}
MESSAGE=${2:-"Hello, can you help me search for code?"}

curl -X POST "http://localhost:8000/conversations/$CONVERSATION_ID/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d "{
    \"content\": \"$MESSAGE\",
    \"role\": \"user\"
  }" | jq '.'
```

Usage:
```bash
chmod +x send_message.sh
./send_message.sh 1 "Search for code that calls startDemo"
```

## Testing Different Agent Types

The agentic-direct endpoint automatically uses the WorkflowOrchestrator which selects appropriate agents. You can test different types of queries:

### Code Search Query
```bash
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Find all methods that call startDemo in the codebase",
    "role": "user"
  }'
```

### Splunk Query Request
```bash
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Generate a Splunk query to find errors in the last 24 hours",
    "role": "user"
  }'
```

### Email Generation
```bash
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Generate and send an email summarizing the code search results",
    "role": "user"
  }'
```

### Complex Multi-Agent Query
```bash
curl -X POST "http://localhost:8000/conversations/1/messages/agentic-direct" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Search for code that calls startDemo, generate a Splunk query for it, and create a summary email",
    "role": "user"
  }'
```

## WebSocket Activity Updates

Note: The agentic-direct endpoint also sends real-time activity updates via WebSocket. To see these updates, you need to connect to the WebSocket endpoint:

```bash
# Using wscat (install with: npm install -g wscat)
wscat -c "ws://localhost:8000/ws?conversation_id=1"
```

Activity updates will be sent as:
```json
{
  "type": "conversation.activity",
  "data": {
    "conversation_id": 1,
    "activity": "Selector Agent: Analyzing user intent...",
    "details": {
      "step": "intent_analysis",
      "agent": "selector"
    }
  }
}
```

## Environment Variables

Default configuration:
- **Host**: `localhost`
- **Port**: `8000`
- **Base URL**: `http://localhost:8000`
- **Auth**: Disabled by default (`auth_enabled: false`)

To change the port, set the `PORT` environment variable or modify the uvicorn command.

