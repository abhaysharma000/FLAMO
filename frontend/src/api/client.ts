/// <reference types="vite/client" />
/**
 * Centralized Typed API Client for FLAMO Autonomous Operations Agent.
 * Handles timeouts, network errors, structured backend responses, and SSE streaming.
 */

import { AuthStatusResponse, LoginRequest, LoginResponse } from '../types/auth';
import { HealthResponse } from '../types/health';
import { MemoryCreateRequest, MemoryItem } from '../types/memory';
import { ReportDetail, ReportSummary } from '../types/report';
import { TaskCreateRequest, TaskListResponse, TaskResponse } from '../types/task';
import { TraceEvent } from '../types/trace';

export class ApiClientError extends Error {
  public status: number;
  public detail: any;

  constructor(status: number, message: string, detail?: any) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.detail = detail;
  }
}

export class FlamoApiClient {
  private baseUrl: string;
  private defaultTimeoutMs: number;
  private csrfToken: string | null = null;

  constructor(baseUrl?: string, defaultTimeoutMs: number = 30000) {
    // Configurable via Vite environment variable, defaults to relative path in production
    const envBase =
      (typeof import.meta !== 'undefined' && (import.meta as any).env && (import.meta as any).env.VITE_API_BASE_URL) ||
      '';
    this.baseUrl = (baseUrl !== undefined ? baseUrl : envBase).replace(/\/+$/, '');
    this.defaultTimeoutMs = defaultTimeoutMs;
  }

  public setCsrfToken(token: string | null): void {
    this.csrfToken = token;
  }

  public getCsrfToken(): string | null {
    return this.csrfToken;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}, timeoutMs?: number): Promise<T> {
    const url = `${this.baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs || this.defaultTimeoutMs);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    if (this.csrfToken && ['POST', 'PUT', 'DELETE', 'PATCH'].includes((options.method || 'GET').toUpperCase())) {
      headers['X-CSRF-Token'] = this.csrfToken;
    }

    try {
      const response = await fetch(url, {
        ...options,
        credentials: 'include',
        signal: controller.signal,
        headers,
      });

      if (!response.ok) {
        let errorDetail = 'Unknown server error';
        try {
          const jsonErr = await response.json();
          errorDetail = jsonErr.detail || jsonErr.message || JSON.stringify(jsonErr);
        } catch {
          errorDetail = await response.text();
        }
        throw new ApiClientError(response.status, `HTTP ${response.status}: ${errorDetail}`, errorDetail);
      }

      if (response.status === 204) {
        return {} as T;
      }

      return (await response.json()) as T;
    } catch (err: any) {
      if (err.name === 'AbortError') {
        throw new ApiClientError(408, `Request timed out after ${timeoutMs || this.defaultTimeoutMs}ms`);
      }
      if (err instanceof ApiClientError) {
        throw err;
      }
      throw new ApiClientError(0, `Network failure connecting to ${url}: ${err.message}`);
    } finally {
      clearTimeout(timeout);
    }
  }

  // --- Health & Diagnostics ---
  public async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/api/health');
  }

  // --- Task Management ---
  public async listTasks(limit: number = 50): Promise<TaskListResponse> {
    return this.request<TaskListResponse>(`/api/tasks?limit=${encodeURIComponent(limit)}`);
  }

  public async getTask(taskId: string): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/api/tasks/${encodeURIComponent(taskId)}`);
  }

  public async createTask(req: TaskCreateRequest): Promise<TaskResponse> {
    return this.request<TaskResponse>('/api/tasks', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  public async getTaskTrace(taskId: string): Promise<TraceEvent[]> {
    return this.request<TraceEvent[]>(`/api/tasks/${encodeURIComponent(taskId)}/trace`);
  }

  public async cancelTask(taskId: string): Promise<{ task_id: string; cancelled: boolean; message: string }> {
    return this.request<{ task_id: string; cancelled: boolean; message: string }>(
      `/api/tasks/${encodeURIComponent(taskId)}/cancel`,
      { method: 'POST' }
    );
  }

  public async resumeTask(taskId: string): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/api/tasks/${encodeURIComponent(taskId)}/resume`, {
      method: 'POST',
    });
  }

  public async approveTask(taskId: string): Promise<{ task_id: string; approved: boolean; status: string }> {
    return this.request<{ task_id: string; approved: boolean; status: string }>(
      `/api/tasks/${encodeURIComponent(taskId)}/approve`,
      { method: 'POST' }
    );
  }

  public async rejectTask(
    taskId: string,
    reason: string = 'Operator declined action'
  ): Promise<{ task_id: string; rejected: boolean; status: string; reason: string }> {
    return this.request<{ task_id: string; rejected: boolean; status: string; reason: string }>(
      `/api/tasks/${encodeURIComponent(taskId)}/reject?reason=${encodeURIComponent(reason)}`,
      { method: 'POST' }
    );
  }

  // --- Reports & Artifacts ---
  public async listReports(): Promise<ReportSummary[]> {
    return this.request<ReportSummary[]>('/api/reports');
  }

  public async getReport(filename: string): Promise<ReportDetail> {
    return this.request<ReportDetail>(`/api/reports/${encodeURIComponent(filename)}`);
  }

  public getReportDownloadUrl(filename: string): string {
    return `${this.baseUrl}/api/reports/${encodeURIComponent(filename)}/download`;
  }

  // --- Semantic Memory ---
  public async searchMemory(query: string, category?: string, limit: number = 10): Promise<MemoryItem[]> {
    const params = new URLSearchParams({ query, limit: String(limit) });
    if (category) {
      params.append('category', category);
    }
    return this.request<MemoryItem[]>(`/api/memory/search?${params.toString()}`);
  }

  public async storeMemory(item: MemoryCreateRequest): Promise<{ id: string; status: string; category: string }> {
    return this.request<{ id: string; status: string; category: string }>('/api/memory', {
      method: 'POST',
      body: JSON.stringify(item),
    });
  }

  // --- Real-time Streaming ---
  public connectTaskEvents(
    taskId: string,
    onEvent: (event: TraceEvent) => void,
    onError?: (err: Event) => void
  ): () => void {
    const sseUrl = `${this.baseUrl}/api/tasks/${encodeURIComponent(taskId)}/events`;
    let eventSource: EventSource | null = null;

    try {
      eventSource = new EventSource(sseUrl);
      eventSource.onmessage = (msg) => {
        try {
          const parsed = JSON.parse(msg.data) as TraceEvent;
          onEvent(parsed);
        } catch (e) {
          console.warn('Failed to parse SSE event data', e);
        }
      };
      if (onError) {
        eventSource.onerror = (err) => {
          onError(err);
        };
      }
    } catch (e) {
      console.error('Failed to create EventSource', e);
    }

    return () => {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
    };
  }
  // --- Authentication & Session Management ---
  public async getAuthStatus(): Promise<AuthStatusResponse> {
    const status = await this.request<AuthStatusResponse>('/api/auth/status');
    if (status.csrf_token) {
      this.csrfToken = status.csrf_token;
    }
    return status;
  }

  public async login(req: LoginRequest): Promise<LoginResponse> {
    const res = await this.request<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(req),
    });
    if (res.csrf_token) {
      this.csrfToken = res.csrf_token;
    }
    return res;
  }

  public async logout(): Promise<{ success: boolean; message: string; authenticated?: boolean }> {
    const res = await this.request<{ success: boolean; message: string; authenticated?: boolean }>('/api/auth/logout', {
      method: 'POST',
    });
    this.csrfToken = null;
    return res;
  }
}

// Default singleton instance
export const apiClient = new FlamoApiClient();
