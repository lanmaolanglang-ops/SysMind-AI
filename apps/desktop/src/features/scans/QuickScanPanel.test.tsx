import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "../../services/api-client";
import type { ScanRecord } from "../../services/scans";
import { QuickScanPanel } from "./QuickScanPanel";

function client(): ApiClient {
  return new ApiClient({ baseUrl: "http://127.0.0.1:45000", sessionToken: "test-token" });
}

function record(status: ScanRecord["status"]): ScanRecord {
  return {
    id: "scan-1",
    status,
    progress: status === "completed" ? 100 : 20,
    current_step: status === "running" ? "system.cpu" : null,
    started_at: "2026-08-19T10:00:00Z",
    finished_at: status === "completed" ? "2026-08-19T10:00:02Z" : null,
    schema_version: "1.0",
    failures: [],
    summary:
      status === "completed"
        ? {
            capabilities: [],
            operating_system: {
              name: "Windows",
              version: "10.0",
              build: "11",
              architecture: "AMD64",
            },
            cpu: {
              model: "Fixture CPU",
              physical_cores: 8,
              logical_cores: 16,
              utilization_percent: 12,
              frequency_mhz: 4200,
            },
            gpus: [],
            memory: {
              total_bytes: 16_000_000_000,
              available_bytes: 8_000_000_000,
              used_bytes: 8_000_000_000,
              utilization_percent: 50,
            },
            disks: [
              {
                volume: "C:",
                mountpoint: "C:\\",
                filesystem: "NTFS",
                total_bytes: 100_000,
                free_bytes: 40_000,
                used_bytes: 60_000,
                utilization_percent: 60,
              },
            ],
            processes: [],
            high_usage_processes: [],
          }
        : null,
  };
}

describe("QuickScanPanel", () => {
  it("starts a scan and renders completed system evidence", async () => {
    const api = client();
    vi.spyOn(api, "get")
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValue(record("completed"));
    vi.spyOn(api, "post").mockResolvedValue(record("running"));

    render(<QuickScanPanel client={api} />);
    expect(await screen.findByText(/首次扫描通常只需几秒/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "开始扫描" }));

    expect(await screen.findByText(/Fixture CPU/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("扫描完成");
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "60");
  });

  it("exposes cancellation while a scan is active", async () => {
    const api = client();
    vi.spyOn(api, "get").mockResolvedValue({ items: [record("running")] });
    const post = vi.spyOn(api, "post").mockResolvedValue(record("cancelled"));

    render(<QuickScanPanel client={api} />);
    fireEvent.click(await screen.findByRole("button", { name: "取消扫描" }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith("/api/v1/scans/scan-1/cancel", undefined);
    });
    await waitFor(() => {
      expect(
        screen.getAllByRole("status").some((element) => element.textContent === "扫描已取消"),
      ).toBe(true);
    });
  });
});
