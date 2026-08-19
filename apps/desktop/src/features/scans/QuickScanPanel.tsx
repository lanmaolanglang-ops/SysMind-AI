import { useEffect, useMemo, useState } from "react";

import { ApiClientError, type ApiClient } from "../../services/api-client";
import {
  cancelScan,
  getRecentScans,
  getScan,
  startQuickScan,
  type ScanRecord,
} from "../../services/scans";

const STEP_LABELS: Record<string, string> = {
  "system.os": "读取 Windows 版本",
  "system.cpu": "读取处理器状态",
  "system.gpu": "读取显卡信息",
  "system.memory": "读取内存状态",
  "system.disks": "读取磁盘空间",
  "process.snapshot": "建立进程快照",
  "process.high_usage": "识别高占用进程",
};

const TERMINAL_STATUSES = new Set(["completed", "partial", "cancelled", "failed"]);

function formatBytes(value: number | null): string {
  if (value === null) return "未知";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount >= 10 || unit === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[unit]}`;
}

function statusCopy(scan: ScanRecord): string {
  switch (scan.status) {
    case "completed":
      return "扫描完成";
    case "partial":
      return "扫描完成，部分项目不可用";
    case "cancelled":
      return "扫描已取消";
    case "failed":
      return "扫描失败";
    default:
      return scan.current_step ? (STEP_LABELS[scan.current_step] ?? "正在采集") : "准备扫描";
  }
}

function normalizeError(error: unknown): { message: string; correlationId?: string } {
  if (error instanceof ApiClientError) {
    return {
      message: "扫描服务暂时不可用，请稍后重试。",
      ...(error.correlationId ? { correlationId: error.correlationId } : {}),
    };
  }
  return { message: "无法完成本地扫描请求。" };
}

export function QuickScanPanel({ client }: { client: ApiClient }) {
  const [scan, setScan] = useState<ScanRecord | null>(null);
  const [error, setError] = useState<{ message: string; correlationId?: string } | null>(null);
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const active = scan !== null && !TERMINAL_STATUSES.has(scan.status);
  const activeScanId = active ? scan.id : null;

  useEffect(() => {
    if (scan && TERMINAL_STATUSES.has(scan.status)) setCancelling(false);
  }, [scan]);

  useEffect(() => {
    const controller = new AbortController();
    void getRecentScans(client, controller.signal)
      .then((response) => setScan(response.items[0] ?? null))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(normalizeError(reason));
      });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!activeScanId) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      void getScan(client, activeScanId, controller.signal)
        .then((next) => {
          setScan(next);
          setError(null);
        })
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) setError(normalizeError(reason));
        });
    }, 350);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [activeScanId, client]);

  const completedAt = useMemo(() => {
    if (!scan?.finished_at) return null;
    return new Intl.DateTimeFormat("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(scan.finished_at));
  }, [scan?.finished_at]);

  const start = () => {
    setStarting(true);
    setError(null);
    void startQuickScan(client)
      .then(setScan)
      .catch((reason: unknown) => setError(normalizeError(reason)))
      .finally(() => setStarting(false));
  };

  const cancel = () => {
    if (!scan) return;
    setCancelling(true);
    void cancelScan(client, scan.id)
      .then(setScan)
      .catch((reason: unknown) => {
        setCancelling(false);
        setError(normalizeError(reason));
      });
  };

  return (
    <section className="scan-panel" aria-labelledby="scan-title">
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {scan ? statusCopy(scan) : ""}
      </div>
      <div className="scan-header">
        <div>
          <h2 id="scan-title">了解这台电脑此刻的状态</h2>
          <p className="scan-description">
            检查系统、硬件、磁盘与当前进程。扫描不会修改设置，也不会结束任何进程。
          </p>
        </div>
        {!active && (
          <button className="primary-action" type="button" onClick={start} disabled={starting}>
            {starting ? "正在创建…" : scan ? "重新扫描" : "开始扫描"}
          </button>
        )}
      </div>

      {error && (
        <div className="inline-error" role="alert">
          <span>{error.message}</span>
          {error.correlationId && <code>问题编号 {error.correlationId}</code>}
        </div>
      )}

      {active && scan && (
        <div className="scan-progress">
          <div className="progress-copy">
            <strong>{statusCopy(scan)}</strong>
            <span>{scan.progress}%</span>
          </div>
          <progress value={scan.progress} max="100" aria-label="快速扫描进度">
            {scan.progress}%
          </progress>
          <button className="text-action" type="button" onClick={cancel} disabled={cancelling}>
            {cancelling ? "正在取消…" : "取消扫描"}
          </button>
        </div>
      )}

      {!scan && !active && (
        <div className="scan-empty">
          <p>首次扫描通常只需几秒。结果只保存在这台电脑的本地数据库中。</p>
        </div>
      )}

      {scan && TERMINAL_STATUSES.has(scan.status) && (
        <div className="scan-result">
          <div className="result-status">
            <div>
              <span className={`result-mark result-mark--${scan.status}`} aria-hidden="true" />
              <strong>{statusCopy(scan)}</strong>
            </div>
            {completedAt && <time>{completedAt}</time>}
          </div>

          {scan.summary && (
            <>
              <dl className="system-overview">
                <div>
                  <dt>Windows</dt>
                  <dd>
                    {scan.summary.operating_system
                      ? `${scan.summary.operating_system.name} ${scan.summary.operating_system.build} · ${scan.summary.operating_system.architecture}`
                      : "未读取"}
                  </dd>
                </div>
                <div>
                  <dt>处理器</dt>
                  <dd>
                    {scan.summary.cpu
                      ? `${scan.summary.cpu.model} · ${scan.summary.cpu.utilization_percent}%`
                      : "未读取"}
                  </dd>
                </div>
                <div>
                  <dt>内存</dt>
                  <dd>
                    {scan.summary.memory
                      ? `${formatBytes(scan.summary.memory.used_bytes)} / ${formatBytes(scan.summary.memory.total_bytes)} · ${scan.summary.memory.utilization_percent}%`
                      : "未读取"}
                  </dd>
                </div>
                <div>
                  <dt>显卡</dt>
                  <dd>{scan.summary.gpus.map((gpu) => gpu.name).join("、") || "未读取"}</dd>
                </div>
              </dl>

              <div className="result-section">
                <div className="section-heading">
                  <h3>磁盘空间</h3>
                  <span>{scan.summary.disks.length} 个卷</span>
                </div>
                <div className="disk-list">
                  {scan.summary.disks.map((disk) => (
                    <div className="disk-row" key={`${disk.volume}-${disk.mountpoint}`}>
                      <strong>{disk.volume || disk.mountpoint}</strong>
                      <span>
                        {formatBytes(disk.free_bytes)} 可用 · 已用 {disk.utilization_percent}%
                      </span>
                      <div
                        className="meter"
                        role="meter"
                        aria-label={`${disk.volume} 磁盘使用率`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={disk.utilization_percent}
                      >
                        <span style={{ width: `${Math.min(disk.utilization_percent, 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="result-section">
                <div className="section-heading">
                  <h3>高占用进程</h3>
                  <span>已观察 {scan.summary.processes.length} 个进程</span>
                </div>
                {scan.summary.high_usage_processes.length ? (
                  <div className="process-list">
                    {scan.summary.high_usage_processes.slice(0, 8).map((process) => (
                      <div className="process-row" key={process.pid}>
                        <span className="process-name">{process.name}</span>
                        <span>CPU {process.cpu_percent}%</span>
                        <span>{formatBytes(process.memory_bytes)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="quiet-result">采样期间未发现明显的高占用进程。</p>
                )}
              </div>
            </>
          )}

          {scan.failures.length > 0 && (
            <div className="scan-warnings">
              <strong>以下项目未完成</strong>
              <ul>
                {scan.failures.map((failure) => (
                  <li key={failure.tool}>{failure.message}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
