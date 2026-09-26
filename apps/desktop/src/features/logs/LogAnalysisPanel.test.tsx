import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "../../services/api-client";
import type { LogAnalysisRecord } from "../../services/log-analyses";
import { LogAnalysisPanel } from "./LogAnalysisPanel";

function client(): ApiClient {
  return new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test-token" });
}

function record(status: LogAnalysisRecord["status"]): LogAnalysisRecord {
  return {
    id: "analysis-1",
    status,
    progress: status === "completed" || status === "partial" ? 100 : 25,
    current_step: status === "running" ? "log.windows_event.query:Application" : null,
    started_at: "2026-08-19T10:00:00Z",
    finished_at: status === "completed" || status === "partial" ? "2026-08-19T10:00:02Z" : null,
    query: {
      channels: ["Application", "System"],
      lookback_hours: 24,
      levels: ["critical", "error", "warning"],
      event_ids: [],
      max_events: 100,
    },
    summary:
      status === "completed" || status === "partial"
        ? {
            event_count: 2,
            notice: "已脱敏",
            event_groups: [
              {
                channel: "Application",
                provider: "Application Error",
                event_id: 1000,
                level: "error",
                count: 2,
                latest_at: "2026-08-19T10:00:00Z",
                sample_summary: "demo.exe stopped working",
              },
            ],
            crash_groups: [
              {
                application: "demo.exe",
                faulting_module: "KERNELBASE.dll",
                exception_code: "0xc0000005",
                count: 2,
                latest_at: "2026-08-19T10:00:00Z",
                evidence_event_ids: [1000, 1001],
                providers: ["Application Error", "Windows Error Reporting"],
              },
            ],
            events: [
              {
                channel: "Application",
                provider: "Application Error",
                event_id: 1000,
                level: "error",
                timestamp: "2026-08-19T10:00:00Z",
                summary: "demo.exe · KERNELBASE.dll · 0xc0000005",
                application: "demo.exe",
                faulting_module: "KERNELBASE.dll",
                exception_code: "0xc0000005",
              },
            ],
          }
        : null,
    failures:
      status === "partial"
        ? [
            {
              tool: "log.windows_event.query:System",
              code: "permission_required",
              message: "当前账户无权读取系统日志。",
            },
          ]
        : [],
    schema_version: "1.0",
  };
}

describe("LogAnalysisPanel", () => {
  it("renders redacted crash groups and partial channel failures", async () => {
    const api = client();
    vi.spyOn(api, "get").mockResolvedValue({ items: [record("partial")] });

    render(<LogAnalysisPanel client={api} />);

    expect(await screen.findByText("demo.exe")).toBeInTheDocument();
    expect(screen.getAllByText(/KERNELBASE.dll/)).toHaveLength(2);
    expect(screen.getByText("当前账户无权读取系统日志。")).toBeInTheDocument();
    expect(screen.getAllByText(/ID 1000/)).toHaveLength(2);
  });

  it("sends only the selected bounded filters", async () => {
    const api = client();
    vi.spyOn(api, "get").mockResolvedValue({ items: [] });
    const postJson = vi.spyOn(api, "postJson").mockResolvedValue(record("running"));

    render(<LogAnalysisPanel client={api} />);
    await screen.findByRole("button", { name: "开始分析" });
    fireEvent.click(screen.getByLabelText("系统"));
    fireEvent.change(screen.getByLabelText("时间范围"), { target: { value: "72" } });
    fireEvent.change(screen.getByLabelText("事件 ID（可选）"), {
      target: { value: "1000, 1001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始分析" }));

    await waitFor(() => {
      expect(postJson).toHaveBeenCalledWith(
        "/api/v1/log-analyses",
        expect.objectContaining({
          channels: ["Application"],
          lookback_hours: 72,
          event_ids: [1000, 1001],
          max_events: 100,
        }),
        undefined,
      );
    });
  });

  it("rejects an invalid event ID instead of silently widening the query", async () => {
    const api = client();
    vi.spyOn(api, "get").mockResolvedValue({ items: [] });
    const postJson = vi.spyOn(api, "postJson").mockResolvedValue(record("running"));

    render(<LogAnalysisPanel client={api} />);
    fireEvent.change(screen.getByLabelText("事件 ID（可选）"), {
      target: { value: "1000, abc" },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("事件 ID");
    expect(screen.getByRole("button", { name: "开始分析" })).toBeDisabled();
    expect(postJson).not.toHaveBeenCalled();
  });
});
