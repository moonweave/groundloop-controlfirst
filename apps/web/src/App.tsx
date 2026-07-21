import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  Beaker,
  Check,
  ChevronDown,
  Clipboard,
  Download,
  FileUp,
  FlaskConical,
  GitBranch,
  LockKeyhole,
  Orbit,
  Plus,
  Radio,
  RefreshCw,
  Ruler,
  ScanLine,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

type RunState =
  | "DRAFT"
  | "PACKET_READY"
  | "SOURCES_INSPECTED"
  | "DATA_ANALYZED"
  | "FINDINGS_VALIDATED"
  | "CONTROL_VALIDATED"
  | "EXPORTED";
type View = "map" | "sources" | "audit";
type AlignmentStatus = "Observed" | "Confounded" | "Missing" | "Contradicted";
type SourceRole = "theory_basis" | "method_limit" | "discriminating_control";

type Run = {
  run_id: string;
  state: RunState;
  fixture?: string;
  created_at: string;
  workflow?: "transport_v1" | "generic_v2";
};
type Dataset = {
  row_count: number;
  temperature_range_c: [number, number];
  first_resistance_ohm: number;
  last_resistance_ohm: number;
  change_ohm: number;
  percent_change: number;
  rows: { temperature_c: number; two_wire_resistance_ohm: number }[];
};
type Source = {
  id: string;
  title: string;
  authors: string[];
  year: number;
  url_or_doi: string;
  locator: { section?: string; page?: number };
  untrusted_content: string;
  retrieval_provider: string;
  publication_status: "peer_reviewed" | "preprint" | "indexed_abstract" | "unknown";
  retrieved_at?: string | null;
  search_query?: string | null;
  discovery_rationale?: string | null;
  content_sha256?: string | null;
};
type SourceAdjudication = {
  source_id: string;
  verdict: "direct" | "contextual" | "reject";
  rationale: string;
  role?: SourceRole;
};
type SourceReview = {
  provider: string;
  status?: "required" | "completed";
  candidate_count?: number;
  direct_source_ids?: string[];
  adjudications: SourceAdjudication[];
  adjudicated_at: string;
};
type EvidenceRef = {
  id: string;
  kind: "source" | "data";
  artifact_id: string;
  excerpt: string;
  sha256: string;
  locator: Record<string, unknown>;
};
type Signature = {
  id: string;
  name: string;
  requirement: string;
  expected_observation: string;
  falsifying_outcome: string;
  theory_evidence_ref_ids: string[];
};
type Alignment = {
  signature_id: string;
  status: AlignmentStatus;
  rationale: string;
  evidence_ref_ids: string[];
  alternative_explanation?: string;
  missing_reason?: string;
};
type Outcome = { if?: string; if_?: string; then: string };
type Control = {
  confound: string;
  experiment: string;
  preconditions: string[];
  outcomes: Outcome[];
  priority: "high" | "medium" | "low";
  feasibility: string;
  closes_signature_ids?: string[];
  leaves_open_signature_ids?: string[];
  signature_ref_ids?: string[];
  required_artifact_labels?: string[];
};
type ConvergenceMap = {
  claim: string;
  measurement_method: string;
  signatures: Signature[];
  alignments: Alignment[];
  dominant_gap: string;
  control?: Control;
  freeze_status: "DRAFT" | "FROZEN";
  recorded_at: string;
};
type Finding = {
  id: string;
  statement: string;
  status: "Established" | "Observed" | "Inferred" | "Unresolved";
  evidence_ref_ids: string[];
  reasoning: string;
  uncertainty?: string;
  alternative_explanation?: string;
};
type Report = {
  run_id: string;
  claim: string;
  state: "EXPORTED";
  findings: Finding[];
  control?: Control;
  sources: Source[];
  source_review?: SourceReview | null;
  dataset?: Dataset;
  dataset_provenance?: "USER_MEASUREMENT" | "LABELLED_DEMO" | "FIXTURE_DEMO";
  verdict: { label: string; reason: string; blocking_finding_ids?: string[]; blocking_signature_ids?: string[] };
  convergence?: ConvergenceMap;
  exported_at: string;
};
type Detail = {
  run: Run;
  timeline?: { at: string; action: string; state: RunState; summary: string }[];
  input_artifacts?: string[];
  draft?: {
    claim: { claim: string } | null;
    sources: Source[];
    methods: string;
    dataset_ready: boolean;
    dataset?: Dataset | null;
    dataset_evidence_ref?: EvidenceRef;
    dataset_provenance?: string;
    artifact?: Artifact;
    artifacts?: Artifact[];
    dataset_profile?: GenericProfile;
    dataset_profiles?: GenericProfile[];
    modality_proposal?: { candidate: string; confidence: string; reasons: string[]; alternatives: string[]; authority: "codex" | "groundloop_heuristic"; recorded_at?: string | null };
    heuristic_modality_signal?: { candidate: string; confidence: string; reasons: string[]; alternatives: string[] };
    dataset_binding?: { x_column_id: string; y_column_ids: string[] } | null;
    artifact_bindings?: ArtifactBinding[];
    recipe?: { id: string; version: string } | null;
    retrieval_review?: {
      provider: string;
      status: "required" | "completed";
      candidate_count: number;
      direct_source_ids: string[];
      adjudications: SourceAdjudication[];
    };
  };
  packet?: {
    claim: { claim: string };
    sources: Source[];
    source_candidates?: Source[];
    candidate_review?: SourceReview;
    methods: string;
    dataset?: Dataset;
    artifacts?: Artifact[];
    dataset_profile?: GenericProfile;
    dataset_profiles?: GenericProfile[];
    dataset_binding?: { x_column_id: string; y_column_ids: string[] };
    artifact_bindings?: ArtifactBinding[];
    recipe?: { id: string; version: string };
    dataset_provenance?: string;
    evidence_refs: EvidenceRef[];
    source_review?: SourceReview;
  };
  convergence?: ConvergenceMap;
  report?: Report;
  data_evidence?: { evidence_id: string; artifact_id: string; operation: string; fact_text: string; selected_columns: string[]; row_start: number; row_end: number }[];
};

type Artifact = {
  artifact_id: string;
  filename: string;
  label?: string | null;
  sha256: string;
  byte_count: number;
  provenance: string;
};
type ArtifactBinding = {
  artifact_id: string;
  x_column_id: string;
  y_column_ids: string[];
};
type GenericProfile = {
  artifact_id: string;
  row_count: number;
  column_count: number;
  columns: { column_id: string; name: string; inferred_type: string; unit: { value?: string; status: string }; missing_count: number }[];
  sample_rows: Record<string, string | null>[];
  warnings: string[];
};

const API_BASE = import.meta.env.VITE_GROUNDLOOP_API_URL ?? "";
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: { message?: string } }
      | null;
    throw new Error(body?.detail?.message ?? "GroundLoop local service is unavailable.");
  }
  return response.json() as Promise<T>;
}

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function formatId(runId: string) {
  return `GL-${runId.slice(0, 8).toUpperCase()}`;
}

function formatNumber(value: number, digits = 1) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

function statusClass(status: AlignmentStatus) {
  return `status-${status.toLowerCase()}`;
}

function statusLabel(status: AlignmentStatus) {
  return status.toUpperCase();
}

function sourceRoleLabel(role?: SourceRole) {
  return role
    ? {
        theory_basis: "THEORY BASIS",
        method_limit: "METHOD LIMIT",
        discriminating_control: "DISCRIMINATING CONTROL",
      }[role]
    : "ROLE PENDING";
}

function friendlyGap(gap: string, state: RunState) {
  if (gap.includes("required_condition_not_recorded")) {
    return state === "DRAFT"
      ? "The claim has not been checked against a recorded data fact yet. Confirm the columns, review sources, then freeze the packet when it looks right."
      : "The packet is frozen, but Codex has not recorded the data fact needed to judge this signature yet.";
  }
  return gap.replaceAll("_", " ");
}

function sourceNextAction(sources: Source[], directCount: number, reviewPending: boolean) {
  if (sources.length === 0) return "Next: paste the Run brief into Codex and ask it to import literature candidates.";
  if (reviewPending) return "Next: ask Codex to review the current candidates and assign evidence roles.";
  if (directCount === 0) return "Next: at least one source needs a direct review before this packet can freeze.";
  return "Ready to freeze when the source roles and data binding look correct.";
}

function viewLabel(view: View) {
  return view === "map" ? "CONVERGENCE MAP" : view === "sources" ? "SOURCE REVIEW" : "AUDIT / EXPORT";
}

function methodLabel(method: string) {
  const lower = method.toLowerCase();
  if (lower.includes("four-wire") || lower.includes("four wire") || lower.includes("four-terminal")) {
    return "FOUR-WIRE R(T)";
  }
  if (lower.includes("two-wire") || lower.includes("two wire") || lower.includes("resistance")) return "TWO-WIRE R(T)";
  return "GENERIC TABULAR";
}

function datasetFrom(detail: Detail): Dataset | undefined {
  return detail.packet?.dataset ?? detail.report?.dataset ?? detail.draft?.dataset ?? undefined;
}

function genericProfileFrom(detail: Detail): GenericProfile | undefined {
  return detail.draft?.dataset_profile ?? detail.packet?.dataset_profile;
}

function artifactsFrom(detail: Detail): Artifact[] {
  return detail.draft?.artifacts ?? detail.packet?.artifacts ?? (detail.draft?.artifact ? [detail.draft.artifact] : []);
}

function genericProfilesFrom(detail: Detail): GenericProfile[] {
  return detail.draft?.dataset_profiles ?? detail.packet?.dataset_profiles ?? (genericProfileFrom(detail) ? [genericProfileFrom(detail)!] : []);
}

function artifactBindingsFrom(detail: Detail): ArtifactBinding[] {
  const fallback = detail.draft?.dataset_binding ?? detail.packet?.dataset_binding;
  return detail.draft?.artifact_bindings ?? detail.packet?.artifact_bindings ?? (fallback ? [{ artifact_id: "artifact-001", x_column_id: fallback.x_column_id, y_column_ids: fallback.y_column_ids }] : []);
}

function briefFor(detail: Detail) {
  const claim = detail.convergence?.claim ?? detail.draft?.claim?.claim ?? detail.packet?.claim.claim ?? "";
  const method = detail.convergence?.measurement_method ?? detail.packet?.methods ?? detail.draft?.methods ?? "";
  const generic = detail.run.workflow === "generic_v2";
  const steps = detail.run.state === "DRAFT"
    ? [
        generic ? "1. Call inspect_measurement_artifacts. Read the claim, method context, artifact profiles, and supplied literature, then call record_measurement_modality with authority='codex'. Header inference is advisory only. The researcher must confirm set_artifact_binding for every artifact and may keep the generic capability pack." : "1. While this Run is DRAFT, call record_source_reviews once for every supplied source. Assign direct sources one role: theory_basis, method_limit, or discriminating_control.",
        generic ? "2. Record source reviews, then stop and ask the researcher to click FREEZE EVIDENCE. Do not freeze from Codex." : "2. Stop and ask the researcher to click FREEZE EVIDENCE in GroundLoop. Do not call create_evidence_packet before the researcher confirms the freeze.",
      ]
    : detail.run.state === "PACKET_READY"
      ? [
          generic ? "1. The researcher has frozen the packet. Call create_evidence_packet, inspect_sources, analyze_dataset, then materialize_data_evidence." : "1. The researcher has frozen the packet. Call create_evidence_packet, inspect_sources, and analyze_dataset in that order.",
          "2. Then call record_signatures, record_alignments, record_control_contract, and export_report in that order.",
        ]
      : detail.run.state === "EXPORTED"
        ? ["1. This Run is already EXPORTED. Read it with get_run and do not replay the workflow; create a new DRAFT Run for a fresh analysis."]
        : [
            "1. Continue from the current Run state with the next valid GroundLoop MCP operation.",
            "2. Finish with record_signatures, record_alignments, record_control_contract, and export_report.",
          ];
  return [
    `Analyze GroundLoop Run ${detail.run.run_id}.`,
    "",
    "This Run is the bounded evidence source of truth. Read only the saved claim, method, dataset facts, and source excerpts.",
    `Claim: ${claim}`,
    `Method: ${method}`,
    `Run state: ${detail.run.state}`,
    "",
    "Use the GroundLoop MCP and follow the state-gated steps below:",
    ...steps,
    generic ? "Observed and Contradicted must cite a GroundLoop materialized data-evidence ID. Confounded must cite materialized data plus a method or source limit." : "Record only Observed, Confounded, Missing, or Contradicted alignments. Name the alternative explanation for Confounded and keep the control atomic.",
    "Export the report when the Convergence Map is complete.",
  ].join("\n");
}

function App() {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [view, setView] = useState<View>("map");
  const [service, setService] = useState<"checking" | "ready" | "unavailable">("checking");
  const [runs, setRuns] = useState<Run[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refreshRuns = useCallback(async () => {
    try {
      const items = await api<Run[]>("/api/runs");
      setRuns(items);
      setService("ready");
    } catch {
      setService("unavailable");
    }
  }, []);

  const openRun = useCallback(async (runId: string) => {
    setBusy(true);
    setError("");
    try {
      setDetail(await api<Detail>(`/api/runs/${runId}`));
      setView("map");
      await refreshRuns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to open the Run.");
    } finally {
      setBusy(false);
    }
  }, [refreshRuns]);

  useEffect(() => {
    let mounted = true;
    api<Run[]>("/api/runs")
      .then((items) => {
        if (mounted) {
          setRuns(items);
          setService("ready");
        }
      })
      .catch(() => {
        if (mounted) setService("unavailable");
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!detail?.run.run_id) return;
    const timer = window.setInterval(() => {
      void api<Detail>(`/api/runs/${detail.run.run_id}`)
        .then(setDetail)
        .catch(() => undefined);
    }, 4500);
    return () => window.clearInterval(timer);
  }, [detail?.run.run_id]);

  const createRun = async (payload: { claim: string; methods: string; datasetCsv: string; fileName: string }) => {
    setBusy(true);
    setError("");
    try {
      const next = await api<Detail>("/api/generic/runs", {
        method: "POST",
        body: JSON.stringify({ claim: payload.claim, methods: payload.methods, dataset_csv: payload.datasetCsv, filename: payload.fileName }),
      });
      setDetail(next);
      setView("map");
      setNotice("Generic Run profiled. Confirm artifact binding; capability packs guide evidence operations only.");
      await refreshRuns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create the Run.");
    } finally {
      setBusy(false);
    }
  };

  const openDemo = async () => {
    setBusy(true);
    setError("");
    try {
      const created = await api<Run>("/api/runs", {
        method: "POST",
        body: JSON.stringify({ fixture_name: "four_wire_contact_control" }),
      });
      await openRun(created.run_id);
      setNotice("MCP-ready resistance sweep opened. Review sources, freeze the packet, then paste the Codex brief.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to open the guided Run.");
      setBusy(false);
    }
  };

  const startNew = () => {
    setDetail(null);
    setView("map");
    setError("");
    setNotice("");
  };

  return (
    <div className="app-shell">
      <div className="ambient-grid" aria-hidden="true" />
      {detail ? (
        <Workspace
          detail={detail}
          view={view}
          busy={busy}
          onView={setView}
          onRefresh={() => void openRun(detail.run.run_id)}
          onNew={startNew}
          onNotice={setNotice}
        />
      ) : (
        <Landing
          service={service}
          runs={runs}
          busy={busy}
          onCreate={createRun}
          onOpenDemo={openDemo}
          onOpenRun={openRun}
        />
      )}
      {(error || notice) && (
        <div className={`toast ${error ? "toast-error" : "toast-success"}`} role="status">
          {error ? <TriangleAlert size={15} /> : <Check size={15} />}
          <span>{error || notice}</span>
          <button type="button" onClick={() => { setError(""); setNotice(""); }} aria-label="Dismiss notification">×</button>
        </div>
      )}
    </div>
  );
}

function Landing({
  service,
  runs,
  busy,
  onCreate,
  onOpenDemo,
  onOpenRun,
}: {
  service: "checking" | "ready" | "unavailable";
  runs: Run[];
  busy: boolean;
  onCreate: (payload: { claim: string; methods: string; datasetCsv: string; fileName: string }) => Promise<void>;
  onOpenDemo: () => Promise<void>;
  onOpenRun: (runId: string) => Promise<void>;
}) {
  const [claim, setClaim] = useState("A spectral feature near 620 nm demonstrates defect-state emission.");
  const [methods, setMethods] = useState("Steady-state photoluminescence spectra were exported as wavelength and intensity tables from the same sample under fixed excitation.");
  const [datasetCsv, setDatasetCsv] = useState(["wavelength_nm,intensity_counts", "580,12", "600,28", "620,91", "640,45", "660,18"].join("\n"));
  const [fileName, setFileName] = useState("spectrum.csv");

  const handleFile = (file?: File) => {
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => setDatasetCsv(String(reader.result ?? ""));
    reader.readAsText(file);
  };

  return (
    <main className="landing-layout">
      <header className="landing-header">
        <div className="brand-lockup"><Orbit size={20} /><span>GROUNDLOOP</span><small>CLAIM / CONTROL / CLOSURE</small></div>
        <div className="service-indicator"><span className={`service-dot ${service}`} />{service === "ready" ? "LOCAL SERVICE READY" : service === "checking" ? "CHECKING LOCAL SERVICE" : "LOCAL SERVICE OFFLINE"}</div>
      </header>
      <section className="landing-hero">
        <div className="hero-copy">
          <p className="kicker">RESEARCH CONVERGENCE WORKSPACE · BOUNDED TABULAR MEASUREMENTS</p>
          <h1>Make the claim<br /><em>decidable.</em></h1>
          <p className="hero-deck">Start with a claim and a CSV. Codex reviews the sources, you freeze the evidence, and GroundLoop shows what the data can support next.</p>
          <div className="hero-rail"><span>THEORY</span><i /><span>MEASUREMENT</span><i /><span>CONTROL</span></div>
        </div>
        <div className="entry-panel panel-linework">
          <div className="panel-head"><div><span className="kicker">NEW RUN / 01</span><h2>Frame the claim.</h2></div><span className="panel-index">GL·01</span></div>
          <label className="field-label" htmlFor="claim">MECHANISM CLAIM <span>REQUIRED</span></label>
          <textarea id="claim" value={claim} onChange={(event) => setClaim(event.target.value)} className="claim-field" rows={4} />
          <div className="entry-grid">
            <div><label className="field-label" htmlFor="method">MEASUREMENT FAMILY</label><div className="select-wrap"><select id="method" value="generic" onChange={() => undefined}><option value="generic">Generic tabular / capability pack optional after profiling</option></select><ChevronDown size={16} /></div></div>
            <div><label className="field-label" htmlFor="method-notes">METHOD CONTEXT</label><input id="method-notes" value={methods} onChange={(event) => setMethods(event.target.value)} /></div>
          </div>
          <div className="upload-zone">
            <div className="upload-copy"><FileUp size={17} /><div><strong>{fileName}</strong><span>UTF-8 CSV · arbitrary headers · profile before interpretation</span></div></div>
            <label className="text-button">REPLACE<input type="file" accept=".csv,text/csv" onChange={(event) => handleFile(event.target.files?.[0])} /></label>
          </div>
          <div className="csv-guidance" aria-label="CSV guidance">
            <div>
              <strong>What GroundLoop reads first</strong>
              <span>Header names, numeric columns, ranges, and simple shape. Scientific meaning is assigned later by Codex through the Run contract.</span>
            </div>
            <div className="csv-requirements" aria-label="Accepted CSV shape">
              <span>First row = headers</span>
              <span>Numeric columns ok</span>
              <span>Units in names ok</span>
            </div>
          </div>
          <div className="entry-footer"><span className="tiny-note"><LockKeyhole size={13} /> Raw file stays in the local Run boundary.</span><button className="primary-button" type="button" disabled={busy || !claim.trim() || datasetCsv.length < 20} onClick={() => void onCreate({ claim, methods, datasetCsv, fileName })}>{busy ? "CREATING RUN…" : "CREATE GROUNDLOOP RUN"}<ArrowRight size={16} /></button></div>
        </div>
      </section>
      <section className="landing-bottom">
        <button className="demo-strip" type="button" onClick={() => void onOpenDemo()} disabled={busy}><div className="demo-orbit"><Radio size={16} /><span>LEGACY DEMO</span></div><div><strong>Open the R(T) contact-control fixture</strong><span>Preserved transport fixture, separate from the generic tabular path</span></div><ArrowRight size={17} /></button>
        <div className="recent-runs"><div className="section-cap"><span>RECENT RUNS</span><span>{runs.length.toString().padStart(2, "0")}</span></div>{runs.length === 0 ? <p className="empty-note">Start with a bounded CSV, then confirm its binding before freezing.</p> : runs.slice(0, 3).map((run) => <button key={run.run_id} type="button" onClick={() => void onOpenRun(run.run_id)}><span>{formatId(run.run_id)}</span><span>{run.state.replaceAll("_", " ")}</span><ChevronDown size={14} /></button>)}</div>
      </section>
    </main>
  );
}

function Workspace({
  detail,
  view,
  busy,
  onView,
  onRefresh,
  onNew,
  onNotice,
}: {
  detail: Detail;
  view: View;
  busy: boolean;
  onView: (view: View) => void;
  onRefresh: () => void;
  onNew: () => void;
  onNotice: (notice: string) => void;
}) {
  const map = detail.convergence;
  const method = map?.measurement_method ?? detail.packet?.methods ?? detail.draft?.methods ?? "Measurement method pending";
  const stateLabel = detail.run.state === "EXPORTED" ? "REPORT EXPORTED" : detail.run.state.replaceAll("_", " ");
  const freeze = async () => {
    try {
      await api(`/api/runs/${detail.run.run_id}/freeze`, { method: "POST", body: "{}" });
      onNotice("Evidence packet frozen. Codex can now inspect the exact Run boundary.");
      onRefresh();
    } catch (caught) {
      onNotice(`Freeze blocked: ${caught instanceof Error ? caught.message : "source review and complete inputs are required."}`);
    }
  };
  return (
    <main className="workspace-shell">
      <header className="workspace-header"><div className="brand-lockup"><Orbit size={19} /><span>GROUNDLOOP</span></div><div className="workspace-meta"><span className="run-stamp">{formatId(detail.run.run_id)}</span><span className="state-stamp"><span className="service-dot ready" />{stateLabel}</span><span className="method-stamp">{methodLabel(method)}</span></div><div className="header-actions"><button className="icon-button" type="button" onClick={onRefresh} disabled={busy} title="Refresh Run"><RefreshCw size={15} className={busy ? "spin" : ""} /></button><button className="outline-button" type="button" onClick={onNew}><Plus size={15} /> NEW RUN</button></div></header>
      <nav className="workspace-nav" aria-label="Run sections"><div className="nav-intro"><span className="kicker">RUN INSTRUMENT</span><span>{detail.run.created_at.slice(0, 10)}</span></div><div className="nav-tabs">{(["map", "sources", "audit"] as View[]).map((item) => <button key={item} type="button" className={view === item ? "active" : ""} aria-current={view === item ? "page" : undefined} onClick={() => onView(item)}>{viewLabel(item)}</button>)}</div><div className="nav-status"><Activity size={14} /> LIVE RUN</div></nav>
      {view === "map" && <MapScreen detail={detail} onNotice={onNotice} onFreeze={freeze} onRefresh={onRefresh} />}
      {view === "sources" && <SourcesScreen detail={detail} onFreeze={freeze} onView={onView} />}
      {view === "audit" && <AuditScreen detail={detail} onNotice={onNotice} />}
    </main>
  );
}

function MapScreen({ detail, onNotice, onFreeze, onRefresh }: { detail: Detail; onNotice: (notice: string) => void; onFreeze: () => Promise<void>; onRefresh: () => void }) {
  const map = detail.convergence;
  const dataset = datasetFrom(detail);
  const genericProfile = genericProfileFrom(detail);
  const genericProfiles = genericProfilesFrom(detail);
  const artifacts = artifactsFrom(detail);
  const genericEvidence = detail.data_evidence ?? [];
  const genericBindings = artifactBindingsFrom(detail);
  const unboundProfile = genericProfiles.find((profile) => !genericBindings.some((binding) => binding.artifact_id === profile.artifact_id));
  const [selectedId, setSelectedId] = useState(map?.signatures[0]?.id ?? "signature-response");
  const [copied, setCopied] = useState(false);
  const selected = map?.signatures.find((item) => item.id === selectedId);
  const selectedAlignment = map?.alignments.find((item) => item.signature_id === selectedId);
  const control = map?.control;
  const rows = dataset?.rows ?? [];
  const change = dataset?.percent_change ?? 0;
  const copyBrief = async () => {
    try {
      await navigator.clipboard.writeText(briefFor(detail));
      setCopied(true);
      onNotice("Run brief copied. Paste it into Codex; GroundLoop will keep the evidence boundary here.");
      window.setTimeout(() => setCopied(false), 2400);
    } catch {
      onNotice("Clipboard access was unavailable. Open Audit / Export; the Run brief is visible there.");
    }
  };
  const copyControl = async () => {
    if (!control) return;
    const contract = [
      "GroundLoop follow-up control contract",
      `Confound: ${control.confound}`,
      `Experiment: ${control.experiment}`,
      `Preconditions: ${control.preconditions.join("; ")}`,
      `Closes signatures: ${control.closes_signature_ids?.join(", ") ?? "none recorded"}`,
      `Leaves open signatures: ${control.leaves_open_signature_ids?.join(", ") ?? "none recorded"}`,
      ...control.outcomes.map((outcome) => `If ${outcome.if_ ?? outcome.if}, then ${outcome.then}`),
    ].join("\n");
    try {
      await navigator.clipboard.writeText(contract);
      onNotice("Follow-up control contract copied. Create the next Run manually when ready.");
    } catch {
      onNotice("Clipboard access was unavailable. The control contract remains visible in this Run.");
    }
  };
  if (!map) return <div className="workspace-empty"><ScanLine size={32} /><h1>Convergence Map waiting for inputs.</h1><p>Add the claim, method, and CSV to begin the deterministic measurement layer.</p></div>;
  return (
    <div className="map-page">
      <div className="map-toolbar"><div><p className="kicker">PRIMARY INSTRUMENT / CLAIM ↔ MEASUREMENT</p><p className="toolbar-caption">First confirm what the columns mean. Then use Codex to review sources and record what the data can actually support.</p></div><div className="toolbar-actions">{detail.run.state === "DRAFT" && <button type="button" className="outline-button" onClick={() => void onFreeze()}><LockKeyhole size={14} /> FREEZE EVIDENCE</button>}<span className={`draft-chip ${map.freeze_status === "FROZEN" ? "frozen" : ""}`}>{map.freeze_status === "FROZEN" ? <LockKeyhole size={13} /> : <Activity size={13} />}{map.freeze_status === "FROZEN" ? "MAP FROZEN" : "DRAFT ALIGNMENT"}</span><button type="button" className="outline-button" onClick={() => void copyBrief()}><Clipboard size={14} />{copied ? " COPIED" : " COPY CODEX BRIEF"}</button></div></div>
      {detail.run.workflow === "generic_v2" && detail.run.state === "DRAFT" && unboundProfile && <BindingPanel detail={detail} profile={unboundProfile} artifact={artifacts.find((item) => item.artifact_id === unboundProfile.artifact_id)} onNotice={onNotice} onRefresh={onRefresh} />}
      <div className="instrument-grid">
        <section className="map-instrument" aria-label="Convergence Map">
          <div className="theory-band"><div className="band-topline"><span><span className="signal-mark" />TOP-DOWN / WHAT THE MECHANISM MUST EXPLAIN</span><span>01 / CLAIM DECOMPOSITION</span></div><h1>{map.claim}</h1><div className="signature-grid">{map.signatures.map((signature, index) => <button type="button" key={signature.id} className={`signature-cell ${selectedId === signature.id ? "selected" : ""}`} aria-pressed={selectedId === signature.id} onClick={() => setSelectedId(signature.id)}><span className="signature-index">S{String(index + 1).padStart(2, "0")}</span><strong>{signature.name}</strong><span>{signature.requirement}</span></button>)}</div></div>
          <div className="alignment-field"><div className="field-caption"><span>ALIGNMENT FIELD</span><span>THEORY → METHOD → EVIDENCE</span></div><div className="alignment-grid">{map.signatures.map((signature) => { const alignment = map.alignments.find((item) => item.signature_id === signature.id); return <button type="button" key={signature.id} className={`alignment-lane ${alignment ? statusClass(alignment.status) : "status-missing"} ${selectedId === signature.id ? "selected" : ""}`} aria-pressed={selectedId === signature.id} onClick={() => setSelectedId(signature.id)}><span className="alignment-wire" /><span className="alignment-node">{alignment?.status === "Observed" ? <Check size={14} /> : alignment?.status === "Contradicted" ? "×" : alignment?.status === "Confounded" ? "∥" : "○"}</span><span className="alignment-status">{statusLabel(alignment?.status ?? "Missing")}</span><span className="alignment-note">{alignment?.status === "Observed" ? "directly supported" : alignment?.status === "Confounded" ? "alternative remains viable" : alignment?.status === "Contradicted" ? "prediction not met" : "not in this measurement"}</span></button>; })}</div></div>
          <div className="evidence-band"><div className="band-topline light"><span><span className="trace-mark" />BOTTOM-UP / WHAT THIS MEASUREMENT ACTUALLY SHOWS</span><span>{genericProfile ? `${artifacts.length || 1} ARTIFACTS / ${genericProfiles.reduce((total, item) => total + item.row_count, 0)} ROWS` : dataset ? `${dataset.row_count} ROWS / DETERMINISTIC` : "DATA PENDING"}</span></div>{genericProfile ? <GenericEvidenceDeck artifacts={artifacts} profiles={genericProfiles} bindings={genericBindings} evidence={genericEvidence} method={map.measurement_method} /> : <><div className="evidence-layout"><div className="trace-wrap">{rows.length ? <TraceChart rows={rows} /> : <div className="trace-empty"><FileUp size={18} /><span>Upload a UTF-8 CSV to render the raw trace.</span></div>}</div><div className="measurement-boundary"><div className="boundary-code"><span>METHOD /</span><strong>{methodLabel(map.measurement_method)}</strong></div><div className="boundary-row"><span>MEASURES</span><strong>TOTAL LOOP RESISTANCE</strong></div><div className="boundary-row"><span>CANNOT DISTINGUISH</span><strong>SAMPLE <i>vs</i> CONTACT + LEAD</strong></div><div className="equation">R<sub>2W</sub> = R<sub>s</sub> + R<sub>c</sub> + R<sub>lead</sub></div></div></div>{dataset && <div className="metric-strip"><Metric label="TEMPERATURE" value={`${formatNumber(dataset.temperature_range_c[0], 0)}–${formatNumber(dataset.temperature_range_c[1], 0)} °C`} /><Metric label="RESISTANCE" value={`${formatNumber(dataset.first_resistance_ohm)} → ${formatNumber(dataset.last_resistance_ohm)} Ω`} /><Metric label="CHANGE" value={`${change >= 0 ? "+" : ""}${formatNumber(change)}%`} accent="cyan" /></div>}</>}</div>
        </section>
        <aside className="gap-rail"><div className="rail-cap"><span>THE GAP</span><span>IDENTIFIABILITY</span></div><div className="verdict-block"><span className="verdict-pulse" /><p>{map.freeze_status === "FROZEN" ? "MECHANISM" : "DECISION"}</p><h2>{map.freeze_status === "FROZEN" ? "NOT ESTABLISHED" : "PENDING"}</h2><div className="verdict-rule" /><span>{friendlyGap(map.dominant_gap, detail.run.state)}</span></div>{control ? <><div className="control-module"><div className="control-label"><FlaskConical size={15} />NEXT DISCRIMINATING MOVE</div><h3>{control.experiment}</h3><div className="control-meta"><div><span>CHANGES</span><strong>SENSING TOPOLOGY</strong></div><div><span>HOLDS FIXED</span><strong>{control.preconditions.slice(0, 2).join(" · ")}</strong></div></div><div className="control-targets"><span><Check size={12} /> CLOSES {control.closes_signature_ids?.join(" / ") ?? "—"}</span><span><ArrowRight size={12} /> LEAVES {control.leaves_open_signature_ids?.join(" / ") ?? "—"} OPEN</span></div><button type="button" className="control-button" onClick={() => void copyControl()}>COPY FOLLOW-UP CONTRACT <ArrowRight size={15} /></button></div><div className="outcome-fork"><span className="fork-label"><GitBranch size={13} />EXPECTED OUTCOME FORK</span>{control.outcomes.slice(0, 2).map((outcome, index) => <div className="outcome-row" key={`${outcome.then}-${index}`}><span>{index === 0 ? "PERSISTS" : "WEAKENS"}</span><p>{outcome.then}</p></div>)}</div></> : <><div className="control-module control-pending"><div className="control-label"><FlaskConical size={15} />CONTROL PENDING</div><h3>No next experiment yet.</h3><p>After the data facts and alignments are recorded, Codex will commit one follow-up control here.</p></div><div className="outcome-fork"><span className="fork-label"><GitBranch size={13} />OUTCOME FORK PENDING</span><p>The two possible outcomes will appear after a control is recorded.</p></div></>}<div className="rail-footer"><span><ShieldCheck size={13} /> GPT-5.6 VIA CODEX MCP</span><span>LOCAL UI · NO CLOUD DATA UPLOAD</span></div></aside>
      </div>
      {selected && selectedAlignment && <section className="signature-inspector"><div><span className="kicker">SELECTED SIGNATURE / {selected.id.replace("signature-", "S")}</span><h2>{selected.name} <StatusBadge status={selectedAlignment.status} /></h2></div><div className="inspector-columns"><div><span className="inspector-label">REQUIRED</span><p>{selected.requirement}</p></div><div><span className="inspector-label">CURRENT RATIONALE</span><p>{selectedAlignment.rationale}</p></div><div><span className="inspector-label">EVIDENCE BOUNDARY</span><p>{selectedAlignment.evidence_ref_ids.length ? selectedAlignment.evidence_ref_ids.join(" · ") : "No direct evidence in this packet."}</p></div></div>{selectedAlignment.alternative_explanation && <div className="alternative-note"><TriangleAlert size={14} /><span>{selectedAlignment.alternative_explanation}</span></div>}</section>}
    </div>
  );
}

function BindingPanel({ detail, profile, artifact, onNotice, onRefresh }: { detail: Detail; profile: GenericProfile; artifact?: Artifact; onNotice: (notice: string) => void; onRefresh: () => void }) {
  const numeric = profile.columns.filter((column) => column.inferred_type === "numeric" || column.inferred_type === "integer");
  const [xColumnId, setXColumnId] = useState(profile.columns[0]?.column_id ?? "");
  const [yColumnId, setYColumnId] = useState(numeric.find((column) => column.column_id !== profile.columns[0]?.column_id)?.column_id ?? numeric[0]?.column_id ?? "");
  const routing = detail.draft?.modality_proposal;
  const codexProposed = routing?.authority === "codex";
  const proposal = codexProposed ? routing.candidate : "generic";
  const confirm = async () => {
    if (!xColumnId || !yColumnId || xColumnId === yColumnId) {
      onNotice("Select distinct X and Y columns before confirming the research binding.");
      return;
    }
    const selected = [xColumnId, yColumnId].map((id) => profile.columns.find((column) => column.column_id === id)).filter(Boolean);
    const confirmedUnits = Object.fromEntries(selected.flatMap((column) => column?.unit.value ? [[column.column_id, column.unit.value]] : []));
    try {
      await api(`/api/generic/runs/${detail.run.run_id}/artifact-binding`, { method: "POST", body: JSON.stringify({ binding: { artifact_id: profile.artifact_id, x_column_id: xColumnId, y_column_ids: [yColumnId], confirmed_units: confirmedUnits, confirmation_authority: "researcher", confirmed_at: new Date().toISOString() }, recipe: proposal }) });
      onNotice("Research binding confirmed. Codex can now review source roles; freeze remains your decision.");
      onRefresh();
    } catch (caught) {
      onNotice(`Binding blocked: ${caught instanceof Error ? caught.message : "check the selected columns."}`);
    }
  };
  return <section className="binding-panel"><div><p className="kicker">RESEARCHER CONFIRMATION / DATA BINDING</p><h2>{artifact?.label ?? profile.artifact_id}: columns are not scientific roles until you confirm them.</h2>{codexProposed ? <p><strong>CODEX PROPOSAL / {proposal.replaceAll("_", " ")}</strong> · {routing?.reasons[0] ?? "Recorded from the Run context."} Confirm the primary axis and observable before the packet can freeze. This proposal does not constrain Codex's later signatures or controls.</p> : <p><strong>CONTROL PENDING / NO CODEX MODALITY COMMITTED</strong> · GroundLoop's header signal is advisory only. Confirm this binding as generic, or ask Codex to read the method and literature before it proposes optional capability metadata.</p>}</div><div className="binding-controls"><label><span>X / INDEPENDENT</span><select value={xColumnId} onChange={(event) => setXColumnId(event.target.value)}>{profile.columns.map((column) => <option value={column.column_id} key={column.column_id}>{column.name} · {column.unit.value ?? "unit unknown"}</option>)}</select></label><label><span>Y / OBSERVABLE</span><select value={yColumnId} onChange={(event) => setYColumnId(event.target.value)}>{numeric.map((column) => <option value={column.column_id} key={column.column_id}>{column.name} · {column.unit.value ?? "unit unknown"}</option>)}</select></label><button type="button" className="primary-button" onClick={() => void confirm()}>CONFIRM {codexProposed ? "PROPOSED" : "GENERIC"} BINDING <Check size={15} /></button></div></section>;
}

function GenericEvidenceDeck({ artifacts, profiles, bindings, evidence, method }: { artifacts: Artifact[]; profiles: GenericProfile[]; bindings: ArtifactBinding[]; evidence: Detail["data_evidence"]; method: string }) {
  const profile = profiles[0];
  const bindingIds = new Set(bindings.map((binding) => binding.artifact_id));
  return <div className="evidence-layout"><div className="trace-wrap generic-data-bay"><div className="field-caption"><span>ARTIFACT / PROFILE / BINDING</span><span>ROWS NEVER MERGED</span></div><div className="artifact-ledger">{artifacts.map((artifact) => { const itemProfile = profiles.find((item) => item.artifact_id === artifact.artifact_id); return <div key={artifact.artifact_id}><span>{artifact.label ?? artifact.artifact_id}</span><span>{artifact.filename}</span><span>{itemProfile ? `${itemProfile.row_count}×${itemProfile.column_count}` : "profile pending"}</span><span>{artifact.sha256.slice(0, 12)}</span><span className={bindingIds.has(artifact.artifact_id) ? "bound" : "unbound"}>{bindingIds.has(artifact.artifact_id) ? "BOUND" : "BINDING REQUIRED"}</span></div>; })}</div>{profile && <><div className="field-caption"><span>CURRENT COLUMNS / {profile.artifact_id}</span><span>BOUND BEFORE INTERPRETATION</span></div><div className="generic-column-table">{profile.columns.slice(0, 6).map((column) => <div key={column.column_id}><span>{column.name}</span><span>{column.inferred_type}</span><span>{column.unit.value ?? "—"} / {column.unit.status}</span><span>{column.missing_count} missing</span></div>)}</div></>}<div className="generic-facts">{evidence?.length ? evidence.slice(-3).map((item) => <p key={item.evidence_id}><strong>{item.artifact_id} / {item.operation.toUpperCase()}</strong> · {item.fact_text}</p>) : <p><strong>NO DATA FACT RECORDED YET</strong> · After you freeze the packet, ask Codex to record the measurement fact for the chosen columns.</p>}</div></div><div className="measurement-boundary"><div className="boundary-code"><span>METHOD /</span><strong>GENERIC TABULAR</strong></div><div className="boundary-row"><span>CONTEXT</span><strong>{method.slice(0, 92)}{method.length > 92 ? "…" : ""}</strong></div><div className="boundary-row"><span>REQUIRES</span><strong>CONFIRMED COLUMN ROLES PER ARTIFACT</strong></div><div className="equation">ARTIFACT → FACT → ALIGNMENT</div></div></div>;
}

function TraceChart({ rows }: { rows: Dataset["rows"] }) {
  const values = rows.map((row) => row.two_wire_resistance_ohm);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = 700;
  const height = 220;
  const plotLeft = 44;
  const plotRight = 680;
  const plotTop = 20;
  const plotBottom = 182;
  const point = (value: number, index: number) => {
    const x = plotLeft + (index / Math.max(rows.length - 1, 1)) * (plotRight - plotLeft);
    const y = plotTop + ((max - value) / Math.max(max - min, 1)) * (plotBottom - plotTop);
    return `${x},${y}`;
  };
  return <svg className="trace-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Raw resistance temperature trace"><line x1={plotLeft} y1={plotBottom} x2={plotRight} y2={plotBottom} className="chart-rule" /><line x1={plotLeft} y1={plotTop} x2={plotLeft} y2={plotBottom} className="chart-rule" /><line x1={plotLeft} y1={(plotTop + plotBottom) / 2} x2={plotRight} y2={(plotTop + plotBottom) / 2} className="chart-grid" /><polyline points={rows.map((row, index) => point(row.two_wire_resistance_ohm, index)).join(" ")} fill="none" className="trace-line" />{rows.map((row, index) => { const [x, y] = point(row.two_wire_resistance_ohm, index).split(","); return <g key={`${row.temperature_c}-${row.two_wire_resistance_ohm}`}><circle cx={x} cy={y} r="3.5" className="trace-dot" /><text x={x} y="205" textAnchor="middle" className="chart-label">{row.temperature_c}°</text></g>; })}<text x="6" y={plotTop + 4} className="chart-label">{formatNumber(max, 0)} Ω</text><text x="8" y={plotBottom + 4} className="chart-label">{formatNumber(min, 0)} Ω</text><text x={plotRight} y="218" textAnchor="end" className="chart-axis-label">TEMPERATURE / °C</text></svg>;
}

function SourcesScreen({ detail, onFreeze, onView }: { detail: Detail; onFreeze: () => Promise<void>; onView: (view: View) => void }) {
  const sources = detail.packet?.source_candidates ?? detail.packet?.sources ?? detail.draft?.sources ?? [];
  const review = detail.packet?.candidate_review ?? detail.packet?.source_review ?? detail.report?.source_review ?? detail.draft?.retrieval_review;
  const adjudications = review?.adjudications ?? [];
  const directCount = adjudications.filter((item) => item.verdict === "direct").length;
  const reviewPending = detail.run.state === "DRAFT" && review?.status === "required";
  const readyToFreeze = detail.run.state === "DRAFT" && sources.length > 0 && directCount > 0 && !reviewPending;
  return <div className="secondary-page"><div className="secondary-heading"><div><p className="kicker">EVIDENCE ROLE REVIEW / SOURCE LEDGER</p><h1>Every source earns its place.</h1><p>Search results start as candidates. Codex must review the excerpt and assign a role before a source can support the decision.</p></div><div className="review-count"><strong>{directCount.toString().padStart(2, "0")}</strong><span>DIRECT<br />UNITS</span></div></div><div className="review-toolbar"><span>{sources.length} candidates · {directCount} direct · {detail.run.state === "DRAFT" ? "UNFROZEN" : "BOUNDARY FROZEN"}</span>{reviewPending && <span className="tiny-note">SOURCE REVIEW STALE · Codex must review the current candidate set again.</span>}<span className="tiny-note"><LockKeyhole size={13} /> Source content is untrusted input.</span></div><div className="source-ledger"><div className="ledger-head"><span>SOURCE / BOUNDED EXCERPT</span><span>SEMANTIC REVIEW</span><span>EVIDENCE ROLE</span><span>PROVENANCE</span></div>{sources.length === 0 ? <div className="ledger-empty"><Beaker size={19} /><span>No literature candidates yet. Open the Run brief, paste it into Codex, and ask it to import bounded source candidates.</span></div> : sources.map((source) => { const adjudication = adjudications.find((item) => item.source_id === source.id); const state = adjudication?.verdict ?? "unreviewed"; return <article className="source-row" key={source.id}><div className="source-main"><span className="source-id">{source.id}</span><h3>{source.title}</h3><p>{source.untrusted_content}</p><a href={source.url_or_doi} target="_blank" rel="noreferrer">{source.locator.section ?? source.url_or_doi}<ArrowRight size={12} /></a></div><div><span className={`source-state ${state}`}>{state.toUpperCase()}</span><p className="source-rationale">{adjudication?.rationale ?? "Awaiting Codex semantic review."}</p></div><div><span className={`role-chip ${adjudication?.role ? "assigned" : ""}`}>{sourceRoleLabel(adjudication?.role)}</span><p className="source-rationale">{adjudication?.role === "theory_basis" ? "What must be true if the mechanism is right." : adjudication?.role === "method_limit" ? "What this measurement cannot distinguish." : adjudication?.role === "discriminating_control" ? "What separates the competing explanations." : "One role is required before this source becomes decision evidence."}</p></div><div className="source-provenance"><span>{source.retrieval_provider.toUpperCase()} / {source.publication_status.replaceAll("_", " ").toUpperCase()}</span><span>{source.year} · {source.authors[0]}</span><span className="hash-line">LOCATOR · {source.locator.section ?? "ABSTRACT"}</span><span className="hash-line">EXCERPT SHA · {(source.content_sha256 ?? "not recorded").slice(0, 16)}</span>{source.search_query && <span className="hash-line">QUERY · {source.search_query}</span>}</div></article>; })}</div><div className={`freeze-callout ${readyToFreeze ? "" : "not-ready"}`}><div>{readyToFreeze ? <LockKeyhole size={18} /> : <Clipboard size={18} />}<div><strong>{detail.run.state === "DRAFT" ? (readyToFreeze ? "Evidence freeze belongs to the researcher." : "Not ready to freeze yet.") : "Evidence boundary is frozen."}</strong><span>{detail.run.state === "DRAFT" ? sourceNextAction(sources, directCount, reviewPending) : "Changing the claim or method now requires a Fork Run."}</span></div></div>{detail.run.state === "DRAFT" ? (readyToFreeze ? <button type="button" className="freeze-action" onClick={() => void onFreeze()}><LockKeyhole size={14} /> FREEZE EVIDENCE</button> : <button type="button" className="freeze-action" onClick={() => onView("audit")}><Clipboard size={14} /> OPEN RUN BRIEF</button>) : <span className="freeze-stamp">IMMUTABLE PACKET</span>}</div></div>;
}

function AuditScreen({ detail, onNotice }: { detail: Detail; onNotice: (notice: string) => void }) {
  const map = detail.convergence;
  const report = detail.report;
  const [copied, setCopied] = useState(false);
  const brief = briefFor(detail);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(brief);
      setCopied(true);
      onNotice("Run brief copied. Paste it into Codex and ask it to continue this GroundLoop Run.");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
      onNotice("Clipboard access was unavailable. Select the visible Run brief, copy it, and paste it into Codex.");
    }
  };
  return <div className="secondary-page audit-page"><div className="secondary-heading"><div><p className="kicker">AUDIT / EXPORT / RUN LINEAGE</p><h1>The decision, with its boundary attached.</h1><p>Use this page to hand the Run to Codex, then export the final decision once the evidence review is complete.</p></div><div className="export-stack"><div className="export-actions"><button type="button" className="primary-button" onClick={() => window.open(apiUrl(`/api/runs/${detail.run.run_id}/report.md`), "_blank")} disabled={!report} title={report ? "Open Markdown export" : "Export unlocks after the Run reaches REPORT EXPORTED"}><Download size={15} /> EXPORT MARKDOWN</button><button type="button" className="outline-button" onClick={() => void copy()}><Clipboard size={14} /> {copied ? "COPIED" : "COPY RUN BRIEF"}</button></div>{!report && <p className="export-hint">Still waiting: reviewed sources, recorded signatures, evidence alignments, and one next experiment.</p>}</div></div><div className="audit-grid"><section className="decision-sheet"><div className="sheet-top"><span className="kicker">DECISION SHEET / {formatId(detail.run.run_id)}</span><span>{report ? "REPORT EXPORTED" : detail.run.state.replaceAll("_", " ")}</span></div><h2>{map?.claim ?? detail.draft?.claim?.claim ?? "Claim pending"}</h2><div className="sheet-verdict"><span>VERDICT</span><strong>{report?.verdict.label.replaceAll("_", " ") ?? "DECISION PENDING"}</strong><p>{report?.verdict.reason ?? "Waiting for Codex to record which signatures the current evidence supports, misses, or leaves confounded."}</p></div><div className="sheet-control"><span>{map?.control ? "NEXT DISCRIMINATING MOVE" : "CONTROL PENDING"}</span><strong>{map?.control?.experiment ?? "No next experiment yet."}</strong>{!map?.control && <p className="sheet-help">A follow-up control appears here after the evidence alignments are recorded.</p>}{map?.control && <div>{map.control.closes_signature_ids?.map((id) => <span key={`close-${id}`}><Check size={12} /> CLOSES {id}</span>)}{map.control.leaves_open_signature_ids?.map((id) => <span key={`open-${id}`}><ArrowRight size={12} /> LEAVES {id} OPEN</span>)}</div>}</div></section><section className="timeline-panel"><div className="section-cap"><span>DECISION HISTORY</span><span>{(detail.timeline ?? []).length.toString().padStart(2, "0")} EVENTS</span></div>{(detail.timeline ?? []).length === 0 ? <p className="empty-note">No state transitions recorded.</p> : <div className="timeline">{detail.timeline?.map((event, index) => <div className="timeline-row" key={`${event.at}-${event.action}`}><span className={`timeline-node ${index === (detail.timeline?.length ?? 1) - 1 ? "current" : ""}`} /><div><span className="timeline-date">{event.at.slice(0, 19).replace("T", "  ")}</span><strong>{event.action.replaceAll("_", " ")}</strong><p>{event.summary}</p></div></div>)}</div>}</section></div><section className="brief-panel"><div className="section-cap"><span>CODEX RUN BRIEF</span><span>PASTE INTO CODEX</span></div><div className="brief-guide"><div><strong>What to do with this</strong><span>Copy the brief below, paste it into Codex, and ask Codex to continue this Run through the GroundLoop MCP.</span></div><ol><li>Codex imports or reviews literature candidates.</li><li>You check Source Review and freeze when it looks right.</li><li>Codex records signatures, alignments, and one next experiment.</li></ol></div><textarea readOnly value={brief} aria-label="Codex Run brief" /></section><div className="audit-footnote"><Ruler size={15} /><span>Run data, source excerpts, and hashes remain local. Export is a view of this boundary, not a replacement for it.</span></div></div>;
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: "cyan" }) {
  return <div className={`metric ${accent ? `metric-${accent}` : ""}`}><span>{label}</span><strong>{value}</strong></div>;
}

function StatusBadge({ status, label }: { status: AlignmentStatus; label?: string }) {
  return <span className={`status-badge ${statusClass(status)}`}><span className="status-glyph" />{label ?? status.toUpperCase()}</span>;
}

export default App;
