export interface ApiClientOptions {
  baseUrl: string;
  sessionToken: string;
  timeoutMs?: number;
}

export interface SseEvent<TData = Record<string, unknown>> {
  id: string | null;
  event: string;
  data: TData;
}

interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    correlation_id?: string;
  };
}

export class ApiClientError extends Error {
  readonly code: string;
  readonly status?: number;
  readonly correlationId?: string;

  constructor(
    code: string,
    message: string,
    options: { status?: number; correlationId?: string; cause?: unknown } = {},
  ) {
    super(message, options.cause ? { cause: options.cause } : undefined);
    this.name = "ApiClientError";
    this.code = code;
    if (options.status !== undefined) this.status = options.status;
    if (options.correlationId !== undefined) this.correlationId = options.correlationId;
  }
}

export class ApiClient {
  readonly #baseUrl: string;
  readonly #sessionToken: string;
  readonly #timeoutMs: number;

  constructor(options: ApiClientOptions) {
    this.#baseUrl = options.baseUrl.replace(/\/$/, "");
    this.#sessionToken = options.sessionToken;
    this.#timeoutMs = options.timeoutMs ?? 5_000;
  }

  async get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return this.#request<T>("GET", path, signal);
  }

  async post<T>(path: string, signal?: AbortSignal): Promise<T> {
    return this.#request<T>("POST", path, signal);
  }

  async postJson<T, TBody>(path: string, body: TBody, signal?: AbortSignal): Promise<T> {
    return this.#request<T>("POST", path, signal, body);
  }

  async download(path: string, signal?: AbortSignal): Promise<Blob> {
    const timeout = AbortSignal.timeout(this.#timeoutMs);
    const combinedSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
    const response = await fetch(`${this.#baseUrl}${path}`, {
      headers: {
        Accept: "application/octet-stream",
        "X-Correlation-ID": crypto.randomUUID(),
        "X-SysMind-Session": this.#sessionToken,
      },
      signal: combinedSignal,
    });
    if (!response.ok) {
      throw new ApiClientError("download_error", "Report export was unavailable.", {
        status: response.status,
      });
    }
    return response.blob();
  }

  async streamSse<TData>(
    path: string,
    onEvent: (event: SseEvent<TData>) => void,
    signal?: AbortSignal,
    lastEventId?: string,
  ): Promise<void> {
    const correlationId = crypto.randomUUID();
    let response: Response;
    try {
      response = await fetch(`${this.#baseUrl}${path}`, {
        method: "GET",
        headers: {
          Accept: "text/event-stream",
          "X-Correlation-ID": correlationId,
          "X-SysMind-Session": this.#sessionToken,
          ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
        },
        ...(signal ? { signal } : {}),
      });
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      throw new ApiClientError("sse_connection_error", "Task event stream disconnected.", {
        correlationId,
        cause: error,
      });
    }
    if (!response.ok || !response.body) {
      throw new ApiClientError("sse_http_error", "Task event stream was unavailable.", {
        status: response.status,
        correlationId: response.headers.get("X-Correlation-ID") ?? correlationId,
      });
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = this.#parseSseBlock<TData>(block);
        if (parsed) onEvent(parsed);
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
  }

  async #request<T>(
    method: "GET" | "POST",
    path: string,
    signal?: AbortSignal,
    body?: unknown,
  ): Promise<T> {
    const timeout = AbortSignal.timeout(this.#timeoutMs);
    const combinedSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
    const correlationId = crypto.randomUUID();

    try {
      const response = await fetch(`${this.#baseUrl}${path}`, {
        method,
        headers: {
          Accept: "application/json",
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          "X-Correlation-ID": correlationId,
          "X-SysMind-Session": this.#sessionToken,
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: combinedSignal,
      });
      const responseCorrelationId = response.headers.get("X-Correlation-ID") ?? correlationId;

      if (!response.ok) {
        let body: ApiErrorBody = {};
        try {
          body = (await response.json()) as ApiErrorBody;
        } catch {
          // A stable local error is more useful than exposing an arbitrary response body.
        }
        throw new ApiClientError(
          body.error?.code ?? "http_error",
          body.error?.message ?? `Local API request failed with status ${response.status}.`,
          {
            status: response.status,
            correlationId: body.error?.correlation_id ?? responseCorrelationId,
          },
        );
      }

      return (await response.json()) as T;
    } catch (error: unknown) {
      if (error instanceof ApiClientError) throw error;
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiClientError("request_cancelled", "Local API request was cancelled.", {
          correlationId,
          cause: error,
        });
      }
      if (error instanceof DOMException && error.name === "TimeoutError") {
        throw new ApiClientError("request_timeout", "Local API did not respond in time.", {
          correlationId,
          cause: error,
        });
      }
      throw new ApiClientError("network_error", "Could not reach the local API.", {
        correlationId,
        cause: error,
      });
    }
  }

  #parseSseBlock<TData>(block: string): SseEvent<TData> | null {
    if (!block || block.startsWith(":")) return null;
    let id: string | null = null;
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("id:")) id = line.slice(3).trimStart();
      if (line.startsWith("event:")) event = line.slice(6).trimStart();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return null;
    try {
      return { id, event, data: JSON.parse(data.join("\n")) as TData };
    } catch (error: unknown) {
      throw new ApiClientError("sse_protocol_error", "Task event stream sent invalid JSON.", {
        cause: error,
      });
    }
  }
}
