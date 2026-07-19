# GroundLoop: ControlFirst

GroundLoop is a local, MCP-first research workflow that keeps four different kinds of conclusion visibly separate:

- **Established** — what supplied source excerpts support;
- **Observed** — what the supplied CSV deterministically contains;
- **Inferred** — an interpretation with uncertainty and an alternative explanation;
- **Unresolved** — the missing evidence that blocks the conclusion.

Its output is one **ControlFirst** experiment: the smallest next measurement that discriminates an interpretation from a plausible confound. GroundLoop is a demonstrator for evidence handling, not a truth-certification or peer-review system.

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

All runtime research artifacts go under `.groundloop/runs/`, which is ignored by Git. No uploaded source, CSV, or claim is sent to a hosted service by GroundLoop.

## Run locally

Use three terminals from this repository root.

```bash
# 1. Local API — binds only to 127.0.0.1:8000
uv run groundloop-api

# 2. Companion UI — opens at http://127.0.0.1:5173
cd apps/web && pnpm dev --host 127.0.0.1

# 3. Codex MCP stdio server — leave this for Codex, do not type into it
uv run groundloop-mcp
```

The UI itself has no analysis button. It can load the fixture and freeze its evidence packet; Codex then performs the bounded reasoning through MCP.

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

## Fixed demo walkthrough

1. Start the API and UI.
2. In the UI, choose **Load fixture**, then **Prepare evidence**.
3. Copy the displayed handoff prompt into Codex:

   ```text
   Analyse GroundLoop run <run-id>. Call inspect_sources and analyze_dataset first, then validate findings and one ControlFirst proposal before exporting the report.
   ```

4. Codex calls `create_evidence_packet`, `inspect_sources`, `analyze_dataset`, `reconcile_evidence`, `propose_control`, and `export_report` in order.
5. Select **Refresh** in the UI to render the validated, saved report.

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

GroundLoop accepts no URL fetching, paper search, shell execution, arbitrary output paths, model API key, automatic experiment execution, email, publication, or external side effect. The API only listens on loopback; CORS permits its configured local web origin. Source excerpts are stored and returned as `untrusted_content`; tool schemas require typed evidence IDs and reject unsupported conclusion states.

See [docs/spec.md](docs/spec.md) and [docs/implementation-contract.md](docs/implementation-contract.md) for the scope freeze and implementation contract.
