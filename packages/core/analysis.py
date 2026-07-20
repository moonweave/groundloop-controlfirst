from __future__ import annotations
import csv, hashlib, io, math, re
from datetime import datetime
from statistics import median

from .models import (
    ClaimInput,
    DatasetAnalysis,
    EvidenceRef,
    Locator,
    SourceInput,
    SourceRelevance,
    TransientAnalysis,
)

MAX_BYTES, MAX_ROWS = 5 * 1024 * 1024, 10_000
REQUIRED = ("temperature_c", "two_wire_resistance_ohm")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "change", "data", "does", "for", "from",
    "in", "is", "it", "measurement", "of", "on", "or", "sample", "that", "the", "this", "to", "with",
}

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def parse_dataset(raw: bytes, artifact_id="data-001") -> tuple[DatasetAnalysis, EvidenceRef]:
    if len(raw) > MAX_BYTES: raise ValueError("CSV exceeds the 5 MiB input limit")
    try: text = raw.decode("utf-8")
    except UnicodeDecodeError as exc: raise ValueError("CSV must be UTF-8") from exc
    try:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames != list(REQUIRED): raise ValueError("CSV must contain exactly temperature_c,two_wire_resistance_ohm")
        rows=[]
        for line, record in enumerate(reader, start=2):
            if line > MAX_ROWS + 1: raise ValueError("CSV exceeds the 10,000 row limit")
            try: rows.append({k: float(record[k]) for k in REQUIRED})
            except (TypeError, ValueError) as exc: raise ValueError(f"CSV row {line} contains non-numeric values") from exc
        if not rows: raise ValueError("CSV must contain at least one data row")
        if any(not math.isfinite(v) for row in rows for v in row.values()): raise ValueError("CSV cannot contain NaN or infinite values")
    except csv.Error as exc: raise ValueError("Malformed CSV") from exc
    temps=[r[REQUIRED[0]] for r in rows]; vals=[r[REQUIRED[1]] for r in rows]
    mn, mx=min(vals), max(vals); threshold=max((mx-mn)*0.001, 1e-12)
    segments=[]; direction=None; start=2
    for i in range(1,len(vals)):
        current = "rising" if vals[i]-vals[i-1] > threshold else "falling" if vals[i]-vals[i-1] < -threshold else "flat"
        if direction is None: direction=current
        elif current != direction:
            segments.append(f"rows {start}-{i+1}: {direction}"); start=i+1; direction=current
    segments.append(f"rows {start}-{len(vals)+1}: {direction}")
    if vals[0] == 0:
        raise ValueError("CSV baseline resistance cannot be zero")
    analysis=DatasetAnalysis(columns=list(REQUIRED), row_count=len(rows), temperature_range_c=(min(temps),max(temps)), resistance_min_ohm=mn, resistance_min_row=vals.index(mn)+2, resistance_max_ohm=mx, resistance_max_row=vals.index(mx)+2, first_resistance_ohm=vals[0], last_resistance_ohm=vals[-1], change_ohm=vals[-1]-vals[0], percent_change=(vals[-1]-vals[0])/vals[0]*100, monotonicity_segments=segments, cited_row_range=(2,len(rows)+1), rows=rows)
    ref=EvidenceRef(id=f"{artifact_id}:rows-2-{len(rows)+1}",kind="data",artifact_id=artifact_id,locator=Locator(columns=list(REQUIRED),row_start=2,row_end=len(rows)+1),excerpt=f"CSV rows 2–{len(rows)+1}; {len(rows)} validated numeric rows.",sha256=sha256_bytes(raw))
    return analysis, ref


def parse_hioki_sm7120_transient(
    raw: bytes,
    artifact_id: str = "data-001",
    fit_window_s: tuple[float, float] = (10.0, 100.0),
) -> tuple[TransientAnalysis, EvidenceRef]:
    """Inspect one Hioki SM7120 resistance-mode transient without inferring a mechanism.

    The instrument exports a metadata preamble followed by a fixed table. Current is
    derived only as V/R and the exponent is a transparent ordinary-least-squares
    log-log diagnostic. It is intentionally not a replacement for an experiment's
    separately specified robust fitting pipeline.
    """
    if len(raw) > MAX_BYTES:
        raise ValueError("CSV exceeds the 5 MiB input limit")
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8") from exc

    header_index = next(
        (index for index, line in enumerate(lines) if line.startswith("DATE,TIME,")),
        None,
    )
    if header_index is None:
        raise ValueError("CSV is not a recognised Hioki SM7120 resistance export")
    try:
        reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
        required = ("DATE", "TIME", "Voltage[V]", "Measurement value[ohm]")
        if not reader.fieldnames or any(name not in reader.fieldnames for name in required):
            raise ValueError("CSV is missing required Hioki transient columns")
        records: list[tuple[datetime, float, float, int]] = []
        for source_row, record in enumerate(reader, start=header_index + 2):
            if len(records) >= MAX_ROWS:
                raise ValueError("CSV exceeds the 10,000 row limit")
            try:
                timestamp = datetime.fromisoformat(f"{record['DATE'].strip()}T{record['TIME'].strip()}")
                voltage = float(record["Voltage[V]"].strip())
                resistance = float(record["Measurement value[ohm]"].strip())
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f"CSV row {source_row} contains an invalid Hioki transient value") from exc
            if not math.isfinite(voltage) or not math.isfinite(resistance) or resistance <= 0:
                raise ValueError(f"CSV row {source_row} must contain finite voltage and positive finite resistance")
            records.append((timestamp, voltage, resistance, source_row))
    except csv.Error as exc:
        raise ValueError("Malformed CSV") from exc

    if len(records) < 3:
        raise ValueError("Hioki transient CSV must contain at least three data rows")
    offsets = [(item[0] - records[0][0]).total_seconds() for item in records]
    if any(later <= earlier for earlier, later in zip(offsets, offsets[1:])):
        raise ValueError("Hioki transient timestamps must be strictly increasing")
    interval_s = median(later - earlier for earlier, later in zip(offsets, offsets[1:]))
    if not math.isfinite(interval_s) or interval_s <= 0:
        raise ValueError("Hioki transient sampling interval must be positive")
    rows = [
        (offset + interval_s, voltage, voltage / resistance, source_row)
        for offset, (_, voltage, resistance, source_row) in zip(offsets, records)
    ]
    start_s, end_s = fit_window_s
    if start_s <= 0 or end_s <= start_s:
        raise ValueError("fit window must be a positive increasing interval")
    fit_rows = [row for row in rows if start_s <= row[0] <= end_s]
    if len(fit_rows) < 3:
        raise ValueError("Hioki transient does not contain three points in the requested fit window")
    xs = [math.log(row[0]) for row in fit_rows]
    ys = [math.log(row[2]) for row in fit_rows]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if denominator == 0:
        raise ValueError("Hioki transient fit window has no time variation")
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    intercept = mean_y - slope * mean_x
    residual_sum = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    total_sum = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1.0 if total_sum == 0 and residual_sum == 0 else 0.0 if total_sum == 0 else 1 - residual_sum / total_sum

    voltages = [row[1] for row in rows]
    voltage_median = median(voltages)
    warnings: list[str] = []
    if rows[0][0] > start_s or rows[-1][0] < end_s:
        warnings.append("FIT_WINDOW_INCOMPLETE")
    if abs(max(voltages) - min(voltages)) > max(abs(voltage_median) * 0.01, 1e-12):
        warnings.append("VOLTAGE_DRIFT")
    if rows[-1][2] >= rows[0][2]:
        warnings.append("NON_DECAYING_CURRENT")
    if r2 < 0.95:
        warnings.append("LOW_LOG_LOG_FIT")

    analysis = TransientAnalysis(
        artifact_id=artifact_id,
        columns=["DATE", "TIME", "Voltage[V]", "Measurement value[ohm]"],
        row_count=len(rows),
        source_row_range=(records[0][3], records[-1][3]),
        time_range_s=(rows[0][0], rows[-1][0]),
        voltage_range_v=(min(voltages), max(voltages)),
        first_current_a=rows[0][2],
        last_current_a=rows[-1][2],
        fit_window_s=fit_window_s,
        fit_point_count=len(fit_rows),
        fit_method="ols_log_log",
        decay_exponent=-slope,
        log_log_r2=r2,
        warnings=warnings,
    )
    ref = EvidenceRef(
        id=f"{artifact_id}:rows-{records[0][3]}-{records[-1][3]}",
        kind="data",
        artifact_id=artifact_id,
        locator=Locator(columns=analysis.columns, row_start=records[0][3], row_end=records[-1][3]),
        excerpt=(
            f"Hioki SM7120 resistance export rows {records[0][3]}–{records[-1][3]}; "
            f"{len(rows)} validated rows, V/R current conversion, OLS log-log diagnostic."
        ),
        sha256=sha256_bytes(raw),
    )
    return analysis, ref

def source_refs(sources: list[SourceInput]) -> list[EvidenceRef]:
    refs=[]
    for source in sources:
        serialized=source.model_dump_json().encode()
        refs.append(EvidenceRef(id=f"{source.id}:evidence",kind="source",artifact_id=source.id,locator=source.locator,excerpt=source.untrusted_content[:1000],sha256=sha256_bytes(serialized)))
    return refs


def screen_source_relevance(claim: ClaimInput, sources: list[SourceInput]) -> list[SourceRelevance]:
    """Screen sources against the claim using only transparent lexical overlap.

    This is deliberately not a relevance ranking model. It tells Codex which supplied
    abstracts share claim terms so it can adjudicate each source without treating a
    search result as support for a mechanism.
    """
    claim_terms = _meaningful_terms(claim.claim)
    screens: list[SourceRelevance] = []
    for source in sources:
        source_terms = _meaningful_terms(f"{source.title} {source.untrusted_content}")
        source_stems = {_stem(term) for term in source_terms}
        matched = sorted(term for term in claim_terms if _stem(term) in source_stems)[:12]
        verdict = "direct" if len(matched) >= 2 else "contextual" if matched else "limited"
        if matched:
            reason = f"Lexical overlap with the claim: {', '.join(matched)}. This does not establish source support."
        else:
            reason = "No material lexical overlap with the claim; retain only as limited context, not mechanism support."
        screens.append(SourceRelevance(source_id=source.id, verdict=verdict, matched_terms=matched, reason=reason))
    return screens


def _meaningful_terms(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _stem(term: str) -> str:
    if term.endswith("ing") and len(term) > 5:
        term = term[:-3]
        if len(term) > 2 and term[-1] == term[-2]:
            term = term[:-1]
    if term.endswith("s") and len(term) > 4:
        term = term[:-1]
    return term
