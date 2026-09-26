import { useEffect, useMemo, useState } from "react";

import { ApiClientError, type ApiClient } from "../../services/api-client";
import {
  cancelLogAnalysis,
  getLogAnalysis,
  getRecentLogAnalyses,
  startLogAnalysis,
  type EventLevel,
  type LogAnalysisRecord,
  type LogChannel,
} from "../../services/log-analyses";

const TERMINAL = new Set(["completed", "partial", "cancelled", "failed"]);
const LEVELS: Array<{ value: EventLevel; label: string }> = [
  { value: "critical", label: "严重" },
  { value: "error", label: "错误" },
  { value: "warning", label: "警告" },
  { value: "information", label: "信息" },
];

function statusCopy(record: LogAnalysisRecord): string {
  if (record.status === "completed") return "日志分析完成";
  if (record.status === "partial") return "分析完成，部分通道不可用";
  if (record.status === "cancelled") return "日志分析已取消";
  if (record.status === "failed") return "日志分析失败";
  if (record.current_step?.includes("Application")) return "正在读取应用程序日志";
  if (record.current_step?.includes("System")) return "正在读取系统日志";
  return "正在聚合应用崩溃";
}

function errorCopy(error: unknown): string {
  return error instanceof ApiClientError
    ? `日志服务暂时不可用${error.correlationId ? `（问题编号 ${error.correlationId}）` : ""}。`
    : "无法完成本地日志分析请求。";
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function LogAnalysisPanel({ client }: { client: ApiClient }) {
  const [record, setRecord] = useState<LogAnalysisRecord | null>(null);
  const [channels, setChannels] = useState<LogChannel[]>(["Application", "System"]);
  const [levels, setLevels] = useState<EventLevel[]>(["critical", "error", "warning"]);
  const [lookback, setLookback] = useState(24);
  const [eventIds, setEventIds] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = record !== null && !TERMINAL.has(record.status);
  const activeId = active ? record.id : null;

  useEffect(() => {
    const controller = new AbortController();
    void getRecentLogAnalyses(client, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) {
          setRecord((current) => current ?? response.items[0] ?? null);
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(errorCopy(reason));
      });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController();
    let disposed = false;
    let timer: number | undefined;
    let delay = 800;
    const poll = () => {
      void getLogAnalysis(client, activeId, controller.signal)
        .then((next) => {
          setRecord((current) => (current?.id === activeId ? next : current));
          setError(null);
          delay = 800;
        })
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) {
            setError(errorCopy(reason));
            delay = Math.min(delay * 2, 4_000);
          }
        })
        .finally(() => {
          if (!disposed) timer = window.setTimeout(poll, delay);
        });
    };
    timer = window.setTimeout(poll, delay);
    return () => {
      disposed = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeId, client]);

  const eventIdFilter = useMemo(() => {
    const values = eventIds.trim().split(/[，,\s]+/).filter(Boolean);
    if (values.length > 32) {
      return { ids: [] as number[], error: "事件 ID 最多输入 32 个。" };
    }
    if (values.some((value) => !/^\d+$/.test(value) || Number(value) > 65535)) {
      return { ids: [] as number[], error: "事件 ID 只能是 0–65535 的整数，请用逗号或空格分隔。" };
    }
    return { ids: values.map(Number), error: null };
  }, [eventIds]);

  const toggleChannel = (channel: LogChannel) => {
    setChannels((current) =>
      current.includes(channel)
        ? current.length === 1
          ? current
          : current.filter((item) => item !== channel)
        : [...current, channel],
    );
  };

  const toggleLevel = (level: EventLevel) => {
    setLevels((current) =>
      current.includes(level)
        ? current.length === 1
          ? current
          : current.filter((item) => item !== level)
        : [...current, level],
    );
  };

  const start = () => {
    if (eventIdFilter.error) return;
    setBusy(true);
    setError(null);
    void startLogAnalysis(client, {
      channels,
      lookback_hours: lookback,
      levels,
      event_ids: eventIdFilter.ids,
      max_events: 100,
    })
      .then(setRecord)
      .catch((reason: unknown) => setError(errorCopy(reason)))
      .finally(() => setBusy(false));
  };

  const cancel = () => {
    if (!record) return;
    setBusy(true);
    void cancelLogAnalysis(client, record.id)
      .then(setRecord)
      .catch((reason: unknown) => setError(errorCopy(reason)))
      .finally(() => setBusy(false));
  };

  return (
    <section className="log-panel" aria-labelledby="log-analysis-title">
      <div className="log-heading">
        <div>
          <h2 id="log-analysis-title">分析 Windows 事件日志</h2>
          <p>仅查询选定通道和时间窗；保存脱敏摘要，不保存原始事件内容。</p>
        </div>
        <span className="sensitivity-label">只读 · 含敏感数据</span>
      </div>

      <div className="log-filters" aria-label="事件日志筛选条件">
        <fieldset>
          <legend>通道</legend>
          {(["Application", "System"] as LogChannel[]).map((channel) => (
            <label key={channel}>
              <input
                type="checkbox"
                checked={channels.includes(channel)}
                onChange={() => toggleChannel(channel)}
              />
              {channel === "Application" ? "应用程序" : "系统"}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>级别</legend>
          {LEVELS.map((level) => (
            <label key={level.value}>
              <input
                type="checkbox"
                checked={levels.includes(level.value)}
                onChange={() => toggleLevel(level.value)}
              />
              {level.label}
            </label>
          ))}
        </fieldset>
        <label className="filter-control">
          时间范围
          <select value={lookback} onChange={(event) => setLookback(Number(event.target.value))}>
            <option value={6}>最近 6 小时</option>
            <option value={24}>最近 24 小时</option>
            <option value={72}>最近 3 天</option>
            <option value={168}>最近 7 天</option>
          </select>
        </label>
        <label className="filter-control">
          事件 ID（可选）
          <input
            value={eventIds}
            onChange={(event) => setEventIds(event.target.value)}
            placeholder="例如 1000, 1001"
            aria-invalid={Boolean(eventIdFilter.error)}
            aria-describedby={eventIdFilter.error ? "event-id-error" : undefined}
          />
          {eventIdFilter.error && <span className="field-error" id="event-id-error" role="alert">{eventIdFilter.error}</span>}
        </label>
      </div>

      {error && <div className="inline-error" role="alert">{error}</div>}

      <div className="log-action-row">
        {active && record ? (
          <>
            <div className="log-progress" role="status">
              <strong>{statusCopy(record)}</strong>
              <progress value={record.progress} max="100" aria-label="日志分析进度" />
            </div>
            <button className="text-action" type="button" onClick={cancel} disabled={busy}>
              {busy ? "正在取消…" : "取消分析"}
            </button>
          </>
        ) : (
          <button className="primary-action" type="button" onClick={start} disabled={busy || Boolean(eventIdFilter.error)}>
            {busy ? "正在创建…" : record ? "重新分析" : "开始分析"}
          </button>
        )}
      </div>

      {record && TERMINAL.has(record.status) && (
        <div className="log-results">
          <div className="result-status">
            <div><strong>{statusCopy(record)}</strong></div>
            {record.finished_at && <time>{formatTime(record.finished_at)}</time>}
          </div>
          {record.summary && (
            <>
              <div className="section-heading">
                <h3>应用崩溃聚合</h3>
                <span>{record.summary.crash_groups.length} 组 · {record.summary.event_count} 条事件</span>
              </div>
              {record.summary.crash_groups.length ? (
                <div className="crash-list">
                  {record.summary.crash_groups.map((group) => (
                    <div className="crash-row" key={`${group.application}-${group.faulting_module}-${group.exception_code}`}>
                      <strong>{group.application}</strong>
                      <span>{group.count} 次</span>
                      <small>
                        {group.faulting_module ?? "未知模块"}
                        {group.exception_code ? ` · ${group.exception_code}` : ""}
                      </small>
                    </div>
                  ))}
                </div>
              ) : <p className="quiet-result">所选范围内未聚合到应用崩溃事件。</p>}

              <div className="section-heading event-heading">
                <h3>常见错误与警告</h3>
                <span>{record.summary.event_groups.length} 组</span>
              </div>
              <div className="crash-list">
                {record.summary.event_groups.slice(0, 10).map((group) => (
                  <div className="crash-row" key={`${group.channel}-${group.provider}-${group.event_id}-${group.level}`}>
                    <strong>{group.provider} · ID {group.event_id}</strong>
                    <span>{group.count} 次</span>
                    <small>{group.channel} · {group.sample_summary}</small>
                  </div>
                ))}
              </div>

              <div className="section-heading event-heading">
                <h3>脱敏事件证据</h3>
                <span>最多显示 20 条</span>
              </div>
              <div className="event-list">
                {record.summary.events.slice(0, 20).map((item, index) => (
                  <article className="event-row" key={`${item.channel}-${item.event_id}-${item.timestamp}-${index}`}>
                    <div>
                      <strong>{item.provider}</strong>
                      <span>{item.channel} · ID {item.event_id} · {formatTime(item.timestamp)}</span>
                    </div>
                    <p>{item.summary}</p>
                  </article>
                ))}
              </div>
            </>
          )}
          {record.failures.length > 0 && (
            <div className="scan-warnings">
              <strong>部分查询未完成</strong>
              <ul>{record.failures.map((failure) => <li key={failure.tool}>{failure.message}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
