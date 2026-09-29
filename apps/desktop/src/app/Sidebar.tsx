import type { BackendConnection } from "../services/backend";
import { Icon } from "../ui/Icon";
import { StatusDot } from "../ui/Badge";
import { VIEWS, type ViewId } from "./navigation";

interface SidebarProps {
  view: ViewId;
  onSelect: (view: ViewId) => void;
  connection: BackendConnection;
}

export function Sidebar({ view, onSelect, connection }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__mark" aria-hidden="true">
          S
        </span>
        <span>
          <span className="sidebar__name">SysMind AI</span>
          <span className="sidebar__tagline">本机诊断</span>
        </span>
      </div>

      <nav className="nav" aria-label="主导航">
        {VIEWS.map((item) => (
          <button
            key={item.id}
            type="button"
            className="nav__item"
            title={item.label}
            aria-current={item.id === view ? "page" : undefined}
            onClick={() => onSelect(item.id)}
          >
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar__foot">
        <p className="connection" role="status" title="本地服务已连接">
          <StatusDot tone="ok" />
          <span>本地服务已连接</span>
          <span className="connection__detail">
            后端 {connection.health.backend_version} · API {connection.health.api_version}
          </span>
        </p>
      </div>
    </aside>
  );
}
