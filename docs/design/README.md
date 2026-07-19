# GroundLoop UI direction

## Selected implementation target

![GroundLoop Alignment final target](groundloop-alignment-final-v1.png)

This is the visual baseline for the MVP report screen. It uses the fixed `four_wire_contact_control` scenario, marks the research claim as not established, separates source-backed theory from deterministic measurement, makes the unresolved contact/lead contribution explicit, and ends with one discriminating four-wire control.

![Generated visual direction board](groundloop-ui-direction-v1.png)

The first image above is an early generated visual direction board, not a literal UI specification. It established the desired information hierarchy, but its paper texture is superseded by the white-background directions below.

## White-background directions

### 1. Clinical instrument — recommended base

![Clinical instrument direction](ui-direction-clinical-v2.png)

Strong for the primary report screen: it makes deterministic measurement and provenance feel trustworthy, and it can be implemented cleanly with normal UI primitives. Keep its white canvas, cobalt data, and restrained coral decision panel. Do not retain its many small thumbnail modules.

### 2. Swiss editorial

![Swiss editorial direction](ui-direction-editorial-v2.png)

Strong for brand, onboarding, and the claim header. It is too sparse for the working report screen, so use its typography, whitespace, and tall ControlFirst edge treatment—not its literal layout.

### 3. Evidence map

![Evidence map direction](ui-direction-evidence-map-v2.png)

This is the most distinctive product moment: a visible map of source evidence, measurements, inference, and the unresolved mechanism. Use it only on the Evidence Packet screen or as a focused report module. Making every screen a graph would obscure the actual research workflow.

## Chosen synthesis

Use the final **Alignment** target as the report baseline: source theory on the left, measurement data on the right, the unresolved gap in the center, a compact four-state strip, and ControlFirst as the bottom decision destination. The earlier clinical, editorial, and evidence-map directions remain exploration references only.

## Design position

GroundLoop should feel like a scientific working paper, not an AI chat surface or an enterprise dashboard. The interface makes a researcher slow down at the exact point where an observation risks becoming an overconfident mechanism claim.

### Visual rules

- **Base:** pure white `#FFFFFF`, graphite `#20211E`, ink `#17324D`.
- **Evidence:** source-backed `#17324D`, observed measurement `#355B3C`, inferred `#7A6955`, unresolved `#6A4A4A`.
- **Decision:** copper `#C8502A` is reserved for ControlFirst and destructive attention only.
- **Typography:** editorial serif headings; compact monospaced metadata and locators; neutral sans-serif for controls.
- **Geometry:** square or lightly rounded edges, hairline rules, no glass cards, no decorative gradients, no oversized dashboard metrics.
- **Accessibility:** each evidence state has a label, icon, and pattern in addition to color. Contrast remains legible on the paper background.

## Navigation and screens

The product has four deliberate screens, matching the implementation contract:

1. **Run setup** — claim, source excerpts, methods note, and CSV. It produces a local packet only.
2. **Evidence packet** — immutable source/data cards and deterministic checks. It establishes the handoff boundary.
3. **Codex handoff** — an explicit run ID and copyable MCP prompt; no hidden model call from the browser.
4. **Report** — four-state findings, provenance ledger, and the single ControlFirst proposal.

The static [report prototype](controlfirst-report-prototype.html) is an early structural experiment. The selected Alignment image above is the current visual target; persisted report JSON remains the source of truth for all visible content.

## Layout contract for the report

```text
Header: run identity, state, exported timestamp
Claim strip: claim plus method qualifier
Evidence traces: Top-down sources | Bottom-up deterministic data
Compact finding strip: Established | Observed | Inferred | Unresolved
Provenance ledger: source/page and CSV row locators
ControlFirst: confound, smallest experiment, discriminating outcomes
```

On narrow screens, the traces and state matrix stack vertically; the ControlFirst panel remains visually last and full width. No state is hidden behind hover-only UI.
