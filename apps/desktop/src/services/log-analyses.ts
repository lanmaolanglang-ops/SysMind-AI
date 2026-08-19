import type { ApiClient } from "./api-client";

export type EventLevel = "critical" | "error" | "warning" | "information";
export type LogChannel = "Application" | "System";
export type LogAnalysisStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial"
  | "cancelled"
  | "failed";

export interface StartLogAnalysisInput {
  channels: LogChannel[];
  lookback_hours: number;
  levels: EventLevel[];
  event_ids: number[];
  max_events: number;
}

export interface EventEvidence {
  channel: LogChannel;
  provider: string;
  event_id: number;
  level: EventLevel;
  timestamp: string;
  summary: string;
  application: string | null;
  faulting_module: string | null;
  exception_code: string | null;
}

export interface CrashGroup {
  application: string;
  faulting_module: string | null;
  exception_code: string | null;
  count: number;
  latest_at: string;
  evidence_event_ids: number[];
  providers: string[];
}

export interface LogAnalysisRecord {
  id: string;
  status: LogAnalysisStatus;
  progress: number;
  current_step: string | null;
  started_at: string;
  finished_at: string | null;
  query: StartLogAnalysisInput;
  summary: {
    event_count: number;
    events: EventEvidence[];
    event_groups: Array<{
      channel: LogChannel;
      provider: string;
      event_id: number;
      level: EventLevel;
      count: number;
      latest_at: string;
      sample_summary: string;
    }>;
    crash_groups: CrashGroup[];
    notice: string | null;
  } | null;
  failures: Array<{ tool: string; code: string; message: string }>;
  schema_version: string;
}

export function startLogAnalysis(
  client: ApiClient,
  input: StartLogAnalysisInput,
  signal?: AbortSignal,
): Promise<LogAnalysisRecord> {
  return client.postJson<LogAnalysisRecord, StartLogAnalysisInput>(
    "/api/v1/log-analyses",
    input,
    signal,
  );
}

export function getLogAnalysis(
  client: ApiClient,
  id: string,
  signal?: AbortSignal,
): Promise<LogAnalysisRecord> {
  return client.get<LogAnalysisRecord>(`/api/v1/log-analyses/${id}`, signal);
}

export function getRecentLogAnalyses(
  client: ApiClient,
  signal?: AbortSignal,
): Promise<{ items: LogAnalysisRecord[] }> {
  return client.get<{ items: LogAnalysisRecord[] }>("/api/v1/log-analyses", signal);
}

export function cancelLogAnalysis(
  client: ApiClient,
  id: string,
  signal?: AbortSignal,
): Promise<LogAnalysisRecord> {
  return client.post<LogAnalysisRecord>(`/api/v1/log-analyses/${id}/cancel`, signal);
}
