import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "./api-client";
import { confirmAndExecute, type ControlledAction } from "./actions";

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

  it("parses SSE frames when CRLF separators cross stream chunks", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("id: 8\r"));
        controller.enqueue(encoder.encode("\nevent: task.status\r"));
        controller.enqueue(encoder.encode('\ndata: {"status":"completed"}\r'));
        controller.enqueue(encoder.encode("\n\r"));
        controller.enqueue(encoder.encode("\n"));
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(stream, { status: 200 })),
    );
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:45000",
      sessionToken: "temporary-session",
    });
    const events: Array<{ id: string | null; event: string; data: { status: string } }> = [];

    await client.streamSse<{ status: string }>("/api/v1/tasks/task-1/events", (event) =>
      events.push(event),
    );

    expect(events).toEqual([{ id: "8", event: "task.status", data: { status: "completed" } }]);
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

  it("waits through the bounded process close before timing out its execution request", async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout");
    const action: ControlledAction = {
      id: "action-1",
      diagnosis_id: "diagnosis-1",
      tool_name: "process.request_close_current_user",
      target_name: "Editor",
      source_kind: "current_user_process",
      status: "proposed",
      recovery_available: false,
      error_code: null,
      error_message: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ action, ticket: "ticket" })))
        .mockResolvedValueOnce(new Response(JSON.stringify({ ...action, status: "close_pending" }))),
    );
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:45000",
      sessionToken: "temporary-session",
    });

    await expect(confirmAndExecute(client, action)).resolves.toMatchObject({
      status: "close_pending",
    });
    expect(timeoutSpy).toHaveBeenLastCalledWith(12_000);
    timeoutSpy.mockRestore();
  });
});
