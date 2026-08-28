import { useEffect, useRef, useState } from "react";

import { ApiClientError, type ApiClient } from "../../services/api-client";
import {
  actionCandidates,
  confirmAndExecute,
  createDisableAction,
  createProcessCloseAction,
  createProcessTermination,
  createRecoveryAction,
  getAction,
  processActionCandidates,
  rejectAction,
  type ControlledAction,
  type ProcessActionCandidate,
  type StartupActionCandidate,
} from "../../services/actions";

export function ControlledActions({ client, diagnosisId }: { client: ApiClient; diagnosisId: string }) {
  const [candidates, setCandidates] = useState<StartupActionCandidate[] | null>(null);
  const [processes, setProcesses] = useState<ProcessActionCandidate[] | null>(null);
  const [action, setAction] = useState<ControlledAction | null>(null);
  const [original, setOriginal] = useState<ControlledAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [canCheckStatus, setCanCheckStatus] = useState(false);
  const diagnosisRef = useRef(diagnosisId);
  const statusController = useRef<AbortController | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);
  const confirmationRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    diagnosisRef.current = diagnosisId;
    statusController.current?.abort();
    setCandidates(null);
    setAction(null);
    setProcesses(null);
    setOriginal(null);
    setMessage(null);
    setCanCheckStatus(false);
    setReconciling(false);
    return () => statusController.current?.abort();
  }, [diagnosisId]);

  useEffect(() => {
    if (action?.status === "proposed" || action?.status === "awaiting_second_confirmation") {
      confirmationRef.current?.focus();
    }
  }, [action?.status]);

  const reconcileUnknownResult = async (actionId: string, expectedDiagnosisId: string) => {
    const controller = new AbortController();
    statusController.current?.abort();
    statusController.current = controller;
    setReconciling(true);
    try {
      setMessage("连接中断，操作结果未知；正在查询审计状态，不会自动重试操作。");
      for (let attempt = 0; attempt < 8 && !controller.signal.aborted; attempt += 1) {
        try {
          const result = await getAction(client, actionId, controller.signal);
          if (diagnosisRef.current !== expectedDiagnosisId) return;
          setAction(result);
          if (result.status !== "executing" && result.status !== "verifying") {
            setMessage(null);
            setCanCheckStatus(false);
            return;
          }
        } catch (error: unknown) {
          if (controller.signal.aborted) return;
          if (!(error instanceof ApiClientError)) break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1_000));
      }
      if (!controller.signal.aborted && diagnosisRef.current === expectedDiagnosisId) {
        setCanCheckStatus(true);
        setMessage("仍无法确认操作结果。请不要重复提交，可以再次检查当前状态。");
      }
    } finally {
      setReconciling(false);
    }
  };

  const checkStatus = () => {
    if (!action) return;
    setBusy(true);
    void getAction(client, action.id)
      .then((result) => {
        setAction(result);
        setCanCheckStatus(false);
        setMessage("已重新读取操作状态。");
      })
      .catch(() => setMessage("暂时仍无法读取操作状态，现有记录不会被重复执行。"))
      .finally(() => setBusy(false));
  };

  const load = () => {
    setBusy(true);
    void actionCandidates(client, diagnosisId)
      .then((result) => setCandidates(result.items))
      .catch(() => setMessage("此报告没有可用的当前用户启动项修复证据。"))
      .finally(() => setBusy(false));
  };

  const loadProcesses = () => {
    setBusy(true);
    void processActionCandidates(client, diagnosisId)
      .then((result) => setProcesses(result.items))
      .catch(() => setMessage("此报告没有可安全关闭的高占用 GUI 应用证据。"))
      .finally(() => setBusy(false));
  };

  const plan = (candidate: StartupActionCandidate) => {
    setBusy(true);
    void createDisableAction(client, diagnosisId, candidate)
      .then((result) => { setAction(result); setMessage(null); })
      .catch(() => setMessage("目标状态已变化，请刷新后重新生成计划。"))
      .finally(() => setBusy(false));
  };

  const planProcess = (candidate: ProcessActionCandidate) => {
    setBusy(true);
    void createProcessCloseAction(client, diagnosisId, candidate)
      .then((result) => { setAction(result); setMessage(null); })
      .catch(() => setMessage("进程身份或窗口已经变化，请刷新后重新生成计划。"))
      .finally(() => setBusy(false));
  };

  const execute = () => {
    if (!action) return;
    const executingAction = action;
    const expectedDiagnosisId = diagnosisId;
    setBusy(true);
    setMessage(null);
    setCanCheckStatus(false);
    void confirmAndExecute(client, executingAction)
      .then((result) => {
        setAction(result);
        if (result.tool_name === "startup.disable_current_user" && result.status === "succeeded") {
          setOriginal(result);
        }
      })
      .catch((error: unknown) => {
        if (
          error instanceof ApiClientError &&
          ["request_timeout", "network_error", "request_cancelled"].includes(error.code)
        ) {
          void reconcileUnknownResult(executingAction.id, expectedDiagnosisId);
          return;
        }
        setMessage("确认已过期或执行请求被拒绝；系统没有自动重试。");
      })
      .finally(() => setBusy(false));
  };

  const prepareRecovery = () => {
    if (!original) return;
    setBusy(true);
    void createRecoveryAction(client, original.id)
      .then((result) => { setAction(result); setMessage(null); })
      .catch(() => setMessage("恢复资料不可用或目标位置已被占用。"))
      .finally(() => setBusy(false));
  };

  const prepareTermination = () => {
    if (!action || action.status !== "close_pending") return;
    setBusy(true);
    void createProcessTermination(client, action.id)
      .then((result) => { setAction(result); setMessage(null); })
      .catch(() => setMessage("进程身份已变化，不能创建强制终止计划。"))
      .finally(() => setBusy(false));
  };

  const reject = () => {
    if (!action) return;
    setBusy(true);
    void rejectAction(client, action.id)
      .then(() => {
        setAction(null);
        setMessage("已取消这次操作，电脑设置没有改变。");
        window.setTimeout(() => sectionRef.current?.focus(), 0);
      })
      .catch(() => setMessage("拒绝决定暂时无法记录，请稍后重试。"))
      .finally(() => setBusy(false));
  };

  const isRestore = action?.tool_name === "startup.restore_current_user";
  const isProcess = action?.tool_name === "process.request_close_current_user";
  const isTerminate = action?.tool_name === "process.terminate_current_user";
  const secondConfirmation = action?.status === "awaiting_second_confirmation";
  const locked = busy || reconciling;
  return (
    <section ref={sectionRef} tabIndex={-1} className="controlled-actions" aria-labelledby={`actions-${diagnosisId}`}>
      <div className="controlled-actions__heading">
        <div>
          <h4 id={`actions-${diagnosisId}`}>可以安全尝试的下一步</h4>
          <p>这些选项来自本次检查证据。SysMind 不会自动执行，每次都会先说明影响并再次确认。</p>
        </div>
        {!action && <div className="controlled-actions__buttons">
          {!processes && <button type="button" className="primary-action" onClick={loadProcesses} disabled={locked}>查看高占用应用</button>}
          {!candidates && <button type="button" onClick={load} disabled={locked}>减少开机负担</button>}
        </div>}
      </div>

      {candidates && !action && (
        <ul className="action-candidates">
          {candidates.length === 0 && <li>当前没有可安全处理的启动项。</li>}
          {candidates.map((candidate) => (
            <li key={candidate.item_id}>
              <div><strong>{candidate.name}</strong><small>登录 Windows 时自动打开 · 可以恢复</small></div>
              <button type="button" onClick={() => plan(candidate)} disabled={locked}>查看停用方案</button>
            </li>
          ))}
        </ul>
      )}

      {processes && !action && (
        <ul className="action-candidates">
          {processes.length === 0 && <li>当前没有可以由 SysMind 安全关闭的高占用应用。</li>}
          {processes.map((candidate) => (
            <li key={candidate.item_id}>
              <div><strong>{candidate.name}</strong><small>CPU {candidate.cpu_percent}% · 内存 {candidate.memory_percent}%</small></div>
              <button type="button" onClick={() => planProcess(candidate)} disabled={locked}>查看关闭方案</button>
            </li>
          ))}
        </ul>
      )}

      {action && (action.status === "proposed" || secondConfirmation) && (
        <div ref={confirmationRef} tabIndex={-1} className="confirmation-card" role="group" aria-label="操作确认">
          <strong>{isTerminate ? "强制关闭应用" : isProcess ? "正常关闭应用" : isRestore ? "恢复自动启动" : "停止自动启动"}：{action.target_name}</strong>
          <p>{isTerminate ? "强制终止不可恢复，未保存内容会丢失。该动作只因先前的正常关闭请求未完成而可用。" : isProcess ? "应用可能提示保存。SysMind 不会替你放弃未保存内容，也不会自动升级为强制终止。" : isRestore ? "恢复后，该程序可能在下次登录时自动启动。" : "禁用后，该程序不会在下次登录时自动启动；不会卸载或删除程序。"}</p>
          <p className="confirmation-warning">执行前会再次比较目标身份。确认仅对这一项有效，并在 2 分钟后失效。{isProcess && " 关闭请求最多等待 8 秒。"}{isTerminate && (secondConfirmation ? " 这是第二次也是最终确认。" : " 需要再次确认后才会执行。")}</p>
          <div>
            <button type="button" className="primary-action" onClick={execute} disabled={locked}>{busy ? "正在验证…" : isTerminate ? (secondConfirmation ? "再次确认并强制关闭" : "我已了解数据丢失风险") : `我已了解，确认${isProcess ? "关闭" : isRestore ? "恢复" : "停用"}`}</button>
            <button type="button" onClick={reject} disabled={locked}>拒绝并取消</button>
          </div>
        </div>
      )}

      {action && action.status !== "proposed" && !secondConfirmation && (
        <div className={`action-result action-result--${action.status}`} role="status">
          <strong>{action.status === "succeeded" ? (isTerminate ? "应用已强制终止并验证" : isProcess ? "应用已关闭并验证" : isRestore ? "启动项已恢复并验证" : "启动项已禁用并验证") : action.status === "close_pending" ? "应用未在 8 秒内关闭；尚未执行强制终止" : "操作未完成"}</strong>
          {action.error_message && <p>{action.error_message}</p>}
          {!isProcess && !isRestore && action.status === "succeeded" && action.recovery_available && (
            <button type="button" onClick={prepareRecovery} disabled={locked}>恢复自动启动</button>
          )}
          {isProcess && action.status === "close_pending" && (
            <button type="button" onClick={prepareTermination} disabled={locked}>查看强制关闭方案</button>
          )}
        </div>
      )}
      {message && <p className="diagnosis-message" role="status">{message}</p>}
      {canCheckStatus && <button type="button" onClick={checkStatus} disabled={locked}>检查操作状态</button>}
    </section>
  );
}
