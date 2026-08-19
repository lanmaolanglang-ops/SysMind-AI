---
name: "SysMind AI"
description: "Calm local Windows diagnostics with readable, auditable evidence."
colors:
  local-green: "#246340"
  local-green-deep: "#194e31"
  canvas-mist: "#edf0eb"
  surface-white: "#fafbf8"
  text-strong: "#1a241f"
  text-body: "#56625b"
  text-muted: "#5d6862"
  border-soft: "#e5e9e4"
  status-connected: "#26824a"
  status-starting: "#b07323"
  status-error: "#b53c36"
typography:
  display:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(42px, 5vw, 64px)"
    fontWeight: 700
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(24px, 3vw, 34px)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.2
rounded:
  symbol: "9px"
  control: "10px"
  panel: "16px"
  pill: "999px"
spacing:
  compact: "10px"
  control-x: "18px"
  shell-x: "32px"
  panel-x: "40px"
components:
  button-primary:
    backgroundColor: "{colors.local-green}"
    textColor: "{colors.surface-white}"
    rounded: "{rounded.control}"
    padding: "11px 18px"
  connection-chip:
    backgroundColor: "rgba(255, 255, 255, 0.7)"
    textColor: "#48534d"
    rounded: "{rounded.pill}"
    padding: "7px 11px"
  scan-panel:
    backgroundColor: "{colors.surface-white}"
    textColor: "{colors.text-strong}"
    rounded: "{rounded.panel}"
    padding: "34px 40px"
---

# Design System: SysMind AI

## Overview

**Creative North Star: "Calm Local Utility"**

SysMind AI uses familiar Windows typography, quiet green-gray surfaces, and one dominant evidence panel to make local diagnostics feel controlled rather than alarming. Phase 1 extends the original connection shell into an operational scan surface without becoming a dense monitoring dashboard.

The interface privileges truthful state: local-service readiness, current collector, terminal result, partial failure, and cancellation are always written in plain Chinese. Hardware evidence is allowed to wrap and data stays readable instead of being shortened for symmetry.

**Key Characteristics:**

- One restrained green accent over warm neutral surfaces.
- One lifted scan surface; internal evidence is separated by flat rows and dividers.
- Large direct headings, compact metadata, and tabular numeric details.
- Text accompanies every semantic color and progress state.
- Narrow windows preserve the primary scan action and all evidence fields.

## Colors

Local green identifies trusted local actions and successful states. Amber is reserved for waiting or partial evidence, red for failure, and neutrals carry nearly all structure.

**The Semantic Status Rule.** Never communicate connection or scan state by color alone; pair every mark with explicit text.

**The Quiet Canvas Rule.** Canvas and panel neutrals own most of the screen. Green is reserved for state and action, not decoration.

## Typography

**Display Font:** Segoe UI Variable Text with Segoe UI and system sans-serif fallbacks  
**Body Font:** Segoe UI Variable Text with Segoe UI and system sans-serif fallbacks  
**Label/Mono Font:** Segoe UI for labels; Cascadia Mono or Consolas only for correlation identifiers

**Character:** The system face feels native to Windows and keeps Chinese and technical values legible. Hierarchy comes from weight and scale; no decorative display face is introduced.

### Hierarchy

- **Display:** Device-level title only; tightly tracked but never below `-0.04em`.
- **Title:** Scan purpose and major runtime state.
- **Body:** Plain-language explanations, capped to readable line lengths.
- **Label:** Connection state, field names, timestamps, and compact metrics.

**The Evidence Can Wrap Rule.** Hardware names and values wrap when necessary; they are never silently ellipsized.

## Layout

The desktop shell centers a maximum-width workspace. A compact overview aligns the device title with local runtime metadata, followed by one full-width scan panel. Within the panel, definition rows, disk meters, and process rows create scanable evidence without nested cards.

At `760px` and below, runtime metadata is removed because the connection chip already carries readiness. The overview tightens, the scan header stacks, and the primary action remains visible in the first window. Result columns collapse without dropping process memory or utilization values.

## Elevation & Depth

Depth is structural and scarce. The scan panel alone uses the diffuse `0 22px 52px rgba(36, 52, 43, 0.13)` shadow. The top bar, status chip, internal sections, and data rows remain flat.

**The Single Lift Rule.** One operational surface may float; evidence inside it uses spacing and dividers, never additional card shadows.

## Shapes

The system uses gently rounded utility geometry: a 16px scan panel, 10px controls, a pill-shaped connection chip, thin rounded meters, and circular status marks. Borders are soft structural dividers rather than decoration.

## Components

### Primary Scan Button

- Deep local green fill, white text, 10px radius, and compact confident padding.
- Hover darkens the fill; keyboard focus uses a visible offset green outline.
- Disabled creation or cancellation states retain explicit working text.

### Connection Chip

- A translucent neutral pill at the trailing edge of the app bar.
- Combines a semantic dot with Chinese local-service status text.

### Scan Panel

- The single elevated surface contains introduction, action, progress, results, and bounded warnings.
- Progress has an accessible name; terminal results remain in a polite live-status region.
- Partial failures preserve and display successful evidence.

### Evidence Rows and Meters

- System facts use definition rows with wrapping values.
- Disk usage includes visible available/used text plus a semantic meter.
- Process rows preserve name, normalized whole-machine CPU, and memory at every supported width.

## Do's and Don'ts

### Do:

- **Do** state that scans are local and read-only near the primary action.
- **Do** keep status copy understandable to non-technical Windows users.
- **Do** preserve evidence and show bounded per-collector failure.
- **Do** honor keyboard focus and reduced-motion preferences.

### Don't:

- **Don't** turn system evidence into a grid of floating statistic cards.
- **Don't** truncate hardware truth or hide metrics merely to simplify narrow layouts.
- **Don't** add phase kickers, decorative sequence numbers, gradients, glass effects, or duplicate in-app branding.
- **Don't** imply Agent, repair, process termination, or other capabilities that Phase 1 does not provide.
