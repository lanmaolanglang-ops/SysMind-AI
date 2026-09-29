import type { BackendConnection } from "../services/backend";
import type { ViewDefinition } from "./navigation";

/**
 * Workspace chrome. Carries the section name and the local runtime facts that
 * apply to every section, so individual panels never repeat them.
 */
export function Topbar({
  definition,
  connection,
}: {
  definition: ViewDefinition;
  connection: BackendConnection;
}) {
  return (
    <header className="topbar">
      <div className="topbar__titles">
        <h1>{definition.title}</h1>
      </div>
      <dl className="topbar__meta">
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
      </dl>
    </header>
  );
}
