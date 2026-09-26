import { useEffect, useRef, useState } from "react";

import { ApiClientError, type ApiClient, type SseEvent } from "../../services/api-client";
import { formatLocalTime } from "../../services/time";
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
  analyzing: "正在生成工具结果说明",
  waiting_user_input: "需要补充信息后新建任务",
  completed: "只读工具自检完成",
  cancelling: "正在取消任务",
  cancelled: "任务已取消",
  failed: "任务已安全停止",
  timed_out: "任务已超时",
  interrupted: "任务因服务重启而中断",
};

const TOOL_LABELS: Record<string, string> = {
  "system.os": "Windows 版本",
  "system.cpu": "处理器状态",
  "system.gpu": "显卡与驱动",
  "system.memory": "内存状态",
  "system.disks": "磁盘空间",
  "process.snapshot": "进程快照",
  "process.high_usage": "高占用进程",
  "log.windows_event.query": "Windows 事件",
  "log.crash.analyze": "应用崩溃记录",
  "network.proxy.get_config": "代理配置",
  "startup.list": "启动项清单",
  "startup.analyze": "启动项分析",
  "service.list": "服务清单",
  "service.analyze": "服务状态分析",
};

function toolLabel(name: string) {
  return TOOL_LABELS[name] ?? name;
}

function errorCopy(error: unknown): string {
  if (error instanceof ApiClientError) {
    const issue = error.correlationId ? `（问题编号 ${error.correlationId}）` : "";
    return `只读工具任务暂时不可用${issue}。`;
  }
  return "无法完成只读工具请求。";
}

function eventCopy(event: SseEvent<AgentTaskEventData>): string {
  if (event.event === "tool.started") return `开始检查：${toolLabel(event.data.tool ?? "未知")}`;
  if (event.event === "tool.completed") return `检查完成：${toolLabel(event.data.tool ?? "未知")}`;
  if (event.event === "tool.failed") return `检查未完成：${toolLabel(event.data.tool ?? "未知")}`;
  if (event.event === "provider.started") return "模型正在分析结果";
  if (event.event === "provider.completed") {
    return `模型步骤：${event.data.action ?? "完成"}`;
  }
  if (event.data.status) return STATUS_COPY[event.data.status] ?? event.data.status;
  return event.event;
}

export function AgentTaskPanel({ client }: { client: ApiClient }) {
  const [task, setTask] = useState<AgentTask | null>(null);
  const [tools, setTools] = useState<ToolDescriptor[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [goal, setGoal] = useState("验证只读工具、任务事件与审计记录");
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
        if (controller.signal.aborted) return;
        setTools(catalog.items);
        setTask((current) => current ?? recent.items[0] ?? null);
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
          <h2 id="agent-runtime-title">只读工具自检</h2>
          <p>模型只能在限定次数和时间内调用你选中的只读工具。这里不会生成诊断报告或更改系统设置。</p>
        </div>
        <span className="runtime-badge">
          {task?.provider === "openai_compatible" ? "在线模型" : "本地模拟模型 · 离线"}
        </span>
      </div>

      <label className="agent-goal">
        这次要检查什么
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
              <span title={tool.qualified_name}>{toolLabel(tool.name)}</span>
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
            {busy ? "正在创建…" : task ? "重新自检" : "运行只读自检"}
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
                  <time>{formatLocalTime(event.data.created_at)}</time>
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
