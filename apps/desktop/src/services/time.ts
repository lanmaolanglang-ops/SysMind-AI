/** Parse API timestamps that may be naive UTC and format in the viewer's locale. */
export function parseApiTimestamp(value: string): Date {
  // SQLAlchemy/SQLite may emit ISO without a timezone. Those values are UTC.
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

export function formatLocalTimestamp(value: string): string {
  return parseApiTimestamp(value).toLocaleString("zh-CN");
}

export function formatLocalTime(value: string): string {
  return parseApiTimestamp(value).toLocaleTimeString("zh-CN");
}
