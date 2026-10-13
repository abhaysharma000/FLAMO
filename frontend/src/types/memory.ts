export type MemoryCategory =
  | 'task_memory'
  | 'user_preferences'
  | 'findings'
  | 'reusable_knowledge';

export interface MemoryItem {
  id: string;
  category: MemoryCategory;
  content: string;
  metadata: Record<string, any>;
  timestamp: string;
  task_id?: string | null;
  relevance_score?: number | null;
  scoring_method?: string | null;
}

export interface MemoryCreateRequest {
  category: MemoryCategory;
  content: string;
  metadata?: Record<string, any>;
  task_id?: string;
}
