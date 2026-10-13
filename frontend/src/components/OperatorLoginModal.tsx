import React, { useState } from 'react';
import { apiClient } from '../api/client';

interface OperatorLoginModalProps {
  isOpen: boolean;
  onLoginSuccess: (username: string) => void;
}

export const OperatorLoginModal: React.FC<OperatorLoginModalProps> = ({ isOpen, onLoginSuccess }) => {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      setError('Password is required.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.login({
        username: username.trim(),
        password: password.trim(),
      });
      setPassword('');
      onLoginSuccess(res.username);
    } catch (err: any) {
      setError(err.detail || err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-container" style={{ maxWidth: '440px' }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '1.4rem' }}>🔐</span>
            <div>
              <h2 className="modal-title">Operator Authentication Required</h2>
              <p className="text-dim" style={{ fontSize: '0.78rem', marginTop: '2px' }}>
                FLAMO deployment access is protected. Please sign in.
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ padding: '20px' }}>
          {error && (
            <div
              className="alert-banner alert-error"
              role="alert"
              style={{ marginBottom: '16px', fontSize: '0.8rem' }}
            >
              <span>✕ {error}</span>
            </div>
          )}

          <div style={{ marginBottom: '14px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.75rem',
                color: 'var(--text-dim)',
                marginBottom: '6px',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
              }}
            >
              Operator Username
            </label>
            <input
              type="text"
              className="input-text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              disabled={loading}
              required
            />
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.75rem',
                color: 'var(--text-dim)',
                marginBottom: '6px',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
              }}
            >
              Operator Password
            </label>
            <input
              type="password"
              className="input-text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter operator password"
              disabled={loading}
              autoFocus
              required
            />
          </div>

          <div className="modal-actions" style={{ justifyContent: 'flex-end' }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !password.trim()}
              style={{ minWidth: '130px' }}
            >
              {loading ? 'Authenticating...' : 'Sign In'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
