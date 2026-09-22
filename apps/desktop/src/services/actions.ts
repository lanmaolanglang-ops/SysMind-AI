import type { ApiClient } from "./api-client";

export interface StartupActionCandidate {
  item_id: string;
  name: string;
  source_kind: "user_run" | "user_startup";
  command_name: string | null;
  observed_revision: string;
}

export interface ProcessActionCandidate {
  item_id: string;
  name: string;
  source_kind: "current_user_process";
  command_name: string | null;
  observed_revision: string;
  cpu_percent: number;
  memory_percent: number;
}

export interface ControlledAction {
  id: string;
  diagnosis_id: string;
  tool_name:
    | "startup.disable_current_user"
    | "startup.restore_current_user"
    | "process.request_close_current_user"
    | "process.terminate_current_user";
  target_name: string;
  source_kind: string;
  status: string;
  recovery_available: boolean;
  error_code: string | null;
  error_message: string | null;
}

export function actionCandidates(client: ApiClient, diagnosisId: string) {
  return client.get<{ items: StartupActionCandidate[] }>(
    `/api/v1/actions/candidates?diagnosis_id=${encodeURIComponent(diagnosisId)}`,
  );
}

export function createDisableAction(
  client: ApiClient,
  diagnosisId: string,
  candidate: StartupActionCandidate,
  signal?: AbortSignal,
) {
  return client.postJson<ControlledAction, Record<string, string>>(
    "/api/v1/actions",
    {
      diagnosis_id: diagnosisId,
      item_id: candidate.item_id,
      observed_revision: candidate.observed_revision,
    },
    signal,
  );
}

export function processActionCandidates(client: ApiClient, diagnosisId: string) {
  return client.get<{ items: ProcessActionCandidate[] }>(
    `/api/v1/actions/process-candidates?diagnosis_id=${encodeURIComponent(diagnosisId)}`,
  );
}

export function createProcessCloseAction(
  client: ApiClient,
  diagnosisId: string,
  candidate: ProcessActionCandidate,
  signal?: AbortSignal,
) {
  return client.postJson<ControlledAction, Record<string, string>>(
    "/api/v1/actions/process-close",
    {
      diagnosis_id: diagnosisId,
      item_id: candidate.item_id,
      observed_revision: candidate.observed_revision,
    },
    signal,
  );
}

export function createProcessTermination(
  client: ApiClient,
  closeActionId: string,
  signal?: AbortSignal,
) {
  return client.post<ControlledAction>(
    `/api/v1/actions/${encodeURIComponent(closeActionId)}/termination`,
    signal,
  );
}

export function createRecoveryAction(client: ApiClient, actionId: string, signal?: AbortSignal) {
  return client.post<ControlledAction>(
    `/api/v1/actions/${encodeURIComponent(actionId)}/recovery`,
    signal,
  );
}

export function rejectAction(client: ApiClient, actionId: string, signal?: AbortSignal) {
  return client.post<ControlledAction>(
    `/api/v1/actions/${encodeURIComponent(actionId)}/reject`,
    signal,
  );
}

export function getAction(client: ApiClient, actionId: string, signal?: AbortSignal) {
  return client.get<ControlledAction>(
    `/api/v1/actions/${encodeURIComponent(actionId)}`,
    signal,
  );
}

export function recentActions(client: ApiClient, signal?: AbortSignal) {
  return client.get<{ items: ControlledAction[] }>("/api/v1/actions", signal);
}

export async function confirmAndExecute(
  client: ApiClient,
  action: ControlledAction,
  signal?: AbortSignal,
) {
  const actionPath = `/api/v1/actions/${encodeURIComponent(action.id)}`;
  const consent = await client.post<{
    action: ControlledAction;
    ticket: string | null;
    expires_at: string | null;
  }>(`${actionPath}/confirm`, signal);
  if (!consent.ticket) return consent.action;
  return client.postJson<ControlledAction, { ticket: string }>(
    `${actionPath}/execute`,
    { ticket: consent.ticket },
    signal,
    12_000,
  );
}
