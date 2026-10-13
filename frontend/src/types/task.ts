export type TaskStatus =
  | 'pending'
  | 'planning'
  | 'running'
  | 'awaiting_approval'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface PlanStep {
  id: number;
  title: string;
  description: string;
  tool_hint?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped';
  output?: string;
  error?: string;
}

export interface ExecutionPlan {
  steps: PlanStep[];
  estimated_complexity: string;
}

export interface ToolCallRecord {
  id: string;
  tool_name: string;
  arguments: Record<string, any>;
  result: any;
  is_error: boolean;
  execution_time_ms: number;
  timestamp: string;
}

export interface VerificationResult {
  is_valid: boolean;
  score: number;
  checks_passed: string[];
  checks_failed: string[];
  critique: string;
  deterministic_checks?: Record<string, boolean>;
  status?: 'VERIFIED' | 'PARTIALLY_VERIFIED' | 'CONFLICTING' | 'UNVERIFIED';
  conflicts_detected?: string[];
  evidence_pipeline?: {
    claims?: Claim[];
    evidence_items?: EvidenceItem[];
    overall_status?: string;
    conflicts_detected?: string[];
    factual_verification_score?: number;
    primary_sources_count?: number;
    secondary_sources_count?: number;
    distinct_domains_count?: number;
  };
  factual_verification_score?: number;
  execution_success?: boolean;
  claims_verified_count?: number;
  claims_partially_verified_count?: number;
  claims_total_count?: number;
  claims_unverified_count?: number;
  claims_conflicting_count?: number;
}

export interface Claim {
  id: string;
  statement: string;
  status: 'VERIFIED' | 'PARTIALLY_VERIFIED' | 'CONFLICTING' | 'UNVERIFIED';
  confidence: number;
  reasoning?: string;
  source_urls?: string[];
  evidence_ids?: string[];
}

export interface EvidenceItem {
  id: string;
  claim_id?: string;
  claim_text: string;
  supporting_snippet: string;
  confidence: number;
  status: 'VERIFIED' | 'PARTIALLY_VERIFIED' | 'CONFLICTING' | 'UNVERIFIED';
  explanation?: string;
  retrieval_status?: string;
  source: {
    url: string;
    title?: string;
    source_type: string;
    domain?: string;
    retrieval_status?: string;
  };
}

export interface TaskResponse {
  id: string;
  goal: string;
  status: TaskStatus;
  plan?: ExecutionPlan | null;
  current_step_index: number;
  completed_steps: string[];
  failed_steps: string[];
  retry_count: number;
  final_answer?: string | null;
  errors: string[];
  created_at: string;
  updated_at: string;
  duration_seconds?: number | null;
  verification_result?: VerificationResult | null;
  total_tool_calls: number;
  tool_results: ToolCallRecord[];
  pending_action?: Record<string, any> | null;
  evidence_count: number;
  claims: Claim[];
  agents_used?: string[];
  metrics?: Record<string, any> | null;
}

export interface TaskListResponse {
  tasks: TaskResponse[];
  total: number;
}

export interface TaskCreateRequest {
  goal: string;
  context?: Record<string, any>;
}
