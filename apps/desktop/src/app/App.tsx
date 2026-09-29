import { useCallback, useEffect, useState } from "react";

import { DiagnosisPanel } from "../features/diagnose/DiagnosisPanel";
import { LogAnalysisPanel } from "../features/logs/LogAnalysisPanel";
import { QuickScanPanel } from "../features/scans/QuickScanPanel";
import { SettingsView } from "../features/settings/SettingsView";
import { AgentTaskPanel } from "../features/tasks/AgentTaskPanel";
import {
  BackendConnectionError,
  connectToBackend,
  restartBackendLauncher,
  type BackendConnection,
} from "../services/backend";
import { ConnectionGate } from "./ConnectionGate";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { DEFAULT_VIEW, viewDefinition, type ViewId } from "./navigation";

type ConnectionState =
  | { kind: "starting" }
  | { kind: "connected"; connection: BackendConnection }
  | { kind: "disconnected"; message: string; correlationId?: string };

export function App() {
  const [state, setState] = useState<ConnectionState>({ kind: "starting" });
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<ViewId>(DEFAULT_VIEW);

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

  if (state.kind !== "connected") {
    return <ConnectionGate state={state} onRetry={reconnect} />;
  }

  const definition = viewDefinition(view);
  const { client } = state.connection;

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        跳到主内容
      </a>
      <Sidebar view={view} onSelect={setView} connection={state.connection} />

      <div className="workspace">
        <Topbar definition={definition} connection={state.connection} />

        <main className="content" id="main-content" tabIndex={-1}>
          <p className="sr-only" role="status">
            {definition.title}已打开
          </p>
          <div className="content__inner">
            <div className="content__stack">
              {/* Only the active section is mounted, so at most one collector
                  polls or streams at a time. Each panel reloads the latest
                  record from the backend when it mounts. */}
              {view === "diagnose" && <DiagnosisPanel client={client} />}
              {view === "scan" && <QuickScanPanel client={client} />}
              {view === "logs" && <LogAnalysisPanel client={client} />}
              {view === "runtime" && <AgentTaskPanel client={client} />}
              {view === "settings" && <SettingsView connection={state.connection} />}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
