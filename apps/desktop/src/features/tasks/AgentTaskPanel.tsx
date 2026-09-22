import { useEffect, useRef, useState } from "react";

import { ApiClientError, type ApiClient, type SseEvent } from "../../services/api-client";
import {
  cancelAgentTask,
  agentTaskReconnectDelay,
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
  analyzing: "正在调用受控 Provider",
  waiting_user_input: "需要补充信息后新建任务",
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
  const activeTaskIdRef = useRef<string | null>(null);
  const active = task !== null && !TERMINAL.has(task.status);
  const activeTaskId = active ? task.id : null;

  useEffect(() => {
    activeTaskIdRef.current = activeTaskId;
  }, [activeTaskId]);

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
    const expectedTaskId = activeTaskId;
    const controller = new AbortController();
    const follow = async () => {
      let failedAttempts = 0;
      while (!controller.signal.aborted) {
        try {
          await streamAgentTaskEvents(
            client,
            activeTaskId,
            (event) => {
              // A stream that belonged to a previous task can deliver one last event
              // just before it is aborted; never merge it into the active task's state.
              if (expectedTaskId !== activeTaskIdRef.current) return;
              if (event.id) lastEventId.current = event.id;
              setEvents((current) => {
                if (event.id && current.some((item) => item.id === event.id)) return current;
                return [...current, event].slice(-50);
              });
              if (event.data.status || event.data.progress !== undefined) {
                setTask((current) =>
                  current && current.id === expectedTaskId
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
          if (expectedTaskId !== activeTaskIdRef.current) return;
          setTask(latest);
          setError(null);
          failedAttempts = 0;
          if (TERMINAL.has(latest.status)) return;
        } catch (reason: unknown) {
          if (controller.signal.aborted) return;
          setError(errorCopy(reason));
          failedAttempts += 1;
        }
        const delay = agentTaskReconnectDelay(failedAttempts || 1);
        await new Promise((resolve) => window.setTimeout(resolve, delay));
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

  return (
    <section className="agent-panel" aria-labelledby="agent-runtime-title">
      <div className="agent-heading">
        <div>
          <h2 id="agent-runtime-title">受限 Agent Runtime</h2>
          <p>Provider 只能在预算内调用版本化只读工具；这里不会生成诊断报告或执行状态变更。</p>
        </div>
        <span className="runtime-badge">
          {task?.provider === "openai_compatible" ? "真实 Provider" : "Fake Provider · 离线"}
        </span>
      </div>

      <label className="agent-goal">
        框架测试目标
        <input value={goal} maxLength={1000} onChange={(event) => setGoal(event.target.value)} />
      </label>

      <fieldset className="agent-tools">
        <legend>允许模型看到的只读工具（可选）</legend>
        <div>
          {tools.map((tool) => (
            <label key={tool.qualified_name}>
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

      {error && <div className="inline-error" role="alert">{error}</div>}

      <div className="agent-action-row">
        {active && task ? (
          <>
            <div className="agent-progress" role="status">
              <strong>{STATUS_COPY[task.status]}</strong>
              <progress value={task.progress} max="100" aria-label="Agent 任务进度" />
            </div>
            <button className="text-action" type="button" onClick={cancel} disabled={busy}>
              {busy ? "正在取消…" : "取消任务"}
            </button>
          </>
        ) : (
          <button
            className="primary-action"
            type="button"
            onClick={start}
            disabled={busy || !goal.trim()}
          >
            {busy ? "正在创建…" : task ? "重新自检" : "运行离线自检"}
          </button>
        )}
      </div>

      {task?.status === "waiting_user_input" && (
        <button
          type="button"
          onClick={() => {
            setGoal((current) => `${current}\n补充信息：`);
            setTask(null);
            setEvents([]);
          }}
        >
          带入上下文新建任务
        </button>
      )}

      {(events.length > 0 || (task && TERMINAL.has(task.status))) && (
        <div className="agent-results">
          {task && TERMINAL.has(task.status) && (
            <div className="result-status">
              <div><strong>{STATUS_COPY[task.status]}</strong></div>
              <span>{task.tool_call_count} 次工具调用 · {task.current_round} 轮</span>
            </div>
          )}
          {events.length > 0 && (
            <ol className="agent-timeline" aria-label="Agent 任务事件">
              {events.map((event, index) => (
                <li key={event.id ?? `${event.event}-${index}`}>
                  <span>{eventCopy(event)}</span>
                  <time>{new Date(event.data.created_at).toLocaleTimeString("zh-CN")}</time>
                </li>
              ))}
            </ol>
          )}
          {task?.final_output && <p className="agent-output">{task.final_output}</p>}
          {task?.failure_message && (
            <div className="scan-warnings"><strong>{task.failure_message}</strong></div>
          )}
        </div>
      )}
    </section>
  );
}
