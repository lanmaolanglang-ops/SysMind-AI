import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "../../services/api-client";
import type { Diagnosis } from "../../services/diagnoses";
import { DiagnosisPanel } from "./DiagnosisPanel";

function api() {
  return new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test-token" });
}

function report(id = "diagnosis-1"): Diagnosis {
  return {
    id,
    status: "completed",
    user_question: "电脑很卡",
    category: "performance",
    provider: "local-rules",
    plan: [{ tool: "system.cpu@1.0", purpose: "采集 CPU 状态", arguments: {} }],
    progress: 100,
    current_step: null,
    report: {
      summary: "CPU 当前负载很高",
      category: "performance",
      confidence: 0.9,
      model_explanation: "CPU 证据达到本地规则阈值。",
      limitations: [],
      findings: [
        {
          id: "finding-1",
          code: "cpu_pressure",
          severity: "high",
          title: "CPU 当前负载很高",
          explanation: "采样利用率为 92%。",
          recommendation: "关闭非必要高占用应用后复测。",
          confidence: 0.9,
          evidence: [{ tool_call_id: "tool-call-123456", field_path: "$.utilization_percent" }],
        },
      ],
    },
    failure_message: null,
    created_at: "2026-08-19T10:00:00Z",
    completed_at: "2026-08-19T10:00:01Z",
    tool_calls: [
      {
        id: "tool-call-123456",
        tool_name: "system.cpu",
        tool_version: "1.0",
        status: "completed",
        error_code: null,
      },
    ],
  };
}

describe("DiagnosisPanel", () => {
  it("renders evidence-bound findings and export controls", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({ items: [report()] });
    render(<DiagnosisPanel client={client} />);

    expect(await screen.findAllByText("CPU 当前负载很高")).toHaveLength(2);
    expect(screen.getByText(/system\.cpu@1\.0 · \$\.utilization_percent/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeInTheDocument();
    expect(screen.getByText(/不会自动修复/)).toBeInTheDocument();
  });

  it("starts a natural-language diagnosis and discloses bounded network traffic", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({ items: [] });
    const post = vi.spyOn(client, "postJson").mockResolvedValue({ ...report(), status: "queued" });
    render(<DiagnosisPanel client={client} />);

    expect(await screen.findByText(/固定测试域名和公共 IP/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("问题描述"), { target: { value: "应用总是崩溃" } });
    fireEvent.click(screen.getByRole("button", { name: "开始诊断" }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith("/api/v1/diagnoses", { question: "应用总是崩溃" });
    });
  });

  it("prevents duplicate feedback while a submission is pending", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({ items: [report()] });
    const post = vi.spyOn(client, "postJson").mockImplementation(() => new Promise(() => {}));
    render(<DiagnosisPanel client={client} />);

    const helpful = await screen.findByRole("button", { name: "有帮助" });
    fireEvent.click(helpful);
    fireEvent.click(helpful);

    expect(post).toHaveBeenCalledTimes(1);
    expect(helpful).toBeDisabled();
  });

  it("keeps pending feedback locked independently across history reports", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({ items: [report("diagnosis-a"), report("diagnosis-b")] });
    const post = vi.spyOn(client, "postJson").mockImplementation(() => new Promise(() => {}));
    render(<DiagnosisPanel client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "有帮助" }));
    const history = screen.getByLabelText("最近报告");
    fireEvent.change(history, { target: { value: "diagnosis-b" } });
    fireEvent.click(screen.getByRole("button", { name: "有帮助" }));
    fireEvent.change(history, { target: { value: "diagnosis-a" } });

    expect(screen.getByRole("button", { name: "有帮助" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "有帮助" }));
    expect(post).toHaveBeenCalledTimes(2);
  });
});
