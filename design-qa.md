# Design QA — Control Map flow

- Source visual truth: `docs/design/groundloop-alignment-final-v1.png` plus the selected page strategy (Proof Path for setup, Two-lane Control Map for packet, Alignment decision brief for report).
- Implementation screenshots: `/tmp/groundloop-implementation/02-setup-selected.png`, `/tmp/groundloop-implementation/03-packet-control-map.png`, `/tmp/groundloop-implementation/05-report-decision-visible.png`.
- Viewport: browser default desktop viewport.
- States checked: retrieved-reference setup, frozen packet, validated report.
- Primary interactions checked: saved-run selection for each state; state-specific control-map content rendered after selection.
- Console errors: none observed in the validated report state.

## Findings

- [Fixed P1] The Decision Brief was hidden at initial render because its motion wrapper kept the critical outcome out of the captured first view.
  - Fix: removed the reveal wrapper from the Decision Brief so the verdict, discriminating experiment, and outcomes render immediately.
  - Post-fix evidence: `/tmp/groundloop-implementation/05-report-decision-visible.png`.

## Required fidelity surfaces

- Typography: retains the existing Geist-based system, high-contrast heading hierarchy, compact mono metadata, and editorial spacing.
- Spacing and layout rhythm: setup now leads with the three-part control path; packet uses the same map; report preserves the decision brief before measurement detail.
- Colors and tokens: theory uses ink blue, measurement uses dark green, and the decision/control lane uses copper; all retain the white canvas and hairline rules.
- Image quality and asset fidelity: no new image assets were added; the implementation uses existing icons and Recharts measurement rendering.
- Copy and content: user-facing wording is action-first; lexical-screen terminology is demoted from the main flow.

## Comparison status

An in-browser side-by-side composite of the source and implementation was required for a full visual-fidelity pass. The browser security policy blocked navigation to the locally constructed comparison surface, and the policy forbids a workaround. Separate source and implementation captures were inspected, but they do not satisfy the required same-input comparison rule.

final result: blocked
