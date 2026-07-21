# GroundLoop: ControlFirst — Devpost project story

## Inspiration

The research bottleneck I wanted to attack is not “find me more papers.” It is the moment after a researcher already has a plausible theory, a measurement, and a plot that looks meaningful. That is where overclaiming happens: a curve changes, a spectrum has a peak, or a device response shifts, and the team starts talking as if the mechanism has been established.

GroundLoop exists for that gap. It asks a stricter question: what does this specific measurement actually identify, what remains confounded, and what one experiment would decide the next step?

## What it does

GroundLoop is a local, Codex-native evidence-bound research workspace for materials, electronics, and functional-device experiments. A researcher starts with a claim, method notes, one or more bounded CSV artifacts, and literature candidates. GroundLoop profiles the data locally, keeps the Run state and hashes, requires researcher-confirmed measurement bindings, and makes Codex commit every scientific judgment through typed MCP contracts.

Every Convergence Map separates four states:

- **Observed** — the required signature is directly present in the data.
- **Confounded** — the data is compatible, but a named alternative explanation remains viable.
- **Missing** — the required observable is outside the measurement boundary.
- **Contradicted** — the measured result opposes the required signature.

The output is not a generic confidence score. It is one smallest discriminating control experiment: the next measurement that could separate the proposed mechanism from the main confound.

## Why it is different

Most research tools focus on what the literature says. GroundLoop focuses on what the current experiment can identify.

The workflow is deliberately split:

1. Codex and GPT-5.6 do the semantic work: literature exploration, source-role review, signature decomposition, alignment reasoning, and control design.
2. GroundLoop owns the boundary: local data profiles, artifact hashes, source candidate provenance, review status, evidence IDs, freeze gates, validation rules, and export.
3. The researcher owns the final freeze and interpretation boundary.

That makes the tool useful even when the answer is conservative. “Not established yet” becomes actionable because the system also says exactly what to measure next.

## How we built it

GroundLoop is a Python and React application with a loopback-only FastAPI adapter, a typed local evidence core, and a stdio MCP server for Codex. It accepts generic UTF-8 CSV measurements, profiles arbitrary headers, supports multiple measurement artifacts, requires explicit column bindings, and only lets Codex cite GroundLoop-materialized evidence IDs for observed or contradicted data claims.

The first deep capability pack is electrical transport R(T), where a falling two-wire resistance trace is real but still confounded by contact and lead contributions. The generic path is broader: spectra, sweeps, time series, grouped comparisons, cyclic traces, and actuator-like CSVs can enter the same evidence-bound workflow without pretending that GroundLoop has a complete scientific recipe for every domain.

Literature search is not hardcoded into the product conclusion. Codex can search externally and import bounded source candidates with provider, publication status, query or rationale, locator, excerpt, and hash. Those candidates start unreviewed. They only become direct evidence after Codex semantically reviews the supplied excerpt and assigns a role such as `theory_basis`, `method_limit`, or `discriminating_control`.

## How we used Codex and GPT-5.6

Codex was the implementation collaborator and the runtime scientific operator. It helped build the run store, evidence contracts, MCP tools, React companion UI, tests, and submission path. It also drives the actual GroundLoop workflow a judge can run: inspect a CSV profile, import literature candidates, review sources, stop at the human freeze gate, materialize data facts, record signatures and alignments, commit one control contract, and export the report.

GPT-5.6 is used through Codex as the reasoning host. GroundLoop does not require an OpenAI API key and the UI does not make model calls. GPT-5.6 handles the hard semantic work, while GroundLoop constrains what can be saved: search snippets are not evidence, title-only claims are rejected, observed or contradicted alignments require local data evidence IDs, and source support must come from reviewed bounded excerpts.

## Challenges we ran into

The hardest product decision was resisting the urge to look universal. A general scientific chatbot would be easier to pitch but less trustworthy. We instead built a narrow boundary that can accept many tabular measurement forms while being explicit about what is generic, what is method-aware, and what still needs a domain pack.

The second challenge was making a conservative answer feel valuable. The UI had to make “this is confounded” as useful as a positive result by pairing it with a concrete next experiment.

## What we are proud of

- A runnable end-to-end Run rather than a static research mockup.
- A clear split between literature claims, measured facts, and mechanism interpretation.
- Codex-authored reasoning that is reviewable, typed, and provenance-bound.
- A generic CSV path that avoids making the project look like a resistance-only analyzer.
- A deep R(T) fixture that shows why method limits matter in real experimental work.

## What's next

Next we would evaluate the workflow with real lab users, add more method-aware packs for materials and electronics measurements, and support multi-artifact evidence Runs where a claim depends on a primary measurement plus a separate control, calibration, or replicate artifact.
