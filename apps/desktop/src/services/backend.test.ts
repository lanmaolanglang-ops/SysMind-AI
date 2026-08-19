import { invoke } from "@tauri-apps/api/core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { connectToBackend } from "./backend";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

describe("connectToBackend", () => {
  beforeEach(() => {
    vi.mocked(invoke).mockReset();
  });

  it("rejects an incompatible API protocol before issuing HTTP", async () => {
    vi.mocked(invoke).mockResolvedValue({
      state: "connected",
      endpoint: {
        base_url: "http://127.0.0.1:41000",
        session_token: "token",
        api_version: "2.0",
      },
      error: null,
    });

    await expect(connectToBackend()).rejects.toMatchObject({
      code: "api_version_mismatch",
    });
  });

  it("normalizes launcher startup failures", async () => {
    vi.mocked(invoke).mockResolvedValue({
      state: "disconnected",
      endpoint: null,
      error: "Backend process exited before readiness.",
    });

    await expect(connectToBackend()).rejects.toMatchObject({
      code: "backend_startup_failed",
      message: "Backend process exited before readiness.",
    });
  });
});
