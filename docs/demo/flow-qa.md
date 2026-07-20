# GroundLoop flow QA

## Scope

Desktop walkthrough of the shipped `four_wire_contact_control` fixture:

1. Start screen
2. Load resistance demo
3. Freeze evidence packet and copy the Codex brief
4. Complete the MCP sequence and return to the validated report

## Captured evidence

- `/tmp/groundloop-flow-qa/01-start.jpg`
- `/tmp/groundloop-flow-qa/02-setup.jpg`
- `/tmp/groundloop-flow-qa/03-packet.jpg`
- `/tmp/groundloop-flow-qa/04-report.jpg`

## Result

The end-to-end loop passed on run `0cfe3f23-17bb-48b9-8d90-f2de770dd371`:

- the fixture loaded through the UI;
- the packet froze with sources, methods, and CSV preserved;
- the copied brief triggered the UI polling path;
- source inspection, deterministic data analysis, four-state findings, one ControlFirst proposal, and export all succeeded;
- the UI returned to `Validated report` automatically and displayed the saved report notice.

## Findings

### [Fixed P1] — screen transitions preserved the prior scroll position

After loading the demo and after freezing the packet, the browser remained at its prior vertical position. The setup and packet screens can therefore open partway down the page, hiding their step title and primary explanation. This weakens task orientation and makes the recording harder to follow.

**Fix:** the UI now scrolls to the top whenever the active run changes or its workflow state changes. The reset is not animated, so it behaves like navigation to the next deliberate stage.

**Verification:** from a report scrolled to `scrollY: 1083`, selecting `New run` opened at `scrollY: 0`; loading the resistance demo also opened setup at `scrollY: 0`. `/tmp/groundloop-flow-qa/05-setup-top.jpg` confirms the setup title, claim, and workflow rail are visible together.

### [Fixed P2] — the start-screen demo action was below the first viewport

The first viewport communicates the product promise well, but the included demo action is below the visible trace. A first-time viewer may need to hunt or scroll before finding the fastest path.

**Fix:** a concise primary `Open the resistance-sweep demo` action now sits beneath the hero explanation, with its fixture scope shown beside it. The detailed action remains lower on the page.

**Verification:** `/tmp/groundloop-flow-qa/06-start-hero-cta.jpg` shows the CTA in the first viewport. Its bounds were `top: 554.6`, `bottom: 602.6` within a `797px` viewport, and activating it opened the setup screen.

## Strengths

- The report immediately communicates the scientific decision as `observation → limitation → decisive control`.
- The packet handoff clearly distinguishes GroundLoop's evidence boundary from Codex's reasoning role.
- The copied-brief polling path returned to the persisted report without manual state reconstruction.

## Limits

This pass checked the desktop happy path and visible state changes only. Keyboard-only navigation, screen-reader semantics, mobile reflow, and invalid-data recovery still need dedicated QA.
