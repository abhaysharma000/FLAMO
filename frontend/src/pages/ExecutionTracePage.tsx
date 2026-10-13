import React, { useState } from 'react';
import { TaskResponse } from '../types/task';
import { TraceEvent } from '../types/trace';

interface ExecutionTracePageProps {
  tasks: TaskResponse[];
  selectedTaskId: string | null;
  traces: TraceEvent[];
  loadingTraces: boolean;
  error: string | null;
  onSelectTaskId: (taskId: string) => void;
  onRefreshTraces: () => void;
  isStreaming: boolean;
}

export const ExecutionTracePage: React.FC<ExecutionTracePageProps> = ({
  tasks,
  selectedTaskId,
  traces,
  loadingTraces,
  error,
  onSelectTaskId,
  onRefreshTraces,
  isStreaming,
}) => {
  const [filterType, setFilterType] = useState<'all' | 'tools' | 'recovery' | 'verification'>('all');
  const [expandedDetails, setExpandedDetails] = useState<Record<string, boolean>>({});

  const activeTask = tasks.find((t) => t.id === selectedTaskId) || null;

  const toggleExpand = (id: string) => {
    setExpandedDetails((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const filteredTraces = traces.filter((event) => {
    if (filterType === 'tools') {
      return event.event_type.startsWith('tool_') || Boolean(event.tool);
    }
    if (filterType === 'recovery') {
      return (
        event.event_type === 'retry_started' ||
        Boolean(event.recovery_decision) ||
        (event.attempt_number !== null && event.attempt_number !== undefined && event.attempt_number > 1) ||
        event.event_type === 'tool_failed'
      );
    }
    if (filterType === 'verification') {
      return (
        event.event_type.startsWith('verification_') ||
        event.event_type === 'claim_verified' ||
        event.event_type === 'conflict_detected'
      );
    }
    return true;
  });

  return (
    <div className="page-container">
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">Execution Trace & Observability</h1>
          <p className="page-desc">
            Chronological audit log of multi-agent dispatch, tool executions, bounded recoveries, and verification.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <select
            className="input-select"
            style={{ width: '280px' }}
            value={selectedTaskId || ''}
            onChange={(e) => onSelectTaskId(e.target.value)}
          >
            <option value="" disabled>Select a Task to Inspect</option>
            {tasks.map((t) => (
              <option key={t.id} value={t.id}>
                [{t.status.toUpperCase()}] {t.id.slice(0, 8)}: {t.goal.slice(0, 35)}...
              </option>
            ))}
          </select>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={onRefreshTraces}
            disabled={loadingTraces || !selectedTaskId}
          >
            {loadingTraces ? 'Loading...' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="alert-banner alert-error" role="alert">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {activeTask && (
        <div className="card" style={{ marginBottom: '20px', background: 'var(--bg-elevated)' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>SELECTED MISSION OBJECTIVE</div>
              <div style={{ fontWeight: 600, color: '#fff', fontSize: '1rem', marginTop: '2px' }}>
                {activeTask.goal}
              </div>
              <div className="font-mono text-dim" style={{ fontSize: '0.75rem', marginTop: '4px' }}>
                Task ID: {activeTask.id}
              </div>
            </div>

            {/* Clear Separation: Execution Status vs Factual Verification Status */}
            <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>WORKFLOW EXECUTION</div>
                <span className={`status-tag status-${activeTask.status}`} style={{ marginTop: '4px' }}>
                  {activeTask.status.toUpperCase()}
                </span>
              </div>

              <div style={{ textAlign: 'right', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '16px' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>FACTUAL VERIFICATION</div>
                {activeTask.verification_result ? (
                  <span
                    className={`status-tag ${
                      activeTask.verification_result.is_valid ? 'verif-verified' : 'verif-conflicting'
                    }`}
                    style={{ marginTop: '4px' }}
                  >
                    {activeTask.verification_result.is_valid
                      ? `PASSED (${Math.round((activeTask.verification_result.score || 1) * 100)}%)`
                      : `FLAGGED (${Math.round((activeTask.verification_result.score || 0) * 100)}%)`}
                  </span>
                ) : (
                  <span className="status-tag status-pending" style={{ marginTop: '4px' }}>
                    PENDING AUDIT
                  </span>
                )}
              </div>

              <div style={{ textAlign: 'right', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '16px' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>STREAM PROTOCOL</div>
                <span
                  className="font-mono"
                  style={{
                    fontSize: '0.75rem',
                    color: isStreaming ? 'var(--accent-green)' : 'var(--text-muted)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    marginTop: '4px',
                  }}
                >
                  <span
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: isStreaming ? 'var(--accent-green)' : 'var(--text-dim)',
                    }}
                  />
                  {isStreaming ? 'SSE Active' : 'Polling Sync'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Trace Timeline Controls */}
      <div className="card">
        <div className="card-header flex-between">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h2 className="card-title">
              ⏱️ Chronological Execution Events ({filteredTraces.length} recorded)
            </h2>
          </div>

          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              type="button"
              className={`btn ${filterType === 'all' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '4px 10px', fontSize: '0.78rem' }}
              onClick={() => setFilterType('all')}
            >
              All Events
            </button>
            <button
              type="button"
              className={`btn ${filterType === 'tools' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '4px 10px', fontSize: '0.78rem' }}
              onClick={() => setFilterType('tools')}
            >
              Tools Only
            </button>
            <button
              type="button"
              className={`btn ${filterType === 'recovery' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '4px 10px', fontSize: '0.78rem' }}
              onClick={() => setFilterType('recovery')}
            >
              Retries & Recoveries
            </button>
            <button
              type="button"
              className={`btn ${filterType === 'verification' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '4px 10px', fontSize: '0.78rem' }}
              onClick={() => setFilterType('verification')}
            >
              Verification
            </button>
          </div>
        </div>

        {!selectedTaskId ? (
          <div className="empty-state">Select a task from the dropdown above to inspect execution events.</div>
        ) : filteredTraces.length === 0 ? (
          <div className="empty-state">
            {loadingTraces
              ? 'Loading execution traces...'
              : 'No execution trace events match the selected filter.'}
          </div>
        ) : (
          <div className="trace-timeline">
            {filteredTraces.map((event) => {
              const isError = event.status === 'error' || Boolean(event.error) || event.event_type === 'tool_failed';
              const isRetry =
                event.event_type === 'retry_started' ||
                Boolean(event.recovery_decision) ||
                (event.attempt_number !== null && event.attempt_number !== undefined && event.attempt_number > 1);
              const isSuccess = event.status === 'success' || event.event_type === 'tool_completed';

              const itemClass = isError
                ? 'is-error'
                : isRetry
                ? 'is-retry'
                : isSuccess
                ? 'is-success'
                : '';

              return (
                <div key={event.id} className={`trace-node-item ${itemClass}`}>
                  <div className="flex-between" style={{ marginBottom: '4px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="font-mono" style={{ fontSize: '0.8rem', fontWeight: 700, color: '#fff' }}>
                        {event.event_type}
                      </span>
                      <span
                        className="font-mono"
                        style={{
                          fontSize: '0.72rem',
                          background: 'rgba(56, 189, 248, 0.12)',
                          color: '#38bdf8',
                          padding: '1px 6px',
                          borderRadius: '4px',
                        }}
                      >
                        [{event.node}]
                      </span>
                      {event.tool && (
                        <span
                          className="font-mono"
                          style={{
                            fontSize: '0.72rem',
                            background: 'rgba(249, 115, 22, 0.15)',
                            color: '#fb923c',
                            padding: '1px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          &lt;{event.tool}&gt;
                        </span>
                      )}
                      {event.attempt_number && event.attempt_number > 1 && (
                        <span
                          className="font-mono"
                          style={{
                            fontSize: '0.7rem',
                            background: 'rgba(245, 158, 11, 0.2)',
                            color: '#fbbf24',
                            padding: '1px 6px',
                            borderRadius: '4px',
                            fontWeight: 600,
                          }}
                        >
                          Attempt #{event.attempt_number}
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {event.duration_ms !== null && event.duration_ms !== undefined && (
                        <span className="font-mono text-dim" style={{ fontSize: '0.75rem' }}>
                          {event.duration_ms}ms
                        </span>
                      )}
                      <span className="font-mono text-dim" style={{ fontSize: '0.72rem' }}>
                        {new Date(event.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>

                  {/* Recovery Decision Banner */}
                  {event.recovery_decision && (
                    <div
                      style={{
                        background: 'rgba(245, 158, 11, 0.1)',
                        border: '1px solid rgba(245, 158, 11, 0.3)',
                        borderRadius: '4px',
                        padding: '6px 10px',
                        fontSize: '0.78rem',
                        color: '#fbbf24',
                        marginBottom: '6px',
                        marginTop: '4px',
                      }}
                    >
                      🛡️ Recovery Decision: <strong>{event.recovery_decision}</strong>
                    </div>
                  )}

                  {/* Sanitized Error Summary */}
                  {event.error && (
                    <div
                      style={{
                        background: 'rgba(244, 63, 94, 0.12)',
                        border: '1px solid rgba(244, 63, 94, 0.3)',
                        borderRadius: '4px',
                        padding: '6px 10px',
                        fontSize: '0.78rem',
                        color: '#fb7185',
                        marginBottom: '6px',
                        marginTop: '4px',
                      }}
                    >
                      ✕ Error: {event.error}
                    </div>
                  )}

                  {/* Details Toggle */}
                  {event.details && Object.keys(event.details).length > 0 && (
                    <div style={{ marginTop: '6px' }}>
                      <button
                        type="button"
                        onClick={() => toggleExpand(event.id)}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--text-dim)',
                          fontSize: '0.72rem',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        {expandedDetails[event.id] ? '▲ Collapse Payload' : '▼ View Arguments & Payload'}
                      </button>

                      {expandedDetails[event.id] && (
                        <pre
                          className="font-mono"
                          style={{
                            background: 'var(--bg-input)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: '4px',
                            padding: '8px 12px',
                            fontSize: '0.75rem',
                            color: '#94a3b8',
                            marginTop: '6px',
                            overflowX: 'auto',
                            maxHeight: '200px',
                          }}
                        >
                          {JSON.stringify(event.details, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
