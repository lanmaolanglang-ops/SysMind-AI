import { useEffect, useRef, useState } from "react";

import type { ApiClient } from "../../services/api-client";
import {
  clearProviderCredential,
  getProviderSettings,
  saveProviderSettings,
  testProvider,
  type ProviderSettings,
} from "../../services/settings";
import { getRetention, runCleanup, saveRetention } from "../../services/history";

export function SettingsPanel({ client }: { client: ApiClient }) {
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [endpoint, setEndpoint] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("gpt-4.1-mini");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [retentionDays, setRetentionDays] = useState(30);
  const [savedRetentionDays, setSavedRetentionDays] = useState<number | null>(null);
  const endpointEdited = useRef(false);
  const modelEdited = useRef(false);
  const retentionEdited = useRef(false);
  const [cleanupArmed, setCleanupArmed] = useState(false);
  const [clearCredentialArmed, setClearCredentialArmed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void getProviderSettings(client, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setSettings(value);
        if (value.endpoint && !endpointEdited.current) setEndpoint(value.endpoint);
        if (value.model && !modelEdited.current) setModel(value.model);
      })
      .catch(() => {
        if (!controller.signal.aborted) setMessage("暂时无法读取模型设置。");
      });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    const controller = new AbortController();
    void getRetention(client, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setSavedRetentionDays(value.retention_days);
        if (!retentionEdited.current) setRetentionDays(value.retention_days);
      })
      .catch(() => { if (!controller.signal.aborted) setMessage("暂时无法读取数据保留策略。"); });
    return () => controller.abort();
  }, [client]);

  const save = () => {
    setBusy(true);
    setMessage(null);
    void saveProviderSettings(client, {
      provider: "openai_compatible",
      model,
      endpoint,
      ...(apiKey ? { api_key: apiKey } : {}),
    })
      .then((value) => {
        setSettings(value);
        setApiKey("");
        setMessage("设置已保存。访问密钥已交给 Windows 安全保存，并已从当前表单清除。");
      })
      .catch(() => setMessage("设置未保存。请检查 HTTPS 地址、模型名称和凭据。"))
      .finally(() => setBusy(false));
  };

  const test = () => {
    setBusy(true);
    void testProvider(client)
      .then((result) =>
        setMessage(
          result.succeeded
            ? `连接成功（${result.duration_ms} ms）。后续任务将使用真实模型解释。`
            : `连接失败：${result.error_code ?? "provider_error"}。诊断仍会降级为本地规则。`,
        ),
      )
      .catch(() => setMessage("连接测试不可用；未发送原始工具结果。"))
      .finally(() => setBusy(false));
  };

  const clear = () => {
    setBusy(true);
    void clearProviderCredential(client)
      .then((value) => {
        setSettings(value);
        setApiKey("");
        setClearCredentialArmed(false);
        setMessage("在线解释的访问密钥已清除，诊断将继续使用本地规则。");
      })
      .catch(() =>
        setMessage("访问密钥未清除：Windows 凭据存储暂时不可用，稍后可重试。"),
      )
      .finally(() => setBusy(false));
  };

  const saveDataPolicy = () => {
    setBusy(true);
    const submittedDays = retentionDays;
    void saveRetention(client, submittedDays)
      .then((value) => {
        setSavedRetentionDays(value.retention_days);
        setMessage(`保留策略已保存：已结束的只读历史保留 ${value.retention_days} 天。`);
      })
      .catch(() => setMessage("保留策略未保存，请输入 7–3650 天。"))
      .finally(() => setBusy(false));
  };

  const cleanup = () => {
    setBusy(true);
    void runCleanup(client)
      .then((value) => {
        setCleanupArmed(false);
        setMessage(`清理完成：扫描 ${value.deleted_scans}、诊断 ${value.deleted_diagnoses}、日志 ${value.deleted_log_analyses}；保护 ${value.protected_records} 条审计关联记录。`);
      })
      .catch(() => setMessage("清理未完成，现有数据保持不变。"))
      .finally(() => setBusy(false));
  };

  return (
    <section className="settings-panel" aria-labelledby="settings-title">
      <header>
        <div>
          <h2 id="settings-title">在线解释与隐私</h2>
          <p>在线模型可能接收脱敏后的问题、最小设备摘要、只读工具说明和有界观察摘要；不会接收原始日志、完整事件 XML、凭据、用户文件或系统修改权限。</p>
        </div>
        <span className="diagnosis-mode">
          {settings?.configured ? "在线解释已开启" : "仅本地分析"}
        </span>
      </header>
      {!settings?.configured && (
        <div className="privacy-notice" role="note">
          <strong>首次使用说明</strong>
          <p>不配置在线模型也能正常诊断。访问密钥不会写入数据库、日志或浏览器存储。</p>
        </div>
      )}
      <div className="settings-grid">
        <label>服务地址<input value={endpoint} onChange={(event) => { endpointEdited.current = true; setEndpoint(event.target.value); }} /></label>
        <label>模型名称<input value={model} onChange={(event) => { modelEdited.current = true; setModel(event.target.value); }} /></label>
        <label>访问密钥<input type="password" autoComplete="off" value={apiKey} placeholder={settings?.configured ? "已安全保存；留空表示不替换" : "只在保存时短暂使用"} onChange={(event) => setApiKey(event.target.value)} /></label>
      </div>
      <div className="settings-actions">
        <button type="button" className="primary-action" onClick={save} disabled={busy || !model.trim() || !endpoint.trim()}>保存设置</button>
        <button type="button" onClick={test} disabled={busy || !settings?.configured}>测试连接</button>
        {clearCredentialArmed ? (
          <>
            <button type="button" className="danger-action" onClick={clear} disabled={busy}>确认清除访问密钥</button>
            <button type="button" onClick={() => setClearCredentialArmed(false)} disabled={busy}>取消</button>
          </>
        ) : (
          <button type="button" onClick={() => setClearCredentialArmed(true)} disabled={busy || !settings?.configured}>清除访问密钥</button>
        )}
      </div>
      {message && <p role="status" className="diagnosis-message">{message}</p>}
      <div className="retention-settings">
        <div><strong>本地历史保留</strong><p>只清理已结束的扫描、日志和未关联动作的诊断；动作与恢复审计始终保留。</p></div>
        <label>天数<input type="number" min="7" max="3650" value={retentionDays} onChange={(event) => { const parsed = Number(event.target.value); retentionEdited.current = true; setRetentionDays(Number.isFinite(parsed) ? parsed : 0); setCleanupArmed(false); }} /></label>
        <div className="settings-actions">
          <button type="button" onClick={saveDataPolicy} disabled={busy || !Number.isFinite(retentionDays) || retentionDays < 7 || retentionDays > 3650}>保存策略</button>
          {cleanupArmed ? (
            <>
              <button type="button" className="danger-action" onClick={cleanup} disabled={busy}>确认清理</button>
              <button type="button" onClick={() => setCleanupArmed(false)} disabled={busy}>取消</button>
            </>
          ) : (
            <button type="button" onClick={() => setCleanupArmed(true)} disabled={busy || savedRetentionDays === null || retentionDays !== savedRetentionDays}>立即清理</button>
          )}
        </div>
        {savedRetentionDays !== null && retentionDays !== savedRetentionDays && <p className="field-error">请先保存保留策略，再按已保存的天数清理。</p>}
        {cleanupArmed && (
          <p role="status" className="diagnosis-message">
            将按已保存的 {savedRetentionDays} 天保留策略清理已结束的扫描、日志和未关联动作的诊断。动作与恢复审计不会删除。此操作不可撤销。
          </p>
        )}
      </div>
    </section>
  );
}
