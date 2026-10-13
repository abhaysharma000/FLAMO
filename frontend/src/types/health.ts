export interface HealthResponse {
  status: 'healthy' | 'degraded';
  timestamp: string;
  version: string;
  system: string;
  llm: {
    provider: string;
    model: string;
    configured: boolean;
  };
  database: {
    type: string;
    status?: string;
    url?: string;
  };
  memory?: {
    backend: string;
    active_backend?: string;
    search_method?: string;
    configured_embedding_model?: string;
    active_embedding_model?: string | null;
    embedding_model?: string | null;
    vector_search_active?: boolean;
    chroma_dir?: string | null;
  };
  workspace: {
    status?: string;
    sandbox_enabled?: boolean;
    sandbox_path?: string;
    exists: boolean;
  };
  tools_registered: {
    count: number;
    tools: string[];
  };
}
