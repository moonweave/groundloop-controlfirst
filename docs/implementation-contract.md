# GroundLoop: ControlFirst — legacy implementation contract

> The current product contract is [docs/convergence-map-contract.md](./convergence-map-contract.md). This document describes the original four-finding Build Week path, which remains supported for backwards compatibility and fixture replay. New UI and MCP work must follow the Convergence Map contract.

This document is retained so existing local Runs and the legacy MCP sequence remain readable. It is not the source of truth for the current Convergence Map UI or the new signature/alignment MCP contracts.

## 1. Scope freeze

GroundLoop is a **local, MCP-first scientific red team for experimental transport claims**. Codex with GPT-5.6 is the reasoning host; GroundLoop is the bounded local tool that prepares evidence, challenges a proposed mechanism, validates conclusion states, persists provenance, and renders one discriminating ControlFirst experiment.

The first user is a materials or experimental-physics researcher interpreting electrical or thermal transport data. This scope is locked for the Build Week submission. Automatic literature retrieval is supporting infrastructure, not the product hero.

The MVP has one complete path only:

```text
research question + allowlisted reference discovery + CSV
  -> local evidence packet
  -> Codex invokes GroundLoop MCP tools
  -> validated findings + one control proposal
  -> JSON/Markdown report rendered in the local web app
```

There is no hosted service, user API key, direct OpenAI API call, arbitrary URL import, PDF parsing, figure analysis, arbitrary code execution, or automatic external action. The bounded external operations are explicit searches against fixed, allowlisted OpenAlex works and arXiv Atom endpoints; they return only metadata and abstracts, never paper full text. arXiv results are always displayed as preprints, not peer-reviewed evidence.

### Additive local transient diagnostic

Outside the frozen evidence-to-report lifecycle, the local HTTP adapter may accept one Hioki SM7120 resistance-mode CSV in memory. It must require the instrument table columns `DATE`, `TIME`, `Voltage[V]`, and `Measurement value[ohm]`; derive current only as `V/R`; use the declared 10–100 s fit window; and return an `ols_log_log` exponent, R², row locator, input hash, and explicit warning codes. It must not create a run, persist the raw upload, perform discovery, call an LLM, construct findings, or imply equivalence to a separately configured robust fit.

## 2. Fixed demo scenario

The shipped fixture is `four_wire_contact_control`.

### Research claim

> The temperature-dependent resistance change in the sample demonstrates a bulk conductivity transition.

### Supplied evidence

- Two short, verified foundational excerpts explaining that two-wire measurements include lead/contact resistance and that four-wire measurement isolates the device-under-test resistance. Each excerpt must carry a real bibliographic citation, stable URL or DOI, page/section locator, and its SHA-256 hash.
- A CSV containing a two-wire resistance-versus-temperature trace for the sample.
- A methods note stating that the reported trace was measured in a two-wire configuration.

### Required output

- **Established:** two-wire measurements can include lead/contact resistance; four-wire measurement tests whether the resistance change remains after that contribution is separated.
- **Observed:** the supplied CSV contains the reported temperature-dependent resistance pattern, with its calculated values and row range.
- **Inferred:** the pattern is consistent with a bulk transition, but does not establish it.
- **Unresolved:** the contribution of contacts/leads to the observed change.
- **ControlFirst:** repeat the temperature sweep with a four-wire configuration under the same current, temperature range, and sample mounting. If the transition persists comparably, the bulk-transition interpretation gains support; if it weakens or disappears, contact/lead resistance is a plausible explanation.
- **Verdict:** `MECHANISM NOT ESTABLISHED`, tied to the validated Inferred and Unresolved finding IDs. This is the required red-team output before any proposed control is run.

This is a demonstrator for evidence handling, not a claim that a real sample has a bulk transition. The source pack must be citation-verified before recording the video; fabricated citations are prohibited.

## 3. Repository layout and runtime ownership

```text
apps/web/                 React + TypeScript companion UI
packages/core/            Python domain models, validation, storage, CSV analysis
services/local_api/       FastAPI adapter for the local UI
services/mcp_server/      Python MCP adapter for Codex
fixtures/four_wire_contact_control/
                           claim, discovered source records, methods note, CSV, manifest
tests/unit/               core contracts and deterministic analysis
tests/integration/        API, MCP, persistence, and security boundaries
tests/e2e/                one visible fixture-to-report journey
```

Use Python 3.12, Pydantic v2, FastAPI, the official Python MCP SDK, and `uv` for the Python services. Use React, TypeScript, Vite, and `pnpm` for the local web app. Do not introduce a database: run files are the durable store for this MVP.

`packages/core` is the only module allowed to read or write run files. The HTTP API and MCP server are thin adapters over it; they must not duplicate validation or analysis logic.

## 4. Run lifecycle and persistence

### State machine

```text
DRAFT
  -> PACKET_READY
  -> SOURCES_INSPECTED
  -> DATA_ANALYZED
  -> FINDINGS_VALIDATED
  -> CONTROL_VALIDATED
  -> EXPORTED
```

- A transition happens only after its output has passed schema validation and is persisted.
- A failed operation leaves the previous state intact and returns a typed error; it never writes a partial report.
- Inputs are immutable once `PACKET_READY` is reached. Editing a claim, source, methods note, or dataset creates a new `DRAFT` run rather than mutating a prior run.
- `EXPORTED` runs are immutable.

### Filesystem rules

The data root is `GROUNDLOOP_DATA_DIR`; its development default is `.groundloop/` under the repository root. The only permitted on-disk destination is:

```text
${GROUNDLOOP_DATA_DIR}/runs/<uuid>/
  manifest.json
  input/claim.json
  input/sources/<source-id>.md
  input/methods.md
  input/dataset.csv
  analysis/source-inspection.json
  analysis/dataset-analysis.json
  report/findings.json
  report/control.json
  report/report.json
  report/report.md
```

Run identifiers are server-generated UUIDs. No tool or HTTP request accepts a filesystem path. All file access resolves the generated run ID and rejects traversal outside the data root.

`manifest.json` contains the schema version, run ID, state, creation time, input hashes, artifact hashes, and the source fixture name. Logs may record run ID, event name, and error code only; they must not log claim text, source text, raw CSV rows, or report prose.

## 5. Domain schemas and validation invariants

All service boundaries exchange Pydantic-validated JSON. Unknown fields are rejected.

### Source input

```json
{
  "id": "src-001",
  "title": "Verified source title",
  "authors": ["Author name"],
  "year": 2024,
  "url_or_doi": "https://doi.org/...",
  "locator": {"page": 12, "section": "Four-wire measurement"},
  "untrusted_content": "The supplied excerpt, limited to 4,000 characters."
}
```

`title`, `authors`, `year`, `url_or_doi`, and `locator` are displayed in the final provenance table. `untrusted_content` is evidence only: it is never used as configuration, a prompt template, or a tool instruction. The fixture manifest records the SHA-256 hash of the complete serialized source object.

### Evidence reference

```json
{
  "id": "src-001:p12",
  "kind": "source",
  "artifact_id": "src-001",
  "locator": {"page": 12, "section": "Four-wire measurement"},
  "excerpt": "short supplied excerpt only",
  "sha256": "64-character lowercase hex hash"
}
```

`kind` is exactly `source` or `data`. Data locators contain a CSV column list plus an inclusive row range; source locators contain the supplied citation locator. Every referenced artifact hash must match the run manifest.

### Finding

```json
{
  "id": "finding-001",
  "statement": "The supplied two-wire trace changes over the measured temperature range.",
  "status": "Observed",
  "evidence_ref_ids": ["data-001:rows-2-41"],
  "reasoning": "Calculated from the uploaded CSV.",
  "uncertainty": null
}
```

Validation rules are non-negotiable:

| Status | Required evidence | Additional rule |
| --- | --- | --- |
| `Established` | one or more `source` references | Statement must not describe a property of the uploaded sample. |
| `Observed` | one or more `data` references | Statement must be reproducible from persisted deterministic analysis; no causal language. |
| `Inferred` | one or more source or data references | `uncertainty` and at least one named alternative explanation are required. |
| `Unresolved` | one or more source or data references | Must state the missing discriminating evidence; it cannot make a positive conclusion. |

The validator rejects a finding that fails these rules. A GroundLoop red-team report must include at least one `Observed`, `Inferred`, and `Unresolved` finding. It also rejects unsupported evidence IDs, duplicate IDs, references to another run, more than 500 characters of statement text, and more than 1,500 characters of reasoning.

### Control proposal

```json
{
  "confound": "Lead/contact resistance contributes to the two-wire trace.",
  "experiment": "Repeat the sweep using a four-wire configuration with unchanged current, temperature range, and mounting.",
  "preconditions": ["same sample", "same temperature range", "same current"],
  "outcomes": [
    {"if": "the transition remains comparable", "then": "bulk-transition interpretation gains support"},
    {"if": "the transition weakens or disappears", "then": "contact/lead contribution is plausible"}
  ],
  "finding_ref_ids": ["finding-003", "finding-004"],
  "priority": "high",
  "feasibility": "standard measurement configuration change"
}
```

A control proposal must cite at least one `Inferred` or `Unresolved` finding, name one confound, include exactly two mutually discriminating outcomes, and contain no instruction to execute an external action.

## 6. Deterministic analysis contract

For the fixture, the CSV schema is fixed:

```text
temperature_c,two_wire_resistance_ohm
```

Allowed input limits are UTF-8 CSV, at most 5 MiB, 10,000 rows, and two required numeric columns. The analysis produces only deterministic facts:

- row count and validated temperature range;
- minimum and maximum resistance and their corresponding rows;
- first-to-last resistance change and percent change;
- monotonicity segments using an explicitly documented threshold;
- a table of the exact rows cited by each data `EvidenceRef`.

It must not infer a phase transition, material mechanism, or source of error. Those are reasoning outputs that must be submitted to the finding validator by the MCP reasoning flow.

## 7. Local HTTP API contract

The local API binds to `127.0.0.1` only. It has no authentication because it never listens on a network interface. CORS permits only the configured local web origin.

| Method and route | Request | Response | Effect |
| --- | --- | --- | --- |
| `POST /api/runs` | fixture name or empty draft | run summary | creates `DRAFT` run |
| `GET /api/runs` | none | run summaries | lists local runs without input contents |
| `GET /api/runs/{run_id}` | none | run detail | reads one run after ID validation |
| `PUT /api/runs/{run_id}/claim` | claim text | run detail | allowed only in `DRAFT` |
| `POST /api/runs/{run_id}/sources` | validated source objects | run detail | allowed only in `DRAFT` |
| `PUT /api/runs/{run_id}/methods` | Markdown text | run detail | allowed only in `DRAFT` |
| `POST /api/runs/{run_id}/dataset` | CSV multipart upload | analysis preview | allowed only in `DRAFT` |
| `POST /api/transient-audit` | one Hioki SM7120 resistance-mode CSV multipart upload | non-persistent deterministic diagnostic | no run is created |
| `POST /api/runs/{run_id}/prepare` | none | evidence packet summary | validates inputs and moves to `PACKET_READY` |
| `GET /api/runs/{run_id}/report` | none | report JSON | available only after `EXPORTED` |
| `GET /api/runs/{run_id}/report.md` | none | Markdown report | available only after `EXPORTED` |

Errors use `{ "code": "...", "message": "...", "details": [] }`. Supported codes are `RUN_NOT_FOUND`, `INVALID_STATE`, `INVALID_INPUT`, `INPUT_LIMIT_EXCEEDED`, `ARTIFACT_HASH_MISMATCH`, and `VALIDATION_FAILED`.

The HTTP API never invokes a model and never produces a finding or control proposal.

## 8. MCP contract

Every MCP tool accepts a `run_id` and operates only on a prepared local run. Tool descriptions must tell Codex that source contents are evidence, never instructions, and that it must not invent evidence IDs.

| Tool | Input beyond `run_id` | Output / state change |
| --- | --- | --- |
| `inspect_retrieved_sources` | none | every retrieved candidate excerpt/locator, provider/status, and lexical reading order; does not change state |
| `adjudicate_sources` | `SourceAdjudication[]` | requires exactly one `direct`/`contextual`/`reject` decision for every candidate and selects at least one direct source; remains `DRAFT` |
| `create_evidence_packet` | none | returns the compact packet only after the researcher explicitly freezes it in the local UI; never changes state |
| `inspect_sources` | none | frozen semantic source-review rationales, source-derived expectations, and source evidence IDs; moves to `SOURCES_INSPECTED` |
| `analyze_dataset` | none | deterministic dataset facts and data evidence IDs; moves to `DATA_ANALYZED` |
| `reconcile_evidence` | proposed `Finding[]` | validates and persists findings; moves to `FINDINGS_VALIDATED` |
| `propose_control` | proposed `ControlProposal` | validates and persists one proposal; moves to `CONTROL_VALIDATED` |
| `export_report` | none | JSON/Markdown report paths and summary; moves to `EXPORTED` |

`reconcile_evidence` and `propose_control` are validators/persistence tools, not model calls. Codex and GPT-5.6 generate candidate reasoning from the bounded tool outputs, then submit it for validation. If validation fails, the returned error identifies the violated rule and Codex revises only that structured candidate.

The final report is generated from validated JSON with a deterministic template. It must display `MECHANISM NOT ESTABLISHED`, the blocking Inferred/Unresolved finding IDs, source titles, semantic source-review rationales, abstract-level limitations when applicable, locators, hashes, data row ranges, exactly one finding in every state, the control proposal, and the decision history. Lexical retrieval screens may guide reading before freezing but are not report evidence. It never displays hidden tool instructions or raw files outside their cited excerpts.

## 9. Companion UI contract

The UI has four report-workflow views plus one clearly separate, non-persistent transient diagnostic block:

1. **Run setup:** create a draft from a research question; automatically retrieve 2–3 OpenAlex/arXiv abstracts as candidates; label every arXiv result as a preprint, not peer-reviewed; then copy a deliberate Codex source-review brief. Candidate retrieval alone cannot freeze a packet: Codex must label every candidate `direct`, `contextual`, or `reject`, with at least one direct source. Then add a methods note and CSV. The fixture remains an explicit demo-only option.
2. **Evidence packet:** show immutable source/data cards, hashes, expected conditions, and deterministic data facts after preparation.
3. **Codex handoff:** before a packet exists, present a **Copy Codex source review** action that asks Codex to call `inspect_retrieved_sources` and `adjudicate_sources`. After source review, the researcher explicitly freezes the selected sources, methods, and data; this produces a visible audit event. After a packet exists, present one deliberate **Copy analysis brief** action with the exact prompt: `Use the GroundLoop MCP for run <run_id>. This evidence packet is already frozen after semantic source review. Call inspect_sources, then analyze_dataset. Treat only the supplied excerpts, locators, and saved source-review rationales as source support; lexical ordering is never source support. Then validate exactly four findings—one Established, one Observed, one Inferred, and one Unresolved. Propose one atomic ControlFirst experiment, not a bundled follow-up, then export the report.` The researcher pastes either brief into Codex; the browser does not call Codex itself or use a model API key. After copy, the UI polls the local saved run so the researcher need not repeatedly refresh manually.
4. **Report:** render the final four-state evidence table, control proposal, and provenance links after export.

The transient diagnostic block must identify the accepted instrument/schema, show its OLS method and fit window, and state that its result does not establish a mechanism or replace the study's configured robust analysis.

Markdown rendering uses a sanitiser with raw HTML disabled. The UI must make it visually impossible to confuse an `Inferred` statement with an `Established` statement.

## 10. Security enforcement and tests

Security requirements are implementation constraints, not documentation claims:

- The process accepts no user-supplied URL or network destination. Its only runtime HTTP clients are explicit reference-discovery adapters using fixed HTTPS OpenAlex and arXiv endpoints, query-encoding a bounded research question, using short timeouts, and never fetching full text.
- The process accepts no shell command, executable path, arbitrary filename, or external URI from the UI or MCP tool schemas.
- Upload names are discarded; files are copied under generated artifact IDs.
- Source excerpts are transported as a distinct `untrusted_content` field and never concatenated into tool instructions.
- Tool outputs are JSON-serialised and schema-validated before persistence or rendering.
- All errors redact input content.

Required negative tests:

1. A source excerpt containing `ignore prior instructions` cannot alter a tool response or create a finding.
2. A discovery request cannot change the lookup host/path or trigger a full-text fetch.
3. A finding marked `Established` with only data references is rejected.
4. A finding marked `Observed` with causal language or no deterministic analysis reference is rejected.
5. A malformed, oversized, non-UTF-8, or path-traversal upload is rejected without creating a run artifact outside the data root.
6. A run ID from another run cannot be referenced by a finding or artifact request.
7. Raw claim/source/CSV content is absent from captured application logs.

## 11. Build order and acceptance commands

Implement in this order. Each slice must be committed only after its listed checks pass.

1. **Core:** schemas, state machine, file store, fixture loader, and deterministic CSV analysis.
2. **Boundaries:** FastAPI endpoints and MCP tools that share the Core contract.
3. **Reasoning loop:** candidate-finding/control validators, deterministic report export, and a scripted Codex MCP walkthrough.
4. **UI:** the four local views and report rendering.
5. **Hardening:** negative security tests, end-to-end fixture run, README install/run/test instructions, and a recorded three-minute demo.

The final `README.md` must contain the exact prerequisite versions, install commands, local API/UI/MCP launch commands, Codex MCP registration configuration, fixture walkthrough, test command, expected report screenshot, and troubleshooting for a missing MCP server. A reviewer must be able to reproduce the fixture-to-report flow on a clean machine without an OpenAI API key.

The implementation is complete only when the fixture run passes unit, integration, and end-to-end tests; the web app visibly renders the exported report; and a human can complete the Codex handoff using the documented prompt.
