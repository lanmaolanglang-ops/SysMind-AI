import type { ReactNode } from "react";

import { cx } from "./classNames";

export type BadgeTone = "neutral" | "accent" | "warn" | "danger";

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: BadgeTone;
  children: ReactNode;
}) {
  return <span className={cx("badge", `badge--${tone}`)}>{children}</span>;
}

export function StatusDot({
  tone = "neutral",
  pulse = false,
}: {
  tone?: "neutral" | "accent" | "ok" | "warn" | "danger";
  pulse?: boolean;
}) {
  return (
    <span
      className={cx("dot", `dot--${tone}`, pulse && "dot--pulse")}
      aria-hidden="true"
    />
  );
}
