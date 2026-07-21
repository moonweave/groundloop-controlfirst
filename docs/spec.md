# GroundLoop: ControlFirst — current product specification

## Product statement

GroundLoop is a local, Codex-native evidence-bound research convergence workspace for materials, electronics, and functional-device experiments. It helps a researcher test whether a claim is actually identifiable from a specific method, CSV artifact, and reviewed source boundary.

The governing rule is simple: an observed effect is not, by itself, a proven mechanism.

## User and outcome

The primary user is a researcher interpreting experimental measurement data. They bring:

- a mechanism claim or hypothesis;
- method context;
- one or more bounded UTF-8 CSV artifacts;
- literature candidates found or selected by Codex.

GroundLoop returns a Convergence Map that separates:

- **Observed** — the required signature is directly present in GroundLoop-materialized data evidence;
- **Confounded** — the data is compatible, but a named alternative explanation remains viable;
- **Missing** — the required observable is outside the measurement boundary;
- **Contradicted** — the measured result opposes the required signature.

It also produces one **ControlFirst** recommendation: the smallest discriminating measurement that can separate the proposed mechanism from the dominant confound.

GroundLoop does not certify scientific truth or replace peer review.

## Interaction model

GroundLoop is MCP-first: the researcher uses Codex with GPT-5.6 as the reasoning host and GroundLoop as the local evidence boundary.

```text
Companion web app                 Codex with GPT-5.6
(claim, methods, CSV, review)          |
             |                         | MCP tool calls
             +---- localhost JSON -----+
                         |
                  GroundLoop Core
          deterministic evidence + provenance
```

The expected flow is:

1. The researcher enters a claim, method note, and bounded CSV artifact in the local web app.
2. GroundLoop profiles the artifact, assigns stable artifact/column IDs, and asks the researcher to confirm measurement bindings.
3. Codex searches literature outside GroundLoop and imports bounded source candidates with provider, publication status, query or rationale, locator, excerpt, and hash.
4. Codex semantically reviews each candidate as `direct`, `contextual`, or `reject`; direct sources require one role: `theory_basis`, `method_limit`, or `discriminating_control`.
5. The researcher freezes the exact claim, methods, source reviews, artifact IDs, hashes, and bindings.
6. Codex uses GroundLoop MCP tools to materialize deterministic data evidence, record required signatures, record alignments, commit one control contract, and export the report.
7. The web app renders the same saved Run as a Convergence Map, Source Review ledger, Audit timeline, and Markdown export.

The companion web app does not call a model. The MCP server does not hold an OpenAI API key.

## Scope

The current Build Week slice includes:

- generic bounded CSV intake with arbitrary headers;
- multiple measurement artifacts per Run;
- local CSV profiling, hashes, column IDs, and confirmed bindings;
- Codex-imported literature candidates without URL fetching;
- semantic source review and source roles;
- allowlisted deterministic evidence operations such as extrema, deltas, monotonicity, linear fits, correlations, and hysteresis windows;
- Convergence Map signatures and alignments;
- one atomic ControlFirst contract;
- JSON and Markdown export with provenance.

Electrical transport R(T) is the first deep method-aware capability pack. Generic spectrum, sweep, time-series, cyclic, grouped-comparison, and actuator routing are advisory layers, not claims of complete domain-specific scientific coverage.

The repository also contains one separate local transient diagnostic for Hioki SM7120 resistance-mode exports. It derives current as `V/R` and returns a fixed-window OLS log-log diagnostic with warnings. This adapter does not create Runs, search literature, validate claims, or export reports.

## Security and trust boundary

All uploaded source excerpts, method notes, and CSV contents are untrusted input.

GroundLoop therefore requires:

- strict separation between tool/system instructions and untrusted content;
- typed JSON schemas and validation at MCP and HTTP boundaries;
- mandatory evidence IDs for saved alignments;
- local per-project Run isolation and no raw research data in logs;
- file-size and UTF-8 CSV limits;
- no arbitrary URL fetching, full-paper crawling, shell execution, email, publication, or external side effects;
- sanitised rendering for Markdown and report content;
- rejection of malformed inputs rather than silent best-effort interpretation.

Threat-model acceptance checks:

1. Prompt-injection text inside a source excerpt cannot modify tool instructions or create a saved decision.
2. Literature candidate import cannot trigger an arbitrary URL fetch or full-text download.
3. A candidate cannot become direct evidence without Codex source review.
4. An `Observed` or `Contradicted` alignment without GroundLoop-materialized data evidence is rejected.
5. A `Confounded` alignment without a named alternative explanation and method/source-limit evidence is rejected.
6. Oversized or malformed CSV input is rejected with an actionable error.
7. One Run's evidence and reports cannot be read from another Run directory.

## Completion criteria for the hackathon demo

The submission is ready when a reviewer can:

1. run the local app and MCP server from the README;
2. start a generic CSV Run or the R(T) method-aware fixture;
3. copy the Run brief into a Codex session using GPT-5.6;
4. see Codex import or review sources, stop at the human freeze gate, and continue after the researcher freezes;
5. inspect a report that visibly separates Observed, Confounded, Missing, and Contradicted alignments;
6. see one specific ControlFirst experiment with two differentiating outcomes;
7. trace every substantive output back to source provenance, artifact hashes, and evidence IDs.

The demo video must show this complete loop, including Codex invoking GroundLoop MCP tools and GPT-5.6's bounded reasoning role.
