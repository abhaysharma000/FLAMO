import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryExplorerPage } from '../src/pages/MemoryExplorerPage';
import { HealthResponse } from '../src/types/health';
import { MemoryItem } from '../src/types/memory';

describe('MemoryExplorerPage Component', () => {
  const mockChromaHealth: HealthResponse = {
    status: 'healthy',
    timestamp: '2026-10-11T12:00:00Z',
    version: '2.0.0',
    system: 'FLAMO Autonomous AI Operations Agent',
    llm: { provider: 'google-genai', model: 'gemini-3.5-flash-lite', configured: true },
    database: { type: 'sqlite', status: 'connected' },
    memory: {
      backend: 'chroma',
      active_backend: 'chroma',
      search_method: 'dense_vector',
      configured_embedding_model: 'gemini-embedding-001',
      active_embedding_model: 'gemini-embedding-001',
      embedding_model: 'gemini-embedding-001',
      vector_search_active: true,
    },
    workspace: { status: 'ready', sandbox_enabled: true, exists: true },
    tools_registered: { count: 8, tools: ['web_search'] },
  };

  const mockSqliteHealth: HealthResponse = {
    status: 'healthy',
    timestamp: '2026-10-11T12:00:00Z',
    version: '2.0.0',
    system: 'FLAMO Autonomous AI Operations Agent',
    llm: { provider: 'google-genai', model: 'gemini-3.5-flash-lite', configured: true },
    database: { type: 'sqlite', status: 'connected' },
    memory: {
      backend: 'sqlite',
      active_backend: 'sqlite',
      search_method: 'stemmed_token_match',
      configured_embedding_model: 'models/text-embedding-004',
      active_embedding_model: null,
      embedding_model: null,
      vector_search_active: false,
    },
    workspace: { status: 'ready', sandbox_enabled: true, exists: true },
    tools_registered: { count: 8, tools: ['web_search'] },
  };

  const mockChromaMemories: MemoryItem[] = [
    {
      id: 'mem-agent-recovery',
      category: 'reusable_knowledge',
      content: 'Autonomous agents recover by storing checkpoints in sqlite and applying bounded retries.',
      metadata: {},
      timestamp: '2026-10-11T12:00:00Z',
      task_id: 'task-test-55',
      relevance_score: 0.874,
      scoring_method: 'cosine_similarity',
    },
  ];

  const mockSqliteMemories: MemoryItem[] = [
    {
      id: 'mem-sqlite-item',
      category: 'reusable_knowledge',
      content: 'SQLite store matches stemmed keyword roots across documents.',
      metadata: {},
      timestamp: '2026-10-11T12:00:00Z',
      task_id: 'task-test-56',
      relevance_score: 0.625,
      scoring_method: 'stemmed_token_match',
    },
  ];

  it('renders active Chroma backend banner and real embedding model', () => {
    render(
      <MemoryExplorerPage
        health={mockChromaHealth}
        memories={[]}
        loading={false}
        error={null}
        onSearch={vi.fn().mockResolvedValue(undefined)}
        onStoreMemory={vi.fn().mockResolvedValue(undefined)}
      />
    );

    expect(screen.getByText(/ACTIVE MEMORY BACKEND: CHROMA STORE/)).toBeInTheDocument();
    expect(screen.getByText(/ChromaDB Persistent Dense Vector/)).toBeInTheDocument();
    expect(screen.getByText(/Active Embedding Model:/)).toBeInTheDocument();
    expect(screen.getByText('gemini-embedding-001')).toBeInTheDocument();
    expect(screen.getByText(/Active \(Cosine space\)/)).toBeInTheDocument();
  });

  it('submits search query and renders Chroma ranked results with Cosine Similarity label', () => {
    const handleSearch = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryExplorerPage
        health={mockChromaHealth}
        memories={mockChromaMemories}
        loading={false}
        error={null}
        onSearch={handleSearch}
        onStoreMemory={vi.fn().mockResolvedValue(undefined)}
      />
    );

    const input = screen.getByPlaceholderText(/Search semantically/i);
    fireEvent.change(input, { target: { value: 'How do agents recover?' } });

    const searchBtn = screen.getByText('🔍 Semantic Vector Search');
    fireEvent.click(searchBtn);

    expect(handleSearch).toHaveBeenCalledWith('How do agents recover?', undefined, 10);

    // Verify rendered memory card has Cosine Similarity label
    expect(screen.getByText(/Autonomous agents recover by storing checkpoints/)).toBeInTheDocument();
    expect(screen.getByText('Cosine Similarity: 0.874')).toBeInTheDocument();
    expect(screen.getByText('Task: task-test-55')).toBeInTheDocument();
  });

  it('accurately renders SQLite telemetry without implying active embeddings and labels scores as Stemmed Token Match', () => {
    const handleSearch = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryExplorerPage
        health={mockSqliteHealth}
        memories={mockSqliteMemories}
        loading={false}
        error={null}
        onSearch={handleSearch}
        onStoreMemory={vi.fn().mockResolvedValue(undefined)}
      />
    );

    expect(screen.getByText(/ACTIVE MEMORY BACKEND: SQLITE STORE/)).toBeInTheDocument();
    expect(screen.getByText(/SQLite Stemmed Token Match \(Lexical\)/)).toBeInTheDocument();
    expect(screen.getByText(/Retrieval Method:/)).toBeInTheDocument();
    expect(screen.getByText(/Stemmed Token Frequency Match/)).toBeInTheDocument();
    expect(screen.getByText(/Inactive for SQLite/)).toBeInTheDocument();
    expect(screen.getByText('models/text-embedding-004')).toBeInTheDocument();

    const searchBtn = screen.getByText('🔍 Stemmed Token Search');
    expect(searchBtn).toBeInTheDocument();

    // Verify rendered score is labeled Stemmed Token Match, never Cosine Similarity
    expect(screen.getByText('Stemmed Token Match: 0.625')).toBeInTheDocument();
    expect(screen.queryByText(/Cosine Similarity/i)).not.toBeInTheDocument();
  });

  it('displays honest backend error without silently substituting mock results', () => {
    render(
      <MemoryExplorerPage
        health={mockChromaHealth}
        memories={[]}
        loading={false}
        error="Invalid model name 'gemini-nonexistent' not supported by Google GenAI API."
        onSearch={vi.fn().mockResolvedValue(undefined)}
        onStoreMemory={vi.fn().mockResolvedValue(undefined)}
      />
    );

    expect(screen.getByText(/Invalid model name 'gemini-nonexistent'/)).toBeInTheDocument();
    expect(screen.queryByText(/Mock result/i)).not.toBeInTheDocument();
  });
});
