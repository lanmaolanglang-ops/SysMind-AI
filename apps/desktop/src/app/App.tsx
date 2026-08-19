import { useCallback, useEffect, useState } from "react";

import { QuickScanPanel } from "../features/scans/QuickScanPanel";
import { LogAnalysisPanel } from "../features/logs/LogAnalysisPanel";
import { AgentTaskPanel } from "../features/tasks/AgentTaskPanel";
import { DiagnosisPanel } from "../features/diagnose/DiagnosisPanel";
import { UpdatePanel } from "../features/updates/UpdatePanel";
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
        <div className={`connection-chip connection-chip--${state.kind}`} role="status">
          <StatusMark state={state.kind} />
          {state.kind === "connected"
            ? "本地服务已连接"
            : state.kind === "starting"
              ? "本地服务启动中"
              : "本地服务未连接"}
        </div>
      </header>

      {state.kind === "connected" ? (
        <section className="dashboard" aria-labelledby="workspace-title">
          <div className="dashboard-intro">
            <div>
              <h1 id="workspace-title">设备概览</h1>
              <p>用一次可审计的只读扫描，建立这台 Windows 电脑的当前状态快照。</p>
            </div>
            <dl className="connection-details">
              <div>
                <dt>本地后端</dt>
                <dd>{state.connection.health.backend_version}</dd>
              </div>
              <div>
                <dt>API</dt>
                <dd>{state.connection.health.api_version}</dd>
              </div>
              <div>
                <dt>网络边界</dt>
                <dd>127.0.0.1</dd>
              </div>
            </dl>
          </div>
          <UpdatePanel />
          <DiagnosisPanel client={state.connection.client} />
          <QuickScanPanel client={state.connection.client} />
          <LogAnalysisPanel client={state.connection.client} />
          <AgentTaskPanel client={state.connection.client} />
        </section>
      ) : (
        <section className="workspace" aria-labelledby="workspace-title">
          <div className="intro">
            <h1 id="workspace-title">正在准备</h1>
            <p>安全启动本地服务后，即可进行只读系统扫描。所有结果默认保存在这台电脑上。</p>
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
      )}

    </main>
  );
}
