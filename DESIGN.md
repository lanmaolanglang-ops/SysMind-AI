---
name: "SysMind AI"
description: "Provisional Phase 0 desktop utility shell for local backend connection states."
colors:
  accent-green: "#246340"
  canvas-mist: "#edf0eb"
  surface-white: "#fafbf8"
  surface-translucent: "rgba(248, 250, 247, 0.78)"
  text-strong: "#1a241f"
  text-body: "#56625b"
  text-muted: "#66726b"
  border-soft: "#e5e9e4"
  status-neutral: "#8a938e"
  status-starting: "#b07323"
  status-connected: "#26824a"
  status-error: "#b53c36"
  action-error: "#8e302c"
  action-error-hover: "#762723"
  text-on-dark: "#ffffff"
typography:
  display:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "clamp(42px, 6vw, 72px)"
    fontWeight: 700
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "23px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.75
  label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "13px"
    fontWeight: 680
    lineHeight: 1.2
    letterSpacing: "0.035em"
  mono:
    fontFamily: "Cascadia Mono, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 400
rounded:
  line: "3px"
  symbol: "9px"
  control: "10px"
  panel: "16px"
  pill: "999px"
spacing:
  chip-y: "7px"
  chip-x: "11px"
  control-y: "10px"
  control-x: "16px"
  shell-x: "32px"
components:
  brand-symbol:
    backgroundColor: "{colors.accent-green}"
    textColor: "{colors.surface-white}"
    rounded: "{rounded.symbol}"
    size: "30px"
  connection-chip:
    backgroundColor: "rgba(255, 255, 255, 0.7)"
    textColor: "#48534d"
    rounded: "{rounded.pill}"
    padding: "7px 11px"
  runtime-panel:
    backgroundColor: "{colors.surface-white}"
    textColor: "{colors.text-strong}"
    rounded: "{rounded.panel}"
    padding: "clamp(30px, 4vw, 48px)"
  reconnect-button:
    backgroundColor: "{colors.action-error}"
    textColor: "{colors.text-on-dark}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  reconnect-button-hover:
    backgroundColor: "{colors.action-error-hover}"
    textColor: "{colors.text-on-dark}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
---

# Design System: SysMind AI

## Overview

**Creative North Star: "Calm Local Utility"**

This is a provisional Phase 0 shell, not a finished brand system. Its current visual language is quiet, spacious, and operational: a muted green-gray canvas, one restrained green accent, a single elevated runtime panel, and plain-language connection feedback.

The implementation communicates local safety and service readiness without suggesting diagnostic capabilities that do not yet exist. The reviewed desktop and narrow layouts both use the same hierarchy and state vocabulary; the final review disposition is Pass after contrast fixes.

**Key Characteristics:**

- Warm neutral surfaces with a restrained green accent.
- Large, direct Chinese display copy paired with compact technical metadata.
- Connection state is always expressed with both text and a colored mark.
- One centered runtime panel carries the active system state.
- Generous spacing keeps this foundation screen calm and legible.

## Colors

The palette is a low-saturation green-gray foundation with narrowly assigned semantic status colors.

### Primary

- **Local Green:** Used for the brand symbol, selection, focus outline, and starting activity line.

### Tertiary

- **Starting Amber:** Animated starting-state mark.
- **Connected Green:** Connected-state mark.
- **Error Red:** Disconnected-state mark.
- **Action Red:** Reconnect action, with a darker hover state.

### Neutral

- **Canvas Mist:** The application canvas and base of the subtle top-right radial wash.
- **Surface White:** The runtime panel and light foreground surfaces.
- **Strong Ink:** Primary headings and high-emphasis content.
- **Body Slate:** Supporting copy and footer text.
- **Soft Divider:** Runtime metadata separators.

**The Semantic Status Rule.** Status color is always accompanied by a written state; color never carries connection meaning alone.

## Typography

**Display Font:** Segoe UI Variable Text with Segoe UI and system sans-serif fallbacks  
**Body Font:** Segoe UI Variable Text with Segoe UI and system sans-serif fallbacks  
**Label/Mono Font:** Cascadia Mono with Consolas fallback for correlation identifiers

**Character:** Familiar Windows system typography keeps the utility native-feeling and readable. Weight, scale, and tight display tracking create hierarchy without introducing a decorative typeface.

### Hierarchy

- **Display:** Oversized workspace title, tightly tracked and nearly solid-set.
- **Title:** Runtime-state heading inside the panel.
- **Body:** Introductory and state-supporting copy; the intro is capped at a readable line length.
- **Label:** Phase marker and compact runtime metadata use stronger weight and restrained tracking.
- **Mono:** Correlation identifiers only.

## Layout

The shell has three rows: a fixed-feeling top bar, a flexible workspace, and a compact footer. The workspace is centered within a 1080px maximum width and uses an asymmetric two-column grid: introduction on the left, runtime state on the right. The gap scales fluidly, and the panel retains a minimum practical width on desktop.

At the observed 760px breakpoint, the workspace becomes a single column, horizontal shell padding tightens, and the display title releases its desktop line-length cap. The connection chip remains in the top bar with a narrow maximum width. The mobile screenshot confirms the intro precedes the full-width runtime panel and the footer stays split across the bottom edge.

## Elevation & Depth

Depth is restrained and structural. The runtime panel is the only lifted surface, using one diffuse shadow (`0 22px 52px rgba(36, 52, 43, 0.13)`); the top bar and connection chip rely on translucency and a soft divider rather than elevation. The canvas radial wash adds atmosphere without becoming a separate surface.

**The Single Lift Rule.** Reserve the established shadow for the runtime panel; all other observed surfaces remain flat or translucent.

## Shapes

The shell uses gently rounded utility geometry: a medium-radius panel, compact rounded controls and brand symbol, a fully pill-shaped connection chip, and circular status marks. Borders are sparse and low contrast, appearing only as structural separators. The progress line uses a small radius that follows its thin silhouette.

## Components

### Brand Lockup

- A compact green rounded-square symbol with a white “S” precedes the text name.
- The name uses a small, strong system-sans label; no separate logo asset is established.

### Connection Chip

- A translucent white pill pairs an 8px semantic status mark with a written backend state.
- Status text uses compact, strong, tabular-number-capable typography.
- Starting pulses; connected and disconnected marks are static.

### Runtime Panel

- A warm-white, gently rounded container holds exactly one connection state.
- Padding scales fluidly on desktop and the content is vertically centered within a stable minimum height.
- Starting uses an animated activity line; connected uses a definition list; disconnected uses a heading, recovery copy, optional correlation ID, and reconnect action.

### Reconnect Button

- The only observed button is an error-recovery action with a deep red fill and white text.
- Hover darkens the fill. Keyboard focus uses the global high-contrast green outline with an offset.

## Do's and Don'ts

### Do:

- **Do** keep this document provisional until later phases establish a broader visual language.
- **Do** pair every connection color with explicit state text.
- **Do** preserve the single-panel hierarchy and readable desktop-to-mobile stacking for this Phase 0 shell.
- **Do** honor reduced-motion preferences for the starting indicators.

### Don't:

- **Don't** infer navigation, input fields, diagnostic dashboards, or future repair interfaces from this foundation screen.
- **Don't** treat the temporary “S” symbol as a finalized logo or the current palette as a complete brand identity.
- **Don't** add unobserved component variants to the documented system.
