import { fireEvent, render, screen } from "@testing-library/react";
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
    }));
  });
});
