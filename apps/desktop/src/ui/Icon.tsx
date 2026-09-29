/**
 * The complete icon set. Five navigation marks, one visual language:
 * 24px grid, 1.7 stroke, round caps, no fills.
 */

export type IconName = "diagnose" | "scan" | "logs" | "runtime" | "settings";

const PATHS: Record<IconName, string[]> = {
  // A question in a speech bubble with a pulse trace inside.
  diagnose: [
    "M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v7a2.5 2.5 0 0 1-2.5 2.5H9.5L4 19z",
    "M7.5 9.2h1.9l1.3-2.2 1.6 4.4 1.2-2.2h2.0",
  ],
  // A gauge needle: a snapshot of current load.
  scan: ["M4.5 17a8 8 0 1 1 15 0", "M12 13.5 16 9.5", "M12 17.2h.01"],
  // A log document with entries.
  logs: ["M6.5 3h7l4.5 4.5V21h-11.5z", "M13.5 3v4.5H18", "M9.5 12.5h5", "M9.5 16h5"],
  // A bounded terminal: the restricted runtime.
  runtime: ["M3.5 5.5h17v13h-17z", "M7.5 10l2.2 2.2-2.2 2.2", "M12.5 14.4h4"],
  // A control dial for settings.
  settings: [
    "M12 9.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6z",
    "M12 3v2.3M12 18.7V21M4.4 7.6l2 1.1M17.6 15.3l2 1.1M4.4 16.4l2-1.1M17.6 8.7l2-1.1",
  ],
};

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className="nav__icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
