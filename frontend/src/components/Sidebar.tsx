import React from 'react';

export type NavigationPage = 'overview' | 'tasks' | 'trace' | 'reports' | 'memory';

interface SidebarProps {
  currentPage: NavigationPage;
  onNavigate: (page: NavigationPage) => void;
  activeTaskId: string | null;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentPage,
  onNavigate,
  activeTaskId,
}) => {
  const navItems: { id: NavigationPage; label: string; icon: string; badge?: string }[] = [
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'tasks', label: 'Task Center', icon: '⚡' },
    { id: 'trace', label: 'Execution Trace', icon: '⏱️', badge: activeTaskId ? 'Active' : undefined },
    { id: 'reports', label: 'Research & Reports', icon: '📑' },
    { id: 'memory', label: 'Semantic Memory', icon: '🧠' },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-badge">🔥</div>
        <div>
          <div className="brand-title">
            FLAMO <span className="brand-badge">v2.0</span>
          </div>
          <div className="brand-subtitle">Autonomous AI Operations</div>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main Navigation">
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`nav-link ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
            type="button"
          >
            <span className="nav-icon" role="img" aria-label={item.label}>
              {item.icon}
            </span>
            <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>
            {item.badge && (
              <span
                style={{
                  fontSize: '0.65rem',
                  fontFamily: 'var(--font-mono)',
                  background: 'rgba(56, 189, 248, 0.2)',
                  color: '#38bdf8',
                  padding: '1px 6px',
                  borderRadius: '4px',
                }}
              >
                {item.badge}
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div>LangGraph Multi-Agent Swarm</div>
        <div style={{ color: 'var(--text-dim)', marginTop: '4px' }}>
          {activeTaskId ? (
            <span style={{ color: 'var(--accent-cyan)' }}>
              Target: <code className="font-mono">{activeTaskId.slice(0, 12)}...</code>
            </span>
          ) : (
            'No active mission'
          )}
        </div>
      </div>
    </aside>
  );
};
