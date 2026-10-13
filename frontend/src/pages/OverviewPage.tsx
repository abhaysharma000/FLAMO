import React from 'react';
import { HealthResponse } from '../types/health';
import { TaskResponse } from '../types/task';

interface OverviewPageProps {
  health: HealthResponse | null;
  tasks: TaskResponse[];
  loading: boolean;
  error: string | null;
  onSelectTask: (taskId: string) => void;
  onRefresh: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  health,
  tasks,
  loading,
  error,
  onSelectTask,
  onRefresh,
}) => {
  // Aggregate real statistics strictly from retrieved backend tasks
  const totalTasks = tasks.length;
  const completedTasks = tasks.filter((t) => t.status === 'completed').length;
  const runningTasks = tasks.filter((t) => ['running', 'planning', 'pending', 'verifying', 'awaiting_approval'].includes(t.status)).length;
  const failedTasks = tasks.filter((t) => t.status === 'failed').length;
  const totalRecoveries = tasks.reduce((sum, t) => sum + (t.retry_count || 0), 0);

  const recentFailures = tasks.filter((t) => t.status === 'failed');

  return (
    <div className="page-container">
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">Operations Overview</h1>
          <p className="page-desc">Real-time system health, persistent memory status, and execution metrics.</p>
        </div>
        <button
          className="btn btn-secondary"
          onClick={onRefresh}
          disabled={loading}
          type="button"
        >
          {loading ? 'Refreshing...' : '↻ Refresh Data'}
        </button>
      </div>

      {error && (
        <div className="alert-banner alert-error" role="alert">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="metrics-grid">
        <div className="kpi-card">
          <div className="kpi-label">TOTAL MISSIONS</div>
          <div className="kpi-value">{totalTasks}</div>
          <div className="kpi-subtext">Persisted in SQLite database</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">COMPLETED MISSIONS</div>
          <div className="kpi-value" style={{ color: 'var(--accent-green)' }}>
            {completedTasks}
          </div>
          <div className="kpi-subtext">Verified workflow executions</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">ACTIVE / RUNNING</div>
          <div className="kpi-value" style={{ color: 'var(--accent-cyan)' }}>
            {runningTasks}
          </div>
          <div className="kpi-subtext">Currently executing in swarm</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">EXECUTION FAILURES</div>
          <div className="kpi-value" style={{ color: failedTasks > 0 ? 'var(--accent-rose)' : '#fff' }}>
            {failedTasks}
          </div>
          <div className="kpi-subtext">Permanent or exhausted failures</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">RECOVERIES TRIGGERED</div>
          <div className="kpi-value" style={{ color: 'var(--accent-amber)' }}>
            {totalRecoveries}
          </div>
          <div className="kpi-subtext">Bounded retries executed</div>
        </div>
      </div>

      {/* System Infrastructure Card */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <div className="card-header">
          <h2 className="card-title">🖥️ Infrastructure & Diagnostics</h2>
          <span
            className={`status-tag ${health?.status === 'healthy' ? 'status-completed' : 'status-pending'}`}
          >
            {health?.status?.toUpperCase() || 'OFFLINE'}
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
          <div style={{ background: 'var(--bg-input)', padding: '14px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '4px' }}>ORCHESTRATOR & LLM</div>
            <div style={{ fontWeight: 600, color: '#fff' }}>{health?.llm.provider || 'google-genai'}</div>
            <div className="font-mono text-muted" style={{ fontSize: '0.8rem', marginTop: '2px' }}>
              Model: {health?.llm.model || 'gemini-3.5-flash-lite'}
            </div>
            <div style={{ fontSize: '0.75rem', marginTop: '4px', color: health?.llm.configured ? 'var(--accent-green)' : 'var(--accent-rose)' }}>
              API Key: {health?.llm.configured ? 'Configured (Server-side)' : 'Missing / Degraded'}
            </div>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '14px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '4px' }}>SEMANTIC MEMORY BACKEND</div>
            <div style={{ fontWeight: 600, color: '#fff' }}>
              {(health?.memory?.backend || 'sqlite').toUpperCase()} STORE
            </div>
            <div className="font-mono text-muted" style={{ fontSize: '0.8rem', marginTop: '2px' }}>
              Method: {health?.memory?.vector_search_active ? 'Dense Vector (Cosine)' : 'Stemmed Token Match (Lexical)'}
            </div>
            <div style={{ fontSize: '0.75rem', marginTop: '4px', color: 'var(--text-dim)' }}>
              {health?.memory?.vector_search_active
                ? `Embedding Model: ${health?.memory?.active_embedding_model || health?.memory?.configured_embedding_model}`
                : `Configured Model: ${health?.memory?.configured_embedding_model || 'text-embedding-004'} (Chroma only)`}
            </div>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '14px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '4px' }}>WORKSPACE SANDBOX</div>
            <div style={{ fontWeight: 600, color: '#fff' }}>
              Status: {health?.workspace.exists ? 'Protected & Mounted' : 'Unavailable'}
            </div>
            <div className="font-mono text-muted" style={{ fontSize: '0.75rem', marginTop: '2px' }}>
              Sandbox: Enforced (Restricted to safe workspace sandbox)
            </div>
            <div style={{ fontSize: '0.75rem', marginTop: '4px', color: 'var(--accent-cyan)' }}>
              Registered Tools: {health?.tools_registered.count || 0}
            </div>
          </div>
        </div>
      </div>

      {/* Two Column Layout: Recent Tasks & Recent Failures */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '20px' }}>
        
        {/* Recent Tasks */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">🕒 Recent Task Executions</h2>
            <span className="text-dim" style={{ fontSize: '0.8rem' }}>Last {Math.min(tasks.length, 10)} missions</span>
          </div>

          {tasks.length === 0 ? (
            <div className="empty-state">No tasks recorded in repository yet.</div>
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Goal</th>
                    <th>Status</th>
                    <th>Runtime</th>
                    <th>Tools</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.slice(0, 8).map((task) => (
                    <tr
                      key={task.id}
                      onClick={() => onSelectTask(task.id)}
                      style={{ cursor: 'pointer' }}
                      title={`Click to inspect task ${task.id}`}
                    >
                      <td>
                        <div style={{ fontWeight: 500, maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
                      <td className="font-mono">{task.total_tool_calls || 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Recent Execution Failures */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">⚠️ Recent Failures & Alerts</h2>
            <span className="text-dim" style={{ fontSize: '0.8rem' }}>{recentFailures.length} logged</span>
          </div>

          {recentFailures.length === 0 ? (
            <div className="empty-state" style={{ color: 'var(--accent-green)' }}>
              ✓ No execution failures or errors recorded in recent missions.
            </div>
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Task ID</th>
                    <th>Error Detail</th>
                    <th>Retries</th>
                  </tr>
                </thead>
                <tbody>
                  {recentFailures.slice(0, 6).map((f) => (
                    <tr
                      key={f.id}
                      onClick={() => onSelectTask(f.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div className="font-mono" style={{ color: '#fb7185', fontWeight: 600 }}>
                          {f.id.slice(0, 10)}...
                        </div>
                        <span className={`status-tag status-${f.status}`}>{f.status}</span>
                      </td>
                      <td style={{ fontSize: '0.78rem', color: 'var(--text-muted)', maxWidth: '240px' }}>
                        {f.errors && f.errors.length > 0 ? f.errors.join('; ') : 'Task exited with failed status.'}
                      </td>
                      <td className="font-mono">{f.retry_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>
    </div>
  );
};
