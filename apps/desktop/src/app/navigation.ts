import type { IconName } from "../ui/Icon";

export type ViewId = "diagnose" | "scan" | "logs" | "runtime" | "settings";

export interface ViewDefinition {
  id: ViewId;
  /** Label used in the navigation rail. */
  label: string;
  /** Heading shown in the workspace header. */
  title: string;
  icon: IconName;
}

/**
 * The product's information architecture, in order of user priority.
 * Natural-language diagnosis is the reason the application exists and leads;
 * application updates are maintenance and belong in settings.
 */
export const VIEWS: ViewDefinition[] = [
  { id: "diagnose", label: "诊断", title: "诊断", icon: "diagnose" },
  { id: "scan", label: "快速扫描", title: "快速扫描", icon: "scan" },
  { id: "logs", label: "事件日志", title: "事件日志", icon: "logs" },
  { id: "runtime", label: "Agent Runtime", title: "受限 Agent Runtime", icon: "runtime" },
  { id: "settings", label: "设置与更新", title: "设置与更新", icon: "settings" },
];

export const DEFAULT_VIEW: ViewId = "diagnose";

export function viewDefinition(id: ViewId): ViewDefinition {
  const found = VIEWS.find((view) => view.id === id);
  if (!found) throw new Error(`Unknown view: ${id}`);
  return found;
}
