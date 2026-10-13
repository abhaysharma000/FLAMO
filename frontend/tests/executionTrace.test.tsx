import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ExecutionTracePage } from '../src/pages/ExecutionTracePage';
import { TaskResponse } from '../src/types/task';
import { TraceEvent } from '../src/types/trace';

describe('ExecutionTracePage Component', () => {
  const mockTask: TaskResponse = {
    id: 'task-trace-test-1',
    goal: 'Research agent frameworks with fallback',
    status: 'completed', // Execution completed
    current_step_index: 1,
    completed_steps: ['Step 1', 'Step 2'],
    failed_steps: [],
    retry_count: 1,
    final_answer: 'Done',
    created_at: '2026-10-11T12:00:00Z',
    updated_at: '2026-10-11T12:00:15Z',
    duration_seconds: 15.2,
    errors: [],
    total_tool_calls: 3,
    tool_results: [],
    claims: [],
    evidence_count: 0,
    verification_result: {
      is_valid: true,
      score: 0.95,
      status: 'VERIFIED',
      checks_passed: ['All claims backed by primary docs'],
      checks_failed: [],
      critique: 'Excellent factual alignment',
    },
  };

  const mockEvents: TraceEvent[] = [
    {
      id: 'ev-1',
      task_id: 'task-trace-test-1',
      timestamp: '2026-10-11T12:00:01Z',
      event_type: 'task_started',
      node: 'supervisor',
      status: 'info',
      details: {},
    },
    {
      id: 'ev-2',
      task_id: 'task-trace-test-1',
      timestamp: '2026-10-11T12:00:03Z',
      event_type: 'tool_failed',
      node: 'research_agent',
      tool: 'browser',
      status: 'error',
      duration_ms: 1200,
      attempt_number: 1,
      error: 'Navigation timeout to primary doc site',
      recovery_decision: 'retry_with_web_search_fallback',
      details: { url: 'https://broken-site.test' },
    },
    {
      id: 'ev-3',
      task_id: 'task-trace-test-1',
      timestamp: '2026-10-11T12:00:06Z',
      event_type: 'retry_started',
      node: 'recovery_engine',
      status: 'warning',
      attempt_number: 2,
      recovery_decision: 'retry_with_web_search_fallback',
      details: {},
    },
    {
      id: 'ev-4',
      task_id: 'task-trace-test-1',
      timestamp: '2026-10-11T12:00:10Z',
      event_type: 'tool_completed',
      node: 'research_agent',
      tool: 'web_search',
      status: 'success',
      duration_ms: 450,
      details: { query: 'langgraph architecture' },
    },
    {
      id: 'ev-5',
      task_id: 'task-trace-test-1',
      timestamp: '2026-10-11T12:00:14Z',
      event_type: 'verification_completed',
      node: 'verifier',
      status: 'success',
      duration_ms: 320,
      details: { score: 0.95 },
    },
  ];

  it('clearly separates execution success from factual verification status', () => {
    render(
      <ExecutionTracePage
        tasks={[mockTask]}
        selectedTaskId="task-trace-test-1"
        traces={mockEvents}
        loadingTraces={false}
        error={null}
        onSelectTaskId={vi.fn()}
        onRefreshTraces={vi.fn()}
        isStreaming={true}
      />
    );

    // Workflow execution status section
    expect(screen.getByText('WORKFLOW EXECUTION')).toBeInTheDocument();
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();

    // Factual verification section
    expect(screen.getByText('FACTUAL VERIFICATION')).toBeInTheDocument();
    expect(screen.getByText(/PASSED \(95%\)/)).toBeInTheDocument();
  });

  it('renders tool names, attempt numbers, recovery decisions, and errors', () => {
    render(
      <ExecutionTracePage
        tasks={[mockTask]}
        selectedTaskId="task-trace-test-1"
        traces={mockEvents}
        loadingTraces={false}
        error={null}
        onSelectTaskId={vi.fn()}
        onRefreshTraces={vi.fn()}
        isStreaming={false}
      />
    );

    // Tools rendered
    expect(screen.getByText('<browser>')).toBeInTheDocument();
    expect(screen.getByText('<web_search>')).toBeInTheDocument();

    // Attempt number rendered
    expect(screen.getByText('Attempt #2')).toBeInTheDocument();

    // Recovery decision rendered
    expect(screen.getAllByText(/retry_with_web_search_fallback/i).length).toBeGreaterThanOrEqual(1);

    // Sanitized error rendered
    expect(screen.getByText(/Navigation timeout to primary doc site/i)).toBeInTheDocument();
  });

  it('filters trace events correctly', () => {
    render(
      <ExecutionTracePage
        tasks={[mockTask]}
        selectedTaskId="task-trace-test-1"
        traces={mockEvents}
        loadingTraces={false}
        error={null}
        onSelectTaskId={vi.fn()}
        onRefreshTraces={vi.fn()}
        isStreaming={false}
      />
    );

    // Initially all events visible (5 events)
    expect(screen.getByText(/5 recorded/i)).toBeInTheDocument();

    // Filter by Tools Only
    fireEvent.click(screen.getByText('Tools Only'));
    expect(screen.getByText('<browser>')).toBeInTheDocument();
    expect(screen.getByText('<web_search>')).toBeInTheDocument();
    expect(screen.queryByText('task_started')).not.toBeInTheDocument();

    // Filter by Retries & Recoveries
    fireEvent.click(screen.getByText('Retries & Recoveries'));
    expect(screen.getByText('retry_started')).toBeInTheDocument();

    // Filter by Verification
    fireEvent.click(screen.getByText('Verification'));
    expect(screen.getByText('verification_completed')).toBeInTheDocument();
  });
});
