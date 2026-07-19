# GroundLoop: ControlFirst

GroundLoop: ControlFirst is an evidence-first research workflow for deciding what a result supports and what should be tested next.

## The problem

Research claims are often assembled from two directions:

- foundational theory and prior literature;
- a new figure, CSV, or experimental observation.

The difficult step is reconciling those directions without turning an interpretation into an established fact. A visible effect may be real while the proposed mechanism is still confounded by an artifact or an alternative explanation.

## The proposed workflow

GroundLoop creates two evidence traces:

1. **Top-down:** foundational sources become explicit expectations and conditions.
2. **Bottom-up:** the researcher’s data becomes observable patterns, anomalies, and possible confounds.

The traces are reconciled into four states:

- **Established** — supported by the supplied foundational evidence;
- **Observed** — directly present in the supplied data;
- **Inferred** — an interpretation that still depends on reasoning;
- **Unresolved** — requires additional evidence.

The flagship output is a **ControlFirst** recommendation: the smallest next control experiment that can distinguish the proposed mechanism from a plausible artifact or alternative explanation.

## Current status

This repository is the initial Build Week scaffold. The working prototype will focus on one research claim, a small set of foundational sources, and one data artifact. It is intentionally not a claim-certification system and does not replace peer review.

The MVP is a Codex-compatible MCP server with a local companion web UI. GPT-5.6 reasons through Codex; GroundLoop performs local deterministic analysis and does not require the researcher to provide an OpenAI API key.

See the [MVP technical specification](docs/spec.md) for the product boundary, and the [implementation contract](docs/implementation-contract.md) for the fixed demo, API/MCP contracts, validation rules, security enforcement, and build order.

## Codex and GPT-5.6

Codex is the interaction surface for the MCP workflow as well as the implementation partner for the prototype. A researcher asks Codex to analyse an active GroundLoop evidence packet; Codex invokes GroundLoop's local MCP tools.

GPT-5.6 is the bounded reasoning layer for connecting source-grounded expectations to observations, identifying contradictions and confounds, and drafting a targeted control experiment. Deterministic checks remain responsible for observable data facts; model-generated interpretations are kept separate and traceable.

## Planned prototype flow

1. Enter one claim and its relevant foundational source excerpts.
2. Upload one CSV and an optional methods note.
3. Review top-down and bottom-up evidence traces.
4. Inspect the Established / Observed / Inferred / Unresolved distinctions.
5. Receive a ControlFirst recommendation with the evidence it is intended to discriminate.

## License

This project is an experimental hackathon prototype.
