"""Bounded, deterministic evidence operations for ordinary tabular measurements.

This module deliberately knows nothing about resistance, spectra, or a mechanism.
It profiles CSV bytes and materializes small, reproducible facts selected by Codex.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime
from statistics import mean, median, pstdev
from typing import Any

from .analysis import MAX_BYTES, MAX_ROWS, sha256_bytes
from .models import (
    ColumnProfile,
    DataEvidence,
    DatasetArtifact,
    DatasetBinding,
    DatasetProfile,
    NumericSummary,
    UnitDescriptor,
    now_iso,
)

_KNOWN_UNITS = {
    "a", "ma", "ua", "na", "v", "mv", "kv", "ohm", "kohm", "mohm", "s", "ms", "us",
    "min", "h", "hz", "khz", "mhz", "nm", "um", "mm", "cm", "m", "k", "c", "degc",
    "counts", "au", "arb", "pa", "w", "mw", "j", "ev", "mev", "rh", "%", "percent",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _decode_rows(raw: bytes) -> tuple[list[str], list[dict[str, str | None]]]:
    if not raw:
        raise ValueError("CSV must not be empty")
    if len(raw) > MAX_BYTES:
        raise ValueError("CSV exceeds the 5 MiB input limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8") from exc
    try:
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if not header:
            raise ValueError("CSV must include a header row")
        names = [item.strip() for item in header]
        if any(not item for item in names):
            raise ValueError("CSV headers must not be empty")
        if len(names) != len(set(names)):
            raise ValueError("CSV headers must be unique")
        if len(names) > 128:
            raise ValueError("CSV exceeds the 128-column input limit")
        rows: list[dict[str, str | None]] = []
        for source_row, values in enumerate(reader, start=2):
            if source_row > MAX_ROWS + 1:
                raise ValueError("CSV exceeds the 10,000 row limit")
            if len(values) != len(names):
                raise ValueError(f"CSV row {source_row} does not match the header width")
            rows.append({name: value.strip() if value.strip() else None for name, value in zip(names, values)})
    except csv.Error as exc:
        raise ValueError("Malformed CSV") from exc
    if not rows:
        raise ValueError("CSV must contain at least one data row")
    return names, rows


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _candidate_unit(name: str) -> UnitDescriptor:
    tokens = [token.lower() for token in re.findall(r"[A-Za-z%]+", name)]
    candidate = next((token for token in reversed(tokens) if token in _KNOWN_UNITS), None)
    return UnitDescriptor(
        value=candidate,
        source="header" if candidate else "none",
        status="candidate" if candidate else "unknown",
    )


def _infer_type(values: list[str | None]) -> str:
    present = [value for value in values if value is not None]
    if not present:
        return "empty"
    numeric = [_number(value) for value in present]
    if all(value is not None for value in numeric):
        return "integer" if all(float(value).is_integer() for value in numeric if value is not None) else "numeric"
    lowered = {value.lower() for value in present}
    if lowered <= {"true", "false", "yes", "no", "0", "1"}:
        return "boolean"
    if all(_is_datetime(value) for value in present[: min(30, len(present))]):
        return "datetime"
    return "categorical" if len(set(present)) <= min(24, max(3, len(present) // 4)) else "text"


def _is_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def profile_csv(raw: bytes, artifact_id: str = "artifact-001") -> tuple[DatasetArtifact, DatasetProfile]:
    names, rows = _decode_rows(raw)
    columns: list[ColumnProfile] = []
    warnings: list[str] = []
    for index, name in enumerate(names):
        values = [row[name] for row in rows]
        inferred = _infer_type(values)
        numeric_values = [value for value in (_number(item) for item in values) if value is not None]
        numeric_summary = None
        if inferred in {"integer", "numeric"}:
            if len(numeric_values) != len([value for value in values if value is not None]):
                warnings.append(f"{name}: non-finite numeric values treated as missing")
            numeric_summary = NumericSummary(
                min=min(numeric_values), max=max(numeric_values), mean=mean(numeric_values),
                median=median(numeric_values), std=pstdev(numeric_values) if len(numeric_values) > 1 else 0.0,
            )
        columns.append(ColumnProfile(
            column_id=f"col-{index + 1:03d}", name=name, index=index, inferred_type=inferred,
            unit=_candidate_unit(name), missing_count=sum(value is None for value in values),
            missing_fraction=sum(value is None for value in values) / len(rows),
            unique_count=len({value for value in values if value is not None}), numeric_summary=numeric_summary,
        ))
    artifact = DatasetArtifact(
        artifact_id=artifact_id, filename="dataset.csv", sha256=sha256_bytes(raw), byte_count=len(raw), imported_at=now_iso(),
    )
    return artifact, DatasetProfile(
        artifact_id=artifact_id, row_count=len(rows), column_count=len(names), columns=columns,
        sample_rows=rows[:12], warnings=sorted(set(warnings)),
    )


def infer_modality(profile: DatasetProfile, methods: str) -> dict[str, Any]:
    names = " ".join(column.name.lower() for column in profile.columns)
    context = f"{names} {methods.lower()}"
    if "temperature" in context and ("resistance" in context or "ohm" in context):
        return {"candidate": "electrical_transport_rt", "confidence": "high", "reasons": ["temperature and resistance/ohm fields are present"], "alternatives": ["generic_sweep"], "requires_confirmation": True}
    if any(token in context for token in ("wavelength", "wavenumber", "intensity", "raman", "emission", "spectrum")):
        return {"candidate": "generic_spectrum", "confidence": "medium", "reasons": ["spectral axis or intensity-like fields are present"], "alternatives": ["generic_sweep"], "requires_confirmation": True}
    if "time" in context:
        candidate = "actuator_dynamics" if any(token in context for token in ("displacement", "curvature", "force", "polarity", "humidity")) else "generic_time_series"
        return {"candidate": candidate, "confidence": "medium", "reasons": ["a time-like field is present"], "alternatives": ["generic_sweep"], "requires_confirmation": True}
    if any(token in context for token in ("cycle", "forward", "reverse")):
        return {"candidate": "generic_cyclic_trace", "confidence": "low", "reasons": ["cyclic-trace language is present"], "alternatives": ["generic_sweep"], "requires_confirmation": True}
    return {"candidate": "generic_sweep", "confidence": "low", "reasons": ["bounded tabular numeric columns are available but modality is ambiguous"], "alternatives": ["grouped_comparison", "unknown"], "requires_confirmation": True}


def _rows(raw: bytes) -> list[dict[str, str | None]]:
    return _decode_rows(raw)[1]


def _columns(profile: DatasetProfile) -> dict[str, ColumnProfile]:
    return {column.column_id: column for column in profile.columns}


def _select_rows(rows: list[dict[str, str | None]], start: int, end: int) -> list[dict[str, str | None]]:
    if start < 2 or end < start or end > len(rows) + 1:
        raise ValueError("row range must be within the frozen artifact")
    return rows[start - 2 : end - 1]


def _numeric_pairs(rows: list[dict[str, str | None]], x_name: str, y_name: str) -> list[tuple[float, float]]:
    result = []
    for row in rows:
        x, y = _number(row[x_name]), _number(row[y_name])
        if x is not None and y is not None:
            result.append((x, y))
    if not result:
        raise ValueError("selected rows contain no finite numeric pairs")
    return result


def materialize_evidence(
    raw: bytes, artifact: DatasetArtifact, profile: DatasetProfile, binding: DatasetBinding,
    operation: str, selected_columns: list[str], row_start: int, row_end: int, parameters: dict[str, Any] | None = None,
) -> DataEvidence:
    """Execute a small allowlisted operation; never evaluate user expressions or code."""
    allowed = {"raw_slice", "column_summary", "endpoint_delta", "argmax", "argmin", "range_extrema", "linear_fit", "correlation", "monotonicity", "group_summary"}
    if operation not in allowed:
        raise ValueError("unsupported deterministic evidence operation")
    parameters = parameters or {}
    columns = _columns(profile)
    if not selected_columns or any(item not in columns for item in selected_columns):
        raise ValueError("evidence must select known column IDs")
    rows = _select_rows(_rows(raw), row_start, row_end)
    names = [columns[item].name for item in selected_columns]
    numeric = {item for item in selected_columns if columns[item].inferred_type in {"integer", "numeric"}}
    if operation != "raw_slice" and not numeric:
        raise ValueError("operation requires at least one numeric selected column")
    result: dict[str, Any]
    hint = "summary"
    if operation == "raw_slice":
        result = {"row_count": len(rows), "rows": [{name: row[name] for name in names} for row in rows[:12]]}
        fact = f"Frozen artifact rows {row_start}–{row_end} contain {len(rows)} selected row(s)."
        hint = "table"
    elif operation == "column_summary":
        values = [_number(row[names[0]]) for row in rows]
        finite = [value for value in values if value is not None]
        if not finite:
            raise ValueError("selected column contains no finite numeric values")
        result = {"count": len(finite), "missing": len(values) - len(finite), "min": min(finite), "max": max(finite), "mean": mean(finite), "median": median(finite)}
        fact = f"{columns[selected_columns[0]].name} has {len(finite)} finite values from {min(finite):.6g} to {max(finite):.6g}."
    elif operation in {"endpoint_delta", "monotonicity", "linear_fit", "argmax", "argmin", "range_extrema"}:
        if len(selected_columns) < 2:
            raise ValueError(f"{operation} requires X and Y columns")
        pairs = _numeric_pairs(rows, names[0], names[1])
        if operation == "endpoint_delta":
            delta = pairs[-1][1] - pairs[0][1]
            result = {"first_x": pairs[0][0], "first_y": pairs[0][1], "last_x": pairs[-1][0], "last_y": pairs[-1][1], "delta_y": delta, "percent_change": None if pairs[0][1] == 0 else delta / pairs[0][1] * 100}
            fact = f"{names[1]} changes from {pairs[0][1]:.6g} to {pairs[-1][1]:.6g} across the selected order (Δ={delta:.6g})."
        elif operation in {"argmax", "argmin"}:
            chosen = (max if operation == "argmax" else min)(pairs, key=lambda pair: pair[1])
            result = {"x": chosen[0], "y": chosen[1], "kind": operation}
            fact = f"Within rows {row_start}–{row_end}, {names[1]} reaches its {operation[3:]} at {names[0]}={chosen[0]:.6g} with value {chosen[1]:.6g}."
        elif operation == "range_extrema":
            low, high = min(pairs, key=lambda pair: pair[1]), max(pairs, key=lambda pair: pair[1])
            result = {"min": {"x": low[0], "y": low[1]}, "max": {"x": high[0], "y": high[1]}}
            fact = f"Within rows {row_start}–{row_end}, {names[1]} spans {low[1]:.6g} to {high[1]:.6g}."
        elif operation == "monotonicity":
            changes = [later[1] - earlier[1] for earlier, later in zip(pairs, pairs[1:])]
            rising, falling, flat = sum(delta > 0 for delta in changes), sum(delta < 0 for delta in changes), sum(delta == 0 for delta in changes)
            direction = "rising" if rising and not falling else "falling" if falling and not rising else "mixed" if rising and falling else "flat"
            result = {"direction": direction, "rising_steps": rising, "falling_steps": falling, "flat_steps": flat}
            fact = f"{names[1]} is {direction} over the selected order ({rising} rising, {falling} falling, {flat} flat steps)."
        else:
            if len(pairs) < 2:
                raise ValueError("linear_fit requires two finite numeric pairs")
            xs, ys = zip(*pairs)
            mean_x, mean_y = mean(xs), mean(ys)
            denominator = sum((value - mean_x) ** 2 for value in xs)
            if denominator == 0:
                raise ValueError("linear_fit requires variation in X")
            slope = sum((x - mean_x) * (y - mean_y) for x, y in pairs) / denominator
            intercept = mean_y - slope * mean_x
            result = {"slope": slope, "intercept": intercept, "point_count": len(pairs)}
            fact = f"Ordinary least-squares fit of {names[1]} versus {names[0]} has slope {slope:.6g} over {len(pairs)} finite pairs."
        hint = "line"
    elif operation == "correlation":
        if len(selected_columns) < 2:
            raise ValueError("correlation requires two numeric columns")
        pairs = _numeric_pairs(rows, names[0], names[1])
        if len(pairs) < 2:
            raise ValueError("correlation requires two finite numeric pairs")
        xs, ys = zip(*pairs)
        dx = sum((value - mean(xs)) ** 2 for value in xs)
        dy = sum((value - mean(ys)) ** 2 for value in ys)
        if not dx or not dy:
            raise ValueError("correlation requires variation in both columns")
        coefficient = sum((x - mean(xs)) * (y - mean(ys)) for x, y in pairs) / math.sqrt(dx * dy)
        result = {"pearson_r": coefficient, "point_count": len(pairs)}
        fact = f"Pearson correlation between {names[0]} and {names[1]} is {coefficient:.6g} across {len(pairs)} finite pairs."
        hint = "scatter"
    else:  # group_summary
        if len(selected_columns) < 2:
            raise ValueError("group_summary requires a group and numeric value column")
        group_name, value_name = names[0], names[1]
        groups: dict[str, list[float]] = {}
        for row in rows:
            value = _number(row[value_name])
            if row[group_name] is not None and value is not None:
                groups.setdefault(row[group_name], []).append(value)
        if not groups:
            raise ValueError("group_summary requires non-empty groups and finite values")
        result = {group: {"count": len(values), "mean": mean(values), "min": min(values), "max": max(values)} for group, values in sorted(groups.items())}
        fact = f"Grouped summary of {value_name} was materialized for {len(groups)} group(s): {', '.join(sorted(groups))}."
        hint = "summary"
    binding_hash = hashlib.sha256(_canonical(binding.model_dump(mode="json")).encode()).hexdigest()
    op_payload = {"operation": operation, "selected_columns": selected_columns, "row_start": row_start, "row_end": row_end, "parameters": parameters}
    operation_hash = hashlib.sha256(_canonical(op_payload).encode()).hexdigest()
    evidence_id = f"data-evidence-{hashlib.sha256(f'{artifact.sha256}:{binding_hash}:{operation_hash}'.encode()).hexdigest()[:16]}"
    return DataEvidence(
        evidence_id=evidence_id, artifact_id=artifact.artifact_id, artifact_sha256=artifact.sha256,
        selected_columns=selected_columns, row_start=row_start, row_end=row_end, operation=operation,
        parameters=parameters, result=result, fact_text=fact, binding_sha256=binding_hash,
        operation_sha256=operation_hash, visualization_hint=hint, created_at=now_iso(),
    )
