import { useCallback, useEffect, useState } from "react";

import type { ApiClient } from "../../services/api-client";
import { ControlledActions } from "./ControlledActions";
import {
  cancelDiagnosis,
  continueDiagnosis,
  fetchDiagnosisExport,
  getDiagnosis,
  recentDiagnoses,
  startDiagnosis,
  submitDiagnosisFeedback,
  type Diagnosis,
  type EvidenceDetail,
} from "../../services/diagnoses";

const TERMINAL = new Set([
  "waiting_user_input",
  "completed",
  "partial",
  "cancelled",
  "failed",
  "interrupted",
]);
const CATEGORY = { performance: "性能", network: "网络", crash: "应用崩溃" } as const;
const SEVERITY = { info: "信息", low: "留意", medium: "中等", high: "较高" } as const;
const HYPOTHESIS_STATUS = {
  active: "待进一步验证",
  confirmed: "已有证据支持",
  rejected: "已被现有证据排除",
  insufficient: "证据不足",
} as const;
const STOP_REASON = {
  evidence_sufficient: "已有本机证据支持以下结论。",
  user_cancelled: "诊断已由你取消。",
  insufficient_information: "未形成可验证的原因结论。",
  budget_exceeded: "已达到安全检查上限，报告仅使用已完成的检查。",
  risk_limit_reached: "诊断因安全限制停止，没有执行受限操作。",
} as const;
const EXAMPLES = ["电脑很慢", "无法上网", "某个软件总是闪退"];
const TOOL_LABELS: Record<string, string> = {
  "system.cpu": "CPU 状态",
  "system.gpu": "显卡与驱动信息",
  "system.memory": "内存状态",
  "system.disks": "磁盘容量",
  "process.high_usage": "高占用进程",
  "process.snapshot": "当前进程",
  "startup.analyze": "启动项",
  "service.analyze": "系统服务状态",
  "network.proxy.get_config": "系统代理设置",
  "network.diagnose": "网络连通性",
  "log.crash.analyze": "Windows 应用崩溃记录",
};
const FIELD_LABELS: Record<string, string> = {
  utilization_percent: "使用率",
  loss_percent: "丢包率",
  item_count: "数量",
  stopped_automatic_count: "未运行的自动服务",
  active_adapter_count: "活动网络适配器",
  adapter_count: "网络适配器",
  has_default_route: "默认路由",
  gateway_reachable: "默认网关可达",
  public_reachable: "公网目标可达",
  dns: "DNS 解析",
  failures: "受限或失败的检查",
};

function confidenceLabel(value: number) {
  if (value >= 0.85) return "判断把握较高";
  if (value >= 0.65) return "判断把握中等";
  return "证据仍然有限";
}

function evidenceValue(path: string, value: unknown) {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number" && path.endsWith("percent")) return `${value}%`;
  if (value && typeof value === "object" && "item_count" in value) {
    return `${String(value.item_count)} 项`;
  }
  if (Array.isArray(value)) return `${value.length} 项`;
  if (value === null || value === undefined) return "未取得结果";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "string") return value;
  if (typeof value === "bigint") return value.toString();
  if (typeof value === "symbol") return value.description ?? "符号值";
  return "无法显示";
}

function evidenceFieldLabel(path: string) {
  const field = path.split(".").at(-1)?.replace(/\[\d+\]/g, "") ?? path;
  return FIELD_LABELS[field] ?? "关键检查结果";
}

function EvidenceSummary({ details }: { details: EvidenceDetail[] }) {
  if (details.length === 0) return <p className="evidence-unavailable">证据详情暂不可用。</p>;
  return (
    <div className="evidence-summary">
      {details.map((detail) => (
        <div key={detail.tool_call_id}>
          <strong>{TOOL_LABELS[detail.tool_name] ?? "本机只读检查"}</strong>
          <time dateTime={detail.observed_at ?? undefined}>
            {detail.observed_at
              ? new Date(detail.observed_at).toLocaleString("zh-CN")
              : "检查时间未记录"}
          </time>
          <dl>
            {Object.entries(detail.key_fields).map(([path, value]) => (
              <div key={path}>
                <dt>{evidenceFieldLabel(path)}</dt>
                <dd>{evidenceValue(path, value)}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

export function DiagnosisPanel({ client }: { client: ApiClient }) {
  const [question, setQuestion] = useState("");
  const [supplementalAnswer, setSupplementalAnswer] = useState("");
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [history, setHistory] = useState<Diagnosis[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedbackIds, setFeedbackIds] = useState<Set<string>>(() => new Set());
  const [feedbackPendingIds, setFeedbackPendingIds] = useState<Set<string>>(() => new Set());
  const [message, setMessage] = useState<string | null>(null);
  const [historyUnavailable, setHistoryUnavailable] = useState(false);
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  const activeId = diagnosis && !TERMINAL.has(diagnosis.status) ? diagnosis.id : null;
  const waitingForInput = diagnosis?.status === "waiting_user_input";
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
        setHistoryUnavailable(false);
        setMessage(null);
      })
      .catch(() => {
        setHistoryUnavailable(true);
        setMessage("以前的报告暂时无法读取。你仍然可以开始新的诊断。");
      });
    return () => controller.abort();
  }, [client, historyReloadKey]);

  useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController();
    let disposed = false;
    let timer: number | undefined;
    let delay = 800;
    const poll = () => {
      void getDiagnosis(client, activeId, controller.signal)
        .then((result) => {
          setDiagnosis((current) => (current?.id === activeId ? result : current));
          setHistory((current) => [result, ...current.filter((item) => item.id !== result.id)]);
          setMessage(null);
          delay = 800;
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setMessage("诊断进度暂时不可用，正在等待本地服务恢复。");
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

  const continueTask = () => {
    if (!diagnosis || !waitingForInput || !supplementalAnswer.trim()) return;
    setBusy(true);
    setMessage(null);
    void continueDiagnosis(client, diagnosis.id, supplementalAnswer)
      .then((result) => {
        setSupplementalAnswer("");
        remember(result);
      })
      .catch(() => setMessage("补充信息未提交；任务可能已被继续或结束。"))
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
    const target = diagnosis;
    void fetchDiagnosisExport(client, target.id, format)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `sysmind-report-${target.id}.${format === "markdown" ? "md" : "json"}`;
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
        // Defer revocation: revoking synchronously after click can abort the download in
        // Safari and some embedded WebViews.
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
      })
      .catch(() => {
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
          <h2 id="diagnosis-title">我的电脑有什么问题？</h2>
          <p>用自己的话描述现象即可。SysMind 会先检查这台电脑，再说明原因和安全的下一步。</p>
        </div>
        <span className="diagnosis-mode">只读诊断</span>
      </header>

      {history.length > 0 && !activeId && (
        <label className="diagnosis-history">
          查看以前的问题
          <select
            value={diagnosis?.id ?? ""}
            onChange={(event) => {
              const selected = history.find((item) => item.id === event.target.value);
              if (selected) setDiagnosis(selected);
            }}
          >
            <option value="" disabled>选择一份以前的报告</option>
            {history.map((item) => (
              <option key={item.id} value={item.id}>
                {item.user_question} · {new Date(item.created_at).toLocaleString("zh-CN")}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="diagnosis-entry">
        <label htmlFor="diagnosis-question">描述现象</label>
        <textarea
          id="diagnosis-question"
          value={question}
          maxLength={1000}
          rows={3}
          placeholder="例如：开机后很慢，打开软件要等很久"
          onChange={(event) => setQuestion(event.target.value)}
          disabled={Boolean(activeId) || waitingForInput}
        />
        {!activeId && !waitingForInput && (
          <div className="diagnosis-examples" aria-label="常见问题示例">
            <span>也可以直接选择：</span>
            {EXAMPLES.map((example) => (
              <button type="button" key={example} onClick={() => setQuestion(example)}>
                {example}
              </button>
            ))}
          </div>
        )}
        <div className="diagnosis-actions">
          <p>检查默认只读。网络问题会访问少量固定测试地址，不会更改网络设置。</p>
          {activeId ? (
            <button type="button" className="text-action" onClick={cancel} disabled={busy}>
              {busy ? "正在取消…" : "取消诊断"}
            </button>
          ) : !waitingForInput ? (
            <button
              type="button"
              className="primary-action"
              onClick={start}
              disabled={busy || question.trim().length < 3}
            >
              {busy ? "正在创建…" : diagnosis ? "开始新的诊断" : "开始诊断"}
            </button>
          ) : null}
        </div>
      </div>

      {message && <div className="diagnosis-message" role="status">
        <span>{message}</span>
        {historyUnavailable && <button type="button" onClick={() => setHistoryReloadKey((value) => value + 1)}>重新读取以前的报告</button>}
      </div>}

      {diagnosis && (
        <div className="diagnosis-workspace">
          <div className="diagnosis-progress" role="status" aria-live="polite" aria-atomic="true">
            <div>
              <strong>{CATEGORY[diagnosis.category]}诊断</strong>
              <span>
                {waitingForInput
                  ? "等待补充信息"
                  : diagnosis.current_step ?? (diagnosis.report ? "检查完成" : "正在准备…")}
              </span>
            </div>
            <progress value={diagnosis.progress} max="100" aria-label="诊断进度" />
          </div>

          {waitingForInput && (
            <div className="diagnosis-message diagnosis-follow-up">
              <strong>需要补充信息</strong>
              {diagnosis.current_step && <span>{diagnosis.current_step}</span>}
              <label htmlFor="diagnosis-follow-up-answer">补充说明</label>
              <textarea
                id="diagnosis-follow-up-answer"
                rows={3}
                maxLength={1000}
                value={supplementalAnswer}
                placeholder="例如：主要在开机后的前十分钟卡顿"
                onChange={(event) => setSupplementalAnswer(event.target.value)}
              />
              <div>
                <button
                  type="button"
                  className="primary-action"
                  disabled={busy || !supplementalAnswer.trim()}
                  onClick={continueTask}
                >
                  {busy ? "正在继续…" : "继续原诊断"}
                </button>
                <button type="button" className="text-action" onClick={cancel} disabled={busy}>
                  取消诊断
                </button>
              </div>
            </div>
          )}

          <details className="technical-details diagnosis-plan-details">
            <summary>查看正在检查的项目</summary>
            <ol className="diagnosis-plan" aria-label="诊断计划">
              {diagnosis.plan.map((step, index) => (
                <li key={`${step.tool}-${index}`}>
                  <span>{index + 1}</span>
                  <div><strong>{step.purpose}</strong></div>
                </li>
              ))}
            </ol>
          </details>

          {diagnosis.report && (
            <article className="diagnosis-report">
              <div className="report-heading">
                <div>
                  <p className="report-question">你描述的问题：{diagnosis.user_question}</p>
                  <h3>{diagnosis.report.summary}</h3>
                  <p>{confidenceLabel(diagnosis.report.confidence)}</p>
                  {diagnosis.stop_reason && (
                    <p className="report-outcome">{STOP_REASON[diagnosis.stop_reason]}</p>
                  )}
                </div>
              </div>

              <section className="finding-list" aria-labelledby={`findings-${diagnosis.id}`}>
                <h4 id={`findings-${diagnosis.id}`} className="report-section-title">发现的问题</h4>
                {diagnosis.report.findings.length > 0 ? (
                  diagnosis.report.findings.map((finding) => (
                    <section key={finding.id} className={`finding finding--${finding.severity}`}>
                      <div className="finding-title">
                        <span>{SEVERITY[finding.severity]}</span><h4>{finding.title}</h4>
                      </div>
                      <p>{finding.explanation}</p>
                      <p className="finding-recommendation"><strong>建议下一步：</strong>{finding.recommendation}</p>
                      <div className="finding-evidence-summary">
                        <h5>判断依据</h5>
                        <EvidenceSummary details={finding.evidence_details ?? []} />
                      </div>
                      <details className="technical-details finding-evidence">
                        <summary>查看技术引用</summary>
                        <p>{confidenceLabel(finding.confidence)}（{Math.round(finding.confidence * 100)}%）</p>
                        <ul aria-label="证据引用">
                          {finding.evidence.map((evidence) => (
                            <li key={`${evidence.tool_call_id}-${evidence.field_path}`}>
                              {callNames.get(evidence.tool_call_id) ?? evidence.tool_call_id.slice(0, 8)} · {evidence.field_path}
                            </li>
                          ))}
                        </ul>
                      </details>
                    </section>
                  ))
                ) : (
                  <p className="report-empty">没有成功完成的检查结果，当前无法判断原因。</p>
                )}
              </section>

              <div className="report-explanation">
                <h4>通俗说明</h4><p>{diagnosis.report.model_explanation}</p>
                <small>这段文字用于帮助理解，判断依据来自上面的本机检查结果。</small>
              </div>
              {diagnosis.report.hypotheses.length > 0 && (
                <section
                  className="diagnosis-hypotheses"
                  aria-labelledby={`hypotheses-${diagnosis.id}`}
                >
                  <h4 id={`hypotheses-${diagnosis.id}`}>可能原因</h4>
                  {diagnosis.report.hypotheses.map((hypothesis) => (
                    <article key={hypothesis.id}>
                      <strong>{hypothesis.hypothesis}</strong>
                      <span>
                        {HYPOTHESIS_STATUS[hypothesis.status]} · {Math.round(hypothesis.confidence * 100)}%
                      </span>
                      <p><b>为什么怀疑：</b>{hypothesis.rationale}</p>
                      <p>
                        <b>支持证据：</b>
                        {hypothesis.supporting_evidence.length > 0
                          ? `${hypothesis.supporting_evidence.length} 条本机检查结果`
                          : "尚无支持证据"}
                      </p>
                      {hypothesis.supporting_evidence.length > 0 && (
                        <EvidenceSummary details={hypothesis.supporting_evidence_details ?? []} />
                      )}
                      <p>
                        <b>反证：</b>
                        {hypothesis.contradicting_evidence.length > 0
                          ? `${hypothesis.contradicting_evidence.length} 条本机检查结果`
                          : "未发现明确反证"}
                      </p>
                      {hypothesis.contradicting_evidence.length > 0 && (
                        <EvidenceSummary details={hypothesis.contradicting_evidence_details ?? []} />
                      )}
                      {(hypothesis.supporting_evidence.length > 0 || hypothesis.contradicting_evidence.length > 0) && (
                        <details className="technical-details hypothesis-technical-details">
                          <summary>查看技术引用</summary>
                          <ul>
                            {[...hypothesis.supporting_evidence, ...hypothesis.contradicting_evidence].map((item) => (
                              <li key={`${item.tool_call_id}-${item.field_path}`}>
                                {callNames.get(item.tool_call_id) ?? item.tool_call_id.slice(0, 8)} · {item.field_path}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </article>
                  ))}
                </section>
              )}
              {diagnosis.report.limitations.length > 0 && (
                <div className="report-limitations">
                  <h4>报告限制</h4>
                  <ul>{diagnosis.report.limitations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
                </div>
              )}
              {(diagnosis.status === "completed" || diagnosis.status === "partial") && diagnosis.category === "performance" && (
                <ControlledActions client={client} diagnosisId={diagnosis.id} />
              )}
              {(diagnosis.status === "completed" || diagnosis.status === "partial") && diagnosis.category !== "performance" && (
                <section className="next-step-summary" aria-labelledby={`next-step-${diagnosis.id}`}>
                  <h4 id={`next-step-${diagnosis.id}`}>接下来怎么做</h4>
                  <p>当前没有适合由 SysMind 直接执行的安全操作。请先按报告建议检查，处理后可重新诊断；需要协助时可以保存一份易读报告交给技术人员。</p>
                </section>
              )}
              <details className="technical-details report-save-options">
                <summary>保存或查看完整技术报告</summary>
                <div className="report-actions">
                  <button type="button" onClick={() => exportReport("markdown")}>保存易读报告</button>
                  <button type="button" onClick={() => exportReport("json")}>保存技术数据</button>
                </div>
              </details>
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
