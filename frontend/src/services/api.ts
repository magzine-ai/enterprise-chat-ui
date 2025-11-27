/** API service for backend communication. */
import type { Message, Job, Conversation } from '@/types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiService {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('auth_token', token);
  }

  getToken(): string | null {
    if (!this.token) {
      this.token = localStorage.getItem('auth_token');
    }
    return this.token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = this.getToken();
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers,
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`API error ${response.status}:`, errorText);
        // Don't throw for 400 errors when auth is disabled
        if (response.status === 400 && errorText.includes('Authentication is disabled')) {
          console.log('Auth is disabled, continuing without token');
          return {} as T; // Return empty object for failed auth requests
        }
        throw new Error(`API error: ${response.status} ${response.statusText}`);
      }

      return response.json();
    } catch (error) {
      if (error instanceof TypeError && error.message.includes('fetch')) {
        console.error('Network error - is the backend running?', error);
        throw new Error('Cannot connect to backend. Please ensure the server is running.');
      }
      throw error;
    }
  }

  // Auth
  async login(username: string, password: string): Promise<{ access_token: string; token_type: string }> {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Login failed' }));
      // If auth is disabled, don't throw - just return empty token
      if (response.status === 400 && errorData.detail?.includes('Authentication is disabled')) {
        console.log('Auth is disabled, skipping login');
        return { access_token: '', token_type: 'bearer' };
      }
      throw new Error(errorData.detail || 'Login failed');
    }

    const data = await response.json();
    this.setToken(data.access_token);
    return data;
  }

  // Conversations
  async getConversations(): Promise<Conversation[]> {
    return this.request<Conversation[]>('/conversations');
  }

  async createConversation(title?: string): Promise<Conversation> {
    return this.request<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
  }

  async deleteConversation(conversationId: number): Promise<void> {
    await this.request(`/conversations/${conversationId}`, {
      method: 'DELETE',
    });
  }

  // Messages
  async createMessage(conversationId: number, content: string, role: 'user' | 'assistant' = 'user', blocks?: any[]): Promise<{ message: Message; job_id: string | null }> {
    return this.request<{ message: Message; job_id: string | null }>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, role, blocks }),
    });
  }

  async getMessages(conversationId: number): Promise<Message[]> {
    return this.request<Message[]>(`/conversations/${conversationId}/messages`);
  }

  // Jobs
  async createJob(type: string, params?: Record<string, any>, conversationId?: number): Promise<Job> {
    return this.request<Job>('/jobs', {
      method: 'POST',
      body: JSON.stringify({ type, params, conversation_id: conversationId }),
    });
  }

  async getJob(jobId: string): Promise<Job> {
    return this.request<Job>(`/jobs/${jobId}`);
  }

  // Splunk Query Execution
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
    return this.request('/splunk/execute', {
      method: 'POST',
      body: JSON.stringify({
        query,
        earliest_time: earliestTime,
        latest_time: latestTime,
        language: 'spl',
      }),
    });
  }
}

export const apiService = new ApiService();
