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
    agent_round_count: 2,
    max_agent_rounds: 4,
    max_tool_calls: 8,
    stop_reason: "evidence_sufficient",
    user_inputs: [],
    progress: 100,
    current_step: null,
    report: {
      summary: "CPU 当前负载很高",
      category: "performance",
      confidence: 0.9,
      model_explanation: "CPU 证据达到本地规则阈值。",
      limitations: [],
      hypotheses: [
        {
          id: "hypothesis-1",
          key: "cpu_pressure",
          hypothesis: "CPU 压力导致卡顿",
          rationale: "CPU 利用率达到本地规则阈值。",
          supporting_evidence: [
            { tool_call_id: "tool-call-123456", field_path: "$.utilization_percent" },
          ],
          contradicting_evidence: [],
          supporting_evidence_details: [
            {
              tool_call_id: "tool-call-123456",
              tool_name: "system.cpu",
              tool_version: "1.0",
              key_fields: { "$.utilization_percent": 92 },
              raw_result_summary: { utilization_percent: 92 },
              observed_at: "2026-08-19T10:00:01Z",
            },
          ],
          contradicting_evidence_details: [],
          confidence: 0.9,
          status: "confirmed",
        },
      ],
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
          evidence_details: [
            {
              tool_call_id: "tool-call-123456",
              tool_name: "system.cpu",
              tool_version: "1.0",
              key_fields: { "$.utilization_percent": 92 },
              raw_result_summary: { utilization_percent: 92 },
              observed_at: "2026-08-19T10:00:01Z",
            },
          ],
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
        started_at: "2026-08-19T10:00:00Z",
        finished_at: "2026-08-19T10:00:01Z",
      },
    ],
  };
}

describe("DiagnosisPanel", () => {
  it("renders evidence-bound findings and export controls", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({ items: [report()] });
    render(<DiagnosisPanel client={client} />);

    fireEvent.change(await screen.findByLabelText("查看以前的问题"), {
      target: { value: "diagnosis-1" },
    });
    expect(await screen.findAllByText("CPU 当前负载很高")).toHaveLength(2);
    expect(screen.getAllByText(/system\.cpu@1\.0 · \$\.utilization_percent/)).toHaveLength(2);
    expect(screen.getAllByText("CPU 状态")).toHaveLength(2);
    expect(screen.getAllByText("使用率")).toHaveLength(2);
    expect(screen.getAllByText("92%")).toHaveLength(2);
    expect(document.querySelectorAll(".evidence-summary time")).toHaveLength(2);
    expect(screen.getByText("为什么怀疑：", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "发现的问题" })).toBeInTheDocument();
    expect(screen.getByText(/已有证据支持 · 90%/)).toBeInTheDocument();
    expect(screen.getByText("已有本机证据支持以下结论。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存易读报告" })).toBeInTheDocument();
    expect(screen.getByText("判断把握较高")).toBeInTheDocument();
  });

  it("starts a natural-language diagnosis and discloses bounded network traffic", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({ items: [] });
    const post = vi.spyOn(client, "postJson").mockResolvedValue({ ...report(), status: "queued" });
    render(<DiagnosisPanel client={client} />);

    expect(await screen.findByText(/少量固定测试地址/)).toBeInTheDocument();
    expect(screen.getByLabelText("描述现象")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "某个软件总是闪退" }));
    expect(screen.getByLabelText("描述现象")).toHaveValue("某个软件总是闪退");
    fireEvent.change(screen.getByLabelText("描述现象"), { target: { value: "应用总是崩溃" } });
    fireEvent.click(screen.getByRole("button", { name: "开始诊断" }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith("/api/v1/diagnoses", { question: "应用总是崩溃" }, undefined);
    });
  });

  it("keeps new diagnosis available and retries when report history cannot load", async () => {
    const client = api();
    const get = vi.spyOn(client, "get")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ items: [] });
    render(<DiagnosisPanel client={client} />);

    expect(screen.getByRole("heading", { name: "我的电脑有什么问题？" })).toBeInTheDocument();
    expect(await screen.findByText(/仍然可以开始新的诊断/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "电脑很慢" }));
    expect(screen.getByRole("button", { name: "开始诊断" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "重新读取以前的报告" }));

    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it("shows the planner clarification without polling forever", async () => {
    const client = api();
    const waiting: Diagnosis = {
      ...report("diagnosis-waiting"),
      status: "waiting_user_input",
      current_step: "请补充具体症状，例如卡顿、无法上网或软件闪退。",
      progress: 5,
      report: null,
      completed_at: null,
    };
    vi.spyOn(client, "get").mockResolvedValue({ items: [waiting] });
    render(<DiagnosisPanel client={client} />);

    fireEvent.change(await screen.findByLabelText("查看以前的问题"), {
      target: { value: waiting.id },
    });
    expect(await screen.findByText("需要补充信息")).toBeInTheDocument();
    expect(screen.getByText(waiting.current_step!)).toBeInTheDocument();
  });

  it("explains the current diagnostic step in plain language", async () => {
    const client = api();
    const running: Diagnosis = {
      ...report("diagnosis-running"),
      status: "running",
      current_step: "检查当前内存压力",
      progress: 40,
      report: null,
      completed_at: null,
    };
    vi.spyOn(client, "get").mockResolvedValue({ items: [running] });
    render(<DiagnosisPanel client={client} />);

    fireEvent.change(await screen.findByLabelText("查看以前的问题"), {
      target: { value: running.id },
    });
    expect(screen.getByText("检查当前内存压力")).toBeInTheDocument();
  });

  it("continues the same diagnosis after supplemental user input", async () => {
    const client = api();
    const waiting: Diagnosis = {
      ...report("diagnosis-waiting"),
      status: "waiting_user_input",
      current_step: "卡顿主要发生在什么时间？",
      progress: 5,
      report: null,
      completed_at: null,
      stop_reason: "insufficient_information",
    };
    vi.spyOn(client, "get").mockResolvedValue({ items: [waiting] });
    const post = vi.spyOn(client, "postJson").mockResolvedValue({
      ...waiting,
      status: "running",
      user_inputs: ["开机后十分钟"],
    });
    render(<DiagnosisPanel client={client} />);

    fireEvent.change(await screen.findByLabelText("查看以前的问题"), {
      target: { value: waiting.id },
    });
    fireEvent.change(screen.getByLabelText("补充说明"), {
      target: { value: "开机后十分钟" },
    });
    fireEvent.click(screen.getByRole("button", { name: "继续原诊断" }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        `/api/v1/diagnoses/${waiting.id}/inputs`,
        { answer: "开机后十分钟" },
        undefined,
      );
    });
  });

  it("states insufficient evidence plainly when no finding is available", async () => {
    const client = api();
    const insufficient: Diagnosis = {
      ...report("diagnosis-insufficient"),
      status: "partial",
      stop_reason: "insufficient_information",
      report: {
        summary: "当前证据不足，无法确定原因。",
        category: "performance",
        confidence: 0,
        model_explanation: "当前证据不足，无法确定原因。建议在问题复现时重新诊断。",
        limitations: ["已完成的检查未达到确定性规则阈值；建议在问题复现时重新诊断。"],
        findings: [],
        hypotheses: [
          {
            id: "hypothesis-insufficient",
            key: "performance_root_cause",
            hypothesis: "尚未确定性能问题原因",
            rationale: "当前证据不足，无法确定原因。",
            supporting_evidence: [],
            contradicting_evidence: [],
            confidence: 0,
            status: "insufficient",
          },
        ],
      },
    };
    vi.spyOn(client, "get").mockResolvedValue({ items: [insufficient] });
    render(<DiagnosisPanel client={client} />);

    fireEvent.change(await screen.findByLabelText("查看以前的问题"), {
      target: { value: insufficient.id },
    });

    expect(screen.getAllByText("当前证据不足，无法确定原因。").length).toBeGreaterThan(1);
    expect(screen.getByText("没有成功完成的检查结果，当前无法判断原因。")).toBeInTheDocument();
    expect(screen.getByText(/证据不足 · 0%/)).toBeInTheDocument();
  });

  it("prevents duplicate feedback while a submission is pending", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({ items: [report()] });
    const post = vi.spyOn(client, "postJson").mockImplementation(() => new Promise(() => {}));
    render(<DiagnosisPanel client={client} />);

    fireEvent.change(await screen.findByLabelText("查看以前的问题"), {
      target: { value: "diagnosis-1" },
    });
    const helpful = screen.getByRole("button", { name: "有帮助" });
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

    const history = await screen.findByLabelText("查看以前的问题");
    fireEvent.change(history, { target: { value: "diagnosis-a" } });
    fireEvent.click(screen.getByRole("button", { name: "有帮助" }));
    fireEvent.change(history, { target: { value: "diagnosis-b" } });
    fireEvent.click(screen.getByRole("button", { name: "有帮助" }));
    fireEvent.change(history, { target: { value: "diagnosis-a" } });

    expect(screen.getByRole("button", { name: "有帮助" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "有帮助" }));
    expect(post).toHaveBeenCalledTimes(2);
  });
});
