import { useEffect, useMemo, useState } from "react";

import type { ApiClient } from "../../services/api-client";
import { recentActions } from "../../services/actions";
import { recentDiagnoses } from "../../services/diagnoses";
import { getRecentLogAnalyses } from "../../services/log-analyses";
import { getRecentScans } from "../../services/scans";
import {
  deleteHistory,
  getBaseline,
  getDeletionImpact,
  type BaselineMetric,
  type DeletionImpact,
} from "../../services/history";

type HistoryKind = "all" | "scan" | "diagnosis" | "log" | "action";

interface HistoryItem {
  id: string;
  kind: Exclude<HistoryKind, "all">;
  title: string;
  status: string;
  timestamp: string | null;
}

export function HistoryPanel({ client }: { client: ApiClient }) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [filter, setFilter] = useState<HistoryKind>("all");
  const [error, setError] = useState<string | null>(null);
  const [impact, setImpact] = useState<DeletionImpact | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<BaselineMetric[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    void Promise.all([
      getRecentScans(client, controller.signal),
      recentDiagnoses(client, controller.signal),
      getRecentLogAnalyses(client, controller.signal),
      recentActions(client, controller.signal),
      getBaseline(client, controller.signal),
    ])
      .then(([scans, diagnoses, logs, actions, baselineResult]) => {
        setItems([
          ...scans.items.map((item) => ({ id: item.id, kind: "scan" as const,
            title: "快速扫描", status: item.status, timestamp: item.started_at })),
          ...diagnoses.items.map((item) => ({ id: item.id, kind: "diagnosis" as const,
            title: item.report?.summary ?? "诊断报告", status: item.status,
            timestamp: item.created_at })),
          ...logs.items.map((item) => ({ id: item.id, kind: "log" as const,
            title: "日志分析", status: item.status, timestamp: item.started_at })),
          ...actions.items.map((item) => ({ id: item.id, kind: "action" as const,
            title: item.target_name, status: item.status, timestamp: null })),
        ]);
        setBaseline(baselineResult.items);
        setError(null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("历史记录暂时不可用。");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [client, reloadKey]);

  const visible = useMemo(
    () => items.filter((item) => filter === "all" || item.kind === filter),
    [filter, items],
  );

  const previewDeletion = (item: HistoryItem) => {
    if (item.kind === "action") return;
    setBusyId(item.id);
    setError(null);
    void getDeletionImpact(client, item.kind, item.id)
      .then(setImpact)
      .catch(() => setError("无法确认删除影响，请稍后再试。"))
      .finally(() => setBusyId(null));
  };

  const confirmDeletion = () => {
    if (!impact?.deletable) return;
    setBusyId(impact.record_id);
    void deleteHistory(client, impact)
      .then(() => {
        setItems((current) => current.filter(
          (item) => item.id !== impact.record_id || item.kind !== impact.kind,
        ));
        setImpact(null);
      })
      .catch(() => {
        setImpact(null);
        setError("记录已变化或删除失败，请重新预览影响。 ");
      })
      .finally(() => setBusyId(null));
  };

  const metricLabels: Record<BaselineMetric["metric"], string> = {
    cpu_percent: "CPU", memory_percent: "内存", disk_peak_percent: "磁盘峰值",
  };
  const kindLabels: Record<Exclude<HistoryKind, "all">, string> = {
    scan: "设备扫描", diagnosis: "问题诊断", log: "事件日志", action: "安全操作",
  };
  const statusLabels: Record<string, string> = {
    queued: "等待开始", running: "正在进行", completed: "已完成", partial: "部分完成",
    failed: "未完成", cancelled: "已取消", interrupted: "意外中断", succeeded: "操作成功",
    rejected: "已拒绝", close_pending: "等待进一步决定",
    proposed: "待确认", awaiting_second_confirmation: "等待二次确认",
    confirmed: "已确认", executing: "执行中", verifying: "校验中",
    verification_failed: "校验失败", expired: "确认已过期", target_changed: "目标已变化",
    waiting_user_input: "等待补充信息",
  };

  return (
    <section className="history-panel" aria-labelledby="history-title">
      <header><div><h2 id="history-title">历史与审计</h2><p>按类型查看最近任务；每项保留可追溯 ID。</p></div>
        <label>筛选<select value={filter} onChange={(event) => setFilter(event.target.value as HistoryKind)}>
          <option value="all">全部</option><option value="scan">扫描</option>
          <option value="diagnosis">诊断</option><option value="log">日志</option>
          <option value="action">动作</option>
        </select></label></header>
      {error && <div role="alert" className="inline-error"><span>{error}</span><button type="button" onClick={() => setReloadKey((value) => value + 1)}>重新加载</button></div>}
      <div className="history-baseline" aria-label="最近扫描基线">
        <strong>最近扫描基线</strong>
        {baseline.length === 0 ? <span>至少完成两次扫描后生成趋势。</span> : baseline.map((metric) => (
          <span key={metric.metric}>{metricLabels[metric.metric]}：当前 {metric.latest}% · 中位数 {metric.median}% · {metric.delta >= 0 ? "+" : ""}{metric.delta}%（{metric.samples} 次）</span>
        ))}
      </div>
      {impact && <div className="deletion-review" role="region" aria-label="删除影响确认">
        <strong>{impact.deletable ? "确认删除历史记录？" : "此记录受保护"}</strong>
        <p>{impact.protected_reason ?? `将同时删除 ${impact.dependent_records} 条从属明细，此操作不可撤销。动作审计不会被删除。`}</p>
        <div className="settings-actions">
          {impact.deletable && <button type="button" className="danger-action" onClick={confirmDeletion} disabled={busyId !== null}>确认删除</button>}
          <button type="button" onClick={() => setImpact(null)}>取消</button>
        </div>
      </div>}
      {!error && !loading && visible.length === 0 && <p>暂无数据。先运行一次扫描或诊断。</p>}
      <ul className="history-list">{visible.map((item) => <li key={`${item.kind}-${item.id}`}>
        <div><strong>{item.title}</strong><small>{kindLabels[item.kind]}</small><details className="history-technical"><summary>记录编号</summary><code>{item.id}</code></details></div>
        <span>{statusLabels[item.status] ?? "状态未知"}{item.timestamp ? ` · ${new Date(item.timestamp).toLocaleString("zh-CN")}` : ""}</span>
        {item.kind === "action" ? <small>强制保留审计</small> : <button type="button" onClick={() => previewDeletion(item)} disabled={busyId !== null}>删除…</button>}
      </li>)}</ul>
    </section>
  );
}
