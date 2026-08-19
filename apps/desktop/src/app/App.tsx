import { useCallback, useEffect, useState } from "react";

import {
  BackendConnectionError,
  connectToBackend,
  restartBackendLauncher,
  type BackendConnection,
} from "../services/backend";

type ConnectionState =
  | { kind: "starting" }
  | { kind: "connected"; connection: BackendConnection }
  | { kind: "disconnected"; message: string; correlationId?: string };

function StatusMark({ state }: { state: ConnectionState["kind"] }) {
  return <span className={`status-mark status-mark--${state}`} aria-hidden="true" />;
}

export function App() {
  const [state, setState] = useState<ConnectionState>({ kind: "starting" });
  const [attempt, setAttempt] = useState(0);

  const reconnect = useCallback(() => {
    setState({ kind: "starting" });
    void restartBackendLauncher()
      .then(() => {
        setAttempt((value) => value + 1);
      })
      .catch(() => {
        setState({
          kind: "disconnected",
          message: "无法重新启动本地后端，请重启应用并检查开发环境。",
        });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    void connectToBackend(controller.signal)
      .then((connection) => {
        setState({ kind: "connected", connection });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const normalized =
          error instanceof BackendConnectionError
            ? error
            : new BackendConnectionError(
                "backend_unavailable",
                "本地服务暂时无法连接，请稍后重试。",
              );
        setState({
          kind: "disconnected",
          message: normalized.message,
          ...(normalized.correlationId
            ? { correlationId: normalized.correlationId }
            : {}),
        });
      });

    return () => {
      controller.abort();
    };
  }, [attempt]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-symbol" aria-hidden="true">
            S
          </span>
          <span>SysMind AI</span>
        </div>
        <div className={`connection-chip connection-chip--${state.kind}`} role="status">
          <StatusMark state={state.kind} />
          {state.kind === "connected"
            ? "Backend Connected"
            : state.kind === "starting"
              ? "Backend Starting"
              : "Backend Disconnected"}
        </div>
      </header>

      <section className="workspace" aria-labelledby="workspace-title">
        <div className="intro">
          <p className="phase-label">Phase 0 · 工程初始化</p>
          <h1 id="workspace-title">本地服务连接</h1>
          <p>
            SysMind AI 正在建立安全的本地运行环境。当前版本只验证桌面端与后端连接，尚未读取或诊断任何系统信息。
          </p>
        </div>

        <div className="runtime-panel">
          {state.kind === "starting" && (
            <div className="state-content" aria-live="polite">
              <div className="activity-line" aria-hidden="true">
                <span />
              </div>
              <h2>正在启动本地后端</h2>
              <p>等待 FastAPI 完成数据库迁移和 readiness 检查。</p>
            </div>
          )}

          {state.kind === "connected" && (
            <div className="state-content" aria-live="polite">
              <div className="state-heading">
                <StatusMark state="connected" />
                <h2>本地运行环境已就绪</h2>
              </div>
              <dl className="runtime-details">
                <div>
                  <dt>Backend</dt>
                  <dd>{state.connection.health.backend_version}</dd>
                </div>
                <div>
                  <dt>API protocol</dt>
                  <dd>{state.connection.health.api_version}</dd>
                </div>
                <div>
                  <dt>Network boundary</dt>
                  <dd>127.0.0.1 only</dd>
                </div>
              </dl>
              <p className="privacy-note">
                会话令牌仅保存在当前进程内存中；本阶段没有模型调用和系统扫描。
              </p>
            </div>
          )}

          {state.kind === "disconnected" && (
            <div className="state-content state-content--error" role="alert">
              <div className="state-heading">
                <StatusMark state="disconnected" />
                <h2>本地后端未连接</h2>
              </div>
              <p>{state.message}</p>
              {state.correlationId && (
                <p className="correlation-id">问题编号：{state.correlationId}</p>
              )}
              <button type="button" onClick={reconnect}>
                重新连接
              </button>
            </div>
          )}
        </div>
      </section>

      <footer>
        <span>Local-first foundation</span>
        <span>v0.1.0</span>
      </footer>
    </main>
  );
}
