import type { ApiClient } from "./api-client";

export type DiagnosisStatus =
  | "queued"
  | "running"
  | "waiting_user_input"
  | "completed"
  | "partial"
  | "cancelled"
  | "failed"
  | "interrupted";

export interface EvidenceReference {
  tool_call_id: string;
  field_path: string;
}

export interface EvidenceDetail {
  tool_call_id: string;
  tool_name: string;
  tool_version: string;
  key_fields: Record<string, unknown>;
  raw_result_summary: Record<string, unknown>;
  observed_at: string | null;
}

export interface DiagnosisFinding {
  id: string;
  code: string;
  severity: "info" | "low" | "medium" | "high";
  title: string;
  explanation: string;
  recommendation: string;
  confidence: number;
  evidence: EvidenceReference[];
  evidence_details?: EvidenceDetail[];
}

export interface DiagnosisHypothesis {
  id: string;
  key: string;
  hypothesis: string;
  rationale: string;
  supporting_evidence: EvidenceReference[];
  contradicting_evidence: EvidenceReference[];
  supporting_evidence_details?: EvidenceDetail[];
  contradicting_evidence_details?: EvidenceDetail[];
  confidence: number;
  status: "active" | "confirmed" | "rejected" | "insufficient";
}

export interface Diagnosis {
  id: string;
  status: DiagnosisStatus;
  user_question: string;
  category: "performance" | "network" | "crash";
  provider: string;
  // `reason` is canonical; `purpose` is a compatibility alias kept during the
  // versioned plan-contract migration and will be removed in a later API version.
  plan: Array<{
    tool: string;
    reason?: string;
    purpose?: string;
    arguments: Record<string, unknown>;
  }>;
  diagnosis_plan?: {
    problem_category: "performance" | "network" | "crash";
    confidence: number;
    status: "ready" | "ask_user" | "complete";
    clarification_question: string | null;
    steps: Array<{
      tool: string;
      reason: string;
      purpose?: string;
      arguments: Record<string, unknown>;
    }>;
  } | null;
  agent_round_count: number;
  max_agent_rounds: number;
  max_tool_calls: number;
  stop_reason:
    | "evidence_sufficient"
    | "user_cancelled"
    | "insufficient_information"
    | "budget_exceeded"
    | "risk_limit_reached"
    | "backend_restarted"
    | "internal_error"
    | null;
  user_inputs: string[];
  progress: number;
  current_step: string | null;
  report: {
    summary: string;
    category: string;
    findings: DiagnosisFinding[];
    confidence: number;
    limitations: string[];
    model_explanation: string;
    hypotheses: DiagnosisHypothesis[];
  } | null;
  failure_message: string | null;
  created_at: string;
  completed_at: string | null;
  tool_calls: Array<{
    id: string;
    tool_name: string;
    tool_version: string;
    status: string;
    error_code: string | null;
    started_at?: string | null;
    finished_at?: string | null;
  }>;
}

export function startDiagnosis(
  client: ApiClient,
  question: string,
  signal?: AbortSignal,
): Promise<Diagnosis> {
  return client.postJson<Diagnosis, { question: string }>(
    "/api/v1/diagnoses",
    { question },
    signal,
  );
}

export function getDiagnosis(client: ApiClient, id: string, signal?: AbortSignal) {
  return client.get<Diagnosis>(`/api/v1/diagnoses/${id}`, signal);
}

export function recentDiagnoses(client: ApiClient, signal?: AbortSignal) {
  return client.get<{ items: Diagnosis[] }>("/api/v1/diagnoses", signal);
}

export function cancelDiagnosis(client: ApiClient, id: string, signal?: AbortSignal) {
  return client.post<Diagnosis>(`/api/v1/diagnoses/${id}/cancel`, signal);
}

export function continueDiagnosis(
  client: ApiClient,
  id: string,
  answer: string,
  signal?: AbortSignal,
) {
  return client.postJson<Diagnosis, { answer: string }>(
    `/api/v1/diagnoses/${id}/inputs`,
    { answer },
    signal,
  );
}

export function submitDiagnosisFeedback(
  client: ApiClient,
  id: string,
  helpful: boolean,
  signal?: AbortSignal,
) {
  return client.postJson<{ accepted: boolean }, { helpful: boolean }>(
    `/api/v1/diagnoses/${id}/feedback`,
    { helpful },
    signal,
  );
}

export function fetchDiagnosisExport(
  client: ApiClient,
  id: string,
  format: "json" | "markdown",
): Promise<Blob> {
  return client.download(`/api/v1/diagnoses/${id}/export?format=${format}`);
}
