import { useCallback, useEffect, useState } from "react";

import type { ApiClient } from "../../services/api-client";
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

export function DiagnosisPanel({ client }: { client: ApiClient }) {
  const [question, setQuestion] = useState("电脑最近很卡，帮我找出可能原因");
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [history, setHistory] = useState<Diagnosis[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedbackIds, setFeedbackIds] = useState<Set<string>>(() => new Set());
  const [feedbackPendingIds, setFeedbackPendingIds] = useState<Set<string>>(() => new Set());
  const [message, setMessage] = useState<string | null>(null);
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
      .catch(() => setMessage("暂时无法读取诊断历史。"));
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
          if (!controller.signal.aborted) setMessage("诊断进度暂时不可用，正在等待本地服务恢复。");
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
      .catch(() => setMessage("无法创建诊断，请确认本地服务仍然连接。"))
      .finally(() => setBusy(false));
  };

  const cancel = () => {
    if (!diagnosis) return;
    setBusy(true);
    void cancelDiagnosis(client, diagnosis.id)
      .then(remember)
      .catch(() => setMessage("取消请求未完成，请稍后重试。"))
      .finally(() => setBusy(false));
  };

  const feedback = (helpful: boolean) => {
    if (!diagnosis || feedbackIds.has(diagnosis.id) || feedbackPendingIds.has(diagnosis.id)) return;
    const diagnosisId = diagnosis.id;
    setFeedbackPendingIds((current) => new Set(current).add(diagnosisId));
    void submitDiagnosisFeedback(client, diagnosis.id, helpful)
      .then(() => {
        setFeedbackIds((current) => new Set(current).add(diagnosisId));
        setMessage("感谢反馈，这会帮助后续改进诊断规则。");
      })
      .catch(() => setMessage("反馈暂时未保存。"))
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
      setMessage("报告导出失败，请确认本地服务仍然连接。 ");
    });
  };

  const callNames = new Map(
    diagnosis?.tool_calls.map((call) => [call.id, `${call.tool_name}@${call.tool_version}`]) ?? [],
  );

  return (
    <section className="diagnosis-panel" aria-labelledby="diagnosis-title">
      <header className="diagnosis-heading">
        <div>
          <h2 id="diagnosis-title">描述电脑遇到的问题</h2>
          <p>本地规则先检查证据，再生成可复查的结论。诊断不会自动修复；受控操作必须逐项确认。</p>
        </div>
        <span className="diagnosis-mode">只读诊断</span>
      </header>

      {history.length > 0 && !activeId && (
        <label className="diagnosis-history">
          最近报告
          <select
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

      <div className="diagnosis-entry">
        <label htmlFor="diagnosis-question">问题描述</label>
        <textarea
          id="diagnosis-question"
          value={question}
          maxLength={1000}
          rows={3}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={Boolean(activeId)}
        />
        <div className="diagnosis-actions">
          <p>网络类诊断会访问固定测试域名和公共 IP；目标、次数和超时均由应用限制。</p>
          {activeId ? (
            <button type="button" className="text-action" onClick={cancel} disabled={busy}>
              {busy ? "正在取消…" : "取消诊断"}
            </button>
          ) : (
            <button
              type="button"
              className="primary-action"
              onClick={start}
              disabled={busy || question.trim().length < 3}
            >
              {busy ? "正在创建…" : diagnosis ? "重新诊断" : "开始诊断"}
            </button>
          )}
        </div>
      </div>

      {message && <p className="diagnosis-message" role="status">{message}</p>}

      {diagnosis && (
        <div className="diagnosis-workspace" aria-live="polite">
          <div className="diagnosis-progress">
            <div>
              <strong>{CATEGORY[diagnosis.category]}诊断</strong>
              <span>{diagnosis.current_step ?? (diagnosis.report ? "报告已生成" : diagnosis.status)}</span>
            </div>
            <progress value={diagnosis.progress} max="100" aria-label="诊断进度" />
          </div>

          <ol className="diagnosis-plan" aria-label="诊断计划">
            {diagnosis.plan.map((step, index) => (
              <li key={step.tool}>
                <span>{index + 1}</span>
                <div><strong>{step.purpose}</strong><small>{step.tool}</small></div>
              </li>
            ))}
          </ol>

          {diagnosis.report && (
            <article className="diagnosis-report">
              <div className="report-heading">
                <div>
                  <h3>{diagnosis.report.summary}</h3>
                  <p>综合置信度 {Math.round(diagnosis.report.confidence * 100)}%</p>
                </div>
                <div className="report-actions">
                  <button type="button" onClick={() => exportReport("markdown")}>导出 Markdown</button>
                  <button type="button" onClick={() => exportReport("json")}>导出 JSON</button>
                </div>
              </div>

              <div className="finding-list">
                {diagnosis.report.findings.map((finding) => (
                  <section key={finding.id} className={`finding finding--${finding.severity}`}>
                    <div className="finding-title">
                      <span>{SEVERITY[finding.severity]}</span><h4>{finding.title}</h4>
                      <strong>{Math.round(finding.confidence * 100)}%</strong>
                    </div>
                    <p>{finding.explanation}</p>
                    <p><strong>建议：</strong>{finding.recommendation}</p>
                    <ul aria-label="证据引用">
                      {finding.evidence.map((evidence) => (
                        <li key={`${evidence.tool_call_id}-${evidence.field_path}`}>
                          {callNames.get(evidence.tool_call_id) ?? evidence.tool_call_id.slice(0, 8)} · {evidence.field_path}
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>

              <div className="report-explanation">
                <h4>综合说明</h4><p>{diagnosis.report.model_explanation}</p>
              </div>
              {diagnosis.report.limitations.length > 0 && (
                <div className="report-limitations">
                  <h4>报告限制</h4>
                  <ul>{diagnosis.report.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
              )}
              {(diagnosis.status === "completed" || diagnosis.status === "partial") && (
                <ControlledActions client={client} diagnosisId={diagnosis.id} />
              )}
              <div className="report-feedback">
                <span>这份报告有帮助吗？</span>
                <button type="button" onClick={() => feedback(true)} disabled={feedbackSent || feedbackPending}>有帮助</button>
                <button type="button" onClick={() => feedback(false)} disabled={feedbackSent || feedbackPending}>需要改进</button>
              </div>
            </article>
          )}
          {diagnosis.failure_message && <p className="inline-error">{diagnosis.failure_message}</p>}
        </div>
      )}
    </section>
  );
}
