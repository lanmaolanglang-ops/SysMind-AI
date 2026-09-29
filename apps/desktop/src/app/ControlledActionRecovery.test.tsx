import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { connectToBackend, restartBackendLauncher } from "../services/backend";
import { ApiClient } from "../services/api-client";
import type { ControlledAction } from "../services/actions";
import type { Diagnosis } from "../services/diagnoses";

vi.mock("../services/backend", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/backend")>();
  return {
    ...actual,
    connectToBackend: vi.fn(),
    restartBackendLauncher: vi.fn(),
  };
});

const DIAGNOSIS_ID = "diagnosis-1";

function completedDiagnosis(): Diagnosis {
  return {
    id: DIAGNOSIS_ID,
    status: "completed",
    user_question: "开机很慢",
    category: "performance",
    provider: "local-rules",
    plan: [{ tool: "startup.list@1.0", purpose: "读取启动项", arguments: {} }],
    progress: 100,
    current_step: null,
    created_at: "2026-09-29T10:00:00Z",
    completed_at: "2026-09-29T10:00:05Z",
    feedback_submitted: false,
    failure_message: null,
    tool_calls: [],
    report: {
      summary: "有三个登录自启动程序占用资源",
      category: "performance",
      confidence: 0.8,
      model_explanation: "启动项证据达到阈值。",
      limitations: [],
      findings: [
        {
          id: "f1",
          code: "startup_heavy",
          severity: "high",
          title: "登录自启动程序占用资源",
          explanation: "采样期间持续占用。",
          recommendation: "禁用不需要的启动项。",
          confidence: 0.8,
          evidence: [],
        },
      ],
    },
  };
}

const disableAction: ControlledAction = {
  id: "action-1",
  diagnosis_id: DIAGNOSIS_ID,
  tool_name: "startup.disable_current_user",
  target_name: "Example",
  source_kind: "user_run",
  status: "proposed",
  recovery_available: false,
  error_code: null,
  error_message: null,
};

const restoreAction: ControlledAction = {
  ...disableAction,
  id: "action-2",
  tool_name: "startup.restore_current_user",
  status: "proposed",
};

/**
 * Drives the real application across a section switch, with the backend
 * simulated as a record store so the UI can only recover what the API holds.
 */
describe("controlled action recovery across navigation", () => {
  let records: ControlledAction[];
  let deferActions: { promise: Promise<unknown>; release: (value: { items: ControlledAction[] }) => void } | null;

  beforeEach(() => {
    records = [];
    deferActions = null;
    vi.mocked(restartBackendLauncher).mockReset();
    vi.mocked(restartBackendLauncher).mockResolvedValue();
  });

  /** Holds the action-record read open so a test can act while it is in flight. */
  function holdActionRecords() {
    let release: (value: { items: ControlledAction[] }) => void = () => {};
    const promise = new Promise<{ items: ControlledAction[] }>((resolve) => {
      release = resolve;
    });
    deferActions = { promise, release: (value) => release(value) };
  }

  function wire() {
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:41234",
      sessionToken: "memory-only-token",
    });

    vi.mocked(connectToBackend).mockResolvedValue({
      endpoint: {
        base_url: "http://127.0.0.1:41234",
        session_token: "memory-only-token",
        api_version: "1.0",
      },
      health: { status: "ok", backend_version: "0.1.0", api_version: "1.0", ready: true },
      client,
    });

    const settle = <T,>(value: T) => Promise.resolve(value) as Promise<never>;

    vi.spyOn(client, "get").mockImplementation(((path: string) => {
      if (path === "/api/v1/actions") {
        if (deferActions) return deferActions.promise;
        return settle({ items: records.map((r) => ({ ...r })) });
      }
      if (path.startsWith("/api/v1/actions/candidates")) {
        return settle({
          items: [
            {
              item_id: "a".repeat(64),
              name: "Example",
              source_kind: "user_run",
              command_name: "example.exe",
              observed_revision: "b".repeat(64),
            },
          ],
        });
      }
      if (path === "/api/v1/diagnoses") return settle({ items: [completedDiagnosis()] });
      if (path === "/api/v1/scans") return settle({ items: [] });
      return settle({ items: [] });
    }));

    vi.spyOn(client, "post").mockImplementation(((path: string) => {
      if (path.endsWith("/confirm")) {
        records = records.map((r) =>
          r.id === "action-1" ? { ...r, status: "confirmed" } : r,
        );
        return settle({
          action: { ...disableAction, status: "confirmed" },
          ticket: "ticket-value",
          expires_at: "in two minutes",
        });
      }
      if (path.endsWith("/recovery")) {
        const created = { ...restoreAction, status: "proposed" };
        records = [...records, created];
        return settle(created);
      }
      if (path.endsWith("/reject")) return settle({ ...disableAction, status: "rejected" });
      return settle(disableAction);
    }));

    vi.spyOn(client, "postJson").mockImplementation(((path: string) => {
      if (path.endsWith("/execute")) {
        // The backend records the outcome; the UI must not be the source of truth.
        const succeeded: ControlledAction = {
          ...disableAction,
          status: "succeeded",
          recovery_available: true,
        };
        records = records.map((r) => (r.id === "action-1" ? succeeded : r));
        return settle(succeeded);
      }
      const proposed = { ...disableAction };
      records = [proposed];
      return settle(proposed);
    }));

    return client;
  }

  it("restores the outcome and the recovery entry point after leaving and returning", async () => {
    wire();
    render(<App />);

    // 1. Execute a recoverable controlled action from the diagnosis section.
    fireEvent.click(await screen.findByRole("button", { name: "查看启动项" }));
    fireEvent.click(await screen.findByRole("button", { name: "生成禁用计划" }));
    fireEvent.click(await screen.findByRole("button", { name: "我已了解，确认禁用" }));

    expect(await screen.findByText("启动项已禁用并验证")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成恢复计划" })).toBeInTheDocument();

    // 2. Leave the diagnosis section: the panel unmounts and its state is gone.
    fireEvent.click(screen.getByRole("button", { name: "快速扫描" }));
    await screen.findByRole("heading", { level: 1, name: "快速扫描" });
    expect(screen.queryByText("启动项已禁用并验证")).not.toBeInTheDocument();

    // 3. Return. The outcome and the recovery entry point must come back from
    //    the backend record, not from unmounted component state.
    fireEvent.click(screen.getByRole("button", { name: "诊断" }));

    expect(await screen.findByText("启动项已禁用并验证")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成恢复计划" })).toBeInTheDocument();

    // 4. The user can still complete the recovery from the restored entry point.
    fireEvent.click(screen.getByRole("button", { name: "生成恢复计划" }));
    expect(await screen.findByText(/恢复后，该程序可能在下次登录时自动启动/)).toBeInTheDocument();
  });

  it("does not resurrect an action that was explicitly rejected", async () => {
    records = [{ ...disableAction, status: "rejected" }];
    wire();
    render(<App />);

    // The panel returns to the candidate list rather than showing a result.
    expect(await screen.findByRole("button", { name: "查看启动项" })).toBeInTheDocument();
    expect(screen.queryByText("操作未完成")).not.toBeInTheDocument();
  });

  it("ignores actions recorded for a different diagnosis", async () => {
    records = [
      { ...disableAction, diagnosis_id: "some-other-diagnosis", status: "succeeded", recovery_available: true },
    ];
    wire();
    render(<App />);

    expect(await screen.findByRole("button", { name: "查看启动项" })).toBeInTheDocument();
    expect(screen.queryByText("启动项已禁用并验证")).not.toBeInTheDocument();
  });

  it("lets the user take over before the restore lands", async () => {
    records = [{ ...disableAction, id: "action-old", status: "succeeded", recovery_available: true }];
    holdActionRecords();
    wire();

    render(<App />);

    // The user opens the candidate list while the record read is still open.
    fireEvent.click(await screen.findByRole("button", { name: "查看启动项" }));
    expect(await screen.findByRole("button", { name: "生成禁用计划" })).toBeInTheDocument();

    deferActions?.release({ items: records });

    // The late restore must not yank the user out of what they are doing.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "生成禁用计划" })).toBeInTheDocument();
    });
    expect(screen.queryByText("启动项已禁用并验证")).not.toBeInTheDocument();
  });
});
