import React, { useState } from 'react';
import { HealthResponse } from '../types/health';
import { MemoryCategory, MemoryItem } from '../types/memory';

interface MemoryExplorerPageProps {
  health: HealthResponse | null;
  memories: MemoryItem[];
  loading: boolean;
  error: string | null;
  onSearch: (query: string, category?: MemoryCategory, limit?: number) => Promise<void>;
  onStoreMemory: (content: string, category: MemoryCategory, taskId?: string) => Promise<void>;
}

export const MemoryExplorerPage: React.FC<MemoryExplorerPageProps> = ({
  health,
  memories,
  loading,
  error,
  onSearch,
  onStoreMemory,
}) => {
  const [queryInput, setQueryInput] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<MemoryCategory | 'all'>('all');
  const [limitCount, setLimitCount] = useState<number>(10);
  const [hasSearched, setHasSearched] = useState(false);

  // Store Memory Modal
  const [showStoreModal, setShowStoreModal] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newCategory, setNewCategory] = useState<MemoryCategory>('reusable_knowledge');
  const [newTaskId, setNewTaskId] = useState('');
  const [storing, setStoring] = useState(false);
  const [storeSuccess, setStoreSuccess] = useState<string | null>(null);

  const memBackend = (health?.memory?.backend || 'sqlite').toLowerCase();
  const isChroma = memBackend === 'chroma' || health?.memory?.vector_search_active === true;
  const configuredModel = health?.memory?.configured_embedding_model || health?.memory?.embedding_model || 'models/text-embedding-004';
  const activeModel = health?.memory?.active_embedding_model;

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryInput.trim()) return;
    setHasSearched(true);
    await onSearch(
      queryInput.trim(),
      categoryFilter === 'all' ? undefined : categoryFilter,
      limitCount
    );
  };

  const handleStoreSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    setStoring(true);
    try {
      await onStoreMemory(newContent.trim(), newCategory, newTaskId.trim() || undefined);
      setStoreSuccess('Memory item successfully stored and indexed!');
      setNewContent('');
      setNewTaskId('');
      setTimeout(() => {
        setStoreSuccess(null);
        setShowStoreModal(false);
      }, 1500);
    } catch (err: any) {
      alert(`Storage failed: ${err.message}`);
    } finally {
      setStoring(false);
    }
  };

  return (
    <div className="page-container">
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">Semantic Memory Explorer</h1>
          <p className="page-desc">
            Natural-language vector retrieval, knowledge persistence, and relevance scoring.
          </p>
        </div>

        <button
          type="button"
          className="btn btn-primary"
          onClick={() => setShowStoreModal(true)}
        >
          + Store Knowledge Memory
        </button>
      </div>

      {/* Backend Status Banner */}
      <div className="card" style={{ marginBottom: '20px', background: 'var(--bg-elevated)' }}>
        <div className="flex-between">
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <span style={{ fontSize: '1.8rem' }}>🧠</span>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: 700, color: '#fff', fontSize: '1rem' }}>
                  ACTIVE MEMORY BACKEND: {memBackend.toUpperCase()} STORE
                </span>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontFamily: 'var(--font-mono)',
                    background: isChroma ? 'rgba(56, 189, 248, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                    color: isChroma ? '#38bdf8' : '#34d399',
                    padding: '2px 8px',
                    borderRadius: '4px',
                  }}
                >
                  {isChroma ? 'ChromaDB Persistent Dense Vector' : 'SQLite Stemmed Token Match (Lexical)'}
                </span>
              </div>
              <div className="font-mono text-dim" style={{ fontSize: '0.78rem', marginTop: '3px' }}>
                {isChroma ? (
                  <>
                    Active Embedding Model: <strong>{activeModel || configuredModel}</strong> • Vector Search: <strong>Active (Cosine space)</strong> • Storage: ChromaDB
                  </>
                ) : (
                  <>
                    Retrieval Method: <strong>Stemmed Token Frequency Match</strong> • Configured Embedding Model: <strong>{configuredModel}</strong> (Inactive for SQLite) • Vector Search: <strong>Inactive</strong>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Semantic Search Box */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <form onSubmit={handleSearchSubmit}>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '14px' }}>
            <input
              type="text"
              className="input-text"
              placeholder="Search semantically: e.g. How do autonomous agents recover from failure?"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !queryInput.trim()}
              style={{ minWidth: '160px' }}
            >
              {loading ? (isChroma ? 'Embedding & Searching...' : 'Searching...') : (isChroma ? '🔍 Semantic Vector Search' : '🔍 Stemmed Token Search')}
            </button>
          </div>

          <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>Category Filter:</span>
              <select
                className="input-select"
                style={{ width: '180px', padding: '6px 10px', fontSize: '0.8rem' }}
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value as any)}
              >
                <option value="all">All Categories</option>
                <option value="reusable_knowledge">Reusable Knowledge</option>
                <option value="findings">Research Findings</option>
                <option value="task_memory">Task Memory</option>
                <option value="user_preferences">User Preferences</option>
              </select>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>Max Results:</span>
              <select
                className="input-select"
                style={{ width: '80px', padding: '6px 10px', fontSize: '0.8rem' }}
                value={limitCount}
                onChange={(e) => setLimitCount(Number(e.target.value))}
              >
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={20}>20</option>
              </select>
            </div>
          </div>
        </form>
      </div>

      {/* Honest Error Message */}
      {error && (
        <div className="alert-banner alert-error" role="alert" style={{ marginBottom: '20px' }}>
          <span>✕ Retrieval Error:</span>
          <span>{error}</span>
        </div>
      )}

      {/* Search Results */}
      <div className="card">
        <div className="card-header flex-between">
          <h2 className="card-title">
            📚 Ranked Memory Items ({memories.length} retrieved)
          </h2>
          {hasSearched && queryInput && (
            <span className="font-mono text-dim" style={{ fontSize: '0.75rem' }}>
              Query: "{queryInput}"
            </span>
          )}
        </div>

        {memories.length === 0 ? (
          <div className="empty-state">
            {loading
              ? 'Computing embeddings and ranking memories...'
              : hasSearched
              ? 'No memory items matched the search query and threshold.'
              : 'Enter a semantic search query above to query the active memory store.'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {memories.map((item, idx) => {
              const score = item.relevance_score !== null && item.relevance_score !== undefined
                ? Math.round(item.relevance_score * 1000) / 1000
                : null;

              return (
                <div
                  key={item.id || idx}
                  style={{
                    background: 'var(--bg-input)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '14px 18px',
                    transition: 'var(--transition)',
                  }}
                >
                  <div className="flex-between" style={{ marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        className="font-mono"
                        style={{
                          fontSize: '0.72rem',
                          background: 'rgba(249, 115, 22, 0.15)',
                          color: 'var(--accent-flame)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontWeight: 600,
                          textTransform: 'uppercase',
                        }}
                      >
                        {item.category.replace('_', ' ')}
                      </span>

                      {score !== null && (() => {
                        const isCosine = item.scoring_method === 'cosine_similarity' || (isChroma && item.scoring_method !== 'stemmed_token_match');
                        const label = isCosine ? `Cosine Similarity: ${score}` : `Stemmed Token Match: ${score}`;
                        return (
                          <span
                            className="font-mono"
                            style={{
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              color: score >= 0.7 ? '#34d399' : '#38bdf8',
                              background: score >= 0.7 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(56, 189, 248, 0.15)',
                              padding: '2px 8px',
                              borderRadius: '4px',
                            }}
                          >
                            {label}
                          </span>
                        );
                      })()}
                    </div>

                    <div className="font-mono text-dim" style={{ fontSize: '0.72rem' }}>
                      {new Date(item.timestamp).toLocaleString()}
                    </div>
                  </div>

                  <div style={{ color: '#e2e8f0', fontSize: '0.9rem', lineHeight: 1.55, margin: '8px 0' }}>
                    {item.content}
                  </div>

                  <div className="flex-between" style={{ marginTop: '8px', fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                    <span className="font-mono">ID: {item.id}</span>
                    {item.task_id && <span className="font-mono">Task: {item.task_id}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Store Knowledge Modal */}
      {showStoreModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="store-modal-title">
          <div className="modal-dialog">
            <h3 id="store-modal-title" style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#fff', marginBottom: '14px' }}>
              Index New Semantic Memory Item
            </h3>

            {storeSuccess && (
              <div className="alert-banner alert-success" role="alert">
                <span>✓</span>
                <span>{storeSuccess}</span>
              </div>
            )}

            <form onSubmit={handleStoreSubmit}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-dim)', marginBottom: '4px' }}>
                  KNOWLEDGE CONTENT
                </label>
                <textarea
                  className="input-textarea"
                  rows={4}
                  placeholder="Enter factual assertion, operational pattern, or finding to embed..."
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-dim)', marginBottom: '4px' }}>
                    CATEGORY
                  </label>
                  <select
                    className="input-select"
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value as any)}
                  >
                    <option value="reusable_knowledge">Reusable Knowledge</option>
                    <option value="findings">Research Findings</option>
                    <option value="task_memory">Task Memory</option>
                    <option value="user_preferences">User Preferences</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-dim)', marginBottom: '4px' }}>
                    ASSOCIATED TASK ID (OPTIONAL)
                  </label>
                  <input
                    type="text"
                    className="input-text"
                    placeholder="e.g. task-12345"
                    value={newTaskId}
                    onChange={(e) => setNewTaskId(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowStoreModal(false)}
                  disabled={storing}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={storing || !newContent.trim()}
                >
                  {storing ? 'Embedding & Indexing...' : 'Save & Index Memory'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
