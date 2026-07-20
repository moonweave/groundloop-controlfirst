# Convergence Map implementation contract

GroundLoop is not a report viewer around a Codex transcript. The shared Run is
the source of truth; Codex proposes semantic records and GroundLoop validates,
freezes, and renders them.

## Run boundary

```text
Run
├── claim
├── method + raw CSV + SHA-256
├── source candidates
├── frozen evidence packet
│   ├── theory_basis source units
│   ├── method_limit source units
│   └── discriminating_control source units
├── required signatures [2–5]
├── alignments [Observed | Confounded | Missing | Contradicted]
├── one control contract
└── audit timeline + export lineage
```

The packet freeze is a user action in the GroundLoop UI. MCP can inspect the
packet only after that action; it cannot silently expand the evidence boundary.

## Alignment invariants

- `Observed` and `Contradicted` require a data evidence reference.
- `Confounded` requires evidence and a named alternative explanation.
- `Missing` requires an explicit missing reason: not measured, not specified by
  theory, outside method capability, or data quality insufficient.
- Every required signature receives exactly one alignment adjudication.
- A control must name at least one signature it closes, any signatures it leaves
  open, and exactly two outcomes.

## Runtime paths

UI-first creates an editable Run, stores the claim/method/CSV locally, and
renders a provisional deterministic map immediately. Codex receives a copied
Run brief, reviews sources, records signatures and adjudications through MCP,
and returns the same Run ID for the UI to render.

Codex-first calls `create_run` with inline CSV content and the claim/method,
then uses the same source-review, freeze, analysis, signature, alignment,
control, and export contracts. No arbitrary filesystem path is accepted by the
MCP boundary.

Legacy four-finding reports remain readable. They are projected into the
current three-signature Map so existing local fixture Runs do not disappear.
