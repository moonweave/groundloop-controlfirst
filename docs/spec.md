# GroundLoop: ControlFirst — MVP specification

## Product statement

GroundLoop: ControlFirst is a Codex-native scientific red team for experimental transport claims. It challenges a proposed mechanism against foundational theory, measurement context, and the researcher's data, then identifies the smallest next control experiment needed before trusting the interpretation.

Its governing rule is simple: an observed effect is not, by itself, a proven mechanism.

## User and outcome

The primary user is a materials or experimental-physics researcher interpreting electrical or thermal transport data. They bring a proposed mechanism, measurement context, and a supported CSV. GroundLoop retrieves a small, bounded set of bibliographic metadata and indexed abstracts from one allowlisted academic index; the researcher does not manually collect or paste source URLs.

The Build Week wedge is intentionally narrow. GroundLoop does not claim support for all researchers, arbitrary scientific domains, or arbitrary dataset schemas.

GroundLoop returns a provenance-backed report that separates:

- **Established** — supported by supplied foundational evidence.
- **Observed** — directly present in the supplied data.
- **Inferred** — an interpretation that depends on reasoning.
- **Unresolved** — a question that needs more evidence.

It also produces a **ControlFirst** recommendation: a plausible confound or alternative explanation, the smallest discriminating experiment, and the outcome patterns that would change the interpretation.

Every exported MVP report also begins with the conservative verdict **`MECHANISM NOT ESTABLISHED`**. It names the Inferred and Unresolved finding IDs that block a mechanism claim; the tool never upgrades that verdict merely because Codex generated a fluent explanation.

GroundLoop does not certify scientific truth or replace peer review.

## MVP interaction model

GroundLoop is MCP-first: a researcher uses Codex as the reasoning host and GroundLoop as a local evidence-analysis tool.

```text
Companion web app                 Codex with GPT-5.6
(claim, sources, CSV, reports)         |
             |                         | MCP tool calls
             +---- localhost JSON -----+
                         |
                  GroundLoop Core
          deterministic analysis + provenance
```

The companion web app prepares evidence, lets the researcher inspect it, and renders saved reports. It does not contain a standalone model-analysis button in the MVP.

The expected flow is:

1. The researcher enters a claim or research question in the local web app.
2. GroundLoop retrieves 2–3 indexed abstracts from an allowlisted academic index, marks them as untrusted evidence, and shows their provenance.
3. The researcher adds measurement context and a CSV, then freezes an evidence packet.
4. The researcher asks Codex to analyse the active GroundLoop packet.
5. Codex invokes GroundLoop MCP tools and GPT-5.6 reasons over their structured results.
6. GroundLoop Core saves a JSON and Markdown report.
7. The web app renders the evidence traces, status labels, and ControlFirst recommendation only after export.

Before Codex sees a packet, GroundLoop records a source-by-source lexical relevance screen (`direct`, `contextual`, or `limited`) using transparent overlap between the research question and each title/abstract. This is a retrieval quality gate only: it never declares that a source supports a mechanism. Codex must inspect the returned excerpt and locator for each source separately.

## Architecture

### GroundLoop Core

Python domain logic shared by the MCP adapter and local HTTP adapter. It performs deterministic source/data inspection, validates tool inputs and outputs, and persists runs under a local `runs/<run-id>/` directory.

### MCP server

Exposes the research workflow to Codex. The MVP tools are:

- `create_evidence_packet`
- `inspect_sources`
- `analyze_dataset`
- `reconcile_evidence`
- `propose_control`
- `export_report`

The MCP server does not hold an OpenAI API key. Codex/GPT-5.6 supplies the reasoning layer through the user's existing Codex environment; GroundLoop supplies the local tools and bounded data context.

### Companion web app

A local React and TypeScript interface for:

- creating or selecting a run;
- entering the research question and reviewing automatically retrieved source provenance;
- uploading or selecting a CSV fixture;
- inspecting top-down and bottom-up traces;
- viewing saved reports and source/data provenance.

The app communicates only with the local GroundLoop HTTP adapter during the MVP.

## Core data contract

Every substantive conclusion must be traceable to evidence.

| Object | Required contents |
| --- | --- |
| `EvidenceRef` | `kind` (`source` or `data`), locator (page, row, cell, or region), content, `source_hash` |
| `Expectation` | expected observation, condition, falsifier, evidence references |
| `Observation` | observed pattern or value, evidence references |
| `Finding` | statement, status, evidence references, unresolved reason when relevant |
| `ControlProposal` | confound, discriminating experiment, predicted outcomes, priority, feasibility |

`Established` may be emitted only when at least one supplied foundational `EvidenceRef` supports it. Model reasoning may propose an inference, but it cannot promote that inference to `Established` without the linked evidence.

## MVP scope

The demonstrable Build Week slice includes:

- one research claim;
- two to three automatically retrieved, provenance-bearing indexed abstracts;
- one CSV artifact, beginning with a fixed public fixture for the demo;
- top-down expectation extraction and bottom-up deterministic data inspection;
- the four output states;
- one ranked ControlFirst recommendation;
- exportable JSON and Markdown reports with provenance;
- a local companion UI and a Codex MCP workflow.

The MVP explicitly excludes:

- full-paper search, web crawling, arbitrary URL fetching, or a general paper-review product;
- all scientific domains and all data formats;
- automatic truth certification or peer-review replacement;
- automatic experiment execution, emailing, publishing, or other side effects;
- a hosted standalone runtime that calls the OpenAI API;
- multi-agent orchestration.
- positioning automatic literature search as the primary product outcome.

## Security and trust boundary

All uploaded sources, data files, and text excerpts are untrusted input. A source may contain misleading instructions, malicious prompt text, malformed CSV content, or sensitive research data.

The MVP therefore requires:

- strict separation between tool/system instructions and untrusted source content;
- typed JSON schemas and validation at MCP and HTTP boundaries;
- mandatory evidence references for findings and reports;
- local per-project run isolation and no raw research data in logs;
- file-size and format limits for CSV input;
- no arbitrary network access, shell execution, external actions, or credential access from the analysis path;
- one allowlisted, read-only OpenAlex metadata/abstract lookup used only during the explicit reference-discovery step; user input is treated only as a search term, never as a URL or request target;
- sanitised rendering for Markdown and report content;
- rejection of malformed inputs rather than silent best-effort interpretation.

Threat-model acceptance checks:

1. A prompt-injection string inside a source cannot modify tool instructions or request external actions.
2. A literature lookup cannot be redirected to an arbitrary host or turned into a full-text fetch.
3. An unsupported conclusion cannot be labelled `Established`.
4. Oversized or malformed CSV input is rejected with an actionable error.
5. One project's evidence and reports cannot be read from another project's run directory.

## Completion criteria for the hackathon demo

The MVP is ready to submit when a reviewer can:

1. run the local app and MCP server from the README;
2. ask a research question and observe the bounded automatic reference lookup;
3. create an evidence packet from the retrieved references and CSV;
4. ask Codex to execute the GroundLoop analysis;
5. inspect a report that visibly separates Established, Observed, Inferred, and Unresolved claims;
6. see one specific ControlFirst experiment with predicted differentiating outcomes;
7. trace each substantive output back to a source excerpt or data locator.

The demo video should show this complete loop, including Codex invoking the MCP workflow and GPT-5.6's bounded reasoning role.
