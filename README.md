# GroundLoop: ControlFirst

GroundLoop is a local, Codex-native scientific red team for experimental transport claims. It challenges a proposed mechanism, separates what the evidence supports from what the result merely suggests, and returns the smallest control experiment needed before trusting the interpretation.

The first user is a materials or experimental-physics researcher interpreting electrical or thermal transport data. GroundLoop is deliberately narrow for the Build Week submission; it does not claim support for every scientific domain or arbitrary dataset. The complete evidence-to-report workflow currently uses a two-wire resistance–temperature CSV. A separate local-only diagnostic accepts one Hioki SM7120 resistance-mode transient export; it reports V/R and a transparent OLS log–log check, not a mechanism conclusion.

Every report keeps four different kinds of conclusion visibly separate:

- **Established** — what supplied source excerpts support;
- **Observed** — what the supplied CSV deterministically contains;
- **Inferred** — an interpretation with uncertainty and an alternative explanation;
- **Unresolved** — the missing evidence that blocks the conclusion.

Its output is one **ControlFirst** experiment: the smallest next measurement that discriminates an interpretation from a plausible confound. Automatic literature retrieval supports this workflow but is not the product itself. GroundLoop is a demonstrator for scientific red-teaming, not a truth-certification or peer-review system.

## What is in this repository

```text
apps/web/                         local React companion UI
packages/core/                    state machine, validation, local run store, CSV analysis
services/local_api/               localhost-only FastAPI adapter
services/mcp_server/              stdio MCP server for Codex
fixtures/four_wire_contact_control/ fixed Build Week walkthrough
```

GroundLoop never calls an OpenAI API and does not need an API key. **Codex with GPT-5.6 is the reasoning host**: it calls GroundLoop's local MCP tools to inspect bounded evidence, validate candidate findings, persist provenance, and export the report. The companion UI deliberately does not make a model call itself.

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

## Judge fast path

GroundLoop is a local developer tool, so judges can exercise the complete
fixture without rebuilding an experiment or supplying an API key:

1. Complete **Install** and **Register the MCP server with Codex** above.
2. Run `./scripts/demo.sh`, then open `http://127.0.0.1:5173`.
3. Choose **Open the resistance-sweep demo**. It loads a clearly labelled,
   synthetic two-wire resistance-temperature record and two measurement-principle
   sources.
4. Choose **Freeze reviewed packet**, then **Copy analysis brief** and paste it
   into a Codex session with the registered `groundloop` MCP server.
5. Let Codex inspect sources, analyze the dataset, validate the four-state
   findings, propose the four-wire control, and export the report. The UI
   automatically returns to the saved report.

The expected conclusion is deliberately conservative: a falling two-wire
resistance trace is observed, but its bulk mechanism is **not established**
until the matched four-wire control is run.

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
3. Choose **Copy Codex source review**. In Codex, call `inspect_retrieved_sources`, read every supplied title/excerpt/locator, then call `adjudicate_sources` once for every candidate. Mark a source `direct` only when its supplied excerpt addresses the measurement, a confound, or the discriminating control. At least one `direct` source is required; contextual and rejected candidates remain in the local audit trail.
4. Add a short measurement-method description and upload a CSV. For the presentation, **Add labelled demo data** makes the synthetic data choice explicit.
5. Before freezing, Codex may call `explore_evidence` to inspect the editable draft. This is exploratory reasoning, not a conclusion or saved decision.
6. Choose **Freeze evidence packet** when you want a decision-ready boundary. The packet can only contain Codex-adjudicated direct sources, exact methods, and local data.
7. Choose **Copy analysis brief**, paste it into a Codex session using GPT-5.6, and keep GroundLoop open while it checks the saved run:

   ```text
   Use the GroundLoop MCP for run <run-id>. This evidence packet is already frozen after semantic source review. Call inspect_sources, then analyze_dataset. Treat only the supplied excerpts, locators, and saved source-review rationales as source support; lexical ordering is never source support. Then validate exactly four findings—one Established, one Observed, one Inferred, and one Unresolved. Propose one atomic ControlFirst experiment, not a bundled follow-up, then export the report.
   ```

8. The researcher explicitly freezes the reviewed packet in GroundLoop. Codex then calls `inspect_sources`, `analyze_dataset`, `reconcile_evidence`, `propose_control`, and `export_report` in order; every saved transition appears in the run's decision history.
9. After either brief is copied, the UI checks the local run automatically; **Refresh** remains available if needed. The report opens with `MECHANISM NOT ESTABLISHED` until the proposed discriminating control is actually run.

The fixture deliberately tests an overreach: a two-wire temperature-dependent resistance trace does not by itself demonstrate a bulk conductivity transition. The required control is the same sweep in four-terminal mode while holding the sample, current, mounting, and temperature program fixed.

For the submission recording, use the resistance fixture as the complete demo path; the timed shot list and narration are in [docs/demo/three-minute-resistance-demo.md](docs/demo/three-minute-resistance-demo.md).

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
