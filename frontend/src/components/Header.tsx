import React from 'react';
import { HealthResponse } from '../types/health';

interface HeaderProps {
  health: HealthResponse | null;
  loading: boolean;
  onRefreshHealth: () => void;
  operatorUsername?: string | null;
  authEnabled?: boolean;
  onLogout?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  loading,
  onRefreshHealth,
  operatorUsername,
  authEnabled,
  onLogout,
}) => {
  const isHealthy = health?.status === 'healthy';
  const memBackend = (health?.memory?.backend || 'sqlite').toLowerCase();
  const isChroma = memBackend === 'chroma' || health?.memory?.vector_search_active === true;
  const memModelLabel = isChroma
    ? (health?.memory?.active_embedding_model || health?.memory?.configured_embedding_model || health?.memory?.embedding_model || 'dense-vector')
    : 'Stemmed Token Match';

  return (
    <header className="top-header">
      <div className="header-status-group">
        <div
          className={`status-pill ${isHealthy ? 'status-live' : 'status-degraded'}`}
          title="Flamo Engine Diagnostics"
        >
          <span className="pulse-dot" />
          <span>{health ? `ENGINE: ${health.status.toUpperCase()}` : 'ENGINE: CONNECTING...'}</span>
        </div>

        {health && (
          <>
            <span className="header-meta-badge" title="Active Generative LLM Provider">
              LLM: <strong>{health.llm.model}</strong>
            </span>
            <span className="header-meta-badge" title="Active Memory Store and Method">
              MEMORY: <strong>{memBackend.toUpperCase()}</strong> ({memModelLabel})
            </span>
            <span className="header-meta-badge" title="Sandbox Tool Registry">
              TOOLS: <strong>{health.tools_registered.count}</strong>
            </span>
          </>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        {authEnabled && operatorUsername && (
          <span
            className="header-meta-badge"
            style={{ borderColor: 'rgba(56, 189, 248, 0.4)', color: '#38bdf8' }}
            title="Authenticated Single Operator"
          >
            OPERATOR: <strong>{operatorUsername}</strong>
          </span>
        )}

        <button
          className="btn btn-secondary"
          onClick={onRefreshHealth}
          disabled={loading}
          title="Refresh backend system diagnostics"
          style={{ padding: '6px 12px', fontSize: '0.8rem' }}
        >
          {loading ? '↻ Checking...' : '↻ Refresh Health'}
        </button>

        {authEnabled && onLogout && (
          <button
            className="btn btn-secondary"
            onClick={onLogout}
            title="Log out of operator session"
            style={{ padding: '6px 12px', fontSize: '0.8rem', color: 'var(--accent-rose)' }}
          >
            Logout
          </button>
        )}
      </div>
    </header>
  );
};
