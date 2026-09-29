---
name: "SysMind AI"
description: "Calm local Windows diagnostics with bounded, readable, auditable evidence."
colors:
  canvas: "#edf0eb"
  surface: "#fafbf8"
  surface-sunken: "#f4f7f3"
  surface-inset: "#edf1ec"
  ink-strong: "#1a241f"
  ink: "#3f4c45"
  ink-muted: "#5d6862"
  ink-subtle: "#78837c"
  accent: "#246340"
  accent-strong: "#194e31"
  accent-soft: "#e4eee7"
  ok: "#26824a"
  warn: "#b07323"
  danger: "#b53c36"
  line: "#e2e7e2"
  line-strong: "#cdd6cf"
typography:
  display:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "23px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 650
    lineHeight: 1.45
rounded:
  control: "10px"
  panel: "14px"
  pill: "999px"
spacing:
  base: "4px"
  control-x: "16px"
  panel-x: "32px"
  shell-x: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.panel}"
    padding: "24px 32px"
---

# Design System: SysMind AI

## Overview

**Creative North Star: "Calm Local Utility"**

SysMind AI uses familiar Windows typography, quiet green-gray surfaces, and one
dominant working surface to make local diagnostics feel controlled rather than
alarming.

The interface privileges truthful state: local-service readiness, the current
collector step, terminal results, partial failures, and cancellation are always
written in plain Chinese. Hardware and redacted event evidence is allowed to
wrap, and data stays readable instead of being shortened for symmetry.

**Key Characteristics:**

- One restrained green accent over warm neutral surfaces.
- One application shell: a navigation rail, a workspace header, and a single
  scrolling working surface.
- Large direct headings, compact metadata, and tabular numeric details.
- Text accompanies every semantic colour and progress state.
- Narrow windows collapse the rail to icons; evidence never drops fields.

## Information Architecture

The product has five destinations, ordered by user priority:

1. **诊断 (Diagnosis)** — the default. Natural-language symptom, an
   application-authored plan, and an evidence-bound report. This is the reason
   the application exists.
2. **快速扫描 (Scan)** — a bounded read-only snapshot of system, hardware,
   disks and processes.
3. **事件日志 (Logs)** — Windows event log analysis over a bounded window.
4. **Agent Runtime** — the restricted Phase 3 runtime self-check. A developer
   and verification surface, not a diagnosis feature.
5. **设置与更新 (Settings)** — application version, updates, and the local data
   and network boundary.

**The One-Section Rule.** Only the active destination is mounted. At most one
collector polls or streams at any moment, and each panel reloads the latest
record from the backend when it mounts. Application updates are maintenance and
must never sit above diagnosis.

## Colours

All colour is defined once in `src/styles/tokens.css`. Components reference
tokens and never introduce raw hex values.

Local green identifies trusted local actions and successful states. Amber is
reserved for waiting, partial evidence and elevated risk; red for failure and
irreversible actions. Neutrals carry nearly all structure.

**The Semantic Status Rule.** Never communicate connection, scan or action state
by colour alone; pair every mark with explicit text.

**The Quiet Canvas Rule.** Canvas and panel neutrals own most of the screen.
Green is reserved for state and action, not decoration.

## Typography

**Display Font:** Segoe UI Variable Text with Segoe UI and system sans-serif fallbacks
**Body Font:** Segoe UI Variable Text with Segoe UI and system sans-serif fallbacks
**Label/Mono Font:** Segoe UI for labels; Cascadia Mono or Consolas for correlation identifiers, tool names and field paths.

**Character:** The system face feels native to Windows and keeps Chinese and
technical values legible. Hierarchy comes from weight and colour as much as from
size; no decorative display face is introduced.

### Hierarchy

Nine steps only, defined as `--text-xs` through `--text-3xl`:

- **Display (`--text-2xl`, 23px):** the application title on the connection gate.
- **Title (`--text-xl`, 19px):** panel headings. Every panel heading is the same size.
- **Subtitle (`--text-lg`, 16px):** section headings and finding titles.
- **Body (`--text-base`/`--text-md`, 13–14px):** explanations and evidence values.
- **Label (`--text-sm`/`--text-xs`, 12–11px):** field names, timestamps, metrics, badges.

**The Evidence Can Wrap Rule.** Hardware names, process names, commands, and
error text wrap when necessary; they are never silently ellipsised.

## Layout

A fixed shell owns the window: a `232px` navigation rail on the left, and a
workspace that stacks a `60px` header above a single scrolling content region.
The page itself never scrolls, so the rail and header stay put while evidence
moves. Content is centred at a maximum of `1180px`.

Each destination renders exactly one Panel. The panel owns its heading,
description, state badge and primary action, so heading scale, padding and
borders are identical across the product.

At `1000px` and below the rail collapses to a `68px` icon strip: labels leave
the visual layout but remain in the accessibility tree, and each destination
carries a hover tooltip. At `720px` and below panel headers stack, metadata is
removed from the workspace header, and inline controls fill the available width.

## Elevation & Depth

Depth is structural and scarce. The navigation rail is flat and separated by a
single border. The working panel is flat with a hairline border. Only the
connection gate may float, using the diffuse `--shadow-panel`.

**The Single Lift Rule.** One surface may float, and only when it is the only
thing on screen. Evidence inside a panel uses spacing and dividers, never
additional card shadows.

## Shapes

Gently rounded utility geometry: `14px` panels, `10px` controls, `8px` inputs
and chips, pill-shaped badges and meters, circular status marks. Borders are
soft structural dividers rather than decoration.

## Components

The shared primitives live in `src/ui/` and their styles in
`src/styles/components.css`.

### Button

- `primary` — deep local green fill; the single most important action on a screen.
- `secondary` — bordered neutral; the default for everything else.
- `ghost` — text-only; used for cancel and other reversible escapes.
- `danger` — red outline; reserved for irreversible confirmation.
- A `busy` control keeps its explicit working label ("正在创建…") and adds a
  spinner; disabled controls stay legible and use `not-allowed`, never `wait`.

### Panel

- One heading, one description, one optional state badge, one optional action.
- Body content is grouped with `PanelSection`, which inserts a divider whenever
  it is not the first block in the body.

### Badge

- States a scope or condition in words: `只读诊断`, `只读 · 含敏感数据`,
  `Fake Provider · 离线`. Colour reinforces, never replaces, the text.

### StatusDot

- An 8px mark pairing colour with adjacent text. Pulses only while starting.

### Notice

- The only way the interface reports an outcome. Tone is explicit
  (`info` / `ok` / `warn` / `danger`), so a failure can never render with the
  same styling as a success.
- `role="alert"` is used for conditions that interrupt; `role="status"` for the rest.

### Fields and Controls

- One `field` wrapper (label + control), one `control` style for inputs, selects
  and textareas, one focus treatment for the whole product.

### Evidence Rows

- Definition rows (`facts`) and list rows (`rows`) are flat and separated by
  hairlines. Disk meters carry both visible text and a semantic `role="meter"`.

## Do's and Don'ts

### Do:

- **Do** state that scans are local and read-only near the primary action.
- **Do** keep status copy understandable to non-technical Windows users.
- **Do** preserve evidence and show bounded per-collector failure.
- **Do** honour keyboard focus and reduced-motion preferences.
- **Do** add a new token before adding a new raw value.

### Don't:

- **Don't** turn system evidence into a grid of floating statistic cards.
- **Don't** truncate hardware truth or hide metrics to simplify narrow layouts.
- **Don't** add phase kickers, decorative sequence numbers, gradients, glass
  effects, or duplicate in-app branding.
- **Don't** present the bounded Agent runtime as autonomous repair, process
  termination, or a Phase 4 diagnosis report.
- **Don't** mount a section that is not visible; background collectors waste
  power and produce duplicated error reporting.

## Feature Surfaces

### Natural-language Diagnosis and Reports

- The composer is the product's primary interaction and sits at the top of the
  default destination.
- A visible read-only label and nearby network disclosure establish scope before
  the primary action; network text names fixed targets and bounded traffic
  without implying a generic connectivity probe.
- The application-authored plan is shown as a compact ordered ledger with
  purpose and exact versioned tool, so progress is understandable without
  exposing raw arguments.
- Reports use one flat evidence document: ranked findings, explanation,
  recommendation, confidence, and readable tool-call/field-path references
  separated by rules rather than nested cards.
- Limitations are first-class report content.

### Controlled Repair Actions

- Controlled repair appears inside a completed evidence report and is visually
  separate from diagnosis.
- The user selects an enumerated candidate, then reviews a confirmation card
  naming the exact target, effect, two-minute scope, and verification behaviour.
- Confirmation is the loudest surface in the product: amber for reversible
  actions, red for forced termination.
- Reject and confirm are explicit per-item decisions; there is no batch
  approval, persistent authorization, or model-authored action.
- Success is shown only after verification.

### Event Log Analysis

- A neutral bordered surface. The sensitivity label states that event logs are
  read-only but may contain sensitive data.
- Filter controls never permit an empty channel or level selection, and the UI
  does not expose raw XPath or arbitrary channel input.

### Bounded Agent Runtime

- Explicitly labelled as the restricted runtime, not a diagnosis report.
- The default Fake Provider is visibly identified as offline; the interface
  never implies that data was sent to a cloud model.
- Users choose from the registered read-only tool catalog. There is no
  free-form tool name, command, privilege, confirmation, or provider-secret input.

### Application Updates

- Updates live in settings, never above the working sections.
- Checking is explicit because it creates outbound traffic; failure states
  confirm that local diagnosis remains usable.
- Long versions and errors wrap; every state remains keyboard accessible and
  never relies on colour alone.
