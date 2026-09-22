import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UpdatePanel } from "./UpdatePanel";
import { checkForAppUpdate, getAppVersion } from "../../services/updates";

vi.mock("../../services/updates", () => ({
  checkForAppUpdate: vi.fn(),
  getAppVersion: vi.fn(),
}));

const mockedCheck = vi.mocked(checkForAppUpdate);
const mockedVersion = vi.mocked(getAppVersion);

describe("UpdatePanel", () => {
  beforeEach(() => {
    mockedCheck.mockReset();
    mockedVersion.mockReset();
    mockedVersion.mockResolvedValue("0.1.0");
  });

  it("disables update checks when the build has no configured updater", async () => {
    render(<UpdatePanel updaterAvailable={false} />);

    expect(await screen.findByText(/当前版本 0.1.0/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开发构建不提供更新" })).toBeDisabled();
    expect(mockedCheck).not.toHaveBeenCalled();
  });

  it("reports when the installed version is current", async () => {
    mockedCheck.mockResolvedValue(null);
    render(<UpdatePanel />);

    expect(await screen.findByText(/当前版本 0.1.0/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "检查更新" }));

    expect(await screen.findByText("当前已是最新版本。")).toBeInTheDocument();
  });

  it("installs only after a separate explicit click", async () => {
    const install = vi.fn().mockResolvedValue(undefined);
    mockedCheck.mockResolvedValue({ version: "0.2.0", notes: null, install });
    render(<UpdatePanel />);

    fireEvent.click(screen.getByRole("button", { name: "检查更新" }));
    expect(await screen.findByText(/发现版本 0.2.0/)).toBeInTheDocument();
    expect(install).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "安装并重启" }));
    expect(await screen.findByText("正在安装版本 0.2.0…")).toBeInTheDocument();
    expect(install).toHaveBeenCalledOnce();
  });

  it("keeps the current installation usable after a check failure", async () => {
    mockedCheck.mockRejectedValue(new Error("offline"));
    render(<UpdatePanel />);

    fireEvent.click(screen.getByRole("button", { name: "检查更新" }));

    expect(
      await screen.findByText("暂时无法连接安全更新服务。当前诊断功能仍可离线使用。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "检查更新" })).toBeEnabled();
  });
});
