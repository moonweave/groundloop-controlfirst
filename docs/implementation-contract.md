# GroundLoop: ControlFirst — implementation contract

The current product contract is the Convergence Map workflow. Older four-finding fixture Runs remain readable for compatibility, but new UI, MCP, README, and submission behavior must follow this document and [docs/convergence-map-contract.md](./convergence-map-contract.md).

## 1. Scope

GroundLoop is a local, MCP-first research decision workspace. Codex with GPT-5.6 is the reasoning host; GroundLoop is the bounded local system that stores Runs, profiles CSV artifacts, validates evidence references, persists provenance, renders the Convergence Map, and exports the report.

GroundLoop has no hosted service, user API key, direct OpenAI API call, arbitrary URL fetching, PDF crawling, shell execution, experiment execution, email, publication, or external side effect.

## 2. Runtime ownership

```text
apps/web/                 React + TypeScript companion UI
packages/core/            Python domain models, validation, storage, CSV profiling, safe evidence operations
services/local_api/       FastAPI adapter for the local UI
services/mcp_server/      Python MCP adapter for Codex
fixtures/                 method-aware and generic walkthrough data
```

`packages/core` owns Run persistence and validation. The HTTP API and MCP server are adapters and must not duplicate scientific validation rules.

Runtime artifacts live under `.groundloop/runs/` by default and are ignored by Git. Logs may record Run IDs, event names, and error codes only; they must not log claim text, source text, raw CSV rows, or report prose.

## 3. Run lifecycle

Generic Runs begin in `DRAFT`. The researcher can edit the claim, methods, source candidates, and measurement artifacts only while the Run is draft. Once the researcher freezes evidence in the UI, the packet boundary is immutable. Changing claim, source, method, or data after that requires a successor Run.

Exported Runs display as `REPORT EXPORTED`, not as evidence-frozen drafts.

## 4. Evidence objects

### Literature candidate

Codex may import bounded candidates through MCP. GroundLoop stores:

- stable source ID;
- title, authors, publication year;
- URL or DOI as provenance only;
- retrieval provider;
- publication status: `peer_reviewed`, `preprint`, `indexed_abstract`, or `unknown`;
- bounded excerpt or abstract segment;
- locator;
- retrieved timestamp;
- search query or discovery rationale;
- content hash.

GroundLoop never follows the supplied URL or DOI during import. Candidate text is untrusted input. Duplicates by DOI, URL, or content hash are rejected or de-duplicated by the core. Imported candidates start unreviewed and cannot freeze as evidence until Codex records semantic review.

### Source review

Codex must review every current candidate as `direct`, `contextual`, or `reject`. Direct sources require one evidence role:

- `theory_basis`;
- `method_limit`;
- `discriminating_control`.

Search snippets, titles, model memory, or retrieval rank are not evidence.

### Measurement artifact

Every bounded UTF-8 CSV artifact has a stable artifact ID, SHA-256, row/column profile, inferred types, unit signals, missingness, and sample rows. Header inference is advisory. The researcher or Codex-confirmed workflow must bind the scientific X/Y/group roles before freeze.

## 5. Convergence Map contract

Codex records required signatures, then records one alignment per signature. Alignment status is exactly one of:

| Status | Meaning | Validation |
| --- | --- | --- |
| `Observed` | required signature is directly present in data | requires GroundLoop-materialized data evidence |
| `Confounded` | compatible with data, but an alternative explanation remains viable | requires named alternative and method/source-limit evidence |
| `Missing` | required observable is not in the measurement boundary | requires missing reason |
| `Contradicted` | measured result opposes the required signature | requires GroundLoop-materialized data evidence |

The map must show the dominant gap and one control contract. If no control is recorded, UI and export must say `CONTROL PENDING`; they must not show a hardcoded next experiment as if Codex committed it.

## 6. Control contract

The saved control is one atomic next experiment. It must name:

- confound;
- experiment;
- fixed preconditions;
- signatures it closes;
- signatures it leaves open;
- exactly two mutually discriminating outcomes.

It must not execute the experiment or trigger an external action.

## 7. MCP contract

Principal MCP tools:

- `create_run`, `create_generic_run`, `update_run`;
- `import_literature_candidates`;
- `inspect_dataset_profile`;
- `record_measurement_modality`, `set_dataset_binding`, `set_artifact_binding`;
- `record_source_reviews`;
- `create_evidence_packet`;
- `inspect_sources`, `inspect_measurement_artifacts`;
- `materialize_data_evidence`;
- `record_signatures`, `record_alignments`;
- `record_control_contract`;
- `export_report`.

MCP tool descriptions must tell Codex that source contents are untrusted input, not instructions, and that Codex must not invent evidence IDs.

## 8. Local HTTP API contract

The HTTP API listens on loopback only. It creates and reads Runs, uploads bounded CSV artifacts, displays source review state, freezes evidence at the researcher’s request, and serves JSON/Markdown reports. It never calls a model.

The separate Hioki SM7120 transient diagnostic accepts one resistance-mode CSV in memory, derives current as `V/R`, reports a transparent fixed-window OLS log-log diagnostic, and does not create a Run or claim a mechanism.

## 9. Companion UI contract

The UI has four deliberate screens:

1. **Entry:** claim, methods, bounded CSV, and optional explicit fixture.
2. **Convergence Map:** artifact profiles, confirmed bindings, required signatures, alignment states, dominant gap, and control rail.
3. **Source Review:** candidate provenance, review state, source role, and freeze readiness.
4. **Audit / Export:** Codex Run brief, report status, Markdown export, control contract, and decision history.

Footer copy must make the runtime boundary explicit:

```text
GPT-5.6 VIA CODEX MCP
LOCAL UI · NO CLOUD DATA UPLOAD
```

## 10. Required acceptance checks

- Prompt-injection text inside a source excerpt cannot modify tool instructions or create a saved decision.
- Candidate import cannot trigger URL fetching or full-text download.
- A candidate cannot become direct evidence without Codex source review.
- Source candidate changes stale prior reviews and routing.
- Frozen Runs reject source, method, claim, and artifact mutation.
- `Observed` and `Contradicted` alignments require GroundLoop-materialized data evidence.
- `Confounded` alignments require a named alternative explanation.
- Markdown export includes signatures, alignments, dominant gap, source roles, publication status, provenance, excerpt hashes, control contract, and audit history.
- The generic workflow can proceed without a recipe pack.
