import type { ReactNode } from "react";

import { cx } from "./classNames";

export interface PanelProps {
  /** Element id used for `aria-labelledby`; pass the id given to the heading. */
  titleId?: string;
  title: ReactNode;
  description?: ReactNode;
  /** Short state label, e.g. a read-only or offline marker. */
  badge?: ReactNode;
  /** Primary or secondary controls belonging to the whole panel. */
  actions?: ReactNode;
  /** Visually hidden live region announced outside the body's layout flow. */
  status?: ReactNode;
  raised?: boolean;
  flush?: boolean;
  className?: string;
  children: ReactNode;
}

/**
 * The single working surface. Every feature renders exactly one Panel, so
 * heading scale, padding and borders stay identical across the product.
 */
export function Panel({
  titleId,
  title,
  description,
  badge,
  actions,
  status,
  raised = false,
  flush = false,
  className,
  children,
}: PanelProps) {
  return (
    <section
      className={cx("panel", raised && "panel--raised", className)}
      {...(titleId ? { "aria-labelledby": titleId } : {})}
    >
      {status ? (
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {status}
        </p>
      ) : null}
      <header className="panel__head">
        <div className="panel__titles">
          <h2 id={titleId}>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {badge || actions ? (
          <div className="panel__aside">
            {badge}
            {actions}
          </div>
        ) : null}
      </header>
      <div className={cx("panel__body", flush && "panel__body--flush")}>{children}</div>
    </section>
  );
}

/** Groups related content inside a panel with a consistent divider. */
export function PanelSection({ children }: { children: ReactNode }) {
  return <div className="panel__section">{children}</div>;
}
