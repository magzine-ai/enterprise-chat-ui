/**
 * Type Definitions
 * 
 * This file contains all TypeScript type definitions for the chat application.
 * 
 * Core Types:
 * - Message: Chat message with blocks
 * - Block: Content block (chart, code, table, etc.)
 * - Conversation: Chat conversation
 * - Job: Async job for long-running operations
 * 
 * Block Types:
 * Each block type has its own data structure. See Block interface for details.
 */

export interface Message {
  id: number;
  content: string;
  role: 'user' | 'assistant';
  conversation_id: number;
  created_at: string;
  blocks?: Block[];
}

export interface Block {
  type: 
    | 'markdown' 
    | 'list' 
    | 'chart' 
    | 'splunk-chart'
    | 'code'
    | 'query'
    | 'table'
    | 'json-explorer'
    | 'timeline'
    | 'search-filter'
    | 'alert'
    | 'collapsible'
    | 'form-viewer'
    | 'file-upload-download'
    | 'checklist'
    | 'diagram'
    | 'async-placeholder' 
    | 'plugin-widget';
  data?: any;
}

export interface Job {
  id: number;
  job_id: string;
  type: string;
  status: 'queued' | 'started' | 'progress' | 'completed' | 'failed';
  progress: number;
  conversation_id?: number;
  params?: Record<string, any>;
  result?: Record<string, any>;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: number;
  title?: string;
  created_at: string;
  updated_at: string;
}

export interface WebSocketMessage {
  type: 'message.new' | 'job.update' | 'ack';
  data: any;
}

