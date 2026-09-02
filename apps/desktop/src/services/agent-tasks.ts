import type { ApiClient, SseEvent } from "./api-client";

const MAX_RECONNECT_DELAY_MS = 5_000;

export function agentTaskReconnectDelay(failedAttempts: number): number {
  return Math.min(350 * 2 ** Math.max(0, failedAttempts - 1), MAX_RECONNECT_DELAY_MS);
}

export type AgentTaskStatus =
  | "created"
  | "planning"
  | "running_tools"
  | "analyzing"
  | "waiting_user_input"
  | "completed"
  | "cancelling"
  | "cancelled"
  | "failed"
  | "timed_out"
  | "interrupted";

export interface ToolDescriptor {
  name: string;
  version: string;
  qualified_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  risk_level: string;
  sensitivity: string[];
}

export interface AgentTask {
  id: string;
  status: AgentTaskStatus;
  user_goal: string;
  provider: string;
  allowed_tools: string[];
  budget: {
    max_rounds: number;
    max_tool_calls: number;
    timeout_seconds: number;
    max_parallel_tools: number;
  };
  current_round: number;
  tool_call_count: number;
  progress: number;
  final_output: string | null;
  failure_code: string | null;
  failure_message: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  schema_version: string;
  tool_calls: Array<{
    id: string;
    tool_name: string;
    tool_version: string;
    status: string;
    duration_ms: number | null;
    result_summary: Record<string, unknown> | null;
    error_code: string | null;
    error_message: string | null;
  }>;
}

export interface AgentTaskEventData {
  status?: AgentTaskStatus;
  progress?: number;
  tool?: string;
  action?: string;
  message?: string;
  error_code?: string;
  created_at: string;
}

export function getToolCatalog(
  client: ApiClient,
  signal?: AbortSignal,
): Promise<{ items: ToolDescriptor[] }> {
  return client.get<{ items: ToolDescriptor[] }>("/api/v1/tasks/tools", signal);
}

export function startAgentTask(
  client: ApiClient,
  userGoal: string,
  allowedTools: string[],
  signal?: AbortSignal,
): Promise<AgentTask> {
  return client.postJson<AgentTask, Record<string, unknown>>(
    "/api/v1/tasks",
    { user_goal: userGoal, allowed_tools: allowedTools },
    signal,
  );
}

export function getAgentTask(
  client: ApiClient,
  taskId: string,
  signal?: AbortSignal,
): Promise<AgentTask> {
  return client.get<AgentTask>(`/api/v1/tasks/${taskId}`, signal);
}

export function getRecentAgentTasks(
  client: ApiClient,
  signal?: AbortSignal,
): Promise<{ items: AgentTask[] }> {
  return client.get<{ items: AgentTask[] }>("/api/v1/tasks", signal);
}

export function cancelAgentTask(
  client: ApiClient,
  taskId: string,
  signal?: AbortSignal,
): Promise<AgentTask> {
  return client.post<AgentTask>(`/api/v1/tasks/${taskId}/cancel`, signal);
}

export function streamAgentTaskEvents(
  client: ApiClient,
  taskId: string,
  onEvent: (event: SseEvent<AgentTaskEventData>) => void,
  signal?: AbortSignal,
  lastEventId?: string,
): Promise<void> {
  return client.streamSse(
    `/api/v1/tasks/${taskId}/events`,
    onEvent,
    signal,
    lastEventId,
  );
}
