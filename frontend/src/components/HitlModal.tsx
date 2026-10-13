import React from 'react';

interface HitlModalProps {
  taskId: string;
  pendingAction: Record<string, any> | null;
  onApprove: () => void;
  onReject: () => void;
  loading: boolean;
}

export const HitlModal: React.FC<HitlModalProps> = ({
  taskId,
  pendingAction,
  onApprove,
  onReject,
  loading,
}) => {
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="hitl-title">
      <div className="modal-dialog">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
          <span style={{ fontSize: '1.8rem' }}>🛡️</span>
          <div>
            <h3 id="hitl-title" style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#fff' }}>
              Human-in-the-Loop Authorization Required
            </h3>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              Task <code className="font-mono">{taskId}</code> paused at an operational checkpoint.
            </p>
          </div>
        </div>

        <div style={{ background: 'var(--bg-input)', padding: '14px', borderRadius: 'var(--radius-sm)', marginBottom: '20px' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '6px' }}>PENDING ACTION PAYLOAD:</div>
          <pre className="font-mono" style={{ fontSize: '0.8rem', color: '#38bdf8', whiteSpace: 'pre-wrap', maxHeight: '180px', overflowY: 'auto' }}>
            {pendingAction ? JSON.stringify(pendingAction, null, 2) : 'Action details not available from checkpoint.'}
          </pre>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
          <button
            type="button"
            className="btn btn-danger"
            onClick={onReject}
            disabled={loading}
          >
            ✕ Decline Action
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onApprove}
            disabled={loading}
          >
            {loading ? 'Authorizing...' : '✓ Authorize & Resume'}
          </button>
        </div>
      </div>
    </div>
  );
};
