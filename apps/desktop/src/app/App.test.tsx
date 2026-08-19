import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import {
  BackendConnectionError,
  connectToBackend,
  restartBackendLauncher,
} from "../services/backend";
import { ApiClient } from "../services/api-client";

vi.mock("../features/scans/QuickScanPanel", () => ({
  QuickScanPanel: () => <div>快速扫描面板</div>,
}));

vi.mock("../services/backend", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/backend")>();
  return {
    ...actual,
    connectToBackend: vi.fn(),
    restartBackendLauncher: vi.fn(),
  };
});

const mockedConnect = vi.mocked(connectToBackend);
const mockedRestart = vi.mocked(restartBackendLauncher);

describe("App", () => {
  beforeEach(() => {
    mockedConnect.mockReset();
    mockedRestart.mockReset();
    mockedRestart.mockResolvedValue();
  });

  it("shows backend connection details when ready", async () => {
    mockedConnect.mockResolvedValue({
      endpoint: {
        base_url: "http://127.0.0.1:41234",
        session_token: "memory-only-token",
        api_version: "1.0",
      },
      health: {
        status: "ok",
        backend_version: "0.1.0",
        api_version: "1.0",
        ready: true,
      },
      client: new ApiClient({ baseUrl: "http://127.0.0.1:41234", sessionToken: "token" }),
    });

    render(<App />);

    expect(await screen.findByText("本地服务已连接")).toBeInTheDocument();
    expect(screen.getByText("127.0.0.1")).toBeInTheDocument();
    expect(screen.getByText("设备概览")).toBeInTheDocument();
    expect(screen.getByText("快速扫描面板")).toBeInTheDocument();
  });

  it("shows a recoverable startup failure", async () => {
    mockedConnect.mockRejectedValueOnce(
      new BackendConnectionError("backend_startup_failed", "Python sidecar 启动失败。"),
    );
    mockedConnect.mockResolvedValueOnce({
      endpoint: {
        base_url: "http://127.0.0.1:41234",
        session_token: "memory-only-token",
        api_version: "1.0",
      },
      health: {
        status: "ok",
        backend_version: "0.1.0",
        api_version: "1.0",
        ready: true,
      },
      client: new ApiClient({ baseUrl: "http://127.0.0.1:41234", sessionToken: "token" }),
    });

    render(<App />);

    expect(await screen.findByText("Python sidecar 启动失败。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新连接" }));
    expect(await screen.findByText("本地服务已连接")).toBeInTheDocument();
    expect(mockedRestart).toHaveBeenCalledOnce();
  });
});
