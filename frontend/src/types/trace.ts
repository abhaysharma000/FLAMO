export type TraceEventType =
  | 'task_started'
  | 'planning_started'
  | 'plan_created'
  | 'agent_reasoning_step'
  | 'tool_requested'
  | 'tool_started'
  | 'tool_completed'
  | 'tool_failed'
  | 'retry_started'
  | 'verification_started'
  | 'verification_completed'
  | 'evidence_collected'
  | 'claim_verified'
  | 'conflict_detected'
  | 'human_approval_required'
  | 'human_approved'
  | 'human_rejected'
  | 'task_completed'
  | 'task_failed'
  | 'task_cancelled';

export interface TraceEvent {
  id: string;
  task_id: string;
  timestamp: string;
  event_type: TraceEventType;
  node: string;
  tool?: string | null;
  status: 'info' | 'success' | 'warning' | 'error' | string;
  duration_ms?: number | null;
  details: Record<string, any>;
  error?: string | null;
  step_id?: number | null;
  attempt_number?: number | null;
  recovery_decision?: string | null;
}
