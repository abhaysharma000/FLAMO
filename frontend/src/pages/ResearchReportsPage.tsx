import React, { useState } from 'react';
import { ReportDetail, ReportSummary } from '../types/report';
import { TaskResponse } from '../types/task';

interface ResearchReportsPageProps {
  reports: ReportSummary[];
  activeReport: ReportDetail | null;
  tasks: TaskResponse[];
  selectedTaskId: string | null;
  loadingReports: boolean;
  loadingDetail: boolean;
  error: string | null;
  onSelectReport: (filename: string) => void;
  onDownloadReport: (filename: string) => void;
  onSelectTask: (taskId: string) => void;
  onRefreshReports: () => void;
}

export const ResearchReportsPage: React.FC<ResearchReportsPageProps> = ({
  reports,
  activeReport,
  tasks,
  selectedTaskId,
  loadingReports,
  loadingDetail,
  error,
  onSelectReport,
  onDownloadReport,
  onSelectTask,
  onRefreshReports,
}) => {
  const [viewMode, setViewMode] = useState<'reports' | 'claims'>('reports');
  const [rawMarkdown, setRawMarkdown] = useState<boolean>(false);

  // Find task for claims audit
  const selectedTask = tasks.find((t) => t.id === selectedTaskId) || tasks.find((t) => t.claims && t.claims.length > 0) || null;
  const taskClaims = selectedTask?.claims || [];
  const evidenceItems = selectedTask?.verification_result?.evidence_pipeline?.evidence_items || [];

  return (
    <div className="page-container">
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">Research & Verification Center</h1>
          <p className="page-desc">
            Workspace research artifacts, claim-by-claim verification table, and authoritative source provenance.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className={`btn ${viewMode === 'reports' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('reports')}
          >
            📑 Workspace Reports ({reports.length})
          </button>
          <button
            type="button"
            className={`btn ${viewMode === 'claims' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('claims')}
          >
            🛡️ Claim Verification Audit ({taskClaims.length})
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onRefreshReports}
            disabled={loadingReports}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="alert-banner alert-error" role="alert">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {/* VIEW MODE 1: WORKSPACE REPORTS */}
      {viewMode === 'reports' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, 340px) 1fr', gap: '24px' }}>
          {/* Reports List Sidebar */}
          <div className="card">
            <div className="card-header">
              <h2 className="card-title" style={{ fontSize: '1rem' }}>
                📂 Generated Artifacts
              </h2>
              <span className="text-dim" style={{ fontSize: '0.75rem' }}>./workspace</span>
            </div>

            {reports.length === 0 ? (
              <div className="empty-state">
                {loadingReports ? 'Scanning workspace sandbox...' : 'No reports generated yet in workspace.'}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '650px', overflowY: 'auto' }}>
                {reports.map((r) => {
                  const isSelected = activeReport?.filename === r.filename;
                  return (
                    <div
                      key={r.filename}
                      onClick={() => onSelectReport(r.filename)}
                      style={{
                        padding: '12px 14px',
                        borderRadius: 'var(--radius-sm)',
                        background: isSelected ? 'rgba(249, 115, 22, 0.12)' : 'var(--bg-input)',
                        border: `1px solid ${isSelected ? 'var(--accent-flame)' : 'var(--border-subtle)'}`,
                        cursor: 'pointer',
                        transition: 'var(--transition)',
                      }}
                    >
                      <div style={{ fontWeight: 600, color: '#fff', fontSize: '0.88rem' }}>
                        {r.title}
                      </div>
                      <div className="font-mono text-dim" style={{ fontSize: '0.75rem', marginTop: '2px' }}>
                        {r.filename}
                      </div>
                      <div className="flex-between" style={{ marginTop: '6px', fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                        <span className="font-mono">{(r.size_bytes / 1024).toFixed(1)} KB</span>
                        <span>{new Date(r.modified_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Report Viewer */}
          <div className="card">
            {activeReport ? (
              <div>
                <div className="card-header flex-between" style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: '14px' }}>
                  <div>
                    <h2 className="card-title">{activeReport.title}</h2>
                    <div className="font-mono text-dim" style={{ fontSize: '0.75rem', marginTop: '2px' }}>
                      {activeReport.filename} • {(activeReport.size_bytes / 1024).toFixed(1)} KB • Modified:{' '}
                      {new Date(activeReport.modified_at).toLocaleString()}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ fontSize: '0.8rem' }}
                      onClick={() => setRawMarkdown(!rawMarkdown)}
                    >
                      {rawMarkdown ? 'Render View' : 'Raw Markdown'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      style={{ fontSize: '0.8rem' }}
                      onClick={() => onDownloadReport(activeReport.filename)}
                    >
                      📥 Download File
                    </button>
                  </div>
                </div>

                <div style={{ padding: '16px 0', maxHeight: '680px', overflowY: 'auto' }}>
                  {loadingDetail ? (
                    <div className="empty-state">Loading report contents...</div>
                  ) : rawMarkdown ? (
                    <pre
                      className="font-mono"
                      style={{
                        background: 'var(--bg-input)',
                        padding: '16px',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.82rem',
                        color: '#cbd5e1',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {activeReport.content}
                    </pre>
                  ) : (
                    <div
                      className="markdown-body"
                      dangerouslySetInnerHTML={{
                        __html: formatReportHtml(activeReport.content),
                      }}
                    />
                  )}
                </div>
              </div>
            ) : (
              <div className="empty-state">
                Select a report from the list on the left to preview contents or download.
              </div>
            )}
          </div>
        </div>
      )}

      {/* VIEW MODE 2: FACTUAL CLAIMS AUDIT */}
      {viewMode === 'claims' && (
        <div>
          {/* Task Selector for claims */}
          <div className="card" style={{ marginBottom: '20px' }}>
            <div className="flex-between">
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '1.2rem' }}>🎯</span>
                <div>
                  <div style={{ fontWeight: 600, color: '#fff' }}>Research Mission Audit Target</div>
                  <div className="text-dim" style={{ fontSize: '0.78rem' }}>
                    Select a task that executed evidence extraction and verification pipeline
                  </div>
                </div>
              </div>

              <select
                className="input-select"
                style={{ width: '320px' }}
                value={selectedTask?.id || ''}
                onChange={(e) => onSelectTask(e.target.value)}
              >
                {tasks.map((t) => (
                  <option key={t.id} value={t.id}>
                    [{t.claims?.length || 0} claims] {t.goal.slice(0, 40)}...
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Verification Scorecard */}
          {selectedTask && (
            <div className="metrics-grid" style={{ marginBottom: '20px' }}>
              <div className="kpi-card">
                <div className="kpi-label">AUDITED CLAIMS</div>
                <div className="kpi-value">{taskClaims.length}</div>
                <div className="kpi-subtext">Total statements evaluated</div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">VERIFIED (PRIMARY)</div>
                <div className="kpi-value" style={{ color: 'var(--accent-green)' }}>
                  {taskClaims.filter((c) => c.status === 'VERIFIED').length}
                </div>
                <div className="kpi-subtext">Supported by authoritative docs</div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">PARTIALLY VERIFIED</div>
                <div className="kpi-value" style={{ color: 'var(--accent-cyan)' }}>
                  {taskClaims.filter((c) => c.status === 'PARTIALLY_VERIFIED').length}
                </div>
                <div className="kpi-subtext">Secondary source support</div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">CONFLICTING / CONTRADICTED</div>
                <div className="kpi-value" style={{ color: 'var(--accent-rose)' }}>
                  {taskClaims.filter((c) => c.status === 'CONFLICTING').length}
                </div>
                <div className="kpi-subtext">Contradictions detected</div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">UNVERIFIED CLAIMS</div>
                <div className="kpi-value" style={{ color: 'var(--text-muted)' }}>
                  {taskClaims.filter((c) => c.status === 'UNVERIFIED').length}
                </div>
                <div className="kpi-subtext">Lacking evidence (not facts)</div>
              </div>
            </div>
          )}

          {/* Claim-by-Claim Table */}
          <div className="card">
            <div className="card-header flex-between">
              <h2 className="card-title">🔍 Claim-by-Claim Evidence Table</h2>
              <span className="text-dim" style={{ fontSize: '0.75rem' }}>
                Authoritative verification guarantees (No status upgrades in UI)
              </span>
            </div>

            {taskClaims.length === 0 ? (
              <div className="empty-state">
                No factual claims were extracted for this task. Run a research task to generate claims.
              </div>
            ) : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: '90px' }}>Claim ID</th>
                      <th style={{ width: '130px' }}>Status</th>
                      <th>Statement & Extracted Evidence Passage</th>
                      <th style={{ width: '150px' }}>Retrieval Mode</th>
                      <th>Provenance URLs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {taskClaims.map((claim) => {
                      const linkedEvidence = evidenceItems.filter(
                        (ev) => ev.claim_id === claim.id || ev.claim_text === claim.statement
                      );
                      const statusClass = `verif-${claim.status.toLowerCase().replace('_', '-')}`;

                      return (
                        <tr key={claim.id}>
                          <td>
                            <code className="font-mono" style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>
                              {claim.id}
                            </code>
                            <div className="font-mono text-dim" style={{ fontSize: '0.7rem' }}>
                              Conf: {Math.round((claim.confidence || 0.8) * 100)}%
                            </div>
                          </td>

                          <td>
                            <span className={`status-tag ${statusClass}`}>{claim.status}</span>
                          </td>

                          <td>
                            <div style={{ fontWeight: 600, color: '#fff', marginBottom: '6px' }}>
                              {claim.statement}
                            </div>

                            {claim.reasoning && (
                              <div style={{ fontSize: '0.78rem', color: 'var(--text-dim)', marginBottom: '8px' }}>
                                ↳ <em>{claim.reasoning}</em>
                              </div>
                            )}

                            {linkedEvidence.length > 0 && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
                                {linkedEvidence.map((ev, eIdx) => (
                                  <div
                                    key={eIdx}
                                    style={{
                                      background: 'var(--bg-input)',
                                      padding: '8px 10px',
                                      borderRadius: '4px',
                                      borderLeft: `3px solid ${
                                        ev.status === 'VERIFIED' ? 'var(--accent-green)' : 'var(--border-subtle)'
                                      }`,
                                      fontSize: '0.78rem',
                                    }}
                                  >
                                    <div style={{ color: '#e2e8f0', fontStyle: 'italic' }}>
                                      "{ev.supporting_snippet}"
                                    </div>
                                    {ev.explanation && (
                                      <div style={{ color: 'var(--text-dim)', marginTop: '4px', fontSize: '0.72rem' }}>
                                        ↳ {ev.explanation}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>

                          <td>
                            {linkedEvidence.length > 0 ? (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                {linkedEvidence.map((ev, evIdx) => {
                                  const isSnippet = ev.source?.retrieval_status === 'search_snippet';
                                  return (
                                    <span
                                      key={evIdx}
                                      className="font-mono"
                                      style={{
                                        fontSize: '0.7rem',
                                        padding: '2px 6px',
                                        borderRadius: '4px',
                                        background: isSnippet ? 'rgba(245, 158, 11, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                                        color: isSnippet ? '#fbbf24' : '#34d399',
                                        border: `1px solid ${isSnippet ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`,
                                      }}
                                    >
                                      {isSnippet ? 'Search Snippet' : 'Full Page Fetch'}
                                    </span>
                                  );
                                })}
                              </div>
                            ) : (
                              <span className="font-mono text-dim" style={{ fontSize: '0.72rem' }}>
                                None recorded
                              </span>
                            )}
                          </td>

                          <td>
                            {claim.source_urls && claim.source_urls.length > 0 ? (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                {claim.source_urls.map((url, uIdx) => (
                                  <a
                                    key={uIdx}
                                    href={url}
                                    target="_blank"
                                    rel="noreferrer noopener"
                                    className="font-mono"
                                    style={{
                                      fontSize: '0.75rem',
                                      color: 'var(--accent-cyan)',
                                      textDecoration: 'none',
                                      maxWidth: '220px',
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      whiteSpace: 'nowrap',
                                      display: 'inline-block',
                                    }}
                                  >
                                    🔗 {url.replace(/^https?:\/\//, '')}
                                  </a>
                                ))}
                              </div>
                            ) : (
                              <span className="text-dim font-mono" style={{ fontSize: '0.72rem' }}>
                                No URLs
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

function formatReportHtml(markdown: string): string {
  if (!markdown) return '';
  return markdown
    .replace(/^### (.*$)/gim, '<h3 style="color:#38bdf8; margin: 16px 0 8px;">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 style="color:#fdba74; margin: 20px 0 10px; border-bottom: 1px solid #334155; padding-bottom: 4px;">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 style="color:#fff; margin: 24px 0 12px; font-size: 1.5rem;">$1</h1>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong style="color:#f8fafc;">$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/```([\s\S]*?)```/gim, '<pre class="font-mono" style="background:#0b1120; padding:12px; border-radius:6px; overflow-x:auto; margin:12px 0;">$1</pre>')
    .replace(/`([^`]+)`/gim, '<code class="font-mono" style="background:#0b1120; color:#fdba74; padding:2px 5px; border-radius:4px;">$1</code>')
    .replace(/\n\n/gim, '<p style="margin-bottom:12px;"></p>');
}
