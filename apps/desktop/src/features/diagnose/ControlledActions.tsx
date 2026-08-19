import { useEffect, useState } from "react";

import type { ApiClient } from "../../services/api-client";
import {
  actionCandidates,
  confirmAndExecute,
  createDisableAction,
  createProcessCloseAction,
  createProcessTermination,
  createRecoveryAction,
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
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setCandidates(null);
    setAction(null);
    setProcesses(null);
    setOriginal(null);
    setMessage(null);
  }, [diagnosisId]);

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
    setBusy(true);
    void confirmAndExecute(client, action)
      .then((result) => {
        setAction(result);
        if (result.tool_name === "startup.disable_current_user" && result.status === "succeeded") {
          setOriginal(result);
        }
      })
      .catch(() => setMessage("确认已过期或执行请求被拒绝；系统没有自动重试。"))
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
      .then(() => setAction(null))
      .catch(() => setMessage("拒绝决定暂时无法记录，请稍后重试。"))
      .finally(() => setBusy(false));
  };

  const isRestore = action?.tool_name === "startup.restore_current_user";
  const isProcess = action?.tool_name === "process.request_close_current_user";
  const isTerminate = action?.tool_name === "process.terminate_current_user";
  const secondConfirmation = action?.status === "awaiting_second_confirmation";
  return (
    <section className="controlled-actions" aria-labelledby={`actions-${diagnosisId}`}>
      <div className="controlled-actions__heading">
        <div>
          <h4 id={`actions-${diagnosisId}`}>受控修复</h4>
          <p>仅处理当前用户启动项或请求关闭有证据的 GUI 应用。每次操作都重新核验目标。</p>
        </div>
        {!action && <div className="controlled-actions__buttons">
          {!candidates && <button type="button" onClick={load} disabled={busy}>查看启动项</button>}
          {!processes && <button type="button" onClick={loadProcesses} disabled={busy}>查看可关闭应用</button>}
        </div>}
      </div>

      {candidates && !action && (
        <ul className="action-candidates">
          {candidates.length === 0 && <li>当前没有可安全处理的启动项。</li>}
          {candidates.map((candidate) => (
            <li key={candidate.item_id}>
              <div><strong>{candidate.name}</strong><small>{candidate.command_name ?? "命令不可用"} · {candidate.source_kind === "user_run" ? "当前用户 Run" : "当前用户 Startup"}</small></div>
              <button type="button" onClick={() => plan(candidate)} disabled={busy}>生成禁用计划</button>
            </li>
          ))}
        </ul>
      )}

      {processes && !action && (
        <ul className="action-candidates">
          {processes.length === 0 && <li>当前没有符合保护策略的高占用 GUI 应用。</li>}
          {processes.map((candidate) => (
            <li key={candidate.item_id}>
              <div><strong>{candidate.name}</strong><small>CPU {candidate.cpu_percent}% · 内存 {candidate.memory_percent}%</small></div>
              <button type="button" onClick={() => planProcess(candidate)} disabled={busy}>生成关闭请求</button>
            </li>
          ))}
        </ul>
      )}

      {action && (action.status === "proposed" || secondConfirmation) && (
        <div className="confirmation-card" role="group" aria-label="操作确认">
          <strong>{isTerminate ? "强制终止应用" : isProcess ? "请求关闭应用" : isRestore ? "恢复启动项" : "禁用启动项"}：{action.target_name}</strong>
          <p>{isTerminate ? "强制终止不可恢复，未保存内容会丢失。该动作只因先前的正常关闭请求未完成而可用。" : isProcess ? "应用可能提示保存。SysMind 不会替你放弃未保存内容，也不会自动升级为强制终止。" : isRestore ? "恢复后，该程序可能在下次登录时自动启动。" : "禁用后，该程序不会在下次登录时自动启动；不会卸载或删除程序。"}</p>
          <p className="confirmation-warning">执行前会再次比较目标身份。确认仅对这一项有效，并在 2 分钟后失效。{isProcess && " 关闭请求最多等待 8 秒。"}{isTerminate && (secondConfirmation ? " 这是第二次也是最终确认。" : " 需要再次确认后才会执行。")}</p>
          <div>
            <button type="button" className="primary-action" onClick={execute} disabled={busy}>{busy ? "正在验证…" : isTerminate ? (secondConfirmation ? "再次确认并强制终止" : "我已了解数据丢失风险") : `我已了解，确认${isProcess ? "请求关闭" : isRestore ? "恢复" : "禁用"}`}</button>
            <button type="button" onClick={reject} disabled={busy}>拒绝并取消</button>
          </div>
        </div>
      )}

      {action && action.status !== "proposed" && !secondConfirmation && (
        <div className={`action-result action-result--${action.status}`} role="status">
          <strong>{action.status === "succeeded" ? (isTerminate ? "应用已强制终止并验证" : isProcess ? "应用已关闭并验证" : isRestore ? "启动项已恢复并验证" : "启动项已禁用并验证") : action.status === "close_pending" ? "应用未在 8 秒内关闭；尚未执行强制终止" : "操作未完成"}</strong>
          {action.error_message && <p>{action.error_message}</p>}
          {!isProcess && !isRestore && action.status === "succeeded" && action.recovery_available && (
            <button type="button" onClick={prepareRecovery} disabled={busy}>生成恢复计划</button>
          )}
          {isProcess && action.status === "close_pending" && (
            <button type="button" onClick={prepareTermination} disabled={busy}>生成强制终止计划</button>
          )}
        </div>
      )}
      {message && <p className="diagnosis-message" role="status">{message}</p>}
    </section>
  );
}
