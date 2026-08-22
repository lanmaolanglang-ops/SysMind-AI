import { useEffect, useState } from "react";

import {
  checkForAppUpdate,
  getAppVersion,
  type AvailableUpdate,
} from "../../services/updates";

type UpdateState =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "current" }
  | { kind: "available"; update: AvailableUpdate }
  | { kind: "installing"; version: string }
  | { kind: "error"; message: string };

export function UpdatePanel({
  updaterAvailable = import.meta.env.PROD || import.meta.env.MODE === "test",
}: {
  updaterAvailable?: boolean;
}) {
  const [version, setVersion] = useState("—");
  const [state, setState] = useState<UpdateState>({ kind: "idle" });

  useEffect(() => {
    let active = true;
    void getAppVersion()
      .then((value) => {
        if (active) setVersion(value);
      })
      .catch(() => {
        if (active) setVersion("未知");
      });
    return () => {
      active = false;
    };
  }, []);

  async function checkForUpdates() {
    setState({ kind: "checking" });
    try {
      const update = await checkForAppUpdate();
      setState(update ? { kind: "available", update } : { kind: "current" });
    } catch {
      setState({
        kind: "error",
        message: "暂时无法连接安全更新服务。当前诊断功能仍可离线使用。",
      });
    }
  }

  async function install(update: AvailableUpdate) {
    setState({ kind: "installing", version: update.version });
    try {
      await update.install();
    } catch {
      setState({
        kind: "error",
        message: "更新未能安装，现有版本未被替换。请稍后重新检查。",
      });
    }
  }

  const busy = state.kind === "checking" || state.kind === "installing";

  return (
    <section className="update-strip" aria-labelledby="update-title">
      <div>
        <h2 id="update-title">应用更新</h2>
        <p>当前版本 {version}。更新包会先验证发布签名，诊断数据在升级时保留在本机。</p>
        <div className="update-message" aria-live="polite">
          {state.kind === "current" && <span>当前已是最新版本。</span>}
          {state.kind === "available" && (
            <span>发现版本 {state.update.version}，安装后应用会重新启动。</span>
          )}
          {state.kind === "installing" && <span>正在安装版本 {state.version}…</span>}
          {state.kind === "error" && <span role="alert">{state.message}</span>}
        </div>
      </div>
      <div className="update-actions">
        {state.kind === "available" ? (
          <button type="button" onClick={() => void install(state.update)} disabled={busy}>
            安装并重启
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void checkForUpdates()}
            disabled={busy || !updaterAvailable}
            title={updaterAvailable ? undefined : "开发构建未配置签名更新器"}
          >
            {state.kind === "checking"
              ? "正在检查…"
              : updaterAvailable
                ? "检查更新"
                : "开发构建不提供更新"}
          </button>
        )}
      </div>
    </section>
  );
}
