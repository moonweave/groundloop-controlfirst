# GroundLoop — three-minute resistance demo

## Decision

This recording uses **only** the shipped `four_wire_contact_control` fixture:

> The temperature-dependent resistance change in the sample demonstrates a bulk conductivity transition.

The fixture is synthetic and must remain visibly labelled as a demo. Do not show the PI transient adapter, private PI filenames, or a claimed physical result in this recording.

The video must prove one product outcome:

> A plausible two-wire resistance trend is an observation, not yet a mechanism. GroundLoop identifies the smallest control that could change the conclusion.

## Preflight

1. Start the local app with `./scripts/demo.sh`.
2. Confirm `codex mcp get groundloop` reports the local `groundloop-mcp` command.
3. Run `uv run pytest -q` and `cd apps/web && pnpm lint && pnpm exec tsc -b --noEmit && pnpm build`.
4. Use a clean browser window at the GroundLoop start screen. Keep browser zoom at 100%.
5. Start a new Codex chat that can call the registered GroundLoop MCP server.

## Shot list and narration

| Time | Screen | Voiceover |
| --- | --- | --- |
| 0:00–0:14 | GroundLoop start screen with the included resistance trace visible | “A temperature-dependent resistance curve can look like a mechanism result. But a two-wire measurement also includes contacts and leads. What does this evidence actually support?” |
| 0:14–0:30 | Click **Open the resistance-sweep demo**; show the claim, the fixed CSV, and two measurement-principle sources | “This is a reproducible synthetic transport fixture. The claim is that the falling resistance proves a bulk conductivity transition. GroundLoop keeps that claim separate from the record and from the measurement boundary.” |
| 0:30–0:48 | Source section, especially **Measurement principle** labels | “These sources do not prove anything about the sample. They establish one limitation: two-wire resistance can include contact and lead contributions.” |
| 0:48–1:02 | Click **Freeze reviewed packet**; show the frozen packet / handoff state | “I freeze the exact claim, methods, sources, and CSV. From this point, the reasoning cannot silently change the evidence.” |
| 1:02–1:42 | Codex screen: show `inspect_sources`, then `analyze_dataset`; show structured returned evidence IDs | “Codex with GPT-5.6 is the reasoning layer. GroundLoop is the local evidence boundary: it supplies deterministic data facts and requires every conclusion to cite the frozen record.” |
| 1:42–2:08 | Codex screen: show validated findings and `propose_control` | “GPT-5.6 can infer a bulk interpretation, but GroundLoop requires it to state uncertainty and an alternative explanation. The unresolved question is the contact contribution.” |
| 2:08–2:36 | Return to GroundLoop report and foreground the verdict | “The result is not a fluent yes. It is `MECHANISM NOT ESTABLISHED`: the curve is observed, but the mechanism is still blocked.” |
| 2:36–2:52 | ControlFirst card and its two outcomes | “The smallest decisive next experiment is the same sweep in four-wire mode. If the trend remains, support for a bulk contribution increases. If it weakens, contacts or leads become more plausible.” |
| 2:52–3:00 | Verdict and provenance / closing logo | “GroundLoop does not automate scientific certainty. It makes the next experiment that can earn it explicit.” |

## Recording rules

- Keep the run ID and the deterministic report visible long enough to establish that the report is persisted, not a mockup.
- Do not call a source a proof of the sample mechanism. In this fixture, sources establish the measurement principle only.
- Do not claim that four-wire mode already confirmed the sample. It is the proposed discriminating control.
- Keep Codex calls short but real. The screen must show that the MCP outputs are structured and cited rather than free-form agent prose.
- If time is tight, shorten the source-card and packet shots—not the report verdict or the two conditional outcomes.

## Submission caption

**GroundLoop: ControlFirst** is a local, Codex-native scientific red team for experimental transport claims. It separates what a measurement observes from what a mechanism claim infers, then uses GPT-5.6 through Codex and a provenance-bound MCP workflow to specify the smallest discriminating control experiment.
