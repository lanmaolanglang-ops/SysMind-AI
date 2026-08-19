import type { ApiClient } from "./api-client";

export type ScanStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial"
  | "cancelled"
  | "failed";

export interface Capability {
  name: string;
  available: boolean;
  reason: string | null;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_bytes: number;
  memory_percent: number;
}

export interface ScanSummary {
  capabilities: Capability[];
  operating_system: {
    name: string;
    version: string;
    build: string;
    architecture: string;
  } | null;
  cpu: {
    model: string;
    physical_cores: number;
    logical_cores: number;
    utilization_percent: number;
    frequency_mhz: number | null;
  } | null;
  gpus: Array<{ name: string; memory_bytes: number | null; driver_version: string | null }>;
  memory: {
    total_bytes: number;
    available_bytes: number;
    used_bytes: number;
    utilization_percent: number;
  } | null;
  disks: Array<{
    volume: string;
    mountpoint: string;
    filesystem: string;
    total_bytes: number;
    free_bytes: number;
    used_bytes: number;
    utilization_percent: number;
  }>;
  processes: ProcessInfo[];
  high_usage_processes: ProcessInfo[];
}

export interface ScanRecord {
  id: string;
  status: ScanStatus;
  progress: number;
  current_step: string | null;
  started_at: string;
  finished_at: string | null;
  summary: ScanSummary | null;
  failures: Array<{ tool: string; code: string; message: string }>;
  schema_version: string;
}

export interface ScanListResponse {
  items: ScanRecord[];
}

export function startQuickScan(client: ApiClient, signal?: AbortSignal): Promise<ScanRecord> {
  return client.post<ScanRecord>("/api/v1/scans/quick", signal);
}

export function getScan(
  client: ApiClient,
  scanId: string,
  signal?: AbortSignal,
): Promise<ScanRecord> {
  return client.get<ScanRecord>(`/api/v1/scans/${scanId}`, signal);
}

export function getRecentScans(
  client: ApiClient,
  signal?: AbortSignal,
): Promise<ScanListResponse> {
  return client.get<ScanListResponse>("/api/v1/scans", signal);
}

export function cancelScan(
  client: ApiClient,
  scanId: string,
  signal?: AbortSignal,
): Promise<ScanRecord> {
  return client.post<ScanRecord>(`/api/v1/scans/${scanId}/cancel`, signal);
}
