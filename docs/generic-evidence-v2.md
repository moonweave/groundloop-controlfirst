# GroundLoop Generic Evidence v2

GroundLoop v2 is an evidence-bound research workflow for bounded tabular
materials, electronics, and functional-device measurements. It is not a claim
that every scientific file format or measurement modality is supported.

```text
claim + method + CSV + source candidates
  → profile + advisory header signal
  → Codex literature candidates + modality proposal
  → researcher-confirmed binding and recipe
  → semantic source roles + human freeze
  → GroundLoop-materialized data facts
  → signatures + four-state alignments
  → derived gap + one discriminating control
  → Convergence Map + audit + export
```

## Authority boundary

| Action | Codex | GroundLoop | Researcher |
|---|---:|---:|---:|
| Search/import literature | searches outside GroundLoop and imports bounded candidates | validates provenance and stores candidates | reviews source roles |
| Propose modality / recipe | proposes from claim, methods, sources, and profile | stores and exposes only an advisory header signal | confirms or keeps generic |
| Assign column roles and units | proposes | validates | confirms |
| Calculate numeric fact | requests | executes | reviews |
| Freeze evidence | no | no | yes |
| Write signature/alignment/control | proposes | validates | reviews |
| Derive verdict / dominant gap | no | yes | views |

## Generic artifact contract

Each v2 Run stores one bounded UTF-8 CSV artifact with a SHA-256 hash, profile,
sample rows, inferred types, candidate units, and explicit binding. The MVP UI
supports one X column, one to three Y columns, optional group, and optional
acquisition order. Header-derived units remain candidates until confirmed by
the researcher.

Codex may import literature candidates through the provider-neutral
`import_literature_candidates` contract. Each candidate carries a bounded
excerpt, URL/DOI, provider, publication status, locator, retrieval timestamp,
search query, discovery rationale, and excerpt hash. GroundLoop does not fetch
URLs. Import creates an unreviewed candidate only; every candidate must be
adjudicated before the researcher can freeze the source boundary.

No generic operation executes arbitrary expressions, Python, SQL, shell,
smoothing, normalization, baseline correction, interpolation, or implicit fit
selection. The v2 allowlist is:

- `raw_slice`
- `column_summary`
- `endpoint_delta`
- `argmax` / `argmin`
- `range_extrema`
- `linear_fit`
- `correlation`
- `monotonicity`
- `group_summary`

Every operation produces a stable `data-evidence-*` ID, exact columns and row
range, artifact hash, binding hash, operation hash, result, and bounded fact
text. Codex must cite that ID rather than supplying a calculated result.

## Alignment and verdict contract

- `Observed` and `Contradicted` require a GroundLoop-materialized data fact.
- `Confounded` requires materialized data, a named alternative explanation, and
  a source or frozen method boundary explaining why the alternatives remain
  inseparable.
- `Missing` records a structured reason.
- The dominant gap is derived in priority order: Contradicted, Confounded,
  Missing, Observed.
- The verdict is derived: any Contradicted →
  `CONTRADICTED_BY_CURRENT_EVIDENCE`; any Confounded/Missing →
  `NOT_ESTABLISHED`; all Observed → `SUPPORTED_WITHIN_FROZEN_BOUNDARY`.

## Recipes

Recipes are optional, versioned guidance layers over the generic engine. They
do not decide the scientific modality: Codex must first record a proposal from
the claim, methods, supplied sources, and CSV profile, then the researcher must
confirm the matching recipe. A researcher may always retain `generic`. Recipes
can suggest column roles, common limitations, confounds, and visualizations,
but cannot bypass validation or create scientific facts.
`electrical_transport_rt` is the first preserved deep recipe. The generic
spectrum fixture deliberately does not claim a full Raman, PL, or XRD recipe.

## Demonstrations

- `fixtures/four_wire_contact_control`: two-wire R(T) response observed,
  localization confounded, four-wire control proposed.
- `fixtures/generic_spectrum`: arbitrary-header spectrum, explicit binding,
  `argmax` evidence near 620 nm, feature observed, assignment confounded,
  matched temperature-series control proposed.
