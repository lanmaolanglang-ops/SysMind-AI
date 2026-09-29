import type { ReactNode } from "react";

export function EmptyState({
  title,
  children,
}: {
  title?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      {title ? <p className="empty__title">{title}</p> : null}
      <p className="empty__text">{children}</p>
    </div>
  );
}
