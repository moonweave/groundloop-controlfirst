# GroundLoop: ControlFirst

GroundLoop is a local, Codex-native scientific red team for experimental transport claims. It challenges a proposed mechanism, separates what the evidence supports from what the result merely suggests, and returns the smallest control experiment needed before trusting the interpretation.

The first user is a materials or experimental-physics researcher interpreting electrical or thermal transport data. GroundLoop is deliberately narrow for the Build Week submission; it does not claim support for every scientific domain or arbitrary dataset.

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

GroundLoop never calls an OpenAI API and does not need an API key. Codex is the reasoning host; GroundLoop's MCP tools prepare bounded evidence, validate candidate findings, persist provenance, and export the report.

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

All runtime research artifacts go under `.groundloop/runs/`, which is ignored by Git. Your CSV and measurement context stay local. When you explicitly select **Find references automatically**, GroundLoop sends only the research question to the allowlisted OpenAlex scholarly index, then stores selected metadata and indexed abstracts locally as untrusted evidence. It never follows user URLs, fetches full paper text, or sends data to an LLM API.

## Run locally

Use one terminal from this repository root.

```bash
./scripts/demo.sh
```

This starts the loopback-only API and companion UI at `http://127.0.0.1:5173`; use `Ctrl-C` to stop both. The MCP server is started by the registered Codex command, not in this terminal. For separate terminal control, run `uv run groundloop-api` and `cd apps/web && pnpm dev --host 127.0.0.1`.

The UI itself has no analysis button. It collects a bounded reference set, freezes the evidence packet, and makes the Codex handoff prominent; Codex then performs the bounded reasoning through MCP.

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

## Automatic reference-to-report walkthrough

1. Start the API and UI.
2. Enter a research question, then choose **Find references automatically**. The local API queries only `api.openalex.org` and returns up to three indexed abstracts with DOI/URL, locator, and a local evidence hash.
3. Add a short measurement-method description and upload a CSV. For the presentation, **Add labelled demo data** makes the synthetic data choice explicit.
4. Choose **Freeze evidence packet**. The immutable packet includes a source-by-source lexical relevance screen; it is a retrieval check, not source support.
5. Copy the displayed handoff prompt into Codex:

   ```text
   Analyse GroundLoop run <run-id>. Call inspect_sources and analyze_dataset first, then validate findings and one ControlFirst proposal before exporting the report.
   ```

6. Codex calls `create_evidence_packet`, `inspect_sources`, `analyze_dataset`, `reconcile_evidence`, `propose_control`, and `export_report` in order.
7. Select **Refresh** in the UI to render the validated, saved report. It opens with `MECHANISM NOT ESTABLISHED` until the proposed discriminating control is actually run.

The fixture deliberately tests an overreach: a two-wire temperature-dependent resistance trace does not by itself demonstrate a bulk conductivity transition. The required control is the same sweep in four-terminal mode while holding the sample, current, mounting, and temperature program fixed.

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

GroundLoop accepts no user-provided URL fetching, full-paper crawling, shell execution, arbitrary output paths, model API key, automatic experiment execution, email, publication, or external side effect. The one exception is a read-only, allowlisted request to `api.openalex.org` during explicit reference discovery; the user supplies only a search term, the host/path are fixed in code, and returned abstracts remain `untrusted_content`. The API only listens on loopback; CORS permits its configured local web origin. Tool schemas require typed evidence IDs and reject unsupported conclusion states.

See [docs/spec.md](docs/spec.md) and [docs/implementation-contract.md](docs/implementation-contract.md) for the scope freeze and implementation contract.
