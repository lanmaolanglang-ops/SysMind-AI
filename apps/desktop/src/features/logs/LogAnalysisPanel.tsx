import { useEffect, useMemo, useState } from "react";

import { ApiClientError, type ApiClient } from "../../services/api-client";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { EmptyState } from "../../ui/EmptyState";
import { Notice } from "../../ui/Notice";
import { Panel, PanelSection } from "../../ui/Panel";
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
      // An analysis started while this request was in flight must not be
      // replaced by the older history snapshot.
      .then((response) => setRecord((current) => current ?? response.items[0] ?? null))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(errorCopy(reason));
      });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController();
    // Only one progress request may be outstanding, so a slow response cannot
    // land after a newer one and roll the progress backwards.
    let inFlight = false;
    const timer = window.setInterval(() => {
      if (inFlight) return;
      inFlight = true;
      void getLogAnalysis(client, activeId, controller.signal)
        .then((next) => {
          setRecord(next);
          setError(null);
        })
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) setError(errorCopy(reason));
        })
        .finally(() => {
          inFlight = false;
        });
    }, 350);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [activeId, client]);

  const parsedEventIds = useMemo(
    () =>
      eventIds
        .split(/[，,\s]+/)
        .filter(Boolean)
        .map(Number)
        .filter((value) => Number.isInteger(value) && value >= 0 && value <= 65535)
        .slice(0, 32),
    [eventIds],
  );

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
    setBusy(true);
    setError(null);
    void startLogAnalysis(client, {
      channels,
      lookback_hours: lookback,
      levels,
      event_ids: parsedEventIds,
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
    <Panel
      titleId="log-analysis-title"
      title="分析 Windows 事件日志"
      description="仅查询选定通道和时间窗；保存脱敏摘要，不保存原始事件内容。"
      badge={<Badge tone="warn">只读 · 含敏感数据</Badge>}
    >
      <div className="filters" aria-label="事件日志筛选条件">
        <fieldset className="filters__group">
          <legend className="field__label">通道</legend>
          <div className="filters__options">
            {(["Application", "System"] as LogChannel[]).map((channel) => (
              <label className="option" key={channel}>
                <input
                  type="checkbox"
                  checked={channels.includes(channel)}
                  onChange={() => toggleChannel(channel)}
                />
                <span>{channel === "Application" ? "应用程序" : "系统"}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="filters__group">
          <legend className="field__label">级别</legend>
          <div className="filters__options">
            {LEVELS.map((level) => (
              <label className="option" key={level.value}>
                <input
                  type="checkbox"
                  checked={levels.includes(level.value)}
                  onChange={() => toggleLevel(level.value)}
                />
                <span>{level.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="field">
          <span className="field__label">时间范围</span>
          <select
            className="control"
            value={lookback}
            onChange={(event) => setLookback(Number(event.target.value))}
          >
            <option value={6}>最近 6 小时</option>
            <option value={24}>最近 24 小时</option>
            <option value={72}>最近 3 天</option>
            <option value={168}>最近 7 天</option>
          </select>
        </label>

        <label className="field">
          <span className="field__label">事件 ID（可选）</span>
          <input
            className="control"
            value={eventIds}
            onChange={(event) => setEventIds(event.target.value)}
            placeholder="例如 1000, 1001"
          />
        </label>
      </div>

      {error && (
        <Notice tone="danger" role="alert" className="panel__notice">
          {error}
        </Notice>
      )}

      <div className="action-row">
        {active && record ? (
          <>
            <div className="progress-row" role="status">
              <div className="progress-row__label">
                <strong>{statusCopy(record)}</strong>
              </div>
              <progress className="progress" value={record.progress} max="100" aria-label="日志分析进度" />
            </div>
            <Button variant="ghost" busy={busy} onClick={cancel} disabled={busy}>
              {busy ? "正在取消…" : "取消分析"}
            </Button>
          </>
        ) : (
          <Button variant="primary" busy={busy} onClick={start} disabled={busy}>
            {busy ? "正在创建…" : record ? "重新分析" : "开始分析"}
          </Button>
        )}
      </div>

      {record && TERMINAL.has(record.status) && (
        <PanelSection>
          <div className="result-head">
            <span className="result-head__state">
              <span
                className={`dot dot--${record.status === "completed" ? "ok" : record.status === "partial" ? "warn" : "danger"}`}
                aria-hidden="true"
              />
              <strong>{statusCopy(record)}</strong>
            </span>
            {record.finished_at && (
              <time className="result-head__time">{formatTime(record.finished_at)}</time>
            )}
          </div>

          {record.summary ? (
            <>
              <PanelSection>
                <div className="section-title">
                  <h3>应用崩溃聚合</h3>
                  <span>
                    {record.summary.crash_groups.length} 组 · {record.summary.event_count} 条事件
                  </span>
                </div>
                {record.summary.crash_groups.length ? (
                  <div className="rows">
                    {record.summary.crash_groups.map((group) => (
                      <div
                        className="crash-row"
                        key={`${group.application}-${group.faulting_module}-${group.exception_code}`}
                      >
                        <strong>{group.application}</strong>
                        <span className="row__meta">{group.count} 次</span>
                        <small>
                          {group.faulting_module ?? "未知模块"}
                          {group.exception_code ? ` · ${group.exception_code}` : ""}
                        </small>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="quiet">所选范围内未聚合到应用崩溃事件。</p>
                )}
              </PanelSection>

              <PanelSection>
                <div className="section-title">
                  <h3>常见错误与警告</h3>
                  <span>{record.summary.event_groups.length} 组</span>
                </div>
                <div className="rows">
                  {record.summary.event_groups.slice(0, 10).map((group) => (
                    <div
                      className="crash-row"
                      key={`${group.channel}-${group.provider}-${group.event_id}-${group.level}`}
                    >
                      <strong>{`${group.provider} · ID ${group.event_id}`}</strong>
                      <span className="row__meta">{group.count} 次</span>
                      <small>{`${group.channel} · ${group.sample_summary}`}</small>
                    </div>
                  ))}
                </div>
              </PanelSection>

              <PanelSection>
                <div className="section-title">
                  <h3>脱敏事件证据</h3>
                  <span>最多显示 20 条</span>
                </div>
                {record.summary.events.length ? (
                  <div className="rows">
                    {record.summary.events.slice(0, 20).map((item, index) => (
                      <article
                        className="event-row"
                        key={`${item.channel}-${item.event_id}-${item.timestamp}-${index}`}
                      >
                        <div className="event-row__head">
                          <strong>{item.provider}</strong>
                          <span className="row__meta">
                            {`${item.channel} · ID ${item.event_id} · ${formatTime(item.timestamp)}`}
                          </span>
                        </div>
                        <p className="event-row__summary">{item.summary}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState>所选范围内没有需要显示的脱敏事件。</EmptyState>
                )}
              </PanelSection>
            </>
          ) : null}

          {record.failures.length > 0 && (
            <Notice tone="warn" title="部分查询未完成" className="panel__notice">
              <ul className="plain-list">
                {record.failures.map((failure) => (
                  <li key={failure.tool}>{failure.message}</li>
                ))}
              </ul>
            </Notice>
          )}
        </PanelSection>
      )}
    </Panel>
  );
}
