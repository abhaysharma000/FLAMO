import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TaskCenterPage } from '../src/pages/TaskCenterPage';
import { TaskResponse } from '../src/types/task';

describe('TaskCenterPage Component', () => {
  const dummyHandlers = {
    onSubmitGoal: vi.fn().mockResolvedValue(undefined),
    onRefreshActiveTask: vi.fn(),
    onCancelTask: vi.fn(),
    onResumeTask: vi.fn(),
    onSelectTask: vi.fn(),
    onNavigateToTrace: vi.fn(),
    onNavigateToReports: vi.fn(),
  };

  it('validates empty goals and prevents submission', async () => {
    render(
      <TaskCenterPage
        activeTask={null}
        tasks={[]}
        loading={false}
        submitting={false}
        error={null}
        {...dummyHandlers}
      />
    );

    const submitBtn = screen.getByText('⚡ Deploy Agent');
    fireEvent.click(submitBtn);

    expect(screen.getByText(/Goal cannot be empty/i)).toBeInTheDocument();
    expect(dummyHandlers.onSubmitGoal).not.toHaveBeenCalled();
  });

  it('submits valid goal and clears validation error', async () => {
    render(
      <TaskCenterPage
        activeTask={null}
        tasks={[]}
        loading={false}
        submitting={false}
        error={null}
        {...dummyHandlers}
      />
    );

    const input = screen.getByPlaceholderText(/Research top AI agent frameworks/i);
    fireEvent.change(input, { target: { value: 'Calculate 125 * 48' } });

    const submitBtn = screen.getByText('⚡ Deploy Agent');
    fireEvent.click(submitBtn);

    expect(dummyHandlers.onSubmitGoal).toHaveBeenCalledWith('Calculate 125 * 48');
    expect(screen.queryByText(/Goal cannot be empty/i)).not.toBeInTheDocument();
  });

  it('renders active task in RUNNING status and does NOT prematurely label completed', () => {
    const runningTask: TaskResponse = {
      id: 'task-active-1',
      goal: 'Research LangGraph state machines',
      status: 'running',
      current_step_index: 0,
      completed_steps: [],
      failed_steps: [],
      retry_count: 0,
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:00:05Z',
      duration_seconds: 4.5,
      errors: [],
      total_tool_calls: 2,
      tool_results: [],
      claims: [],
      evidence_count: 0,
      plan: {
        steps: [
          {
            id: 1,
            title: 'Search LangGraph docs',
            description: 'Query web for LangGraph core features',
            tool_hint: 'web_search',
            status: 'in_progress',
          },
        ],
        estimated_complexity: 'moderate',
      },
    };

    render(
      <TaskCenterPage
        activeTask={runningTask}
        tasks={[runningTask]}
        loading={false}
        submitting={false}
        error={null}
        {...dummyHandlers}
      />
    );

    // Status pill must be RUNNING
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
    expect(screen.queryByText('COMPLETED')).not.toBeInTheDocument();
    // Step item visible
    expect(screen.getByText('1. Search LangGraph docs')).toBeInTheDocument();
    // Cancel mission button visible when running
    expect(screen.getByText('Cancel Mission')).toBeInTheDocument();
  });

  it('renders COMPLETED task with final answer and copy button', () => {
    const completedTask: TaskResponse = {
      id: 'task-done-1',
      goal: 'Calculate 125 * 48',
      status: 'completed',
      current_step_index: 0,
      completed_steps: ['Step 1'],
      failed_steps: [],
      retry_count: 0,
      final_answer: '125 multiplied by 48 is 6000.',
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:00:03Z',
      duration_seconds: 2.8,
      errors: [],
      total_tool_calls: 1,
      tool_results: [],
      claims: [],
      evidence_count: 0,
    };

    render(
      <TaskCenterPage
        activeTask={completedTask}
        tasks={[completedTask]}
        loading={false}
        submitting={false}
        error={null}
        {...dummyHandlers}
      />
    );

    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
    expect(screen.getByText('125 multiplied by 48 is 6000.')).toBeInTheDocument();
    expect(screen.getByText('📋 Copy Text')).toBeInTheDocument();
  });
});
