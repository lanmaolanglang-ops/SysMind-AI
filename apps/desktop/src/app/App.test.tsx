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

vi.mock("../features/logs/LogAnalysisPanel", () => ({
  LogAnalysisPanel: () => <div>日志分析面板</div>,
}));

vi.mock("../features/tasks/AgentTaskPanel", () => ({
  AgentTaskPanel: () => <div>Agent 任务面板</div>,
}));

vi.mock("../features/diagnose/DiagnosisPanel", () => ({
  DiagnosisPanel: () => <div>自然语言诊断面板</div>,
}));

vi.mock("../features/settings/SettingsView", () => ({
  SettingsView: () => <div>设置与更新面板</div>,
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

function connection() {
  return {
    endpoint: {
      base_url: "http://127.0.0.1:41234",
      session_token: "memory-only-token",
      api_version: "1.0",
    },
    health: {
      status: "ok" as const,
      backend_version: "0.1.0",
      api_version: "1.0",
      ready: true,
    },
    client: new ApiClient({ baseUrl: "http://127.0.0.1:41234", sessionToken: "token" }),
  };
}

describe("App", () => {
  beforeEach(() => {
    mockedConnect.mockReset();
    mockedRestart.mockReset();
    mockedRestart.mockResolvedValue();
  });

  it("opens on diagnosis and reports local runtime facts in the workspace header", async () => {
    mockedConnect.mockResolvedValue(connection());

    render(<App />);

    expect(await screen.findByText("本地服务已连接")).toBeInTheDocument();
    expect(screen.getByText("127.0.0.1")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "诊断" })).toBeInTheDocument();
    expect(screen.getByText("自然语言诊断面板")).toBeInTheDocument();
  });

  it("mounts only the active section so one collector runs at a time", async () => {
    mockedConnect.mockResolvedValue(connection());

    render(<App />);

    expect(await screen.findByText("自然语言诊断面板")).toBeInTheDocument();
    expect(screen.queryByText("快速扫描面板")).not.toBeInTheDocument();
    expect(screen.queryByText("日志分析面板")).not.toBeInTheDocument();
    expect(screen.queryByText("Agent 任务面板")).not.toBeInTheDocument();
    expect(screen.queryByText("设置与更新面板")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "快速扫描" }));

    expect(screen.getByText("快速扫描面板")).toBeInTheDocument();
    expect(screen.queryByText("自然语言诊断面板")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "快速扫描" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "设置与更新" }));
    expect(screen.getByText("设置与更新面板")).toBeInTheDocument();
  });

  it("marks the current section for assistive technology", async () => {
    mockedConnect.mockResolvedValue(connection());

    render(<App />);
    await screen.findByText("自然语言诊断面板");

    expect(screen.getByRole("button", { name: "诊断" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    fireEvent.click(screen.getByRole("button", { name: "事件日志" }));

    expect(screen.getByRole("button", { name: "事件日志" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("button", { name: "诊断" })).not.toHaveAttribute("aria-current");
  });

  it("shows a recoverable startup failure", async () => {
    mockedConnect.mockRejectedValueOnce(
      new BackendConnectionError("backend_startup_failed", "Python sidecar 启动失败。"),
    );
    mockedConnect.mockResolvedValueOnce(connection());

    render(<App />);

    expect(await screen.findByText("Python sidecar 启动失败。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新连接" }));
    expect(await screen.findByText("本地服务已连接")).toBeInTheDocument();
    expect(mockedRestart).toHaveBeenCalledOnce();
  });
});
