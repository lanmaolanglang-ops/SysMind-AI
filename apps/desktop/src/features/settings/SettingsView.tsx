import type { BackendConnection } from "../../services/backend";
import { Panel, PanelSection } from "../../ui/Panel";
import { UpdatePanel } from "../updates/UpdatePanel";

/**
 * Maintenance surface: application version and the local data boundary.
 * Kept out of the working sections so it never competes with diagnosis.
 */
export function SettingsView({ connection }: { connection: BackendConnection }) {
  return (
    <>
      <Panel
        titleId="settings-update-title"
        title="应用更新"
        description="检查、安装并重启。更新只在你明确操作后发生，不会在后台自动下载。"
      >
        <UpdatePanel />
      </Panel>

      <Panel
        titleId="settings-boundary-title"
        title="本机数据与网络边界"
        description="SysMind AI 默认只读、最小权限运行，并且只在回环地址上与本机服务通信。"
      >
        <dl className="facts">
          <div>
            <dt>本地后端</dt>
            <dd>{connection.health.backend_version}</dd>
          </div>
          <div>
            <dt>API</dt>
            <dd>{connection.health.api_version}</dd>
          </div>
          <div>
            <dt>网络边界</dt>
            <dd>127.0.0.1</dd>
          </div>
          <div>
            <dt>诊断数据</dt>
            <dd>仅保存在这台电脑</dd>
          </div>
        </dl>

        <PanelSection>
          <ul className="plain-list">
            <li>扫描与诊断默认只读，不会修改系统设置或结束进程。</li>
            <li>会话令牌只存在于进程内存，不写入数据库、日志或浏览器存储。</li>
            <li>网络类诊断只访问应用固定的测试目标，并在开始前明确提示。</li>
            <li>受控修复需要逐项确认，且每次都重新核验目标身份。</li>
          </ul>
        </PanelSection>
      </Panel>
    </>
  );
}
