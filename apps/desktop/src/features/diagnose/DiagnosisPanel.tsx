import { useCallback, useEffect, useState } from "react";

import type { ApiClient } from "../../services/api-client";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Notice, type NoticeTone } from "../../ui/Notice";
import { Panel, PanelSection } from "../../ui/Panel";
import { ControlledActions } from "./ControlledActions";
import {
  cancelDiagnosis,
  downloadDiagnosis,
  getDiagnosis,
  recentDiagnoses,
  startDiagnosis,
  submitDiagnosisFeedback,
  type Diagnosis,
} from "../../services/diagnoses";

const TERMINAL = new Set(["completed", "partial", "cancelled", "failed", "interrupted"]);
const CATEGORY = { performance: "性能", network: "网络", crash: "应用崩溃" } as const;
const SEVERITY = { info: "信息", low: "留意", medium: "中等", high: "较高" } as const;

/** Internal status values are never shown to the user. */
const STATUS_LABEL: Record<string, string> = {
  queued: "已排队，等待开始",
  running: "正在诊断",
  completed: "诊断完成",
  partial: "诊断完成，部分证据不可用",
  cancelled: "诊断已取消",
  failed: "诊断失败",
  interrupted: "诊断因服务重启而中断",
};

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? "诊断进行中";
}

/** Severity also sets the layout accent for a finding; the label carries the meaning. */
const SEVERITY_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  high: "danger",
  medium: "warn",
  low: "neutral",
  info: "neutral",
};

interface Message {
  tone: NoticeTone;
  text: string;
}

export function DiagnosisPanel({ client }: { client: ApiClient }) {
  const [question, setQuestion] = useState("电脑最近很卡，帮我找出可能原因");
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [history, setHistory] = useState<Diagnosis[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedbackIds, setFeedbackIds] = useState<Set<string>>(() => new Set());
  const [feedbackPendingIds, setFeedbackPendingIds] = useState<Set<string>>(() => new Set());
  const [message, setMessage] = useState<Message | null>(null);
  const activeId = diagnosis && !TERMINAL.has(diagnosis.status) ? diagnosis.id : null;
  const feedbackSent = diagnosis ? feedbackIds.has(diagnosis.id) : false;
  const feedbackPending = diagnosis ? feedbackPendingIds.has(diagnosis.id) : false;

  const remember = useCallback((result: Diagnosis) => {
    setDiagnosis(result);
    setHistory((current) => [result, ...current.filter((item) => item.id !== result.id)]);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void recentDiagnoses(client, controller.signal)
      .then((result) => {
        setHistory(result.items);
        setDiagnosis(result.items[0] ?? null);
      })
      .catch(() =>
        setMessage({ tone: "warn", text: "暂时无法读取诊断历史，本机服务恢复后会重新加载。" }),
      );
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      void getDiagnosis(client, activeId, controller.signal)
        .then((result) => {
          remember(result);
          setMessage(null);
          if (TERMINAL.has(result.status)) window.clearInterval(timer);
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setMessage({
              tone: "warn",
              text: "诊断进度暂时不可用，正在等待本地服务恢复。",
            });
          }
        });
    }, 350);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [activeId, client, remember]);

  const start = () => {
    setBusy(true);
    setMessage(null);
    void startDiagnosis(client, question)
      .then(remember)
      .catch(() =>
        setMessage({ tone: "danger", text: "无法创建诊断，请确认本地服务仍然连接。" }),
      )
      .finally(() => setBusy(false));
  };

  const cancel = () => {
    if (!diagnosis) return;
    setBusy(true);
    void cancelDiagnosis(client, diagnosis.id)
      .then(remember)
      .catch(() => setMessage({ tone: "danger", text: "取消请求未完成，请稍后重试。" }))
      .finally(() => setBusy(false));
  };

  const feedback = (helpful: boolean) => {
    if (!diagnosis || feedbackIds.has(diagnosis.id) || feedbackPendingIds.has(diagnosis.id)) return;
    const diagnosisId = diagnosis.id;
    setFeedbackPendingIds((current) => new Set(current).add(diagnosisId));
    void submitDiagnosisFeedback(client, diagnosis.id, helpful)
      .then(() => {
        setFeedbackIds((current) => new Set(current).add(diagnosisId));
        setMessage({ tone: "ok", text: "感谢反馈，这会帮助后续改进诊断规则。" });
      })
      .catch(() => setMessage({ tone: "warn", text: "反馈暂时未保存。" }))
      .finally(() => {
        setFeedbackPendingIds((current) => {
          const next = new Set(current);
          next.delete(diagnosisId);
          return next;
        });
      });
  };

  const exportReport = (format: "json" | "markdown") => {
    if (!diagnosis) return;
    void downloadDiagnosis(client, diagnosis.id, format).catch(() => {
      setMessage({ tone: "danger", text: "报告导出失败，请确认本地服务仍然连接。" });
    });
  };

  const callNames = new Map(
    diagnosis?.tool_calls.map((call) => [call.id, `${call.tool_name}@${call.tool_version}`]) ?? [],
  );

  return (
    <Panel
      titleId="diagnosis-title"
      title="描述电脑遇到的问题"
      description="本地规则先检查证据，再生成可复查的结论。诊断不会自动修复；受控操作必须逐项确认。"
      badge={<Badge tone="accent">只读诊断</Badge>}
    >
      {history.length > 0 && !activeId && (
        <label className="field diagnosis-history">
          <span className="field__label">最近报告</span>
          <select
            className="control"
            value={diagnosis?.id ?? ""}
            onChange={(event) => {
              const selected = history.find((item) => item.id === event.target.value);
              if (selected) setDiagnosis(selected);
            }}
          >
            {history.map((item) => (
              <option key={item.id} value={item.id}>
                {CATEGORY[item.category]} · {new Date(item.created_at).toLocaleString("zh-CN")}
              </option>
            ))}
          </select>
        </label>
      )}

      {/* The composer is the product's primary interaction. */}
      <div className="composer">
        <label className="field" htmlFor="diagnosis-question">
          <span className="field__label">问题描述</span>
          <textarea
            id="diagnosis-question"
            className="control"
            value={question}
            maxLength={1000}
            rows={3}
            onChange={(event) => setQuestion(event.target.value)}
            disabled={Boolean(activeId)}
          />
        </label>
        <div className="composer__foot">
          <p className="composer__note">
            网络类诊断会访问固定测试域名和公共 IP；目标、次数和超时均由应用限制。
          </p>
          {activeId ? (
            <Button variant="ghost" busy={busy} onClick={cancel}>
              {busy ? "正在取消…" : "取消诊断"}
            </Button>
          ) : (
            <Button
              variant="primary"
              busy={busy}
              onClick={start}
              disabled={busy || question.trim().length < 3}
            >
              {busy ? "正在创建…" : diagnosis ? "重新诊断" : "开始诊断"}
            </Button>
          )}
        </div>
      </div>

      {message && <Notice tone={message.tone} role="status" className="composer__notice">{message.text}</Notice>}

      {diagnosis && (
        <PanelSection>
          <div className="progress-row" aria-live="polite">
            <div className="progress-row__label">
              <strong>{CATEGORY[diagnosis.category]}诊断</strong>
              <span>
                {diagnosis.current_step ?? (diagnosis.report ? "报告已生成" : statusLabel(diagnosis.status))}
              </span>
            </div>
            <progress className="progress" value={diagnosis.progress} max="100" aria-label="诊断进度" />
          </div>

          <ol className="plan" aria-label="诊断计划">
            {diagnosis.plan.map((step, index) => (
              <li className="plan__step" key={step.tool}>
                <span className="plan__index" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="plan__text">
                  <strong>{step.purpose}</strong>
                  <small>{step.tool}</small>
                </span>
              </li>
            ))}
          </ol>

          {diagnosis.report && (
            <article className="report">
              <div className="report__head">
                <div>
                  <h3>{diagnosis.report.summary}</h3>
                  <p>综合置信度 {Math.round(diagnosis.report.confidence * 100)}%</p>
                </div>
                <div className="report__actions">
                  <Button size="sm" onClick={() => exportReport("markdown")}>
                    导出 Markdown
                  </Button>
                  <Button size="sm" onClick={() => exportReport("json")}>
                    导出 JSON
                  </Button>
                </div>
              </div>

              <div className="findings">
                {diagnosis.report.findings.map((finding) => (
                  <section className="finding" key={finding.id}>
                    <div className="finding__head">
                      <span className={`finding__severity is-${SEVERITY_TONE[finding.severity]}`}>
                        {SEVERITY[finding.severity]}
                      </span>
                      <h4>{finding.title}</h4>
                      <strong className="finding__confidence">
                        {Math.round(finding.confidence * 100)}%
                      </strong>
                    </div>
                    <p className="finding__body">{finding.explanation}</p>
                    <p className="finding__body">
                      <strong>建议：</strong>
                      {finding.recommendation}
                    </p>
                    <ul className="finding__evidence" aria-label="证据引用">
                      {finding.evidence.map((evidence) => (
                        <li key={`${evidence.tool_call_id}-${evidence.field_path}`}>
                          {`${callNames.get(evidence.tool_call_id) ?? evidence.tool_call_id.slice(0, 8)} · ${evidence.field_path}`}
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>

              <div className="report__block">
                <h4>综合说明</h4>
                <p>{diagnosis.report.model_explanation}</p>
              </div>

              {diagnosis.report.limitations.length > 0 && (
                <div className="report__block">
                  <h4>报告限制</h4>
                  <ul className="plain-list">
                    {diagnosis.report.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {(diagnosis.status === "completed" || diagnosis.status === "partial") && (
                <ControlledActions client={client} diagnosisId={diagnosis.id} />
              )}

              <div className="report__feedback">
                <span>这份报告有帮助吗？</span>
                <Button size="sm" onClick={() => feedback(true)} disabled={feedbackSent || feedbackPending}>
                  有帮助
                </Button>
                <Button size="sm" onClick={() => feedback(false)} disabled={feedbackSent || feedbackPending}>
                  需要改进
                </Button>
              </div>
            </article>
          )}

          {diagnosis.failure_message && (
            <Notice tone="danger" role="alert" title="诊断未完成">
              {diagnosis.failure_message}
            </Notice>
          )}
        </PanelSection>
      )}
    </Panel>
  );
}
