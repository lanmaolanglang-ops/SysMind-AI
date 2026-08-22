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
) {
  return client.putJson<ProviderSettings, typeof value>("/api/v1/settings", value);
}

export function testProvider(client: ApiClient) {
  return client.post<{ succeeded: boolean; error_code: string | null; duration_ms: number }>(
    "/api/v1/providers/test",
  );
}

export function clearProviderCredential(client: ApiClient) {
  return client.delete<ProviderSettings>("/api/v1/settings/credential");
}
