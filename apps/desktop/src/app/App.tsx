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

type WorkspaceView = "solve" | "history" | "advanced";
type AdvancedTool = "scan" | "logs" | "settings" | "agent";

function StatusMark({ state }: { state: ConnectionState["kind"] }) {
  return <span className={`status-mark status-mark--${state}`} aria-hidden="true" />;
}

export function App() {
  const [state, setState] = useState<ConnectionState>({ kind: "starting" });
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<WorkspaceView>("solve");
  const [advancedTool, setAdvancedTool] = useState<AdvancedTool>("scan");

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
              <p>先说出你遇到的现象，SysMind 会检查证据并告诉你下一步怎么做。</p>
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
          <PanelErrorBoundary name="更新"><UpdatePanel /></PanelErrorBoundary>
          <nav className="workspace-nav" aria-label="主要功能">
            <button
              type="button"
              aria-current={view === "solve" ? "page" : undefined}
              onClick={() => setView("solve")}
            >
              解决电脑问题
              <small>从描述现象开始</small>
            </button>
            <button
              type="button"
              aria-current={view === "history" ? "page" : undefined}
              onClick={() => setView("history")}
            >
              记录与报告
              <small>回看检查结果</small>
            </button>
            <button
              type="button"
              aria-current={view === "advanced" ? "page" : undefined}
              onClick={() => setView("advanced")}
            >
              高级工具
              <small>手动扫描与设置</small>
            </button>
          </nav>

          {view === "solve" && (
            <PanelErrorBoundary name="问题诊断">
              <DiagnosisPanel client={state.connection.client} />
            </PanelErrorBoundary>
          )}

          {view === "history" && (
            <PanelErrorBoundary name="记录与报告">
              <HistoryPanel client={state.connection.client} />
            </PanelErrorBoundary>
          )}

          {view === "advanced" && (
            <section className="advanced-workspace" aria-labelledby="advanced-title">
              <header>
                <div>
                  <h2 id="advanced-title">高级工具</h2>
                  <p>通常不需要手动使用这些功能。需要更详细的检查或配置时再进入。</p>
                </div>
              </header>
              <div className="advanced-tool-switcher" role="group" aria-label="选择高级工具">
                <button type="button" aria-pressed={advancedTool === "scan"} onClick={() => setAdvancedTool("scan")}>设备扫描</button>
                <button type="button" aria-pressed={advancedTool === "logs"} onClick={() => setAdvancedTool("logs")}>事件日志</button>
                <button type="button" aria-pressed={advancedTool === "settings"} onClick={() => setAdvancedTool("settings")}>模型与隐私</button>
                <button type="button" aria-pressed={advancedTool === "agent"} onClick={() => setAdvancedTool("agent")}>开发者 Agent</button>
              </div>
              {advancedTool === "scan" && <PanelErrorBoundary name="设备扫描"><QuickScanPanel client={state.connection.client} /></PanelErrorBoundary>}
              {advancedTool === "logs" && <PanelErrorBoundary name="事件日志"><LogAnalysisPanel client={state.connection.client} /></PanelErrorBoundary>}
              {advancedTool === "settings" && <PanelErrorBoundary name="模型与隐私"><SettingsPanel client={state.connection.client} /></PanelErrorBoundary>}
              {advancedTool === "agent" && <PanelErrorBoundary name="开发者 Agent"><AgentTaskPanel client={state.connection.client} /></PanelErrorBoundary>}
            </section>
          )}
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

    </main>
  );
}
