# Message and Block Schema

## Message Schema

```typescript
interface Message {
  id: number;
  content: string;                    // Plain text content
  role: 'user' | 'assistant';
  conversation_id: number;
  created_at: string;                 // ISO 8601 timestamp
  blocks?: Block[];                    // Optional structured blocks
}
```

## Block Types

### 1. Markdown Block

```json
{
  "type": "markdown",
  "data": {
    "content": "# Heading\n\nParagraph with **bold** text."
  }
}
```

### 2. List Block

```json
{
  "type": "list",
  "data": {
    "items": [
      "Item 1",
      "Item 2",
      "Item 3"
    ]
  }
}
```

### 3. Chart Block

```json
{
  "type": "chart",
  "data": {
    "chartId": "chart_123",
    "dataset": [
      { "date": "2024-01-01", "value": 42 },
      { "date": "2024-01-02", "value": 55 }
    ]
  }
}
```

### 4. Async Placeholder Block

Shown while a job is processing. Replaced with final blocks on completion.

```json
{
  "type": "async-placeholder",
  "data": {
    "jobId": "job-uuid-here"
  }
}
```

### 5. Plugin Widget Block

```json
{
  "type": "plugin-widget",
  "data": {
    "url": "https://plugin.example.com/widget",
    "pluginId": "plugin-123"
  }
}
```

## Job Schema

```typescript
interface Job {
  id: number;
  job_id: string;                     // UUID
  type: string;                        // "chart", "plugin", etc.
  status: 'queued' | 'started' | 'progress' | 'completed' | 'failed';
  progress: number;                    // 0-100
  conversation_id?: number;
  params?: Record<string, any>;        // Job parameters
  result?: {                           // Final result (when completed)
    type: string;
    dataset?: any[];
    blocks?: Block[];
  };
  error?: string;                      // Error message (if failed)
  created_at: string;
  updated_at: string;
}
```

## WebSocket Message Schema

```typescript
interface WebSocketMessage {
  type: 'message.new' | 'job.update' | 'ack';
  data: any;                           // Payload depends on type
}
```

### message.new

```json
{
  "type": "message.new",
  "data": {
    "id": 1,
    "content": "Hello!",
    "role": "user",
    "conversation_id": 1,
    "created_at": "2024-01-01T00:00:00Z",
    "blocks": []
  }
}
```

### job.update

```json
{
  "type": "job.update",
  "data": {
    "job_id": "job-uuid",
    "status": "progress",
    "progress": 50,
    "result": null
  }
}
```

## Example Complete Message

```json
{
  "id": 1,
  "content": "Here's a chart showing the data:",
  "role": "assistant",
  "conversation_id": 1,
  "created_at": "2024-01-01T00:00:00Z",
  "blocks": [
    {
      "type": "markdown",
      "data": {
        "content": "## Analysis Results"
      }
    },
    {
      "type": "chart",
      "data": {
        "chartId": "chart_123",
        "dataset": [
          { "date": "2024-01-01", "value": 42 },
          { "date": "2024-01-02", "value": 55 }
        ]
      }
    }
  ]
}
```


