# Components Guide - Enterprise Chat UI

## Overview

This application includes reusable block components that can display rich content types including code snippets, executable queries, data tables, and Splunk-style charts. All components are dynamically bound from API responses.

## Quick Start

### Testing the Components

Try these messages in the chat to see different components:

1. **Code Block**: "Show me a SQL query" or "Show code example"
2. **Query Block**: "Show Splunk query" or "Execute SQL query"
3. **Data Table**: "Show data table" or "Display table data"
4. **Charts**: "Create a chart" or "Show timechart" or "Bar chart"
5. **Combined**: "Show SQL query with results"

## Component Architecture

```
BlockRenderer (Main Router)
  ├── CodeBlock - Code snippets with syntax highlighting
  ├── QueryBlock - Executable SQL/Splunk queries
  ├── DataTable - Sortable, paginated data tables
  ├── SplunkChart - Multiple chart types (line, bar, area, pie, timechart)
  └── ... (other existing blocks)
```

## Component Details

### 1. CodeBlock

**Location**: `frontend/src/components/blocks/CodeBlock.tsx`

**Features**:
- Syntax highlighting support
- Copy to clipboard functionality
- Optional title
- Dark theme code display

**Usage Example**:
```json
{
  "type": "code",
  "data": {
    "code": "SELECT * FROM users",
    "language": "sql",
    "title": "User Query"
  }
}
```

### 2. QueryBlock

**Location**: `frontend/src/components/blocks/QueryBlock.tsx`

**Features**:
- Displays SQL or Splunk queries
- Execute button with loading state
- Auto-execute option
- Results displayed in DataTable
- Execution time tracking

**Usage Example**:
```json
{
  "type": "query",
  "data": {
    "query": "index=web_logs_UI | stats count by status",
    "language": "spl",
    "autoExecute": true
  }
}
```

### 3. DataTable

**Location**: `frontend/src/components/blocks/DataTable.tsx`

**Features**:
- Sortable columns
- Pagination
- Row numbers
- Hover effects
- Responsive design

**Usage Example**:
```json
{
  "type": "table",
  "data": {
    "columns": ["ID", "Name", "Status"],
    "rows": [
      ["1", "Item A", "Active"],
      ["2", "Item B", "Inactive"]
    ]
  }
}
```

### 4. SplunkChart

**Location**: `frontend/src/components/blocks/SplunkChart.tsx`

**Features**:
- Multiple chart types: line, bar, area, pie, timechart
- Multi-series support
- Customizable axes
- Legend support
- Responsive sizing

**Usage Example**:
```json
{
  "type": "splunk-chart",
  "data": {
    "type": "timechart",
    "title": "Request Rate",
    "data": [
      { "time": "10:00", "requests": 1000 },
      { "time": "11:00", "requests": 1200 }
    ]
  }
}
```

## API Integration

### Backend Response Format

Messages from the API can include blocks:

```json
{
  "id": 1,
  "content": "Here's your query results:",
  "role": "assistant",
  "blocks": [
    {
      "type": "query",
      "data": { ... }
    },
    {
      "type": "table",
      "data": { ... }
    }
  ]
}
```

### Mock API Examples

The mock API automatically generates blocks based on user messages:

- "Show SQL query" → Generates code + query blocks
- "Create chart" → Generates splunk-chart block
- "Display table" → Generates table block
- "Splunk query" → Generates query block with SPL

## Styling

All components use CSS variables for theming:
- `--bg-primary`, `--bg-secondary`, `--bg-tertiary`
- `--text-primary`, `--text-secondary`
- `--border-color`
- `--user-bubble`

Styles are defined in `App.css` and follow the modern chat UI design.

## Extending Components

### Adding a New Block Type

1. Create component in `components/blocks/YourBlock.tsx`
2. Add type to `types/index.ts`
3. Update `BlockRenderer.tsx` to handle the new type
4. Update mock API (if using) to generate the type

### Example: Adding a Map Block

```typescript
// 1. Create MapBlock.tsx
export const MapBlock: React.FC<MapBlockProps> = ({ data }) => {
  // Component implementation
};

// 2. Add to types
type: 'map' | ...

// 3. Add to BlockRenderer
case 'map':
  return <MapBlock {...block.data} />;
```

## Developer Notes

### Component Props

All components use TypeScript interfaces for type safety. Check each component file for detailed prop documentation.

### Error Handling

Components handle missing or invalid data gracefully:
- Empty states for no data
- Error messages for failures
- Loading states for async operations

### Performance

- Components use React.memo where appropriate
- Large tables support pagination
- Charts are rendered with ResponsiveContainer
- Code blocks have max-height with scrolling

## Testing

### Manual Testing

Use these test messages:
- "Show SQL query" - Tests code block
- "Execute Splunk query" - Tests query block with execution
- "Display data table" - Tests table block
- "Create bar chart" - Tests chart block
- "Show code example" - Tests code block with examples

### Component Testing

Each component can be tested independently:

```typescript
import { render } from '@testing-library/react';
import CodeBlock from './blocks/CodeBlock';

test('renders code block', () => {
  render(<CodeBlock code="test" language="sql" />);
  // assertions
});
```

## Documentation

See `frontend/src/components/blocks/README.md` for detailed component documentation including:
- Complete prop interfaces
- Usage examples
- Best practices
- Performance considerations

## Support

For questions or issues:
1. Check component README files
2. Review TypeScript interfaces
3. Check console for errors
4. Review API response format


