export interface ApiClientOptions {
  baseUrl: string;
  sessionToken: string;
  timeoutMs?: number;
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

  async #request<T>(method: "GET" | "POST", path: string, signal?: AbortSignal): Promise<T> {
    const timeout = AbortSignal.timeout(this.#timeoutMs);
    const combinedSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
    const correlationId = crypto.randomUUID();

    try {
      const response = await fetch(`${this.#baseUrl}${path}`, {
        method,
        headers: {
          Accept: "application/json",
          "X-Correlation-ID": correlationId,
          "X-SysMind-Session": this.#sessionToken,
        },
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
}

