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

  it("serializes bounded JSON request bodies", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "analysis-1" }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:45000",
      sessionToken: "temporary-session",
    });

    await client.postJson("/api/v1/log-analyses", { lookback_hours: 24 });

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(request.body).toBe(JSON.stringify({ lookback_hours: 24 }));
  });

  it("parses SSE frames and sends the reconnect cursor", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("id: 7\r\nevent: task.status\r\n"));
        controller.enqueue(
          encoder.encode('data: {"status":"planning","created_at":"2026-08-19T10:00:00Z"}\r\n\r\n'),
        );
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:45000",
      sessionToken: "temporary-session",
    });
    const events: Array<{ id: string | null; event: string }> = [];

    await client.streamSse("/api/v1/tasks/task-1/events", (event) => events.push(event), undefined, "6");

    expect(events).toMatchObject([{ id: "7", event: "task.status" }]);
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.headers).toMatchObject({ "Last-Event-ID": "6" });
  });

  it("downloads reports with the in-memory session header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("# report", { status: 200, headers: { "Content-Type": "text/markdown" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:45000",
      sessionToken: "temporary-session",
    });

    await expect(client.download("/api/v1/diagnoses/d-1/export?format=markdown")).resolves.toBeInstanceOf(Blob);
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.headers).toMatchObject({ "X-SysMind-Session": "temporary-session" });
  });
});
