# GroundLoop: ControlFirst

GroundLoop is a local, Codex-native **evidence-bound research convergence workspace** for materials, electronics, and functional-device experiments. It connects a claim, frozen method context, bounded tabular measurement artifacts, reviewed literature, falsifiable signatures, reproducible data facts, and one smallest discriminating control.

GroundLoop is deliberately not universal scientific AI. The v2 core accepts bounded UTF-8 CSV measurements with arbitrary headers, profiles them conservatively, requires researcher-confirmed column bindings, and permits only allowlisted deterministic evidence operations. Measurement capability packs guide deterministic operation and validation surfaces; they never limit Codex's signatures, alignments, controls, or scientific reasoning. Electrical transport R(T) remains the first method-aware capability pack. Generic spectrum, sweep, time-series, cyclic, grouped-comparison, and actuator routing are advisory configuration layers rather than claims of complete domain-specific packs. A separate local-only diagnostic accepts one Hioki SM7120 resistance-mode transient export; it reports V/R and a transparent OLS log–log check, not a mechanism conclusion.

Every Convergence Map keeps four alignment states visibly separate:

- **Observed** — the required signature is directly present in the data;
- **Confounded** — the data is compatible, but an alternative explanation remains viable;
- **Missing** — the required observable is not in the measurement boundary;
- **Contradicted** — the measured result opposes the required signature.

Its output is one **ControlFirst** experiment: the smallest next measurement that discriminates an interpretation from a plausible confound. Automatic literature retrieval supports this workflow but is not the product itself. GroundLoop is a demonstrator for scientific red-teaming, not a truth-certification or peer-review system.

## What is in this repository

```text
apps/web/                         local React companion UI
packages/core/                    evidence kernel, generic CSV profiler, safe operations, transport compatibility
services/local_api/               localhost-only FastAPI adapter
services/mcp_server/              stdio MCP server for Codex
fixtures/four_wire_contact_control/ electrical-transport recipe walkthrough
fixtures/generic_spectrum/         generic non-resistance spectrum walkthrough
```

GroundLoop never calls an OpenAI API and does not need an API key. **Codex with GPT-5.6 is the reasoning host**: it calls GroundLoop's local MCP tools to inspect bounded evidence, decompose signatures, record semantic source roles, persist provenance, and export the report. The companion UI deliberately does not make a model call itself; it owns the Run, freeze boundary, map, and export.

## Prerequisites

- Python 3.12 or 3.13
- [uv](https://docs.astral.sh/uv/)
- Node 22.12+ (Node 24 LTS recommended)
- pnpm 11+

## Install

```bash
uv sync --extra test
cd apps/web && pnpm install && cd ../..
```

All runtime research artifacts go under `.groundloop/runs/`, which is ignored by Git. Your CSV and measurement context stay local. When you explicitly select **Find references automatically**, GroundLoop sends only the research question to fixed OpenAlex and arXiv scholarly endpoints, then stores bounded metadata and abstracts locally as untrusted evidence. OpenAlex results are labelled indexed abstracts; arXiv results are always labelled preprints, not peer-reviewed. It never follows user URLs, fetches full paper text, or sends data to an LLM API.

## Run locally

Use one terminal from this repository root.

```bash
./scripts/demo.sh
```

This starts the loopback-only API and companion UI at `http://127.0.0.1:5173`; use `Ctrl-C` to stop both. The MCP server is started by the registered Codex command, not in this terminal. For separate terminal control, run `uv run groundloop-api` and `cd apps/web && pnpm dev --host 127.0.0.1`.

The UI does not make a model call. It collects a bounded reference set, freezes the evidence packet, and makes the Codex handoff prominent; Codex then performs the bounded reasoning through MCP. Its optional **Check transient record** action is deterministic only, processes an uploaded Hioki SM7120 resistance-mode export in memory, and does not create a run or persist the raw file.

## Register the MCP server with Codex

Run once, replacing the path only if you cloned the repository elsewhere:

```bash
codex mcp add groundloop -- uv run --directory "$(pwd)" groundloop-mcp
```

Verify that Codex can see it:

```bash
codex mcp get groundloop
```

If `groundloop-mcp` is not found, run `uv sync --extra test` again from the repository root and verify `uv run groundloop-mcp` starts without an import error.

## Install the GroundLoop Codex skill

The MCP server exposes the tools; the skill teaches Codex the staged workflow and
the human freeze gate. Install it once from the repository root:

```bash
mkdir -p "$HOME/.codex/skills"
ln -sfn "$(pwd)/skills/groundloop-controlfirst" "$HOME/.codex/skills/groundloop-controlfirst"
```

Then start a Codex session with GPT-5.6 and say `Run the GroundLoop workflow for
this Run`. The skill uses the registered `groundloop` MCP server; it does not
upload the CSV or call an OpenAI API directly.

## Generic CSV workflow

The generic v2 path is the canonical research workflow:

1. Create a Run with a claim or hypothesis, method context, one bounded UTF-8 CSV, and optional source candidates. Treat the claim as a proposition to test, not as an established fact.
2. Add additional bounded CSV artifacts when the decision requires a separate control, spectrum, time series, lifetime, geometry, or grouped-comparison table. GroundLoop stores each artifact separately and never merges rows.
3. GroundLoop profiles every artifact's columns, candidate units, missingness, sample rows, and SHA-256. Its header signal is advisory only. Codex reads the claim, method context, artifact profiles, and supplied literature, then records a reviewable modality proposal.
4. Codex may search literature outside GroundLoop and import bounded candidates with provider, publication status, query, rationale, locator, and excerpt hash. Literature informs theory basis, method limits, and controls; it does not prove that this Run's data observed the mechanism. GroundLoop never fetches the supplied URL or DOI; imported candidates remain unreviewed.
5. The researcher confirms one X column, up to three Y columns, optional grouping/order, units, and an optional measurement capability pack for every artifact. `generic` is always valid.
6. Codex semantically reviews every candidate by role. The researcher freezes the exact claim, method, artifact IDs, hashes, profiles, bindings, capability pack metadata, selected excerpts, and source provenance.
7. Codex requests allowlisted operations such as `argmax`, `endpoint_delta`, `grouped_extrema`, `hysteresis_window`, `linear_fit`, `correlation`, or `monotonicity` against explicit artifact IDs. GroundLoop returns the only valid data-evidence IDs and calculated facts.
8. Codex records signatures, alignments, one control, and an export. `Observed` and `Contradicted` require GroundLoop-materialized data evidence. `Confounded` also requires a named alternative plus method/source limit evidence.

The included `generic_spectrum` fixture demonstrates this path with
`wavelength_nm,intensity_counts`. It establishes feature presence through an
`argmax` fact but conservatively leaves microscopic assignment confounded.

## Judge fast path

GroundLoop is a local developer tool, so judges can exercise the complete
fixture without rebuilding an experiment or supplying an API key:

1. Complete **Install** and **Register the MCP server with Codex** above.
2. Run `./scripts/demo.sh`, then open `http://127.0.0.1:5173`.
3. Choose **Open the resistance sweep**. It creates a clearly labelled synthetic
   two-wire resistance-temperature **DRAFT** with supplied source candidates.
4. Choose **Copy Codex brief** and paste it into a GPT-5.6 Codex session with the
   registered `groundloop` MCP server, or invoke the installed
   `groundloop-controlfirst` skill.
5. Let Codex review every source by role. When it stops at the freeze gate, return
   to the UI and choose **FREEZE EVIDENCE**, then tell Codex to continue.
6. Codex inspects the frozen packet, analyzes the dataset, records signatures and
   four-state alignments, commits one four-wire control contract, and exports the
   report. The UI updates the same Map automatically.

The electrical transport fixture remains a complete deep capability-pack demo: a falling
two-wire resistance trace is observed, but its bulk mechanism is **not
established** until the matched four-wire control is run. The generic spectrum
fixture proves that the same evidence-bound workflow is not limited to R(T).

## How we collaborated with Codex and GPT-5.6

GroundLoop was built as a collaboration boundary, not as a hidden chatbot.

- **Product decisions:** Codex helped turn the research problem into a
  ControlFirst workflow: preserve a claim, sources, methods, and measurement;
  keep observed facts separate from mechanism inference; and end with the
  smallest discriminating experiment.
- **Engineering decisions:** Codex implemented and tested the typed local run
  state machine, deterministic CSV analysis, evidence-reference validation,
  loopback-only API, and stdio MCP surface. It also drove the fixture through
  the same source-to-report path that a judge can run.
- **Design decisions:** Codex iterated the companion UI around one immediate
  report story: what changed, what cannot yet be claimed, and which next test
  can decide. The visual report remains an audit trail, not a model answer.
- **GPT-5.6's role:** GPT-5.6, through Codex, explores hypotheses and
  counterarguments over the frozen packet. GroundLoop constrains only the
  commit: findings must cite supplied evidence IDs, inferred claims require an
  uncertainty and alternative explanation, and one ControlFirst proposal must
  name two discriminating outcomes.

## Automatic reference-to-report walkthrough

1. Start the API and UI.
2. Enter a research question, then choose **Find references automatically**. The local API queries only `api.openalex.org` and `export.arxiv.org` with bounded measurement-focused searches and returns up to three labelled abstracts with DOI/URL and locators. These are candidates, not evidence; an arXiv candidate is not a peer-review claim.
3. Choose **Copy Codex source review**. In Codex, call `inspect_retrieved_sources`, read every supplied title/excerpt/locator, then call `record_source_reviews` once for every candidate. Mark a source `direct` only when its supplied excerpt addresses the measurement, a confound, or the discriminating control, and assign one role: `theory_basis`, `method_limit`, or `discriminating_control`.
4. Add a short measurement-method description and upload a CSV. For the presentation, **Add labelled demo data** makes the synthetic data choice explicit.
5. Before freezing, Codex may call `explore_evidence` to inspect the editable draft. This is exploratory reasoning, not a conclusion or saved decision.
6. Choose **Freeze evidence packet** when you want a decision-ready boundary. The packet can only contain Codex-adjudicated direct sources, exact methods, and local data.
7. Choose **Copy analysis brief**, paste it into a Codex session using GPT-5.6, and keep GroundLoop open while it checks the saved run:

   ```text
   Use the GroundLoop MCP for run <run-id>. This evidence packet is already frozen after semantic source review. Call inspect_sources, then analyze_dataset, record_signatures, record_alignments, record_control_contract, and export_report. Treat only the supplied excerpts, locators, and saved role rationales as source support; lexical ordering is never source support. Use only Observed, Confounded, Missing, or Contradicted alignments. Propose one atomic four-wire control, then export the report.
   ```

8. The researcher explicitly freezes the reviewed packet in GroundLoop. Codex then calls `create_evidence_packet`, `inspect_sources`, `analyze_dataset`, `record_signatures`, `record_alignments`, `record_control_contract`, and `export_report` in order; every saved transition appears in the run's decision history.
9. After the brief is copied, the UI checks the local run automatically; **Refresh** remains available if needed. The report opens with `MECHANISM NOT ESTABLISHED` until the proposed discriminating control is actually run.

The fixture deliberately tests an overreach: a two-wire temperature-dependent resistance trace does not by itself demonstrate a bulk conductivity transition. The required control is the same sweep in four-terminal mode while holding the sample, current, mounting, and temperature program fixed.

## Convergence Map contract

The shared Run is the product boundary. The web UI and Codex-first MCP path
both write to the same local Run directory and can be opened by the same Run ID.

```text
claim + method + CSV
        ↓
GroundLoop Run / immutable evidence packet
        ↓
Codex: source roles + required signatures + alignment adjudications
        ↓
GroundLoop: validation + Convergence Map + one control contract
        ↓
decision sheet / Markdown / JSON export
```

The principal MCP contracts are:

- `create_run`, `get_run`, `update_run` — Codex-first creation and shared Run access;
- `create_generic_run`, `add_measurement_artifact`, `inspect_measurement_artifacts`, `inspect_dataset_profile`, `propose_measurement_modality`, `set_dataset_binding`, `set_artifact_binding` — v2 generic intake, researcher-confirmed measurement roles, and optional non-constraining capability pack metadata;
- `record_source_reviews` — one semantic review and one explicit evidence role per source;
- `import_literature_candidates` — import bounded Codex-discovered source candidates without URL fetching;
- `create_evidence_packet` — read the packet only after the researcher freezes it in the UI;
- `inspect_sources`, `analyze_dataset`, `materialize_data_evidence` — bounded source checks, generic profiles, artifact-aware reproducible facts;
- `record_signatures`, `record_alignments` — the claim-to-measurement Convergence Map;
- `record_control_contract`, `export_report` — one atomic next control and the report.

The local store keeps raw inputs, evidence references, source-role review, hashes,
alignment records, control targets, and audit events under `.groundloop/runs/`.
Changing a frozen claim or method requires a successor Run rather than mutating
the frozen packet.

For the submission recording, open with the generic spectrum evidence path and
then show the transport capability pack as proof of method-aware depth. See
[docs/generic-evidence-v2.md](docs/generic-evidence-v2.md) for the v2 contract.

## Additional local transient check

Use **Check transient record** on the start screen only for a Hioki SM7120 CSV exported in resistance mode with these columns after the instrument metadata preamble:

```text
DATE,TIME,Voltage[V],Measurement value[ohm]
```

GroundLoop derives current as `V/R`, uses the fixed 10–100 s window where available, and returns an ordinary-least-squares log–log exponent and R². It labels incomplete windows, voltage drift, non-decaying current, or a low fit quality. This adapter is intentionally separate from the report lifecycle: it does not search literature, freeze evidence, generate findings, or replace an experiment's configured robust-fitting method.

The fixture's source pack is real but intentionally treated as **untrusted input** by the tool boundary:

- [Keysight: How to Measure Resistance Using Four-Wire Measurement](https://www.keysight.com/us/en/use-cases/measure-resistance-using-four-wire-measurement.html), “Removing the effects of cable resistance.”
- [Tektronix: Using the DMM Series to Make Simple and Accurate Resistance Measurements](https://www.tek.com/en/documents/application-note/using-dmm-series-make-simple-and-accurate-resistance-measurements), application-note summary.

The data trace is synthetic demonstration data; it makes no claim about a physical sample.

## Verify

```bash
uv run pytest
cd apps/web && pnpm exec tsc -b --noEmit && pnpm build
```

## Security boundary

GroundLoop accepts no user-provided URL fetching, full-paper crawling, shell execution, arbitrary output paths, model API key, automatic experiment execution, email, publication, or external side effect. The only exceptions are read-only, allowlisted requests to `api.openalex.org` and `export.arxiv.org` during explicit reference discovery; the user supplies only a search term, both host/paths are fixed in code, and returned abstracts remain `untrusted_content`. The API only listens on loopback; CORS permits its configured local web origin. Tool schemas require typed evidence IDs and reject unsupported conclusion states.

See [docs/spec.md](docs/spec.md) and [docs/implementation-contract.md](docs/implementation-contract.md) for the scope freeze and implementation contract.
