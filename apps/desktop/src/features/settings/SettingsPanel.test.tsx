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

    const key = await screen.findByLabelText("API Key");
    fireEvent.change(screen.getByLabelText("兼容端点"), { target: { value: "https://example.test/v1" } });
    fireEvent.change(screen.getByLabelText("模型"), { target: { value: "fixture" } });
    fireEvent.change(key, { target: { value: "secret-value" } });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    expect(await screen.findByText(/表单内存已清空/)).toBeInTheDocument();
    expect(key).toHaveValue("");
    expect(put).toHaveBeenCalledWith("/api/v1/settings", expect.objectContaining({
      api_key: "secret-value",
    }));
  });
});
