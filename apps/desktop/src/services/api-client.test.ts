import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "./api-client";

describe("ApiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the in-memory session and a correlation id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:45000/",
      sessionToken: "temporary-session",
    });

    await client.get("/health");

    expect(fetchMock).toHaveBeenCalledOnce();
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.headers).toMatchObject({
      "X-SysMind-Session": "temporary-session",
    });
    expect((request.headers as Record<string, string>)["X-Correlation-ID"]).toBeTruthy();
  });

  it("normalizes structured API failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "invalid_session", message: "Invalid session", correlation_id: "c-1" },
          }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:45000",
      sessionToken: "temporary-session",
    });

    await expect(client.get("/health")).rejects.toMatchObject({
      code: "invalid_session",
      status: 401,
      correlationId: "c-1",
    });
  });

  it("supports authenticated POST requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "scan-1" }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:45000",
      sessionToken: "temporary-session",
    });

    await expect(client.post<{ id: string }>("/api/v1/scans/quick")).resolves.toEqual({
      id: "scan-1",
    });
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "POST" });
  });
});
