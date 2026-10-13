import React, { useState } from 'react';
import { TaskResponse } from '../types/task';

interface TaskCenterPageProps {
  activeTask: TaskResponse | null;
  tasks: TaskResponse[];
  loading: boolean;
  submitting: boolean;
  error: string | null;
  onSubmitGoal: (goal: string) => Promise<void>;
  onRefreshActiveTask: () => void;
  onCancelTask: (taskId: string) => void;
  onResumeTask: (taskId: string) => void;
  onSelectTask: (taskId: string) => void;
  onNavigateToTrace: (taskId: string) => void;
  onNavigateToReports: (taskId: string) => void;
}

export const TaskCenterPage: React.FC<TaskCenterPageProps> = ({
  activeTask,
  tasks,
  loading,
  submitting,
  error,
  onSubmitGoal,
  onRefreshActiveTask,
  onCancelTask,
  onResumeTask,
  onSelectTask,
  onNavigateToTrace,
  onNavigateToReports,
}) => {
  const [goalInput, setGoalInput] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const presets = [
    {
      label: '🏆 Top 5 Agent Frameworks (Full Research)',
      query:
        'Research the top 5 AI agent frameworks and compare architecture, capabilities, persistence, tool support, and documentation. Detect conflicting claims, verify facts, save a report to the workspace, and provide evidence.',
    },
    { label: '🧮 Single-Step Math (125 * 48)', query: 'Calculate 125 * 48.' },
    {
      label: '➗ Multi-Step Math (125 * 48 / 5)',
      query: 'Calculate 125 multiplied by 48, then divide the result by 5.',
    },
    {
      label: '🌐 Research LangGraph Architecture',
      query: 'Research what LangGraph is and summarize its core stateful workflow features in 2 sentences.',
    },
    {
      label: '⚠️ Zero-Division Recovery Policy',
      query: 'Use the calculator to divide 100 by 0. If it fails, explain why dividing by zero is undefined.',
    },
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanGoal = goalInput.trim();
    if (!cleanGoal) {
      setValidationError('Goal cannot be empty. Please enter an operational instruction.');
      return;
    }
    setValidationError(null);
    try {
      await onSubmitGoal(cleanGoal);
    } catch {
      // Error handled by parent component and passed via error prop
    }
  };

  const handleCopyAnswer = () => {
    if (!activeTask?.final_answer) return;
    navigator.clipboard.writeText(activeTask.final_answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isRunning = activeTask && ['running', 'planning', 'pending', 'verifying'].includes(activeTask.status);

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Autonomous Task Center</h1>
        <p className="page-desc">Dispatch goals, monitor multi-agent decomposition, and inspect verified outputs.</p>
      </div>

      {/* Input Console */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <div className="card-header">
          <h2 className="card-title">⚡ Operational Mission Objective</h2>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
            <input
              type="text"
              className="input-text"
              placeholder="e.g., Research top AI agent frameworks, calculate values, or browse documentation..."
              value={goalInput}
              onChange={(e) => {
                setGoalInput(e.target.value);
                if (validationError) setValidationError(null);
              }}
              disabled={submitting}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting}
              style={{ minWidth: '160px' }}
            >
              {submitting ? 'Deploying...' : '⚡ Deploy Agent'}
            </button>
          </div>
        </form>

        {validationError && (
          <div className="alert-banner alert-warning" role="alert">
            <span>⚠️</span>
            <span>{validationError}</span>
          </div>
        )}

        {error && (
          <div className="alert-banner alert-error" role="alert">
            <span>✕ Backend Error:</span>
            <span>{error}</span>
          </div>
        )}

        {/* Presets */}
        <div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '6px' }}>
            PORTFOLIO BENCHMARK PRESETS:
          </div>
          <div className="presets-grid">
            {presets.map((preset, idx) => (
              <button
                key={idx}
                type="button"
                className="preset-chip"
                onClick={() => {
                  setGoalInput(preset.query);
                  setValidationError(null);
                }}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Active Task Dashboard */}
      {activeTask && (
        <div className="card" style={{ marginBottom: '24px' }}>
          <div className="card-header flex-between">
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className={`status-tag status-${activeTask.status}`}>
                  {activeTask.status.toUpperCase()}
                </span>
                <h2 className="card-title" style={{ fontSize: '1.15rem' }}>
                  Mission: <span style={{ color: '#fff' }}>{activeTask.goal}</span>
                </h2>
              </div>
              <div className="font-mono text-dim" style={{ fontSize: '0.78rem', marginTop: '4px' }}>
                ID: {activeTask.id} • Created: {new Date(activeTask.created_at).toLocaleTimeString()}
              </div>
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onRefreshActiveTask}
                disabled={loading}
                title="Fetch latest task state"
              >
                {loading ? '↻ Syncing...' : '↻ Refresh Status'}
              </button>

              {isRunning && (
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => onCancelTask(activeTask.id)}
                >
                  Cancel Mission
                </button>
              )}

              {activeTask.status === 'failed' && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => onResumeTask(activeTask.id)}
                  title="Attempt bounded resume from persisted checkpoint"
                >
                  ↻ Resume Task
                </button>
              )}

              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onNavigateToTrace(activeTask.id)}
              >
                Inspect Trace →
              </button>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="metrics-grid" style={{ marginBottom: '16px' }}>
            <div className="kpi-card" style={{ padding: '12px 16px' }}>
              <div className="kpi-label">EXECUTION DURATION</div>
              <div className="kpi-value" style={{ fontSize: '1.4rem' }}>
                {activeTask.duration_seconds ? `${activeTask.duration_seconds.toFixed(1)}s` : 'In progress'}
              </div>
            </div>

            <div className="kpi-card" style={{ padding: '12px 16px' }}>
              <div className="kpi-label">TOOL CALLS</div>
              <div className="kpi-value" style={{ fontSize: '1.4rem' }}>
                {activeTask.total_tool_calls || 0}
              </div>
            </div>

            <div className="kpi-card" style={{ padding: '12px 16px' }}>
              <div className="kpi-label">RETRIES / RECOVERIES</div>
              <div className="kpi-value" style={{ fontSize: '1.4rem' }}>
                {activeTask.retry_count || 0}
              </div>
            </div>

            <div className="kpi-card" style={{ padding: '12px 16px' }}>
              <div className="kpi-label">FACTUAL CLAIMS</div>
              <div className="kpi-value" style={{ fontSize: '1.4rem' }}>
                {activeTask.claims?.length || 0}
              </div>
            </div>
          </div>

          {/* Execution Plan Steps */}
          {activeTask.plan && activeTask.plan.steps && activeTask.plan.steps.length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                  📋 EXECUTION PLAN ({activeTask.plan.estimated_complexity.toUpperCase()})
                </h3>
                <span className="font-mono text-dim" style={{ fontSize: '0.75rem' }}>
                  Step {Math.min(activeTask.current_step_index + 1, activeTask.plan.steps.length)} of {activeTask.plan.steps.length}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {activeTask.plan.steps.map((step, idx) => {
                  const isCurrent = idx === activeTask.current_step_index && isRunning;
                  const isDone = step.status === 'completed';
                  const isFailed = step.status === 'failed';

                  let statusIcon = '○';
                  let iconColor = 'var(--text-dim)';
                  if (isDone) {
                    statusIcon = '✓';
                    iconColor = 'var(--accent-green)';
                  } else if (isCurrent) {
                    statusIcon = '→';
                    iconColor = 'var(--accent-cyan)';
                  } else if (isFailed) {
                    statusIcon = '⚠️';
                    iconColor = 'var(--accent-rose)';
                  }

                  return (
                    <div
                      key={step.id}
                      style={{
                        background: isCurrent ? 'rgba(56, 189, 248, 0.08)' : 'var(--bg-input)',
                        border: `1px solid ${isCurrent ? 'var(--accent-cyan)' : 'var(--border-subtle)'}`,
                        borderRadius: 'var(--radius-sm)',
                        padding: '10px 14px',
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '12px',
                      }}
                    >
                      <span style={{ color: iconColor, fontWeight: 700, fontSize: '1.1rem', lineHeight: 1 }}>
                        {statusIcon}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontWeight: 600, color: '#fff', fontSize: '0.9rem' }}>
                            {step.id}. {step.title}
                          </span>
                          {step.tool_hint && (
                            <span className="font-mono" style={{ fontSize: '0.7rem', color: 'var(--accent-cyan)' }}>
                              &lt;{step.tool_hint}&gt;
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                          {step.description}
                        </div>
                        {step.output && (
                          <div
                            className="font-mono"
                            style={{
                              fontSize: '0.75rem',
                              color: '#a7f3d0',
                              marginTop: '4px',
                              background: 'rgba(16, 185, 129, 0.08)',
                              padding: '4px 8px',
                              borderRadius: '4px',
                            }}
                          >
                            Observation: {step.output}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Final Result / Verification */}
          <div>
            <div className="flex-between" style={{ marginBottom: '8px' }}>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                🎯 FINAL VERIFIED RESULT
              </h3>
              {activeTask.final_answer && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                  onClick={handleCopyAnswer}
                >
                  {copied ? '✓ Copied' : '📋 Copy Text'}
                </button>
              )}
            </div>

            <div
              style={{
                background: 'var(--bg-input)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '16px',
                minHeight: '80px',
              }}
            >
              {activeTask.final_answer ? (
                <div style={{ whiteSpace: 'pre-wrap', fontSize: '0.9rem', lineHeight: 1.6, color: '#e2e8f0' }}>
                  {activeTask.final_answer}
                </div>
              ) : activeTask.status === 'failed' ? (
                <div style={{ color: 'var(--accent-rose)', fontSize: '0.85rem' }}>
                  Task failed with errors: {activeTask.errors.join('; ') || 'Execution error.'}
                </div>
              ) : (
                <div className="empty-state">
                  <span className="pulse-dot" style={{ display: 'inline-block', marginRight: '8px' }} />
                  Agent execution and reasoning currently in progress...
                </div>
              )}
            </div>

            {activeTask.claims && activeTask.claims.length > 0 && (
              <div style={{ marginTop: '12px', textAlign: 'right' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => onNavigateToReports(activeTask.id)}
                  style={{ fontSize: '0.8rem' }}
                >
                  View Evidence & Claim Audit Table ({activeTask.claims.length} claims) →
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Task History Drawer */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">📜 Past Mission History</h2>
          <span className="text-dim" style={{ fontSize: '0.8rem' }}>{tasks.length} total tasks</span>
        </div>

        {tasks.length === 0 ? (
          <div className="empty-state">No previous tasks recorded.</div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Goal</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Claims Audited</th>
                  <th>Timestamp</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id}>
                    <td>
                      <div style={{ fontWeight: 500, maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {task.goal}
                      </div>
                      <div className="font-mono text-dim" style={{ fontSize: '0.7rem' }}>
                        {task.id}
                      </div>
                    </td>
                    <td>
                      <span className={`status-tag status-${task.status}`}>{task.status}</span>
                    </td>
                    <td className="font-mono">
                      {task.duration_seconds !== null && task.duration_seconds !== undefined
                        ? `${task.duration_seconds.toFixed(1)}s`
                        : '—'}
                    </td>
                    <td className="font-mono">{task.claims?.length || 0}</td>
                    <td className="text-dim" style={{ fontSize: '0.78rem' }}>
                      {new Date(task.created_at).toLocaleString()}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ padding: '3px 8px', fontSize: '0.75rem' }}
                        onClick={() => onSelectTask(task.id)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
