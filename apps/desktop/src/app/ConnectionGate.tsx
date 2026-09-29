import { Button } from "../ui/Button";
import { StatusDot } from "../ui/Badge";
import { Notice } from "../ui/Notice";

export type GateState =
  | { kind: "starting" }
  | { kind: "disconnected"; message: string; correlationId?: string };

/**
 * Shown until the local backend is reachable. The shell is not usable yet, so
 * the product presents one honest, recoverable panel instead of a dead rail.
 */
export function ConnectionGate({
  state,
  onRetry,
}: {
  state: GateState;
  onRetry: () => void;
}) {
  return (
    <main className="gate">
      <div className="gate__panel">
        {state.kind === "starting" ? (
          <>
            <div className="track" aria-hidden="true">
              <span />
            </div>
            <div className="gate__status" role="status">
              <StatusDot tone="warn" pulse />
              <span className="gate__text">正在启动本地后端</span>
            </div>
            <h1 className="gate__title">正在准备</h1>
            <p className="gate__text">
              安全启动本地服务后，即可进行只读系统扫描。所有结果默认保存在这台电脑上。
            </p>
            <p className="gate__text">等待 FastAPI 完成数据库迁移和 readiness 检查。</p>
          </>
        ) : (
          <>
            <Notice
              tone="danger"
              role="alert"
              title="本地后端未连接"
              meta={state.correlationId ? `问题编号：${state.correlationId}` : undefined}
            >
              {state.message}
            </Notice>
            <h1 className="gate__title">无法开始诊断</h1>
            <p className="gate__text">
              本地服务启动失败时，SysMind AI 不会改用云端处理。可重新连接，或重启应用后重试。
            </p>
            <div className="gate__actions">
              <Button variant="primary" onClick={onRetry}>
                重新连接
              </Button>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
