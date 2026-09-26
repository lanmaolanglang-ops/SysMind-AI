import { useCallback, useEffect, useState } from "react";

import { QuickScanPanel } from "../features/scans/QuickScanPanel";
import { LogAnalysisPanel } from "../features/logs/LogAnalysisPanel";
import { AgentTaskPanel } from "../features/tasks/AgentTaskPanel";
import { DiagnosisPanel } from "../features/diagnose/DiagnosisPanel";
import { UpdatePanel } from "../features/updates/UpdatePanel";
import { SettingsPanel } from "../features/settings/SettingsPanel";
import { PanelErrorBoundary } from "../components/PanelErrorBoundary";
import { HistoryPanel } from "../features/history/HistoryPanel";
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

type WorkspaceView = "diagnose" | "scan" | "logs" | "history" | "settings" | "agent" | "updates";

const WORKSPACES: Array<{
  id: WorkspaceView;
  label: string;
  description: string;
  group: "常用" | "详细检查" | "管理";
}> = [
  { id: "diagnose", label: "问题诊断", description: "描述现象，查看证据与建议", group: "常用" },
  { id: "scan", label: "设备扫描", description: "查看此刻的设备状态", group: "常用" },
  { id: "history", label: "记录与报告", description: "回看结果与审计记录", group: "常用" },
  { id: "logs", label: "事件日志", description: "分析崩溃与系统事件", group: "详细检查" },
  { id: "agent", label: "受限 Agent", description: "运行指定的只读工具", group: "详细检查" },
  { id: "settings", label: "模型与隐私", description: "设置供应商与数据边界", group: "管理" },
  { id: "updates", label: "应用更新", description: "检查签名更新", group: "管理" },
];

function StatusMark({ state }: { state: ConnectionState["kind"] }) {
  return <span className={`status-mark status-mark--${state}`} aria-hidden="true" />;
}

export function App() {
  const [state, setState] = useState<ConnectionState>({ kind: "starting" });
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<WorkspaceView>("diagnose");
  const currentWorkspace = WORKSPACES.find((item) => item.id === view) ?? {
    id: "diagnose", label: "问题诊断", description: "描述现象，查看证据与建议", group: "常用",
  };

  const reconnect = useCallback(() => {
    setState({ kind: "starting" });
    void restartBackendLauncher()
      .then(() => {
        setAttempt((value) => value + 1);
      })
      .catch(() => {
        setState({
          kind: "disconnected",
          message: "无法重新启动本地服务。请重新打开应用；若问题持续，请记录错误信息以便排查。",
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
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup" aria-label="SysMind AI">
          <span className="brand-symbol" aria-hidden="true">S</span>
          <span>SysMind AI</span>
        </div>
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
        <div className="desktop-layout">
          <aside className="workspace-sidebar" aria-label="工作台导航">
            <nav aria-label="主要功能">
              {(["常用", "详细检查", "管理"] as const).map((group) => (
                <div className="nav-group" key={group}>
                  <p>{group}</p>
                  {WORKSPACES.filter((item) => item.group === group).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      aria-current={view === item.id ? "page" : undefined}
                      onClick={() => setView(item.id)}
                    >
                      <strong>{item.label}</strong>
                      <small>{item.description}</small>
                    </button>
                  ))}
                </div>
              ))}
            </nav>
            <details className="runtime-disclosure">
              <summary>本地运行信息</summary>
              <dl>
                <div><dt>后端版本</dt><dd>{state.connection.health.backend_version}</dd></div>
                <div><dt>API 版本</dt><dd>{state.connection.health.api_version}</dd></div>
                <div><dt>监听地址</dt><dd>127.0.0.1</dd></div>
              </dl>
            </details>
          </aside>
          <main className="dashboard" aria-labelledby="workspace-title">
            <div className="workspace-intro">
              <h1 id="workspace-title">{currentWorkspace.label}</h1>
              <p>{currentWorkspace.description}</p>
            </div>
            {view === "diagnose" && <PanelErrorBoundary name="问题诊断"><DiagnosisPanel client={state.connection.client} /></PanelErrorBoundary>}
            {view === "scan" && <PanelErrorBoundary name="设备扫描"><QuickScanPanel client={state.connection.client} /></PanelErrorBoundary>}
            {view === "history" && <PanelErrorBoundary name="记录与报告"><HistoryPanel client={state.connection.client} /></PanelErrorBoundary>}
            {view === "logs" && <PanelErrorBoundary name="事件日志"><LogAnalysisPanel client={state.connection.client} /></PanelErrorBoundary>}
            {view === "agent" && <PanelErrorBoundary name="受限 Agent"><AgentTaskPanel client={state.connection.client} /></PanelErrorBoundary>}
            {view === "settings" && <PanelErrorBoundary name="模型与隐私"><SettingsPanel client={state.connection.client} /></PanelErrorBoundary>}
            {view === "updates" && <PanelErrorBoundary name="应用更新"><UpdatePanel /></PanelErrorBoundary>}
          </main>
        </div>
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
              <h2>正在准备本地诊断服务</h2>
              <p>首次启动可能需要稍长时间，请保持应用打开。</p>
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

    </div>
  );
}
