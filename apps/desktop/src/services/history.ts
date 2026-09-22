import type { ApiClient } from "./api-client";

export type DeletableHistoryKind = "scan" | "diagnosis" | "log";

export interface DeletionImpact {
  kind: DeletableHistoryKind;
  record_id: string;
  revision: string;
  deletable: boolean;
  dependent_records: number;
  protected_reason: string | null;
}

export interface BaselineMetric {
  metric: "cpu_percent" | "memory_percent" | "disk_peak_percent";
  samples: number;
  median: number;
  latest: number;
  delta: number;
}

export interface CleanupResult {
  deleted_scans: number;
  deleted_diagnoses: number;
  deleted_log_analyses: number;
  protected_records: number;
  completed_at: string;
}

export const getDeletionImpact = (
  client: ApiClient,
  kind: DeletableHistoryKind,
  id: string,
  signal?: AbortSignal,
) => client.get<DeletionImpact>(`/api/v1/history/${kind}/${id}/deletion-impact`, signal);

export const deleteHistory = (
  client: ApiClient,
  impact: DeletionImpact,
  signal?: AbortSignal,
) => client.postJson<{ deleted: boolean }, { revision: string }>(
  `/api/v1/history/${impact.kind}/${impact.record_id}/delete`,
  { revision: impact.revision },
  signal,
);

export const getBaseline = (client: ApiClient, signal?: AbortSignal) =>
  client.get<{ items: BaselineMetric[] }>("/api/v1/history/baseline", signal);

export const getRetention = (client: ApiClient, signal?: AbortSignal) =>
  client.get<{ retention_days: number }>("/api/v1/history/retention", signal);

export const saveRetention = (client: ApiClient, retentionDays: number, signal?: AbortSignal) =>
  client.putJson<{ retention_days: number }, { retention_days: number }>(
    "/api/v1/history/retention", { retention_days: retentionDays }, signal,
  );

export const runCleanup = (client: ApiClient, signal?: AbortSignal) =>
  client.postJson<CleanupResult, { confirm: "cleanup" }>(
    "/api/v1/history/cleanup",
    { confirm: "cleanup" },
    signal,
  );
