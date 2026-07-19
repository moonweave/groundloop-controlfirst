from __future__ import annotations
from .models import *

def validate_findings(findings: list[Finding], refs: list[EvidenceRef], deterministic: DatasetAnalysis) -> list[Finding]:
    ids={r.id:r for r in refs}; seen=set()
    for f in findings:
        if f.id in seen: raise ValueError(f"duplicate finding id: {f.id}")
        seen.add(f.id)
        if any(x not in ids for x in f.evidence_ref_ids): raise ValueError(f"{f.id} references unsupported evidence")
        linked=[ids[x] for x in f.evidence_ref_ids]
        if f.status=="Established" and not any(r.kind=="source" for r in linked): raise ValueError("Established findings require source evidence")
        if f.status=="Established" and any(word in f.statement.lower() for word in ("sample", "uploaded", "trace")): raise ValueError("Established cannot describe the uploaded sample")
        if f.status=="Observed":
            if not all(r.kind=="data" for r in linked): raise ValueError("Observed findings require data evidence")
            if any(word in f.statement.lower() for word in ("causes", "demonstrates", "proves", "mechanism")): raise ValueError("Observed findings cannot use causal language")
        if f.status=="Inferred" and (not f.uncertainty or not f.alternative_explanation): raise ValueError("Inferred findings require uncertainty and an alternative explanation")
        if f.status=="Unresolved" and not any(word in f.statement.lower() for word in ("unresolved", "unknown", "requires", "not known", "cannot")): raise ValueError("Unresolved finding must state missing evidence")
    return findings

def validate_control(control: ControlProposal, findings: list[Finding]) -> ControlProposal:
    by_id={f.id:f for f in findings}
    if any(x not in by_id for x in control.finding_ref_ids): raise ValueError("Control references unsupported finding")
    if not any(by_id[x].status in ("Inferred","Unresolved") for x in control.finding_ref_ids): raise ValueError("Control must cite an Inferred or Unresolved finding")
    if len(control.outcomes)!=2: raise ValueError("Control requires exactly two outcomes")
    if any(word in (control.experiment+control.confound).lower() for word in ("email", "publish", "execute shell", "curl", "http://")): raise ValueError("Control contains an external action")
    return control

