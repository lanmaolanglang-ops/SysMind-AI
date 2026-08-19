import type { ApiClient } from "./api-client";

export type DiagnosisStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial"
  | "cancelled"
  | "failed"
  | "interrupted";

export interface EvidenceReference {
  tool_call_id: string;
  field_path: string;
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
}

export interface Diagnosis {
  id: string;
  status: DiagnosisStatus;
  user_question: string;
  category: "performance" | "network" | "crash";
  provider: string;
  plan: Array<{ tool: string; purpose: string; arguments: Record<string, unknown> }>;
  progress: number;
  current_step: string | null;
  report: {
    summary: string;
    category: string;
    findings: DiagnosisFinding[];
    confidence: number;
    limitations: string[];
    model_explanation: string;
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
  }>;
}

export function startDiagnosis(client: ApiClient, question: string): Promise<Diagnosis> {
  return client.postJson<Diagnosis, { question: string }>("/api/v1/diagnoses", { question });
}

export function getDiagnosis(client: ApiClient, id: string, signal?: AbortSignal) {
  return client.get<Diagnosis>(`/api/v1/diagnoses/${id}`, signal);
}

export function recentDiagnoses(client: ApiClient, signal?: AbortSignal) {
  return client.get<{ items: Diagnosis[] }>("/api/v1/diagnoses", signal);
}

export function cancelDiagnosis(client: ApiClient, id: string) {
  return client.post<Diagnosis>(`/api/v1/diagnoses/${id}/cancel`);
}

export function submitDiagnosisFeedback(client: ApiClient, id: string, helpful: boolean) {
  return client.postJson<{ accepted: boolean }, { helpful: boolean }>(
    `/api/v1/diagnoses/${id}/feedback`,
    { helpful },
  );
}

export async function downloadDiagnosis(
  client: ApiClient,
  id: string,
  format: "json" | "markdown",
) {
  const blob = await client.download(`/api/v1/diagnoses/${id}/export?format=${format}`);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `sysmind-report-${id}.${format === "markdown" ? "md" : "json"}`;
  anchor.click();
  URL.revokeObjectURL(url);
}
