import { invoke } from "@tauri-apps/api/core";

import { ApiClient, ApiClientError } from "./api-client";
import { EXPECTED_API_VERSION } from "./generated-version";

export type { components } from "./openapi-types";
export { EXPECTED_API_VERSION, PRODUCT_VERSION } from "./generated-version";

export interface BackendEndpoint {
  base_url: string;
  session_token: string;
  api_version: string;
}

export interface BackendSnapshot {
  state: "starting" | "connected" | "disconnected";
  endpoint: BackendEndpoint | null;
  error: string | null;
}

export interface HealthResponse {
  status: "ok";
  backend_version: string;
  api_version: string;
  ready: boolean;
}

export interface BackendConnection {
  endpoint: BackendEndpoint;
  health: HealthResponse;
  client: ApiClient;
}

export class BackendConnectionError extends Error {
  readonly code: string;
  readonly correlationId?: string;

  constructor(code: string, message: string, correlationId?: string) {
    super(message);
    this.name = "BackendConnectionError";
    this.code = code;
    if (correlationId !== undefined) this.correlationId = correlationId;
  }
}

export async function restartBackendLauncher(): Promise<void> {
  await invoke<BackendSnapshot>("restart_backend");
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve();
      return;
    }
    const onAbort = () => resolve();
    signal?.addEventListener("abort", onAbort, { once: true });
    window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
  });
}

async function waitForEndpoint(signal?: AbortSignal): Promise<BackendEndpoint> {
  const deadline = Date.now() + 12_000;

  while (Date.now() < deadline) {
    if (signal?.aborted) {
      throw new BackendConnectionError("connection_cancelled", "连接已取消。");
    }

    let snapshot: BackendSnapshot | null = null;
    // The Tauri launcher can briefly fail to answer while the backend process is
    // still attaching; retry a few times before declaring the launcher unavailable.
    for (let attempt = 0; attempt < 3 && snapshot === null; attempt += 1) {
      try {
        snapshot = await invoke<BackendSnapshot>("backend_status");
      } catch {
        if (attempt === 2) {
          throw new BackendConnectionError(
            "launcher_unavailable",
            "无法读取本地后端启动状态。",
          );
        }
        await delay(200, signal);
      }
    }
    if (snapshot === null) {
      throw new BackendConnectionError(
        "launcher_unavailable",
        "无法读取本地后端启动状态。",
      );
    }

    if (snapshot.state === "connected" && snapshot.endpoint) return snapshot.endpoint;
    if (snapshot.state === "disconnected") {
      throw new BackendConnectionError(
        "backend_startup_failed",
        snapshot.error ?? "本地后端启动失败。",
      );
    }

    // Abort-aware wait so unmounting a component cancels the pending poll immediately.
    await delay(150, signal);
  }

  throw new BackendConnectionError(
    "backend_startup_timeout",
    "本地后端启动超时，请检查开发环境或重启应用。",
  );
}

export async function connectToBackend(signal?: AbortSignal): Promise<BackendConnection> {
  const endpoint = await waitForEndpoint(signal);
  if (endpoint.api_version !== EXPECTED_API_VERSION) {
    throw new BackendConnectionError(
      "api_version_mismatch",
      `桌面端需要 API ${EXPECTED_API_VERSION}，当前后端为 ${endpoint.api_version}。`,
    );
  }

  const client = new ApiClient({
    baseUrl: endpoint.base_url,
    sessionToken: endpoint.session_token,
  });

  try {
    const health = await client.get<HealthResponse>("/health", signal);
    if (!health.ready || health.api_version !== EXPECTED_API_VERSION) {
      throw new BackendConnectionError(
        "api_version_mismatch",
        `本地后端尚未就绪或协议版本不兼容（${health.api_version}）。`,
      );
    }
    return { endpoint, health, client };
  } catch (error: unknown) {
    if (error instanceof BackendConnectionError) throw error;
    if (error instanceof ApiClientError) {
      throw new BackendConnectionError(error.code, error.message, error.correlationId);
    }
    throw error;
  }
}
