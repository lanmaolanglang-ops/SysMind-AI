import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "../../services/api-client";
import { SettingsPanel } from "./SettingsPanel";

describe("SettingsPanel", () => {
  it("keeps the key in form memory and clears it after secure submission", async () => {
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test" });
    vi.spyOn(client, "get").mockImplementation((path) => Promise.resolve(path.includes("retention")
      ? { retention_days: 30 }
      : { provider: "local-rules", model: "", endpoint: "", configured: false,
          updated_at: null, restart_required: false }));
    const put = vi.spyOn(client, "putJson").mockResolvedValue({
      provider: "openai_compatible", model: "fixture", endpoint: "https://example.test/v1",
      configured: true, updated_at: "now", restart_required: false,
    });
    render(<SettingsPanel client={client} />);

    const key = await screen.findByLabelText("访问密钥");
    expect(screen.getByText(/脱敏后的问题、最小设备摘要/)).toBeInTheDocument();
    expect(screen.getByText(/不会接收原始日志、完整事件 XML、凭据、用户文件或系统修改权限/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("服务地址"), { target: { value: "https://example.test/v1" } });
    fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "fixture" } });
    fireEvent.change(key, { target: { value: "secret-value" } });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    expect(await screen.findByText(/已从当前表单清除/)).toBeInTheDocument();
    expect(key).toHaveValue("");
    expect(put).toHaveBeenCalledWith("/api/v1/settings", expect.objectContaining({
      api_key: "secret-value",
    }), undefined);
  });

  it("requires an explicit in-panel confirmation before history cleanup", async () => {
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test" });
    vi.spyOn(client, "get").mockImplementation((path) => Promise.resolve(path.includes("retention")
      ? { retention_days: 30 }
      : { provider: "local-rules", model: "", endpoint: "", configured: false,
          updated_at: null, restart_required: false }));
    const postJson = vi.spyOn(client, "postJson").mockResolvedValue({
      deleted_scans: 1, deleted_diagnoses: 0, deleted_log_analyses: 0,
      protected_records: 0, completed_at: "now",
    });
    render(<SettingsPanel client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "立即清理" }));
    expect(postJson).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "确认清理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument();
    expect(screen.getByText(/此操作不可撤销/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "确认清理" }));
    await waitFor(() => expect(postJson).toHaveBeenCalledWith(
      "/api/v1/history/cleanup",
      { confirm: "cleanup" },
      undefined,
    ));
    expect(await screen.findByText(/清理完成/)).toBeInTheDocument();
  });

  it("cancels cleanup without calling the API", async () => {
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test" });
    vi.spyOn(client, "get").mockImplementation((path) => Promise.resolve(path.includes("retention")
      ? { retention_days: 30 }
      : { provider: "local-rules", model: "", endpoint: "", configured: false,
          updated_at: null, restart_required: false }));
    const postJson = vi.spyOn(client, "postJson").mockResolvedValue({
      deleted_scans: 0, deleted_diagnoses: 0, deleted_log_analyses: 0,
      protected_records: 0, completed_at: "now",
    });
    render(<SettingsPanel client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "立即清理" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    expect(postJson).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "立即清理" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认清理" })).not.toBeInTheDocument();
  });

  it("keeps edits made while saved settings are loading", async () => {
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test" });
    let finishSettings!: (value: unknown) => void;
    let finishRetention!: (value: unknown) => void;
    vi.spyOn(client, "get").mockImplementation((path) => new Promise((resolve) => {
      if (path.includes("retention")) finishRetention = resolve;
      else finishSettings = resolve;
    }));
    render(<SettingsPanel client={client} />);
    fireEvent.change(screen.getByLabelText("服务地址"), { target: { value: "https://edited.test/v1" } });
    fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "edited-model" } });
    fireEvent.change(screen.getByLabelText("天数"), { target: { value: "90" } });
    finishSettings({ provider: "openai_compatible", endpoint: "https://saved.test/v1", model: "saved-model", configured: true, updated_at: null, restart_required: false });
    finishRetention({ retention_days: 30 });
    await waitFor(() => expect(screen.getByText("在线解释已开启")).toBeInTheDocument());
    expect(screen.getByLabelText("服务地址")).toHaveValue("https://edited.test/v1");
    expect(screen.getByLabelText("模型名称")).toHaveValue("edited-model");
    expect(screen.getByLabelText("天数")).toHaveValue(90);
  });

  it("requires saving changed retention days before arming cleanup", async () => {
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test" });
    vi.spyOn(client, "get").mockImplementation((path) => Promise.resolve(path.includes("retention")
      ? { retention_days: 30 }
      : { provider: "local-rules", model: "", endpoint: "", configured: false,
          updated_at: null, restart_required: false }));
    const post = vi.spyOn(client, "postJson");
    render(<SettingsPanel client={client} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "立即清理" })).toBeEnabled());
    fireEvent.change(screen.getByLabelText("天数"), { target: { value: "90" } });
    expect(screen.getByRole("button", { name: "立即清理" })).toBeDisabled();
    expect(screen.getByText(/请先保存保留策略/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });
});
