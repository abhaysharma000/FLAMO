import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Sidebar } from '../src/components/Sidebar';
import { Header } from '../src/components/Header';
import { OverviewPage } from '../src/pages/OverviewPage';
import { HealthResponse } from '../src/types/health';

describe('Navigation and Layout Components', () => {
  it('renders sidebar navigation links and responds to navigation clicks', () => {
    const handleNavigate = vi.fn();
    render(
      <Sidebar
        currentPage="overview"
        onNavigate={handleNavigate}
        activeTaskId="task-12345"
      />
    );

    expect(screen.getByText('FLAMO')).toBeInTheDocument();
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Task Center')).toBeInTheDocument();
    expect(screen.getByText('Execution Trace')).toBeInTheDocument();
    expect(screen.getByText('Research & Reports')).toBeInTheDocument();
    expect(screen.getByText('Semantic Memory')).toBeInTheDocument();

    // Active task badge in sidebar footer
    expect(screen.getByText(/Target:/)).toBeInTheDocument();

    // Click Task Center link
    fireEvent.click(screen.getByText('Task Center'));
    expect(handleNavigate).toHaveBeenCalledWith('tasks');

    // Click Research & Reports link
    fireEvent.click(screen.getByText('Research & Reports'));
    expect(handleNavigate).toHaveBeenCalledWith('reports');
  });

  it('renders header telemetry with real health and memory backend', () => {
    const mockHealth: HealthResponse = {
      status: 'healthy',
      timestamp: '2026-10-11T12:00:00Z',
      version: '2.0.0',
      system: 'FLAMO Autonomous AI Operations Agent',
      llm: { provider: 'google-genai', model: 'gemini-3.5-flash-lite', configured: true },
      database: { type: 'sqlite', url: 'sqlite:///flamo.db' },
      memory: { backend: 'chroma', embedding_model: 'gemini-embedding-001' },
      workspace: { sandbox_path: 'C:/workspace', exists: true },
      tools_registered: { count: 8, tools: ['web_search', 'calculator'] },
    };

    const handleRefresh = vi.fn();
    render(<Header health={mockHealth} loading={false} onRefreshHealth={handleRefresh} />);

    expect(screen.getByText('ENGINE: HEALTHY')).toBeInTheDocument();
    expect(screen.getByText('gemini-3.5-flash-lite')).toBeInTheDocument();
    expect(screen.getByText('CHROMA')).toBeInTheDocument();
    expect(screen.getByText(/gemini-embedding-001/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('↻ Refresh Health'));
    expect(handleRefresh).toHaveBeenCalled();
  });

  it('renders OverviewPage showing recovered completed tasks as completed without false failure alerts', () => {
    const mockHealth: HealthResponse = {
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

    const recoveredTask = {
      id: 'task-recovered-abc12345',
      goal: 'Research agent frameworks',
      status: 'completed' as const,
      current_step_index: 4,
      completed_steps: ['Step 1', 'Step 2'],
      failed_steps: [],
      retry_count: 2,
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:02:00Z',
      duration_seconds: 45.2,
      errors: ['Verification retry: Incomplete required step resolved on retry'],
      total_tool_calls: 10,
      tool_results: [],
      claims: [],
      evidence_count: 5,
    };

    render(
      <OverviewPage
        health={mockHealth}
        tasks={[recoveredTask]}
        loading={false}
        error={null}
        onSelectTask={vi.fn()}
        onRefresh={vi.fn()}
      />
    );

    // Should report 1 completed mission and 2 recoveries triggered
    expect(screen.getByText('COMPLETED MISSIONS')).toBeInTheDocument();
    expect(screen.getByText('RECOVERIES TRIGGERED')).toBeInTheDocument();

    // Should indicate no active execution failures
    expect(screen.getByText(/No execution failures or errors recorded in recent missions/i)).toBeInTheDocument();
  });
});
