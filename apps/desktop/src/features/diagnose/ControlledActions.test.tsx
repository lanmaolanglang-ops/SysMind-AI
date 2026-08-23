import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiClientError } from "../../services/api-client";
import { ControlledActions } from "./ControlledActions";

function api() {
  return new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test-token" });
}

const proposed = {
  id: "action-1",
  diagnosis_id: "diagnosis-1",
  tool_name: "startup.disable_current_user" as const,
  target_name: "Example",
  source_kind: "user_run",
  status: "proposed",
  recovery_available: false,
  error_code: null,
  error_message: null,
};

describe("ControlledActions", () => {
  it("shows exact impact and waits for a separate explicit confirmation", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({
      items: [{ item_id: "a".repeat(64), name: "Example", source_kind: "user_run",
        command_name: "example.exe", observed_revision: "b".repeat(64) }],
    });
    const post = vi.spyOn(client, "post").mockResolvedValue({
      action: { ...proposed, status: "confirmed" }, ticket: "ticket", expires_at: "soon",
    });
    const postJson = vi.spyOn(client, "postJson")
      .mockResolvedValueOnce(proposed)
      .mockResolvedValueOnce({ ...proposed, status: "succeeded", recovery_available: true });
    render(<ControlledActions client={client} diagnosisId="diagnosis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "减少开机负担" }));
    fireEvent.click(await screen.findByRole("button", { name: "查看停用方案" }));
    expect(await screen.findByText(/不会在下次登录时自动启动/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "操作确认" })).toHaveFocus();
    expect(post).not.toHaveBeenCalled();
    expect(postJson).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "我已了解，确认停用" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/actions/action-1/confirm"));
    expect(await screen.findByText("启动项已禁用并验证")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "恢复自动启动" })).toBeInTheDocument();
  });

  it("never escalates a pending GUI close request to forced termination", async () => {
    const client = api();
    vi.spyOn(client, "get").mockResolvedValue({
      items: [{ item_id: "c".repeat(64), name: "Editor.exe",
        source_kind: "current_user_process", command_name: "editor.exe",
        observed_revision: "d".repeat(64), cpu_percent: 41, memory_percent: 8 }],
    });
    const processAction = {
      ...proposed,
      id: "process-action",
      tool_name: "process.request_close_current_user" as const,
      target_name: "Editor.exe",
      source_kind: "current_user_process",
    };
    const terminateAction = {
      ...processAction,
      id: "terminate-action",
      tool_name: "process.terminate_current_user" as const,
      status: "proposed",
    };
    const post = vi.spyOn(client, "post")
      .mockResolvedValueOnce({
        action: { ...processAction, status: "confirmed" }, ticket: "ticket", expires_at: "soon",
      })
      .mockResolvedValueOnce(terminateAction)
      .mockResolvedValueOnce({
        action: { ...terminateAction, status: "awaiting_second_confirmation" },
        ticket: null, expires_at: null,
      })
      .mockResolvedValueOnce({
        action: { ...terminateAction, status: "confirmed" },
        ticket: "terminate-ticket", expires_at: "soon",
      });
    vi.spyOn(client, "postJson")
      .mockResolvedValueOnce(processAction)
      .mockResolvedValueOnce({ ...processAction, status: "close_pending",
        error_code: "close_pending", error_message: null })
      .mockResolvedValueOnce({ ...terminateAction, status: "succeeded" });
    render(<ControlledActions client={client} diagnosisId="diagnosis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "查看高占用应用" }));
    fireEvent.click(await screen.findByRole("button", { name: "查看关闭方案" }));
    expect(await screen.findByText(/不会自动升级为强制终止/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "我已了解，确认关闭" }));

    expect(await screen.findByText(/尚未执行强制终止/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看强制关闭方案" }));
    expect(await screen.findByText(/未保存内容会丢失/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "我已了解数据丢失风险" }));
    expect(await screen.findByText(/第二次也是最终确认/)).toBeInTheDocument();
    expect(screen.queryByText("应用已强制终止并验证")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "再次确认并强制关闭" }));
    expect(await screen.findByText("应用已强制终止并验证")).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(4);
  });

  it("queries status after an unknown network result without retrying execution", async () => {
    const client = api();
    const get = vi.spyOn(client, "get")
      .mockResolvedValueOnce({
        items: [{ item_id: "a".repeat(64), name: "Example", source_kind: "user_run",
          command_name: "example.exe", observed_revision: "b".repeat(64) }],
      })
      .mockResolvedValueOnce({ ...proposed, status: "succeeded", recovery_available: true });
    vi.spyOn(client, "post").mockResolvedValue({
      action: { ...proposed, status: "confirmed" }, ticket: "ticket", expires_at: "soon",
    });
    const postJson = vi.spyOn(client, "postJson")
      .mockResolvedValueOnce(proposed)
      .mockRejectedValueOnce(new ApiClientError("network_error", "disconnected"));
    render(<ControlledActions client={client} diagnosisId="diagnosis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "减少开机负担" }));
    fireEvent.click(await screen.findByRole("button", { name: "查看停用方案" }));
    fireEvent.click(await screen.findByRole("button", { name: "我已了解，确认停用" }));

    expect(await screen.findByText("启动项已禁用并验证")).toBeInTheDocument();
    expect(postJson).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenCalledWith("/api/v1/actions/action-1", expect.any(AbortSignal));
  });
});
