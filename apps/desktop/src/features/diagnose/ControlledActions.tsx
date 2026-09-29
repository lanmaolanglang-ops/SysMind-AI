import { useEffect, useRef, useState } from "react";

import type { ApiClient } from "../../services/api-client";
import { Button } from "../../ui/Button";
import { Notice } from "../../ui/Notice";
import {
  actionCandidates,
  confirmAndExecute,
  createDisableAction,
  createProcessCloseAction,
  createProcessTermination,
  createRecoveryAction,
  processActionCandidates,
  recentControlledActions,
  rejectAction,
  restoreControlledActions,
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

  const engaged = useRef(false);

  /** Marks that the user has taken over, so the restore cannot overwrite them. */
  const engage = () => {
    engaged.current = true;
  };

  // The panel is unmounted while another section is open, so the outcome of an
  // executed action is restored from the backend record rather than from
  // component state that no longer exists.
  useEffect(() => {
    let active = true;
    engaged.current = false;
    setCandidates(null);
    setAction(null);
    setProcesses(null);
    setOriginal(null);
    setMessage(null);

    void recentControlledActions(client)
      .then((response) => {
        if (!active || engaged.current) return;
        const restored = restoreControlledActions(response.items, diagnosisId);
        setAction((current) => current ?? restored.action);
        setOriginal((current) => current ?? restored.original);
      })
      .catch(() => {
        if (active) setMessage("暂时无法读取此前的受控操作记录，可稍后重试。");
      });

    return () => {
      active = false;
    };
  }, [client, diagnosisId]);

  const load = () => {
    engage();
    setBusy(true);
    void actionCandidates(client, diagnosisId)
      .then((result) => setCandidates(result.items))
      .catch(() => setMessage("此报告没有可用的当前用户启动项修复证据。"))
      .finally(() => setBusy(false));
  };

  const loadProcesses = () => {
    engage();
    setBusy(true);
    void processActionCandidates(client, diagnosisId)
      .then((result) => setProcesses(result.items))
      .catch(() => setMessage("此报告没有可安全关闭的高占用 GUI 应用证据。"))
      .finally(() => setBusy(false));
  };

  const plan = (candidate: StartupActionCandidate) => {
    engage();
    setBusy(true);
    void createDisableAction(client, diagnosisId, candidate)
      .then((result) => {
        setAction(result);
        setMessage(null);
      })
      .catch(() => setMessage("目标状态已变化，请刷新后重新生成计划。"))
      .finally(() => setBusy(false));
  };

  const planProcess = (candidate: ProcessActionCandidate) => {
    engage();
    setBusy(true);
    void createProcessCloseAction(client, diagnosisId, candidate)
      .then((result) => {
        setAction(result);
        setMessage(null);
      })
      .catch(() => setMessage("进程身份或窗口已经变化，请刷新后重新生成计划。"))
      .finally(() => setBusy(false));
  };

  const execute = () => {
    if (!action) return;
    engage();
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
    engage();
    setBusy(true);
    void createRecoveryAction(client, original.id)
      .then((result) => {
        setAction(result);
        setMessage(null);
      })
      .catch(() => setMessage("恢复资料不可用或目标位置已被占用。"))
      .finally(() => setBusy(false));
  };

  const prepareTermination = () => {
    if (!action || action.status !== "close_pending") return;
    engage();
    setBusy(true);
    void createProcessTermination(client, action.id)
      .then((result) => {
        setAction(result);
        setMessage(null);
      })
      .catch(() => setMessage("进程身份已变化，不能创建强制终止计划。"))
      .finally(() => setBusy(false));
  };

  const reject = () => {
    if (!action) return;
    engage();
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

  const confirmLabel = isTerminate
    ? secondConfirmation
      ? "再次确认并强制终止"
      : "我已了解数据丢失风险"
    : `我已了解，确认${isProcess ? "请求关闭" : isRestore ? "恢复" : "禁用"}`;

  return (
    <section className="repair" aria-labelledby={`actions-${diagnosisId}`}>
      <div className="repair__head">
        <div>
          <h4 id={`actions-${diagnosisId}`}>受控修复</h4>
          <p>仅处理当前用户启动项或请求关闭有证据的 GUI 应用。每次操作都重新核验目标。</p>
        </div>
        {!action && (
          <div className="repair__actions">
            {!candidates && (
              <Button size="sm" busy={busy} onClick={load} disabled={busy}>
                查看启动项
              </Button>
            )}
            {!processes && (
              <Button size="sm" busy={busy} onClick={loadProcesses} disabled={busy}>
                查看可关闭应用
              </Button>
            )}
          </div>
        )}
      </div>

      {candidates && !action && (
        <ul className="candidates">
          {candidates.length === 0 && <li className="quiet">当前没有可安全处理的启动项。</li>}
          {candidates.map((candidate) => (
            <li key={candidate.item_id}>
              <span className="candidates__text">
                <strong>{candidate.name}</strong>
                <small>
                  {candidate.command_name ?? "命令不可用"} ·{" "}
                  {candidate.source_kind === "user_run" ? "当前用户 Run" : "当前用户 Startup"}
                </small>
              </span>
              <Button size="sm" busy={busy} onClick={() => plan(candidate)} disabled={busy}>
                生成禁用计划
              </Button>
            </li>
          ))}
        </ul>
      )}

      {processes && !action && (
        <ul className="candidates">
          {processes.length === 0 && (
            <li className="quiet">当前没有符合保护策略的高占用 GUI 应用。</li>
          )}
          {processes.map((candidate) => (
            <li key={candidate.item_id}>
              <span className="candidates__text">
                <strong>{candidate.name}</strong>
                <small>
                  CPU {candidate.cpu_percent}% · 内存 {candidate.memory_percent}%
                </small>
              </span>
              <Button size="sm" busy={busy} onClick={() => planProcess(candidate)} disabled={busy}>
                生成关闭请求
              </Button>
            </li>
          ))}
        </ul>
      )}

      {action && (action.status === "proposed" || secondConfirmation) && (
        <div
          className={`confirm ${isTerminate ? "confirm--danger" : "confirm--warn"}`}
          role="group"
          aria-label="操作确认"
        >
          <strong className="confirm__title">
            {isTerminate ? "强制终止应用" : isProcess ? "请求关闭应用" : isRestore ? "恢复启动项" : "禁用启动项"}
            ：{action.target_name}
          </strong>
          <p>
            {isTerminate
              ? "强制终止不可恢复，未保存内容会丢失。该动作只因先前的正常关闭请求未完成而可用。"
              : isProcess
                ? "应用可能提示保存。SysMind 不会替你放弃未保存内容，也不会自动升级为强制终止。"
                : isRestore
                  ? "恢复后，该程序可能在下次登录时自动启动。"
                  : "禁用后，该程序不会在下次登录时自动启动；不会卸载或删除程序。"}
          </p>
          <p className="confirm__warning">
            执行前会再次比较目标身份。确认仅对这一项有效，并在 2 分钟后失效。
            {isProcess && " 关闭请求最多等待 8 秒。"}
            {isTerminate &&
              (secondConfirmation ? " 这是第二次也是最终确认。" : " 需要再次确认后才会执行。")}
          </p>
          <div className="confirm__actions">
            <Button
              variant={isTerminate ? "danger" : "primary"}
              busy={busy}
              onClick={execute}
              disabled={busy}
            >
              {busy ? "正在验证…" : confirmLabel}
            </Button>
            <Button variant="ghost" onClick={reject} disabled={busy}>
              拒绝并取消
            </Button>
          </div>
        </div>
      )}

      {action && action.status !== "proposed" && !secondConfirmation && (
        <Notice
          tone={action.status === "succeeded" ? "ok" : "warn"}
          role="status"
          className="repair__result"
          title={
            action.status === "succeeded"
              ? isTerminate
                ? "应用已强制终止并验证"
                : isProcess
                  ? "应用已关闭并验证"
                  : isRestore
                    ? "启动项已恢复并验证"
                    : "启动项已禁用并验证"
              : action.status === "close_pending"
                ? "应用未在 8 秒内关闭；尚未执行强制终止"
                : "操作未完成"
          }
        >
          {action.error_message ? <p>{action.error_message}</p> : null}
          <div className="repair__result-actions">
            {!isProcess && !isRestore && action.status === "succeeded" && action.recovery_available && (
              <Button size="sm" busy={busy} onClick={prepareRecovery} disabled={busy}>
                生成恢复计划
              </Button>
            )}
            {isProcess && action.status === "close_pending" && (
              <Button size="sm" variant="danger" busy={busy} onClick={prepareTermination} disabled={busy}>
                生成强制终止计划
              </Button>
            )}
          </div>
        </Notice>
      )}

      {message && (
        <Notice tone="warn" role="status" className="repair__result">
          {message}
        </Notice>
      )}
    </section>
  );
}
