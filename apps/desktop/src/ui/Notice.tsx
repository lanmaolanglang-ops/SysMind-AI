import type { ReactNode } from "react";

import { cx } from "./classNames";

export type NoticeTone = "info" | "ok" | "warn" | "danger";

interface NoticeProps {
  tone?: NoticeTone;
  /** Short lead-in, e.g. "以下项目未完成". */
  title?: ReactNode;
  /** Correlation id or other machine-readable detail. */
  meta?: ReactNode;
  /** Pass "alert" for conditions that interrupt the user, "status" for the rest. */
  role?: "alert" | "status";
  className?: string;
  children?: ReactNode;
}

/**
 * The only way the interface reports outcomes. Tone is explicit, so a failure
 * can never render with the same styling as a success.
 */
export function Notice({
  tone = "info",
  title,
  meta,
  role,
  className,
  children,
}: NoticeProps) {
  return (
    <div className={cx("notice", `notice--${tone}`, className)} {...(role ? { role } : {})}>
      <div className="notice__body">
        {title ? <p className="notice__title">{title}</p> : null}
        {children ? <div className="notice__text">{children}</div> : null}
        {meta ? <p className="notice__meta">{meta}</p> : null}
      </div>
    </div>
  );
}
