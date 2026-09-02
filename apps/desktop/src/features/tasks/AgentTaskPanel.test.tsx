import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiClient, type SseEvent } from "../../services/api-client";
import {
  agentTaskReconnectDelay,
  type AgentTask,
  type AgentTaskEventData,
} from "../../services/agent-tasks";
import { AgentTaskPanel } from "./AgentTaskPanel";

function client(): ApiClient {
  return new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test-token" });
}

function task(status: AgentTask["status"]): AgentTask {
  return {
    id: "task-1",
    status,
    user_goal: "framework test",
    provider: "fake",
    allowed_tools: ["system.cpu@1.0"],
    budget: {
      max_rounds: 4,
      max_tool_calls: 8,
      timeout_seconds: 30,
      max_parallel_tools: 2,
    },
    current_round: status === "completed" ? 1 : 0,
    tool_call_count: 0,
    progress: status === "completed" ? 100 : 0,
    final_output: status === "completed" ? "Phase 3 离线 Agent Runtime 自检完成。" : null,
    failure_code: null,
    failure_message: null,
    cancel_requested: false,
    created_at: "2026-08-19T10:00:00Z",
    started_at: null,
    finished_at: status === "completed" ? "2026-08-19T10:00:01Z" : null,
    schema_version: "1.0",
    tool_calls: [],
  };
}

describe("AgentTaskPanel", () => {
  it("backs off repeated SSE reconnects with a bounded delay", () => {
    expect([1, 2, 3, 4, 5, 6].map(agentTaskReconnectDelay)).toEqual([
      350,
      700,
      1_400,
      2_800,
      5_000,
      5_000,
    ]);
  });

  it("follows SSE progress and renders the deterministic terminal result", async () => {
    const api = client();
    vi.spyOn(api, "get").mockImplementation((path) => {
      if (path === "/api/v1/tasks/tools") {
        return Promise.resolve({
          items: [
            {
              name: "system.cpu",
              version: "1.0",
              qualified_name: "system.cpu@1.0",
              description: "Read CPU",
              input_schema: { type: "object" },
              risk_level: "read_only",
              sensitivity: [],
            },
          ],
        });
      }
      if (path === "/api/v1/tasks") return Promise.resolve({ items: [] });
      return Promise.resolve(task("completed"));
    });
    const postJson = vi.spyOn(api, "postJson").mockResolvedValue(task("created"));
    vi.spyOn(api, "streamSse").mockImplementation((_path, callback) => {
      const event: SseEvent<AgentTaskEventData> = {
        id: "2",
        event: "task.status",
        data: {
          status: "planning",
          progress: 5,
          created_at: "2026-08-19T10:00:00Z",
        },
      };
      callback(event);
      return Promise.resolve();
    });

    render(<AgentTaskPanel client={api} />);
    fireEvent.click(await screen.findByLabelText("system.cpu"));
    fireEvent.click(screen.getByRole("button", { name: "运行离线自检" }));

    expect(await screen.findByText("Phase 3 离线 Agent Runtime 自检完成。")).toBeInTheDocument();
    expect(screen.getByText("正在规划受限步骤")).toBeInTheDocument();
    await waitFor(() => {
      expect(postJson).toHaveBeenCalledWith(
        "/api/v1/tasks",
        expect.objectContaining({ allowed_tools: ["system.cpu@1.0"] }),
        undefined,
      );
    });
  });

  it("shows that the runtime is offline and does not promise a diagnosis", async () => {
    const api = client();
    vi.spyOn(api, "get").mockImplementation((path) =>
      Promise.resolve(
        path === "/api/v1/tasks/tools" ? { items: [] } : { items: [task("completed")] },
      ),
    );

    render(<AgentTaskPanel client={api} />);

    expect(await screen.findByText("Fake Provider · 离线")).toBeInTheDocument();
    expect(screen.getByText(/这里不会生成诊断报告/)).toBeInTheDocument();
  });
});
