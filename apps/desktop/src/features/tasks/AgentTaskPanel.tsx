import { useEffect, useRef, useState } from "react";

import { ApiClientError, type ApiClient, type SseEvent } from "../../services/api-client";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Notice } from "../../ui/Notice";
import { Panel, PanelSection } from "../../ui/Panel";
import {
  cancelAgentTask,
  getAgentTask,
  getRecentAgentTasks,
  getToolCatalog,
  startAgentTask,
  streamAgentTaskEvents,
  type AgentTask,
  type AgentTaskEventData,
  type ToolDescriptor,
} from "../../services/agent-tasks";

const TERMINAL = new Set([
  "completed",
  "waiting_user_input",
  "cancelled",
  "failed",
  "timed_out",
  "interrupted",
]);

const STATUS_COPY: Record<string, string> = {
  created: "任务已创建",
  planning: "正在规划受限步骤",
  running_tools: "正在运行只读工具",
  analyzing: "正在调用离线模拟 Provider",
  waiting_user_input: "任务需要更多信息",
  completed: "Agent Runtime 自检完成",
  cancelling: "正在取消任务",
  cancelled: "任务已取消",
  failed: "任务已安全停止",
  timed_out: "任务已超时",
  interrupted: "任务因服务重启而中断",
};

function errorCopy(error: unknown): string {
  if (error instanceof ApiClientError) {
    const issue = error.correlationId ? `（问题编号 ${error.correlationId}）` : "";
    return `Agent Runtime 暂时不可用${issue}。`;
  }
  return "无法完成 Agent Runtime 请求。";
}

function eventCopy(event: SseEvent<AgentTaskEventData>): string {
  if (event.event === "tool.started") return `开始工具：${event.data.tool ?? "未知"}`;
  if (event.event === "tool.completed") return `工具完成：${event.data.tool ?? "未知"}`;
  if (event.event === "tool.failed") return `工具未完成：${event.data.tool ?? "未知"}`;
  if (event.event === "provider.started") return "Provider 推理开始";
  if (event.event === "provider.completed") {
    return `Provider 动作：${event.data.action ?? "完成"}`;
  }
  if (event.data.status) return STATUS_COPY[event.data.status] ?? event.data.status;
  return event.event;
}

export function AgentTaskPanel({ client }: { client: ApiClient }) {
  const [task, setTask] = useState<AgentTask | null>(null);
  const [tools, setTools] = useState<ToolDescriptor[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [goal, setGoal] = useState("验证受限 Agent Runtime、任务事件与审计链路");
  const [events, setEvents] = useState<Array<SseEvent<AgentTaskEventData>>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastEventId = useRef<string | undefined>(undefined);
  const active = task !== null && !TERMINAL.has(task.status);
  const activeTaskId = active ? task.id : null;

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      getToolCatalog(client, controller.signal),
      getRecentAgentTasks(client, controller.signal),
    ])
      .then(([catalog, recent]) => {
        setTools(catalog.items);
        setTask(recent.items[0] ?? null);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(errorCopy(reason));
      });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!activeTaskId) return;
    const controller = new AbortController();
    const follow = async () => {
      while (!controller.signal.aborted) {
        try {
          await streamAgentTaskEvents(
            client,
            activeTaskId,
            (event) => {
              if (event.id) lastEventId.current = event.id;
              setEvents((current) => {
                if (event.id && current.some((item) => item.id === event.id)) return current;
                return [...current, event].slice(-50);
              });
              if (event.data.status || event.data.progress !== undefined) {
                setTask((current) =>
                  current
                    ? {
                        ...current,
                        ...(event.data.status ? { status: event.data.status } : {}),
                        ...(event.data.progress !== undefined
                          ? { progress: event.data.progress }
                          : {}),
                      }
                    : current,
                );
              }
            },
            controller.signal,
            lastEventId.current,
          );
          if (controller.signal.aborted) return;
          const latest = await getAgentTask(client, activeTaskId, controller.signal);
          setTask(latest);
          setError(null);
          if (TERMINAL.has(latest.status)) return;
        } catch (reason: unknown) {
          if (controller.signal.aborted) return;
          setError(errorCopy(reason));
        }
        await new Promise((resolve) => window.setTimeout(resolve, 350));
      }
    };
    void follow();
    return () => controller.abort();
  }, [activeTaskId, client]);

  const toggleTool = (qualifiedName: string) => {
    setSelectedTools((current) =>
      current.includes(qualifiedName)
        ? current.filter((item) => item !== qualifiedName)
        : [...current, qualifiedName],
    );
  };

  const start = () => {
    setBusy(true);
    setError(null);
    setEvents([]);
    lastEventId.current = undefined;
    void startAgentTask(client, goal, selectedTools)
      .then(setTask)
      .catch((reason: unknown) => setError(errorCopy(reason)))
      .finally(() => setBusy(false));
  };

  const cancel = () => {
    if (!task) return;
    setBusy(true);
    void cancelAgentTask(client, task.id)
      .then(setTask)
      .catch((reason: unknown) => setError(errorCopy(reason)))
      .finally(() => setBusy(false));
  };

  const showResults = events.length > 0 || (task !== null && TERMINAL.has(task.status));

  return (
    <Panel
      titleId="agent-runtime-title"
      title="受限 Agent Runtime"
      description="Phase 3 使用离线 Fake Provider 验证预算、工具白名单、SSE 和审计；这里不会生成诊断报告。"
      badge={<Badge tone="accent">Fake Provider · 离线</Badge>}
    >
      <label className="field goal">
        <span className="field__label">框架测试目标</span>
        <input
          className="control"
          value={goal}
          maxLength={1000}
          onChange={(event) => setGoal(event.target.value)}
        />
      </label>

      <fieldset className="tools">
        <legend className="field__label">允许模型看到的只读工具（可选）</legend>
        <div className="tools__options">
          {tools.map((tool) => (
            <label className="option option--boxed" key={tool.qualified_name}>
              <input
                type="checkbox"
                checked={selectedTools.includes(tool.qualified_name)}
                onChange={() => toggleTool(tool.qualified_name)}
              />
              <span>{tool.name}</span>
              {tool.sensitivity.length > 0 && <small>敏感</small>}
            </label>
          ))}
        </div>
      </fieldset>

      {error && (
        <Notice tone="danger" role="alert" className="panel__notice">
          {error}
        </Notice>
      )}

      <div className="action-row">
        {active && task ? (
          <>
            <div className="progress-row" role="status">
              <div className="progress-row__label">
                <strong>{STATUS_COPY[task.status]}</strong>
              </div>
              <progress className="progress" value={task.progress} max="100" aria-label="Agent 任务进度" />
            </div>
            <Button variant="ghost" busy={busy} onClick={cancel} disabled={busy}>
              {busy ? "正在取消…" : "取消任务"}
            </Button>
          </>
        ) : (
          <Button variant="primary" busy={busy} onClick={start} disabled={busy || !goal.trim()}>
            {busy ? "正在创建…" : task ? "重新自检" : "运行离线自检"}
          </Button>
        )}
      </div>

      {showResults && (
        <PanelSection>
          {task && TERMINAL.has(task.status) && (
            <div className="result-head">
              <span className="result-head__state">
                <strong>{STATUS_COPY[task.status]}</strong>
              </span>
              <span className="row__meta">
                {task.tool_call_count} 次工具调用 · {task.current_round} 轮
              </span>
            </div>
          )}

          {events.length > 0 && (
            <ol className="timeline" aria-label="Agent 任务事件">
              {events.map((event, index) => (
                <li key={event.id ?? `${event.event}-${index}`}>
                  <span className="timeline__text">{eventCopy(event)}</span>
                  <time className="timeline__time">
                    {new Date(event.data.created_at).toLocaleTimeString("zh-CN")}
                  </time>
                </li>
              ))}
            </ol>
          )}

          {task?.final_output && <p className="output">{task.final_output}</p>}

          {task?.failure_message && (
            <Notice tone="warn" title="任务未完成" className="panel__notice">
              {task.failure_message}
            </Notice>
          )}
        </PanelSection>
      )}
    </Panel>
  );
}
