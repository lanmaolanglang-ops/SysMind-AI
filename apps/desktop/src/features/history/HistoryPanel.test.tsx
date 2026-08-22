import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "../../services/api-client";
import { HistoryPanel } from "./HistoryPanel";

describe("HistoryPanel", () => {
  it("previews cascade impact before deleting and labels action audit as retained", async () => {
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test" });
    vi.spyOn(client, "get").mockImplementation((path) => {
      if (path === "/api/v1/scans") return Promise.resolve({ items: [{ id: "scan-1", status: "completed", started_at: "2026-01-01T00:00:00Z" }] });
      if (path === "/api/v1/diagnoses") return Promise.resolve({ items: [] });
      if (path === "/api/v1/log-analyses") return Promise.resolve({ items: [] });
      if (path === "/api/v1/actions") return Promise.resolve({ items: [{ id: "action-1", target_name: "demo.exe", status: "completed" }] });
      if (path === "/api/v1/history/baseline") return Promise.resolve({ items: [] });
      return Promise.resolve({ kind: "scan", record_id: "scan-1", revision: "a".repeat(64), deletable: true, dependent_records: 3, protected_reason: null });
    });
    const post = vi.spyOn(client, "postJson").mockResolvedValue({ deleted: true });
    render(<HistoryPanel client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "删除…" }));
    expect(await screen.findByText(/同时删除 3 条从属明细/)).toBeInTheDocument();
    expect(screen.getByText("强制保留审计")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(post).toHaveBeenCalledWith(
      "/api/v1/history/scan/scan-1/delete", { revision: "a".repeat(64) }, undefined,
    );
  });
});
