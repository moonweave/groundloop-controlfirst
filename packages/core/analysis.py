from __future__ import annotations
import csv, hashlib, io, math
from .models import DatasetAnalysis, EvidenceRef, Locator, SourceInput

MAX_BYTES, MAX_ROWS = 5 * 1024 * 1024, 10_000
REQUIRED = ("temperature_c", "two_wire_resistance_ohm")

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
    analysis=DatasetAnalysis(columns=list(REQUIRED), row_count=len(rows), temperature_range_c=(min(temps),max(temps)), resistance_min_ohm=mn, resistance_min_row=vals.index(mn)+2, resistance_max_ohm=mx, resistance_max_row=vals.index(mx)+2, first_resistance_ohm=vals[0], last_resistance_ohm=vals[-1], change_ohm=vals[-1]-vals[0], percent_change=(vals[-1]-vals[0])/vals[0]*100 if vals[0] else float("inf"), monotonicity_segments=segments, cited_row_range=(2,len(rows)+1), rows=rows)
    ref=EvidenceRef(id=f"{artifact_id}:rows-2-{len(rows)+1}",kind="data",artifact_id=artifact_id,locator=Locator(columns=list(REQUIRED),row_start=2,row_end=len(rows)+1),excerpt=f"CSV rows 2–{len(rows)+1}; {len(rows)} validated numeric rows.",sha256=sha256_bytes(raw))
    return analysis, ref

def source_refs(sources: list[SourceInput]) -> list[EvidenceRef]:
    refs=[]
    for source in sources:
        serialized=source.model_dump_json().encode()
        refs.append(EvidenceRef(id=f"{source.id}:evidence",kind="source",artifact_id=source.id,locator=source.locator,excerpt=source.untrusted_content[:1000],sha256=sha256_bytes(serialized)))
    return refs

