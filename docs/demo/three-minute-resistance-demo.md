# GroundLoop — three-minute Build Week demo

## Decision

The safest recording path is one coherent R(T) story, with one short opening line that makes the broader generic CSV path visible. Use the shipped `four_wire_contact_control` fixture for the full end-to-end proof:

> The temperature-dependent resistance change in the sample demonstrates a bulk conductivity transition.

The fixture is synthetic and must remain visibly labelled as a demo. Do not show private PI filenames, private data, or a claimed physical result in this recording.

The video must prove one product outcome:

> A plausible two-wire resistance trend is an observation, not yet a mechanism. GroundLoop identifies the smallest control that could change the conclusion.

## Preflight

1. Start the local app with `./scripts/demo.sh`.
2. Confirm `codex mcp get groundloop` reports the local `groundloop-mcp` command.
3. Run `uv sync --extra test`, `uv run pytest -q`, and `cd apps/web && pnpm install && pnpm lint && pnpm exec tsc -b --noEmit && pnpm build`.
4. Install the repo's `skills/groundloop-controlfirst` skill or have the copied brief ready for a Codex chat that can call the registered MCP server.
5. Use a clean browser window at the GroundLoop start screen. Keep browser zoom at 100%.
6. Confirm the voiceover explicitly says both “Codex” and “GPT-5.6”.

## Shot list and narration

| Time | Screen | Voiceover |
| --- | --- | --- |
| 0:00–0:12 | GroundLoop start screen, generic CSV entry visible, then the method-aware demo button | “GroundLoop starts with a claim, methods, and a CSV. For this demo, I’ll use the transport fixture because it shows the core research problem clearly.” |
| 0:12–0:28 | Click **Open the R(T) contact-control fixture**; show the claim, method note, CSV profile, and source candidates in the DRAFT Run | “The claim is that a falling resistance curve proves a bulk conductivity transition. GroundLoop keeps that claim separate from the data record and from the measurement boundary.” |
| 0:28–0:48 | Codex screen: show `record_source_reviews` with `theory_basis` and `method_limit` roles | “Codex with GPT-5.6 reviews the bounded source excerpts. These sources do not prove the sample mechanism; they define the theory basis and the method limit.” |
| 0:48–1:02 | Return to GroundLoop and click **FREEZE EVIDENCE** | “The researcher freezes the exact claim, methods, source excerpts, CSV hash, and confirmed binding. After this, Codex cannot silently change the evidence.” |
| 1:02–1:36 | Codex screen: show `create_evidence_packet`, `inspect_sources`, `inspect_measurement_artifacts`, and `materialize_data_evidence` | “GPT-5.6 is the reasoning layer through Codex. GroundLoop is the local evidence boundary: it supplies deterministic data facts and requires saved conclusions to cite real evidence IDs.” |
| 1:36–2:08 | Codex screen: show `record_signatures`, `record_alignments`, and `record_control_contract` | “Codex decomposes the mechanism into required signatures. GroundLoop only accepts Observed, Confounded, Missing, or Contradicted, and observed claims require materialized data evidence.” |
| 2:08–2:35 | Return to GroundLoop report and foreground the verdict | “The result is not a fluent yes. It is `MECHANISM NOT ESTABLISHED`: the curve is observed, but the bulk mechanism is still confounded by contacts and leads.” |
| 2:35–2:52 | Control card and its two outcomes | “The smallest decisive next experiment is the same sweep in four-wire mode while holding the sample, current, mounting, and temperature program fixed.” |
| 2:52–3:00 | Verdict, source provenance, export, and closing frame | “GroundLoop does not automate scientific certainty. It makes the next experiment that can earn it explicit.” |

## Recording rules

- Keep the run ID and deterministic report visible long enough to establish that the report is persisted, not a mockup.
- Do not call a source a proof of the sample mechanism. In this fixture, sources establish theory basis and method limits only.
- Do not claim that four-wire mode already confirmed the sample. It is the proposed discriminating control.
- Keep Codex calls short but real. The screen must show structured MCP calls, not only free-form agent prose.
- If time is tight, shorten the source-card and packet shots, not the verdict or the two conditional outcomes.

## Submission caption

**GroundLoop: ControlFirst** is a local, Codex-native research decision workspace. It separates what an experiment observes from what a mechanism claim can identify, then uses GPT-5.6 through Codex and a provenance-bound MCP workflow to specify the smallest discriminating control experiment.
