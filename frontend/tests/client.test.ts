import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { FlamoApiClient, ApiClientError } from '../src/api/client';

describe('FlamoApiClient', () => {
  let client: FlamoApiClient;
  const mockBaseUrl = 'http://localhost:8000';

  beforeEach(() => {
    client = new FlamoApiClient(mockBaseUrl, 2000);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('correctly configures base URL and strips trailing slashes', () => {
    const c = new FlamoApiClient('http://localhost:8000///');
    // @ts-ignore
    expect(c.baseUrl).toBe('http://localhost:8000');
  });

  it('fetches system health successfully', async () => {
    const mockHealth = {
      status: 'healthy',
      timestamp: '2026-10-11T12:00:00Z',
      version: '2.0.0',
      system: 'FLAMO Autonomous AI Operations Agent',
      llm: { provider: 'google-genai', model: 'gemini-3.5-flash-lite', configured: true },
      database: { type: 'sqlite', url: 'sqlite:///flamo.db' },
      memory: { backend: 'sqlite', embedding_model: 'gemini-embedding-001' },
      workspace: { sandbox_path: 'C:/workspace', exists: true },
      tools_registered: { count: 8, tools: ['web_search', 'calculator'] },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockHealth,
    } as any);

    const res = await client.getHealth();
    expect(res.status).toBe('healthy');
    expect(res.memory?.backend).toBe('sqlite');
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/api/health', expect.any(Object));
  });

  it('propagates HTTP error with backend detail', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Goal cannot be empty.' }),
    } as any);

    await expect(client.createTask({ goal: '' })).rejects.toThrow(ApiClientError);
    try {
      await client.createTask({ goal: '' });
    } catch (e: any) {
      expect(e.status).toBe(400);
      expect(e.detail).toBe('Goal cannot be empty.');
    }
  });

  it('handles network timeouts properly', async () => {
    // Simulate AbortError on timeout
    global.fetch = vi.fn().mockRejectedValue({ name: 'AbortError', message: 'The operation was aborted' });

    await expect(client.getHealth()).rejects.toThrow('Request timed out');
  });

  it('creates task with POST request and returns TaskResponse', async () => {
    const mockTask = {
      id: 'task-test-123',
      goal: 'Calculate 125 * 48',
      status: 'pending',
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:00:00Z',
      errors: [],
      completed_steps: [],
      failed_steps: [],
      retry_count: 0,
      total_tool_calls: 0,
      tool_results: [],
      claims: [],
      evidence_count: 0,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => mockTask,
    } as any);

    const res = await client.createTask({ goal: 'Calculate 125 * 48' });
    expect(res.id).toBe('task-test-123');
    expect(res.status).toBe('pending');
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/tasks',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ goal: 'Calculate 125 * 48' }),
      })
    );
  });

  it('lists workspace reports and builds safe download URL', async () => {
    const mockReports = [
      {
        filename: 'ai_frameworks.md',
        title: 'AI Frameworks Comparison',
        size_bytes: 4096,
        modified_at: '2026-10-11T10:00:00Z',
        is_markdown: true,
      },
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockReports,
    } as any);

    const res = await client.listReports();
    expect(res).toHaveLength(1);
    expect(res[0].filename).toBe('ai_frameworks.md');

    const downloadUrl = client.getReportDownloadUrl('ai_frameworks.md');
    expect(downloadUrl).toBe('http://localhost:8000/api/reports/ai_frameworks.md/download');
  });

  it('queries semantic memory with parameters', async () => {
    const mockMemories = [
      {
        id: 'mem-1',
        category: 'reusable_knowledge',
        content: 'LangGraph uses state graphs for agent cycles.',
        metadata: {},
        timestamp: '2026-10-11T12:00:00Z',
        relevance_score: 0.912,
      },
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockMemories,
    } as any);

    const res = await client.searchMemory('LangGraph state', 'reusable_knowledge', 5);
    expect(res).toHaveLength(1);
    expect(res[0].relevance_score).toBe(0.912);
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/memory/search?query=LangGraph+state&limit=5&category=reusable_knowledge',
      expect.any(Object)
    );
  });

  it('fetches auth status correctly', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ auth_enabled: true, authenticated: false, username: null }),
    } as any);

    const res = await client.getAuthStatus();
    expect(res.auth_enabled).toBe(true);
    expect(res.authenticated).toBe(false);
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/auth/status',
      expect.objectContaining({ credentials: 'include' })
    );
  });

  it('performs operator login and captures csrf token', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        authenticated: true,
        username: 'admin',
        csrf_token: 'csrf-secret-12345',
        expires_at: '2026-10-12T00:00:00Z',
      }),
    } as any);

    const res = await client.login({ username: 'admin', password: 'correctpassword' });
    expect(res.authenticated).toBe(true);
    expect(res.username).toBe('admin');
    expect(client.getCsrfToken()).toBe('csrf-secret-12345');
  });

  it('performs operator logout and clears csrf token', async () => {
    client.setCsrfToken('some-token');
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ authenticated: false, message: 'Logged out successfully' }),
    } as any);

    const res = await client.logout();
    expect(res.authenticated).toBe(false);
    expect(client.getCsrfToken()).toBeNull();
  });
});

