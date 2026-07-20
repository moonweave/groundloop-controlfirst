# GroundLoop: ControlFirst — Devpost project story

## Inspiration

Experimental research often gets stuck at a deceptively small gap: a graph can show a real change, while the mechanism used to explain that change is still untested. A falling two-wire resistance trace, for example, can arise from the sample, contacts, or leads. Existing research assistants are good at finding and summarizing papers; the moment we needed help was later: deciding what the current evidence actually justifies and what one measurement would resolve the ambiguity.

## What it does

GroundLoop: ControlFirst is a local, Codex-native scientific red team for an experimental claim. A researcher records one claim, a bounded source set, a methods note, and a CSV. GroundLoop then keeps four conclusion states visibly separate:

- **Established** — supplied source excerpts support it.
- **Observed** — it is deterministically present in the supplied data.
- **Inferred** — it is a plausible interpretation, with uncertainty and an alternative explanation.
- **Unresolved** — the missing evidence that blocks a decision.

Instead of returning a generic confidence score, it produces one **ControlFirst** experiment: the smallest next test that can distinguish the proposed mechanism from a plausible confound.

The Build Week demo deliberately uses a conservative resistance-temperature fixture. It observes a 45.8% fall in a two-wire resistance trace, but refuses to claim a bulk conductivity transition until the same sweep is repeated in four-terminal mode with the sample, current, mounting, and temperature program held fixed.

## Why it is different

GroundLoop does not try to replace scientific judgment or peer review. It turns an often implicit research move into a transparent, reviewable loop:

1. Start **top-down** with what measurement theory says a method can and cannot establish.
2. Check **bottom-up** what the actual data record contains.
3. Commit only a provenance-bound decision and one discriminating control.

The useful output is not “the model is confident.” It is “this observation is real; this mechanism is not yet established; here is the next test that can decide.”

## How we built it

GroundLoop is a local Python and React application with a loopback-only FastAPI adapter and a stdio MCP server. The shared typed core freezes an evidence packet, calculates the resistance trace deterministically, validates finding states and provenance locators, and exports the saved report. Automatic reference discovery is deliberately bounded to fixed OpenAlex and arXiv scholarly endpoints; returned abstracts remain untrusted evidence rather than instructions, and arXiv results are visibly marked as preprints.

The companion UI makes the workflow legible: frame the question, preserve evidence, check evidence, then decide the next test. The report leads with the decision sequence—what changed, what cannot yet be claimed, and what test can decide—before exposing detailed evidence.

## How we used Codex and GPT-5.6

Codex was the implementation collaborator: it helped define the ControlFirst workflow, build the typed state machine, local API, MCP surface, and React interface, then drove the same fixture-to-report path that a judge can run.

GPT-5.6 is used through Codex as the bounded reasoning host. It can explore hypotheses and counterarguments over a frozen packet, but GroundLoop constrains the saved decision: every finding must cite a supplied evidence ID; inference must include uncertainty and an alternative explanation; and the result must contain one ControlFirst proposal with two discriminating outcomes. No OpenAI API key is required by GroundLoop.

## Challenges we ran into

The central design challenge was avoiding a polished but overconfident research chatbot. We had to make the conservative conclusion feel like progress. The answer was to make the missing control concrete and visual, while preserving the richer source and dataset detail for reviewers who need to audit it.

We also kept the demonstrator narrow. It supports a reproducible two-wire resistance-temperature CSV workflow rather than claiming that one tool can validate arbitrary scientific data.

## What we are proud of

- A real, runnable fixture-to-report loop instead of a static mockup.
- A clear separation between observation and mechanism claim.
- Provenance-bound conclusions that make it difficult to save unsupported confidence.
- One decisive next experiment, understandable at a glance.

## What's next

We will broaden the data adapters while retaining the same decision contract, add more measurement-specific control templates, and evaluate whether the workflow improves how research groups document and resolve competing interpretations.
