# Enterprise Chat UI - Complete Developer Guide

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Getting Started](#getting-started)
5. [Development Guide](#development-guide)
6. [Architecture](#architecture)
7. [Key Features](#key-features)
8. [Component Guide](#component-guide)
9. [State Management](#state-management)
10. [Services & API](#services--api)
11. [Styling](#styling)
12. [Adding New Features](#adding-new-features)
13. [Troubleshooting](#troubleshooting)
14. [Best Practices](#best-practices)

---

## 🎯 Project Overview

Enterprise Chat UI is a modern, production-ready chat application built with React, TypeScript, and Vite. It provides a ChatGPT-like interface with support for multiple conversations, rich interactive components, and real-time updates.

### Key Capabilities

- **Multi-Conversation Management**: Create, search, and organize multiple chat conversations
- **Rich Content Blocks**: Support for charts, tables, code, queries, forms, and more
- **Splunk Integration**: Specialized components for Splunk query execution and visualization
- **Real-time Updates**: WebSocket support for live message and job updates
- **Mock Services**: Frontend-only development mode with in-memory data
- **Administration Marketplace**: Component marketplace for onboarding and integrations

---

## 🛠️ Technology Stack

### Core Technologies

- **React 18.2+**: UI library
- **TypeScript 5.3+**: Type safety
- **Vite 5.0+**: Build tool and dev server
- **Redux Toolkit 2.0+**: State management
- **React Redux 9.0+**: React bindings for Redux

### Key Libraries

- **react-markdown**: Markdown rendering
- **recharts**: Chart visualizations
- **react-hook-form**: Form handling
- **zod**: Schema validation

### Development Tools

- **Jest**: Testing framework
- **TypeScript**: Type checking
- **ESLint**: Code linting (if configured)

---

## 📁 Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   │   ├── blocks/          # Content block components
│   │   │   ├── CodeBlock.tsx
│   │   │   ├── QueryBlock.tsx
│   │   │   ├── SplunkChart.tsx
│   │   │   ├── DataTable.tsx
│   │   │   ├── JsonExplorer.tsx
│   │   │   ├── TimelineViewer.tsx
│   │   │   ├── SearchFilter.tsx
│   │   │   ├── AlertBlock.tsx
│   │   │   ├── CollapsibleSection.tsx
│   │   │   └── FormViewer.tsx
│   │   ├── onboarding/      # Onboarding components
│   │   │   ├── SplunkOnboarding.tsx
│   │   │   └── GrafanaOnboarding.tsx
│   │   ├── BlockRenderer.tsx
│   │   ├── ConversationSidebar.tsx
│   │   ├── MessageList.tsx
│   │   ├── MessageInput.tsx
│   │   ├── Dialog.tsx
│   │   └── Marketplace.tsx
│   ├── store/               # Redux state management
│   │   ├── index.ts         # Store configuration
│   │   ├── hooks.ts         # Typed Redux hooks
│   │   └── slices/          # Redux slices
│   │       ├── messagesSlice.ts
│   │       ├── conversationsSlice.ts
│   │       └── jobsSlice.ts
│   ├── services/            # API and service layer
│   │   ├── api.ts           # Real API client
│   │   ├── mockApi.ts       # Mock API (frontend-only)
│   │   ├── websocket.ts     # Real WebSocket
│   │   └── mockWebSocket.ts # Mock WebSocket
│   ├── types/               # TypeScript type definitions
│   │   └── index.ts
│   ├── utils/               # Utility functions
│   │   └── popupUtils.ts
│   ├── App.tsx              # Main application component
│   ├── App.css              # Global styles
│   └── main.tsx             # Application entry point
├── index.html               # Main HTML entry
├── marketplace.html         # Marketplace HTML entry
├── package.json             # Dependencies and scripts
├── tsconfig.json            # TypeScript configuration
├── vite.config.ts           # Vite configuration
└── README.md                # This file
```

---

## 🚀 Getting Started

### Prerequisites

- **Node.js**: Version 18.0 or higher
- **npm**: Version 9.0 or higher (comes with Node.js)
- **Git**: For version control

### Installation

1. **Navigate to the frontend directory**:
   ```bash
   cd enterprise-chat-ui/frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

   This will install all required packages listed in `package.json`.

### Running the Application

#### Development Mode

```bash
npm run dev
```

The application will start at `http://localhost:5173`

- **Main Chat UI**: `http://localhost:5173/`
- **Marketplace**: `http://localhost:5173/marketplace.html`

#### Production Build

```bash
npm run build
```

This creates an optimized production build in the `dist/` directory.

#### Preview Production Build

```bash
npm run preview
```

This serves the production build locally for testing.

### Environment Variables

Create a `.env` file in the `frontend/` directory:

```bash
# Use mock services (default: true)
VITE_MOCK_SERVICES=true

# Backend API URL (when using real services)
VITE_API_URL=http://localhost:8000

# WebSocket URL (when using real services)
VITE_WS_URL=ws://localhost:8000/ws
```

---

## 💻 Development Guide

### Development Mode

The app runs in **mock mode** by default, which means:
- ✅ No backend required
- ✅ In-memory data storage
- ✅ Simulated network delays
- ✅ Event-based WebSocket simulation

### Mock vs Real Services

The application supports two modes:

1. **Mock Mode** (default): Uses `mockApi.ts` and `mockWebSocket.ts`
   - No backend required
   - Perfect for frontend-only development
   - Fast iteration

2. **Production Mode**: Uses `api.ts` and `websocket.ts`
   - Connects to FastAPI backend
   - Real HTTP requests
   - Real WebSocket connection

Switch modes by setting `VITE_MOCK_SERVICES=false` in `.env`.

### Available Scripts

```bash
npm run dev        # Start development server
npm run build      # Build for production
npm run preview    # Preview production build
npm test           # Run tests (Jest configured)
npm test:watch     # Run tests in watch mode
```

---

## 🏗️ Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Application                      │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Components  │  │  Redux Store │  │   Services   │ │
│  │              │  │              │  │              │ │
│  │ - Chat UI    │  │ - Messages   │  │ - API Client │ │
│  │ - Sidebar    │  │ - Jobs       │  │ - WebSocket  │ │
│  │ - Blocks     │  │ - Convs      │  │ - Mock API   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User Action** → Component dispatches Redux action
2. **Redux Store** → Updates state
3. **Service Layer** → Makes API call (or mock call)
4. **WebSocket** → Receives real-time updates
5. **Component** → Re-renders with new data

### Component Hierarchy

```
App
├── ConversationSidebar
│   └── Dialog (for rename/delete)
├── MessageList
│   └── Message
│       └── BlockRenderer
│           ├── CodeBlock
│           ├── QueryBlock
│           ├── SplunkChart
│           └── ... (other blocks)
└── MessageInput
```

---

## ✨ Key Features

### 1. Block-Based Content System

Messages contain **blocks** - rich, interactive content components:

```typescript
{
  type: 'splunk-chart',
  data: {
    type: 'line',
    data: [...],
    title: 'Chart Title'
  }
}
```

The `BlockRenderer` component routes blocks to the correct component based on `block.type`.

### 2. Mock Services

For frontend-only development:
- `mockApi.ts`: In-memory API with simulated delays
- `mockWebSocket.ts`: Event-based WebSocket simulation

### 3. Redux State Structure

```typescript
{
  conversations: {
    conversations: Conversation[],
    currentConversationId: number | null
  },
  messages: {
    messagesByConversation: Record<number, Message[]>
  },
  jobs: {
    jobsById: Record<string, Job>
  }
}
```

### 4. Multi-Page Support

- Main chat UI: `index.html` → `main.tsx`
- Marketplace: `marketplace.html` → `marketplace-main.tsx`

---

## 🧩 Component Guide

### Core Components

#### `App.tsx`
- Main application container
- Handles authentication and WebSocket connection
- Manages conversation selection

#### `ConversationSidebar.tsx`
- Left sidebar with conversation list
- Search and folder functionality
- Conversation management (create, rename, delete)

#### `MessageList.tsx`
- Displays messages for current conversation
- Auto-scrolls to bottom on new messages
- Uses `BlockRenderer` for message blocks

#### `MessageInput.tsx`
- Chat input field
- Handles message sending and job creation
- Auto-resize textarea

#### `BlockRenderer.tsx`
Routes blocks to the correct component. **This is where you add new block types.**

### Block Components

All block components are in `components/blocks/`:

| Component | Block Type | Purpose |
|-----------|-----------|---------|
| `CodeBlock` | `code` | Syntax-highlighted code snippets |
| `QueryBlock` | `query` | Executable SQL/Splunk queries |
| `SplunkChart` | `splunk-chart` | Data visualizations |
| `DataTable` | `table` | Tabular data with sorting |
| `JsonExplorer` | `json-explorer` | Interactive JSON viewer |
| `TimelineViewer` | `timeline-viewer` | Event timeline |
| `SearchFilter` | `search-filter` | Search and filter interface |
| `AlertBlock` | `alert` | Alert/notification messages |
| `CollapsibleSection` | `collapsible` | Expandable content |
| `FormViewer` | `form-viewer` | Structured form display |

---

## 🔄 State Management

### Redux Slices

#### `conversationsSlice.ts`
Manages conversation list and current conversation:
- `setConversations`: Load all conversations
- `addConversation`: Create new conversation
- `updateConversation`: Update conversation (e.g., rename)
- `deleteConversation`: Remove conversation
- `setCurrentConversation`: Switch active conversation

#### `messagesSlice.ts`
Manages messages per conversation:
- `setMessages`: Load messages for a conversation
- `addMessage`: Add new message
- `clearMessages`: Clear messages for a conversation

**Important**: Messages are stored per conversation ID in a Record.

#### `jobsSlice.ts`
Manages async job states:
- `updateJob`: Update job progress/status
- `removeJob`: Remove completed job

### Using Redux

```typescript
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { addMessage } from '@/store/slices/messagesSlice';

const MyComponent = () => {
  const dispatch = useAppDispatch();
  const messages = useAppSelector(state => 
    state.messages.messagesByConversation[convId]
  );
  
  const handleAction = () => {
    dispatch(addMessage(newMessage));
  };
};
```

### Best Practices

1. **Use Typed Hooks**: Always use `useAppDispatch` and `useAppSelector`
2. **Memoize Selectors**: Use `useMemo` for derived state
3. **No Non-Serializable Values**: Never store functions or class instances in Redux

---

## 🌐 Services & API

### Mock API Service (`mockApi.ts`)

In-memory API service for frontend-only development:

```typescript
import { mockApiService } from '@/services/mockApi';

// Get conversations
const convs = await mockApiService.getConversations();

// Create message
const message = await mockApiService.createMessage(convId, 'Hello');

// Create job
const job = await mockApiService.createJob('chart', { range: 30 });
```

### Real API Service (`api.ts`)

For production, use the real API service:

```typescript
import { apiService } from '@/services/api';

// Same interface as mockApi
const convs = await apiService.getConversations();
```

### WebSocket Service

```typescript
import { mockWsService } from '@/services/mockWebSocket';

// Connect
mockWsService.connect(token);

// Listen for events
mockWsService.on('message.new', (message) => {
  dispatch(addMessage(message));
});
```

---

## 🎨 Styling

### CSS Variables

The app uses CSS variables for theming (defined in `App.css`):

```css
--bg-primary: #ffffff;
--bg-secondary: #f7f7f8;
--text-primary: #353740;
--user-bubble: #19c37d;
--input-focus: #10a37f;
```

### Component Styles

- Global styles in `App.css`
- Component-specific styles use BEM-like naming
- No CSS-in-JS or CSS modules (plain CSS)

### Responsive Design

- Desktop-first design
- Fixed sidebar (280px)
- Max-width chat area (1200px)
- Mobile: Not yet optimized (future work)

---

## ➕ Adding New Features

### Adding a New Block Type

1. **Create the component** in `components/blocks/`:
```typescript
// MyNewBlock.tsx
interface MyNewBlockProps {
  data: any;
}

const MyNewBlock: React.FC<MyNewBlockProps> = ({ data }) => {
  return <div>My New Block</div>;
};

export default MyNewBlock;
```

2. **Add to BlockRenderer**:
```typescript
// BlockRenderer.tsx
import MyNewBlock from './blocks/MyNewBlock';

case 'my-new-block':
  return <MyNewBlock data={block.data} />;
```

3. **Update types**:
```typescript
// types/index.ts
export interface Block {
  type: 
    | 'markdown'
    | 'my-new-block'  // Add here
    | ...
}
```

4. **Add to mock API** (if needed):
```typescript
// mockApi.ts
if (lower.includes('my new feature')) {
  blocks.push({
    type: 'my-new-block',
    data: { ... }
  });
}
```

### Adding a New Redux Slice

1. Create slice file in `store/slices/`:
```typescript
// myFeatureSlice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

const myFeatureSlice = createSlice({
  name: 'myFeature',
  initialState: { ... },
  reducers: { ... }
});

export const { myAction } = myFeatureSlice.actions;
export default myFeatureSlice.reducer;
```

2. Add to store:
```typescript
// store/index.ts
import myFeatureReducer from './slices/myFeatureSlice';

export const store = configureStore({
  reducer: {
    // ... existing reducers
    myFeature: myFeatureReducer,
  },
});
```

### Adding a New Service Method

1. Add to interface (both `api.ts` and `mockApi.ts`):
```typescript
async myNewMethod(param: string): Promise<Result> {
  // Implementation
}
```

2. Implement in both services with the same interface.

---

## 🐛 Troubleshooting

### Common Issues

#### Chart selector not showing
- Check that `allowChartTypeSwitch` or `isTimeSeries` is true
- Verify the chart type is not 'pie'
- Check browser console for errors

#### Messages not appearing
- Verify WebSocket connection
- Check Redux state in DevTools
- Ensure messages are being dispatched

#### Redux selector warnings
- Use `useMemo` for derived state
- Ensure selectors return stable references
- Check for non-serializable values in state

#### Styling issues
- Check CSS variable values
- Verify class names match
- Check for CSS specificity conflicts

#### Build errors
- Clear `node_modules` and reinstall: `rm -rf node_modules && npm install`
- Check TypeScript errors: `npm run build`
- Verify all imports are correct

---

## 📚 Best Practices

### Code Organization
- Keep components small and focused
- Extract reusable logic into hooks or utilities
- Use TypeScript for type safety
- Follow existing naming conventions

### State Management
- Use Redux for global state
- Use local state for component-specific UI state
- Never store non-serializable values in Redux

### Component Design
- Make components reusable and composable
- Use props for configuration
- Keep components pure when possible
- Document component props with JSDoc

### Performance
- Use `React.memo` for expensive components
- Avoid unnecessary re-renders
- Memoize selectors and derived state
- Lazy load heavy components if needed

### Testing
- Write unit tests for utilities
- Test component rendering
- Test Redux actions and reducers
- Use Jest and React Testing Library

---

## 📦 Dependencies

### Production Dependencies

```json
{
  "react": "^18.2.0",
  "react-dom": "^18.2.0",
  "@reduxjs/toolkit": "^2.0.1",
  "react-redux": "^9.0.4",
  "react-hook-form": "^7.49.3",
  "zod": "^3.22.4",
  "@hookform/resolvers": "^3.3.3",
  "react-markdown": "^9.0.1",
  "recharts": "^2.10.3"
}
```

### Development Dependencies

```json
{
  "@types/react": "^18.2.43",
  "@types/react-dom": "^18.2.17",
  "@vitejs/plugin-react": "^4.2.1",
  "typescript": "^5.3.3",
  "vite": "^5.0.8",
  "@testing-library/react": "^14.1.2",
  "@testing-library/jest-dom": "^6.1.5",
  "jest": "^29.7.0",
  "jest-environment-jsdom": "^29.7.0",
  "@types/jest": "^29.5.11",
  "ts-jest": "^29.1.1"
}
```

---

## 🔗 External Resources

- [React Documentation](https://react.dev)
- [Redux Toolkit Documentation](https://redux-toolkit.js.org)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Vite Documentation](https://vitejs.dev)
- [Recharts Documentation](https://recharts.org)

---

## 📝 License

See root directory for license information.

---

## 🤝 Contributing

When adding new features:
1. Follow existing code patterns
2. Add TypeScript types
3. Update this documentation
4. Test with mock services
5. Ensure no linter errors
6. Write clear commit messages

---

## 📞 Support

For issues or questions:
1. Check this documentation
2. Review existing code examples
3. Check browser console for errors
4. Review Redux DevTools for state issues

---

**Last Updated**: 2024
**Version**: 1.0.0
