import type { ApiClient } from "./api-client";

export interface ProviderSettings {
  provider: string;
  model: string;
  endpoint: string;
  configured: boolean;
  updated_at: string | null;
  restart_required: boolean;
}

export function getProviderSettings(client: ApiClient, signal?: AbortSignal) {
  return client.get<ProviderSettings>("/api/v1/settings", signal);
}

export function saveProviderSettings(
  client: ApiClient,
  value: { provider: string; model: string; endpoint: string; api_key?: string },
  signal?: AbortSignal,
) {
  return client.putJson<ProviderSettings, typeof value>("/api/v1/settings", value, signal);
}

export function testProvider(client: ApiClient, signal?: AbortSignal) {
  return client.post<{ succeeded: boolean; error_code: string | null; duration_ms: number }>(
    "/api/v1/providers/test",
    signal,
  );
}

export function clearProviderCredential(client: ApiClient, signal?: AbortSignal) {
  return client.delete<ProviderSettings>("/api/v1/settings/credential", signal);
}
