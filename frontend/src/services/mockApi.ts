/** Mock API service for frontend-only development. */
import type { Message, Job, Conversation } from '@/types';

const MOCK_DELAY = 300; // Simulate network delay

// In-memory storage
let conversations: Conversation[] = [];
let messagesByConversation: Record<number, Message[]> = {};
let nextConversationId = 1;
let nextMessageId = 1;
let nextJobId = 1;

// Generate mock token
const MOCK_TOKEN = 'mock-jwt-token-' + Date.now();

class MockApiService {
  private token: string | null = MOCK_TOKEN;

  constructor() {
    // Log initial state on service creation
    console.log('[Mock API] Service initialized. Initial conversations count:', conversations.length);
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('auth_token', token);
  }

  getToken(): string | null {
    return this.token || localStorage.getItem('auth_token');
  }

  private async delay(ms: number = MOCK_DELAY): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // Auth
  async login(username: string, password: string): Promise<{ access_token: string; token_type: string }> {
    await this.delay(200);
    this.setToken(MOCK_TOKEN);
    return {
      access_token: MOCK_TOKEN,
      token_type: 'bearer',
    };
  }

  // Conversations
  async getConversations(): Promise<Conversation[]> {
    await this.delay();
    // Return a copy with new objects to avoid mutation issues
    const result = conversations.map(conv => ({ ...conv })).sort((a, b) => 
      new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
    console.log(`[Mock API] getConversations() returning ${result.length} conversations:`, result.map(c => ({ id: c.id, title: c.title })));
    return result;
  }

  async createConversation(title?: string): Promise<Conversation> {
    await this.delay();
    const now = new Date().toISOString();
    const conv: Conversation = {
      id: nextConversationId++,
      title: title || 'New Chat',
      created_at: now,
      updated_at: now,
    };
    // Create a new array to avoid extensibility issues
    conversations = [...conversations, conv];
    messagesByConversation[conv.id] = [];
    return { ...conv }; // Return a copy
  }

  async updateConversationTitle(conversationId: number, title: string): Promise<void> {
    await this.delay();
    const convIndex = conversations.findIndex((c) => c.id === conversationId);
    if (convIndex !== -1) {
      conversations = [
        ...conversations.slice(0, convIndex),
        { ...conversations[convIndex], title, updated_at: new Date().toISOString() },
        ...conversations.slice(convIndex + 1),
      ];
    }
  }

  async deleteConversation(conversationId: number): Promise<void> {
    await this.delay();
    // Remove conversation from in-memory storage
    const beforeCount = conversations.length;
    conversations = conversations.filter((c) => c.id !== conversationId);
    const afterCount = conversations.length;
    // Remove messages for this conversation
    delete messagesByConversation[conversationId];
    console.log(`[Mock API] Deleted conversation ${conversationId}. Conversations: ${beforeCount} -> ${afterCount}`);
  }

  // Messages
  async createMessage(
    conversationId: number,
    content: string,
    role: 'user' | 'assistant' = 'user',
    blocks?: any[]
  ): Promise<{ message: Message; job_id: string | null }> {
    await this.delay();
    const now = new Date().toISOString();
    const message: Message = {
      id: nextMessageId++,
      content,
      role,
      conversation_id: conversationId,
      created_at: now,
      blocks: blocks || [],
    };

    // Ensure we have a mutable array
    if (!messagesByConversation[conversationId]) {
      messagesByConversation[conversationId] = [];
    }
    // Create a new array to avoid extensibility issues
    // Check for duplicates before adding
    const existingMessages = messagesByConversation[conversationId] || [];
    const isDuplicate = existingMessages.some((msg) => msg.id === message.id);
    if (!isDuplicate) {
      messagesByConversation[conversationId] = [...existingMessages, message];
      
      // Auto-generate conversation title from first user message if title is "New Chat"
      if (role === 'user' && existingMessages.length === 0) {
        const convIndex = conversations.findIndex((c) => c.id === conversationId);
        if (convIndex !== -1 && conversations[convIndex].title === 'New Chat') {
          // Generate title from first 50 chars of user message
          const generatedTitle = content.substring(0, 50).trim();
          if (generatedTitle) {
            conversations = [
              ...conversations.slice(0, convIndex),
              { ...conversations[convIndex], title: generatedTitle },
              ...conversations.slice(convIndex + 1),
            ];
          }
        }
      }
      
      // Broadcast user message via WebSocket
      if (window.dispatchEvent) {
        window.dispatchEvent(
          new CustomEvent('mock:message.new', {
            detail: message,
          })
        );
      }
    }

    // Update conversation timestamp (immutable update)
    const convIndex = conversations.findIndex((c) => c.id === conversationId);
    if (convIndex !== -1) {
      conversations = [
        ...conversations.slice(0, convIndex),
        { ...conversations[convIndex], updated_at: now },
        ...conversations.slice(convIndex + 1),
      ];
    }

    // Generate job_id for user messages (simulating async response)
    let job_id: string | null = null;
    if (role === 'user') {
      job_id = `mock-job-${nextJobId++}`;
      // Simulate thinking time (500-1500ms) then generate assistant response
      const delay = 500 + Math.random() * 1000;
      setTimeout(() => {
        this.generateAssistantResponse(conversationId, content);
      }, delay);
    }

    // Return format matching real API: { message, job_id }
    return {
      message: { ...message },
      job_id
    };
  }

  private async generateAssistantResponse(conversationId: number, userMessage: string) {
    await this.delay(500);
    const response = this.generateResponse(userMessage);
    const now = new Date().toISOString();
    
    // Generate blocks based on response type
    const blocks = this.generateBlocksForResponse(userMessage, response);
    
    const assistantMessage: Message = {
      id: nextMessageId++,
      content: typeof response === 'string' ? response : response.content || '',
      role: 'assistant',
      conversation_id: conversationId,
      created_at: now,
      blocks: blocks,
    };

    // Ensure we have a mutable array
    if (!messagesByConversation[conversationId]) {
      messagesByConversation[conversationId] = [];
    }
    // Create a new array to avoid extensibility issues
    // Check for duplicates before adding
    const existingMessages = messagesByConversation[conversationId] || [];
    const isDuplicate = existingMessages.some((msg) => msg.id === assistantMessage.id);
    if (!isDuplicate) {
      messagesByConversation[conversationId] = [...existingMessages, assistantMessage];
    }

    // Update conversation timestamp (immutable update)
    const convIndex = conversations.findIndex((c) => c.id === conversationId);
    if (convIndex !== -1) {
      conversations = [
        ...conversations.slice(0, convIndex),
        { ...conversations[convIndex], updated_at: now },
        ...conversations.slice(convIndex + 1),
      ];
    }

    // Simulate WebSocket broadcast
    if (window.dispatchEvent) {
      window.dispatchEvent(
        new CustomEvent('mock:message.new', {
          detail: assistantMessage,
        })
      );
    }

    // Return a copy to avoid extensibility issues
    return { ...assistantMessage };
  }

  private generateBlocksForResponse(userMessage: string, response: string | { content: string; blocks?: any[] }): any[] {
    const lower = userMessage.toLowerCase().trim();
    const blocks: any[] = [];
    
    // SQL queries
    if (lower.match(/(show.*sql|sql query|select.*from|create table|insert into)/)) {
      blocks.push({
        type: 'code',
        data: {
          code: `SELECT 
  user_id,
  username,
  email,
  created_at,
  last_login
FROM users
WHERE active = true
ORDER BY created_at DESC
LIMIT 100;`,
          language: 'sql',
          title: 'SQL Query Example',
        },
      });
      
      blocks.push({
        type: 'table',
        data: {
          columns: ['user_id', 'username', 'email', 'created_at', 'last_login'],
          rows: [
            ['1', 'john_doe', 'john@example.com', '2024-01-15 10:30:00', '2024-11-20 14:22:00'],
            ['2', 'jane_smith', 'jane@example.com', '2024-01-16 11:00:00', '2024-11-21 09:15:00'],
            ['3', 'bob_wilson', 'bob@example.com', '2024-01-17 12:30:00', '2024-11-19 16:45:00'],
          ],
        },
      });
    }
    
    // Splunk queries
    if (lower.match(/(splunk|spl query|index=.*\||stats count|timechart)/)) {
      blocks.push({
        type: 'query',
        data: {
          query: `index=web_logs _mockapi
| stats count by status
| sort -count`,
          language: 'spl',
          title: 'Splunk Query: Status Counts',
          autoExecute: true,
        },
      });
    }
    
    // Chart requests
    if (lower.match(/(chart|graph|visualization|plot|timechart|bar chart|line chart|show.*chart|create.*chart|visualize.*data)/)) {
      const chartType = lower.includes('bar') ? 'bar' : 
                       lower.includes('pie') ? 'pie' :
                       lower.includes('area') ? 'area' :
                       lower.includes('time') ? 'timechart' : 'line';
      
      // Generate chart data based on type
      let chartData: any[] = [];
      if (chartType === 'timechart') {
        chartData = Array.from({ length: 24 }, (_, i) => {
          const hour = String(i).padStart(2, '0') + ':00';
          return {
            time: hour,
            requests: Math.floor(Math.random() * 1000) + 500,
            errors: Math.floor(Math.random() * 50) + 10,
          };
        });
      } else if (chartType === 'pie') {
        chartData = [
          { name: 'Success', value: 1250 },
          { name: 'Warning', value: 150 },
          { name: 'Error', value: 75 },
          { name: 'Info', value: 200 },
        ];
      } else {
        // Default bar/line/area data - simple single series
        chartData = [
          { name: 'Mon', value: 1200 },
          { name: 'Tue', value: 1350 },
          { name: 'Wed', value: 1100 },
          { name: 'Thu', value: 1450 },
          { name: 'Fri', value: 1300 },
          { name: 'Sat', value: 980 },
          { name: 'Sun', value: 1050 },
        ];
      }
      
      blocks.push({
        type: 'splunk-chart',
        data: {
          type: chartType,
          title: 'Sample Data Visualization',
          data: chartData,
          xAxis: chartType === 'timechart' ? 'time' : 'name',
          yAxis: chartType === 'pie' ? 'value' : undefined,
          series: chartType === 'timechart' ? ['requests', 'errors'] : undefined,
          height: 300,
          isTimeSeries: chartType === 'timechart',
          allowChartTypeSwitch: chartType !== 'pie', // Allow switching for all charts except pie
        },
      });
    }
    
    // Code examples
    if (lower.match(/(show.*code|code example|python code|javascript code|example.*code)/)) {
      const codeExamples = [
        {
          code: `def process_data(data):
    """Process and analyze data."""
    results = []
    for item in data:
        if item['status'] == 'active':
            results.append(item)
    return results`,
          language: 'python',
          title: 'Python Example',
        },
        {
          code: `function analyzeData(data) {
  return data
    .filter(item => item.status === 'active')
    .map(item => ({
      ...item,
      processed: true
    }));
}`,
          language: 'javascript',
          title: 'JavaScript Example',
        },
      ];
      
      const example = codeExamples[Math.floor(Math.random() * codeExamples.length)];
      blocks.push({
        type: 'code',
        data: example,
      });
    }
    
    // Data table requests
    if (lower.match(/(show.*table|display.*data|list.*data|table.*data)/)) {
      blocks.push({
        type: 'table',
        data: {
          columns: ['ID', 'Name', 'Status', 'Value', 'Timestamp'],
          rows: [
            ['1', 'Item A', 'Active', '1250', '2024-11-21 10:00:00'],
            ['2', 'Item B', 'Active', '980', '2024-11-21 11:00:00'],
            ['3', 'Item C', 'Inactive', '750', '2024-11-21 12:00:00'],
            ['4', 'Item D', 'Active', '2100', '2024-11-21 13:00:00'],
            ['5', 'Item E', 'Pending', '450', '2024-11-21 14:00:00'],
          ],
        },
      });
    }
    
    // JSON explorer requests
    if (lower.match(/(json|show.*json|explore.*data|view.*json|json.*data)/)) {
      blocks.push({
        type: 'json-explorer',
        data: {
          title: 'JSON Data Explorer',
          data: {
            user: {
              id: 1,
              name: 'John Doe',
              email: 'john@example.com',
              preferences: {
                theme: 'dark',
                notifications: true,
              },
              tags: ['admin', 'developer'],
            },
            metadata: {
              created: '2024-01-15',
              updated: '2024-11-21',
            },
          },
          collapsed: false,
          maxDepth: 3,
        },
      });
    }
    
    // Timeline requests
    if (lower.match(/(timeline|events|log.*view|event.*history|show.*events)/)) {
      blocks.push({
        type: 'timeline',
        data: {
          title: 'Event Timeline',
          events: [
            {
              time: '10:00:00',
              title: 'System Started',
              description: 'Application initialized successfully',
              type: 'success',
            },
            {
              time: '10:15:30',
              title: 'User Login',
              description: 'User authenticated',
              type: 'info',
            },
            {
              time: '10:30:45',
              title: 'Warning',
              description: 'High memory usage detected',
              type: 'warning',
            },
            {
              time: '10:45:12',
              title: 'Error Occurred',
              description: 'Failed to process request',
              type: 'error',
              metadata: { errorCode: 'ERR_500', details: 'Internal server error' },
            },
          ],
          showTime: true,
          orientation: 'vertical',
        },
      });
    }
    
    // Search/filter requests
    if (lower.match(/(search|filter|find.*data|lookup)/)) {
      blocks.push({
        type: 'search-filter',
        data: {
          data: [
            { id: 1, name: 'Item A', category: 'Type 1', status: 'Active' },
            { id: 2, name: 'Item B', category: 'Type 2', status: 'Inactive' },
            { id: 3, name: 'Item C', category: 'Type 1', status: 'Active' },
            { id: 4, name: 'Item D', category: 'Type 3', status: 'Pending' },
          ],
          placeholder: 'Search items...',
          showResultsCount: true,
        },
      });
    }
    
    // Alert/notification requests
    if (lower.match(/(alert|warning|error|notification|important)/)) {
      const alertType = lower.includes('error') ? 'error' :
                       lower.includes('warning') ? 'warning' :
                       lower.includes('success') ? 'success' : 'info';
      blocks.push({
        type: 'alert',
        data: {
          type: alertType,
          title: alertType === 'error' ? 'Error' : alertType === 'warning' ? 'Warning' : 'Information',
          message: `This is a ${alertType} message. Important information or notifications can be displayed here.`,
          dismissible: true,
        },
      });
    }
    
    // Form viewer / ServiceNow change request
    if (lower.match(/(change request|servicenow|ticket|form|cr[0-9]|inc[0-9]|show.*form|display.*form)/)) {
      const isChangeRequest = lower.includes('change') || lower.includes('cr');
      const formTitle = isChangeRequest ? 'Change Request CR12345' : 'ServiceNow Ticket INC67890';
      
      blocks.push({
        type: 'form-viewer',
        data: {
          title: formTitle,
          fields: [
            {
              name: 'number',
              label: 'Number',
              value: isChangeRequest ? 'CR12345' : 'INC67890',
              type: 'text',
              icon: '📋',
            },
            {
              name: 'state',
              label: 'State',
              value: 'In Progress',
              type: 'badge',
              badgeType: 'info',
            },
            {
              name: 'priority',
              label: 'Priority',
              value: 'High',
              type: 'badge',
              badgeType: 'warning',
            },
            {
              name: 'category',
              label: 'Category',
              value: isChangeRequest ? 'Standard' : 'Incident',
              type: 'text',
            },
            {
              name: 'assigned_to',
              label: 'Assigned To',
              value: 'John Doe',
              type: 'text',
              icon: '👤',
            },
            {
              name: 'short_description',
              label: 'Short Description',
              value: isChangeRequest 
                ? 'Deploy new application version to production'
                : 'Application server experiencing high CPU usage',
              type: 'text',
            },
            {
              name: 'description',
              label: 'Description',
              value: isChangeRequest
                ? 'This change request involves deploying version 2.1.0 of the application to the production environment. All tests have passed and approval has been obtained.'
                : 'Users are reporting slow response times. Monitoring shows CPU usage at 95%. Investigation needed.',
              type: 'multiline',
            },
            {
              name: 'risk',
              label: 'Risk',
              value: 'Medium',
              type: 'badge',
              badgeType: 'warning',
            },
            {
              name: 'impact',
              label: 'Impact',
              value: 'High',
              type: 'badge',
              badgeType: 'error',
            },
            {
              name: 'planned_start',
              label: 'Planned Start',
              value: '2024-11-22T02:00:00Z',
              type: 'date',
            },
            {
              name: 'planned_end',
              label: 'Planned End',
              value: '2024-11-22T04:00:00Z',
              type: 'date',
            },
            {
              name: 'approval_status',
              label: 'Approval Status',
              value: 'Approved',
              type: 'badge',
              badgeType: 'success',
            },
            {
              name: 'sys_id',
              label: 'System ID',
              value: 'a1b2c3d4e5f6g7h8i9j0',
              type: 'text',
            },
            {
              name: 'link',
              label: 'View in ServiceNow',
              value: 'Open Ticket',
              type: 'link',
              link: 'https://servicenow.example.com/nav_to.do?uri=change_request.do?sys_id=a1b2c3d4',
            },
          ],
          sections: [
            {
              title: 'Basic Information',
              fields: ['number', 'state', 'priority', 'category'],
            },
            {
              title: 'Assignment',
              fields: ['assigned_to'],
            },
            {
              title: 'Description',
              fields: ['short_description', 'description'],
            },
            {
              title: 'Risk & Impact',
              fields: ['risk', 'impact'],
            },
            {
              title: 'Schedule',
              fields: ['planned_start', 'planned_end'],
            },
            {
              title: 'Approval',
              fields: ['approval_status'],
            },
            {
              title: 'System Information',
              fields: ['sys_id', 'link'],
              collapsed: true,
            },
          ],
          metadata: {
            created: '2024-11-20T10:30:00Z',
            updated: '2024-11-21T14:45:00Z',
            createdBy: 'System Administrator',
            updatedBy: 'Change Manager',
          },
          actions: [
            {
              label: 'Approve',
              actionId: 'approve',
              variant: 'primary',
            },
            {
              label: 'Reject',
              actionId: 'reject',
              variant: 'danger',
            },
          ],
        },
      });
    }

    // File upload/download
    if (lower.match(/(upload.*file|download.*file|file.*upload|file.*download|share.*file|attach.*file)/)) {
      blocks.push({
        type: 'file-upload-download',
        data: {
          title: 'File Manager',
          mode: 'both',
          files: [
            {
              name: 'application.log',
              size: 1048576,
              url: '/files/application.log',
              type: 'text/plain',
              uploadedAt: new Date(Date.now() - 86400000).toISOString(),
              description: 'Application logs from yesterday',
            },
            {
              name: 'config.json',
              size: 2048,
              url: '/files/config.json',
              type: 'application/json',
              uploadedAt: new Date(Date.now() - 3600000).toISOString(),
              description: 'Application configuration file',
            },
            {
              name: 'report.pdf',
              size: 5242880,
              url: '/files/report.pdf',
              type: 'application/pdf',
              uploadedAt: new Date(Date.now() - 7200000).toISOString(),
              description: 'Monthly report document',
            },
          ],
          accept: '.log,.txt,.json,.pdf,.csv',
          maxSize: 10485760, // 10MB
          multiple: true,
        },
      });
    }

    // Checklist
    if (lower.match(/(checklist|task.*list|todo.*list|deployment.*checklist|action.*items|steps.*to.*complete)/)) {
      blocks.push({
        type: 'checklist',
        data: {
          title: 'Deployment Checklist',
          items: [
            {
              id: '1',
              text: 'Backup production database',
              checked: true,
              priority: 'high',
              assignee: 'devops-team',
            },
            {
              id: '2',
              text: 'Run automated test suite',
              checked: true,
              priority: 'high',
              assignee: 'qa-team',
            },
            {
              id: '3',
              text: 'Update configuration files',
              checked: false,
              priority: 'medium',
              assignee: 'dev-team',
              dueDate: new Date(Date.now() + 86400000).toISOString().split('T')[0],
            },
            {
              id: '4',
              text: 'Deploy to staging environment',
              checked: false,
              priority: 'high',
              assignee: 'devops-team',
              dueDate: new Date(Date.now() + 172800000).toISOString().split('T')[0],
            },
            {
              id: '5',
              text: 'Perform smoke tests',
              checked: false,
              priority: 'medium',
              assignee: 'qa-team',
              notes: 'Focus on critical user flows',
            },
            {
              id: '6',
              text: 'Deploy to production',
              checked: false,
              priority: 'critical',
              assignee: 'devops-team',
              subItems: [
                {
                  id: '6-1',
                  text: 'Schedule maintenance window',
                  checked: false,
                },
                {
                  id: '6-2',
                  text: 'Notify stakeholders',
                  checked: true,
                },
                {
                  id: '6-3',
                  text: 'Execute deployment script',
                  checked: false,
                },
              ],
            },
            {
              id: '7',
              text: 'Monitor application metrics',
              checked: false,
              priority: 'high',
              assignee: 'monitoring-team',
            },
          ],
          showProgress: true,
          showPriority: true,
          showDueDate: true,
          collapsible: true,
        },
      });
    }

    // Diagram/Architecture
    if (lower.match(/(diagram|architecture|workflow|aws.*architecture|system.*design|flowchart|sequence.*diagram)/)) {
      const diagramType = lower.includes('aws') ? 'aws' :
                        lower.includes('workflow') || lower.includes('flowchart') ? 'flowchart' :
                        lower.includes('sequence') ? 'sequence' :
                        lower.includes('architecture') ? 'architecture' : 'mermaid';

      if (diagramType === 'mermaid') {
        blocks.push({
          type: 'diagram',
          data: {
            type: 'mermaid',
            title: 'System Workflow Diagram',
            description: 'High-level system workflow',
            diagram: `graph TD
    A[User Request] --> B{Authentication}
    B -->|Valid| C[Process Request]
    B -->|Invalid| D[Return Error]
    C --> E[Query Database]
    E --> F[Generate Response]
    F --> G[Return to User]
    D --> H[Log Error]`,
            interactive: true,
            showControls: true,
          },
        });
      } else if (diagramType === 'aws') {
        blocks.push({
          type: 'diagram',
          data: {
            type: 'aws',
            title: 'AWS Architecture',
            description: 'Cloud infrastructure architecture',
            diagram: `Load Balancer
Application Server
Database
S3 Storage
CloudWatch`,
            interactive: true,
            showControls: true,
          },
        });
      } else if (diagramType === 'flowchart') {
        blocks.push({
          type: 'diagram',
          data: {
            type: 'flowchart',
            title: 'Process Flow',
            description: 'Step-by-step process flow',
            diagram: `Start Process
Validate Input
Process Data
Generate Output
End Process`,
            interactive: true,
            showControls: true,
          },
        });
      } else if (diagramType === 'sequence') {
        blocks.push({
          type: 'diagram',
          data: {
            type: 'sequence',
            title: 'Sequence Diagram',
            description: 'Interaction sequence between components',
            diagram: `User Login Request
Validate Credentials
Check Permissions
Return Session Token`,
            interactive: true,
            showControls: true,
          },
        });
      } else if (diagramType === 'architecture') {
        blocks.push({
          type: 'diagram',
          data: {
            type: 'architecture',
            title: 'System Architecture',
            description: 'Layered system architecture',
            diagram: `Frontend Application
API Gateway
Business Logic Layer
Data Access Layer
Database`,
            interactive: true,
            showControls: true,
          },
        });
      }
    }
    
    return blocks;
  }

  private generateResponse(userMessage: string): string {
    const lower = userMessage.toLowerCase().trim();
    const responses: string[] = [];
    
    // Greetings
    if (lower.match(/^(hi|hello|hey|greetings|good morning|good afternoon|good evening)/)) {
      const greetings = [
        "Hello! 👋 I'm your AI assistant. How can I help you today?",
        "Hi there! Nice to meet you. What can I do for you?",
        "Hey! I'm here to help. What would you like to know?",
        "Greetings! I'm ready to assist you. How can I help?",
      ];
      return greetings[Math.floor(Math.random() * greetings.length)];
    }
    
    // Help requests
    if (lower.includes('help') || lower.includes('what can you do') || lower.includes('capabilities')) {
      return `I can help you with various tasks:

📊 **Data & Analytics**
- Generate charts and visualizations
- Analyze data and provide insights
- Process and transform data

💬 **Conversation**
- Answer questions
- Provide explanations
- Assist with problem-solving

🔧 **Tools & Features**
- Create async jobs for long-running tasks
- Generate reports and summaries
- Much more!

What would you like to try first?`;
    }
    
    // Chart/visualization requests
    if (lower.includes('chart') || lower.includes('graph') || lower.includes('visualization') || lower.includes('plot')) {
      return `Here's a sample chart visualization for you! 📊`;
    }
    
    // Questions
    if (lower.includes('?')) {
      const questionResponses = [
        `That's a great question! Let me help you with that. Based on what you're asking about "${userMessage.substring(0, 40)}${userMessage.length > 40 ? '...' : ''}", I'd suggest exploring this topic further. Would you like me to provide more details?`,
        `Interesting question! I understand you're asking about "${userMessage.substring(0, 40)}${userMessage.length > 40 ? '...' : ''}". Let me think about this... Could you provide a bit more context so I can give you a more accurate answer?`,
        `Good question! To give you the best answer about "${userMessage.substring(0, 40)}${userMessage.length > 40 ? '...' : ''}", I'd need a bit more information. What specific aspect would you like to know more about?`,
      ];
      return questionResponses[Math.floor(Math.random() * questionResponses.length)];
    }
    
    // Time/date requests
    if (lower.match(/(what.*time|current time|what.*date|current date)/)) {
      const now = new Date();
      return `The current date and time is:\n**${now.toLocaleString('en-US', { 
        weekday: 'long', 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })}**

Is there anything specific you'd like to do with this information?`;
    }
    
    // Name/identity questions
    if (lower.match(/(who are you|what are you|your name|what.*you.*called)/)) {
      return `I'm an AI assistant designed to help you with various tasks. You can call me:
- Assistant
- AI Helper
- Chat Assistant
- Or any name you prefer! 😊

I'm here to assist with questions, generate charts, process data, and much more. What would you like to do?`;
    }
    
    // Weather requests
    if (lower.includes('weather') || lower.includes('temperature') || lower.includes('forecast')) {
      return `I don't have access to real-time weather data, but I can help you with:
- Data analysis and visualization
- Creating charts from your data
- Answering questions
- Processing information

Is there something else I can help you with?`;
    }
    
    // Thank you
    if (lower.match(/(thank|thanks|appreciate|grateful)/)) {
      const thanksResponses = [
        "You're welcome! Happy to help. Is there anything else you'd like to know?",
        "My pleasure! Feel free to ask if you need anything else.",
        "You're very welcome! I'm here whenever you need assistance.",
        "Glad I could help! Let me know if you have more questions.",
      ];
      return thanksResponses[Math.floor(Math.random() * thanksResponses.length)];
    }
    
    // Goodbye
    if (lower.match(/(bye|goodbye|see you|farewell|exit|quit)/)) {
      return "Goodbye! It was nice chatting with you. Feel free to come back anytime if you need help! 👋";
    }
    
    // Data/numbers
    if (lower.match(/(data|numbers|statistics|stats|analyze|analysis)/)) {
      return `Here's some sample data analysis for you! 📊`;
    }
    
    // SQL queries
    if (lower.match(/(sql|show.*query|select.*from|database query)/)) {
      return `Here's a SQL query example with results:`;
    }
    
    // Splunk queries
    if (lower.match(/(splunk|spl query|index=)/)) {
      return `Here's a Splunk query you can execute:`;
    }
    
    // Code/programming
    if (lower.match(/(code|programming|script|function|algorithm|syntax)/)) {
      return `I can help with programming questions! While I can't execute code directly, I can:
- Explain programming concepts
- Help with syntax and structure
- Provide guidance on best practices
- Answer questions about code

What programming topic would you like to explore?`;
    }
    
    // Requests for examples
    if (lower.match(/(example|sample|demo|show me|demonstrate)/)) {
      return `I'd be happy to show you an example! Here are some things I can demonstrate:

📊 **Charts**: Click the chart button (📊) to see a sample visualization
💬 **Conversations**: We're already having one!
📈 **Data Analysis**: Ask me to analyze something

What would you like to see an example of?`;
    }
    
    // Default contextual responses
    const defaultResponses = [
      `I understand you're talking about "${userMessage.substring(0, 50)}${userMessage.length > 50 ? '...' : ''}". That's interesting! How can I help you with this?`,
      `Thanks for sharing that! Regarding "${userMessage.substring(0, 50)}${userMessage.length > 50 ? '...' : ''}", I'm here to assist. What would you like to know more about?`,
      `Got it! You mentioned "${userMessage.substring(0, 50)}${userMessage.length > 50 ? '...' : ''}". I can help you with this. What specific aspect would you like to explore?`,
      `I see! About "${userMessage.substring(0, 50)}${userMessage.length > 50 ? '...' : ''}" - that's something I can help with. What would you like to do next?`,
      `Interesting! You're asking about "${userMessage.substring(0, 50)}${userMessage.length > 50 ? '...' : ''}". Let me help you with that. Could you provide a bit more detail?`,
    ];
    
    return defaultResponses[Math.floor(Math.random() * defaultResponses.length)];
  }

  async getMessages(conversationId: number): Promise<Message[]> {
    await this.delay();
    // Return a copy with new objects to avoid mutation issues
    const messages = messagesByConversation[conversationId] || [];
    return messages.map(msg => ({ ...msg }));
  }

  // Jobs
  async createJob(
    type: string,
    params?: Record<string, any>,
    conversationId?: number
  ): Promise<Job> {
    await this.delay();
    const jobId = `job-${nextJobId++}`;
    const now = new Date().toISOString();
    
    const job: Job = {
      id: nextJobId,
      job_id: jobId,
      type,
      status: 'queued',
      progress: 0,
      conversation_id: conversationId,
      created_at: now,
      updated_at: now,
      params: params || {},
      result: null,
    };

    // Broadcast initial job creation
    this.broadcastJobUpdate(job);

    // Simulate job processing
    this.simulateJobProcessing(job);

    return job;
  }

  private async simulateJobProcessing(job: Job) {
    // Update to started
    setTimeout(() => {
      job.status = 'started';
      job.progress = 10;
      this.broadcastJobUpdate(job);
    }, 500);

    // Simulate progress updates
    const progressSteps = [20, 40, 60, 80, 100];
    progressSteps.forEach((progress, index) => {
      setTimeout(() => {
        job.progress = progress;
        job.status = progress === 100 ? 'completed' : 'progress';
        
        if (progress === 100) {
          // Generate mock chart data
          job.result = {
            blocks: [
              {
                type: 'chart',
                data: {
                  title: 'Sample Chart',
                  dataset: this.generateMockChartData(),
                },
              },
            ],
          };
        }
        
        this.broadcastJobUpdate(job);
      }, 1000 + index * 800);
    });
  }

  private generateMockChartData() {
    const data = [];
    const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    for (let i = 0; i < 7; i++) {
      data.push({
        name: labels[i],
        value: Math.floor(Math.random() * 100) + 20,
      });
    }
    return data;
  }

  private broadcastJobUpdate(job: Job) {
    if (window.dispatchEvent) {
      // Broadcast with job_id for Redux update
      window.dispatchEvent(
        new CustomEvent('mock:job.update', {
          detail: {
            job_id: job.job_id,
            ...job,
          },
        })
      );
    }
  }

  async getJob(jobId: string): Promise<Job> {
    await this.delay();
    // In a real implementation, we'd track jobs
    // For now, return a mock job
    return {
      id: 1,
      job_id: jobId,
      type: 'chart',
      status: 'completed',
      progress: 100,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      params: {},
      result: {
        blocks: [
          {
            type: 'chart',
            data: {
              title: 'Sample Chart',
              dataset: this.generateMockChartData(),
            },
          },
        ],
      },
    };
  }

  // Utility method to clear all conversations and reset state
  clearAllConversations(): void {
    conversations = [];
    messagesByConversation = {};
    nextConversationId = 1;
    nextMessageId = 1;
    nextJobId = 1;
    // Clear localStorage if needed
    localStorage.removeItem('conversations');
    localStorage.removeItem('messages');
    console.log('[Mock API] All conversations cleared, state reset');
  }

  // Splunk Query Execution (Mock)
  async executeSplunkQuery(
    query: string,
    earliestTime?: string,
    latestTime?: string
  ): Promise<{
    columns: string[];
    rows: any[][];
    rowCount: number;
    executionTime?: number;
    visualizationType?: 'table' | 'chart' | 'single-value' | 'gauge' | 'map' | 'heatmap' | 'scatter';
    visualizationConfig?: {
      chartType?: 'line' | 'bar' | 'area' | 'pie' | 'column';
      xAxis?: string;
      yAxis?: string;
      series?: string[];
      format?: string;
      valueField?: string;
      labelField?: string;
      unit?: string;
    };
    singleValue?: number;
    gaugeValue?: number;
    chartData?: any[];
    isTimeSeries?: boolean;
    allowChartTypeSwitch?: boolean;
    error?: string;
  }> {
    await this.delay(500); // Simulate network delay
    
    const queryLower = query.toLowerCase();
    
    // Determine visualization type based on query
    const isTimechart = queryLower.includes('timechart');
    const isStats = queryLower.includes('stats');
    const isSingleValue = (queryLower.includes('stats count') || queryLower.includes('stats sum')) && !queryLower.includes('by');
    
    if (isTimechart) {
      // Time series chart
      const hours = Array.from({ length: 24 }, (_, i) => i);
      return {
        columns: ['_time', 'count', 'errors'],
        rows: hours.map(h => [`${h.toString().padStart(2, '0')}:00:00`, Math.floor(Math.random() * 1000) + 500, Math.floor(Math.random() * 50) + 10]),
        rowCount: 24,
        executionTime: 0.5,
        visualizationType: 'chart',
        visualizationConfig: {
          chartType: 'line',
          xAxis: '_time',
          yAxis: 'count',
          series: ['count', 'errors']
        },
        chartData: hours.map(h => ({
          time: `${h.toString().padStart(2, '0')}:00:00`,
          count: Math.floor(Math.random() * 1000) + 500,
          errors: Math.floor(Math.random() * 50) + 10
        })),
        isTimeSeries: true,
        allowChartTypeSwitch: true
      };
    } else if (isSingleValue) {
      // Single value
      return {
        columns: ['count'],
        rows: [[Math.floor(Math.random() * 10000) + 1000]],
        rowCount: 1,
        executionTime: 0.3,
        visualizationType: 'single-value',
        visualizationConfig: {
          format: 'number',
          valueField: 'count',
          unit: ''
        },
        singleValue: Math.floor(Math.random() * 10000) + 1000,
        isTimeSeries: false
      };
    } else if (isStats && queryLower.includes('by')) {
      // Chart with grouping
      const categories = ['Success', 'Warning', 'Error', 'Info'];
      return {
        columns: ['status', 'count'],
        rows: categories.map(cat => [cat, Math.floor(Math.random() * 1000) + 100]),
        rowCount: categories.length,
        executionTime: 0.4,
        visualizationType: 'chart',
        visualizationConfig: {
          chartType: 'bar',
          xAxis: 'status',
          yAxis: 'count',
          labelField: 'status',
          valueField: 'count'
        },
        chartData: categories.map(cat => ({
          name: cat,
          value: Math.floor(Math.random() * 1000) + 100
        })),
        isTimeSeries: false,
        allowChartTypeSwitch: true
      };
    } else {
      // Default table
      return {
        columns: ['_time', 'host', 'source', 'message'],
        rows: Array.from({ length: 10 }, (_, i) => [
          new Date(Date.now() - i * 60000).toISOString(),
          `host-${i + 1}`,
          `/var/log/app.log`,
          `Sample log message ${i + 1}`
        ]),
        rowCount: 10,
        executionTime: 0.6,
        visualizationType: 'table',
        isTimeSeries: false
      };
    }
  }
}

export const mockApiService = new MockApiService();

// Expose to window for easy console access
if (typeof window !== 'undefined') {
  (window as any).clearAllConversations = () => {
    mockApiService.clearAllConversations();
  };
}

