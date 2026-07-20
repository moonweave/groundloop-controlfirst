import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowRight,
  Check,
  ChevronRight,
  Clipboard,
  ExternalLink,
  FileSearch,
  Layers3,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";

type RunState =
  | "DRAFT"
  | "PACKET_READY"
  | "SOURCES_INSPECTED"
  | "DATA_ANALYZED"
  | "FINDINGS_VALIDATED"
  | "CONTROL_VALIDATED"
  | "EXPORTED";
type ServiceStatus = "checking" | "ready" | "unavailable";
type ReviewState = Exclude<RunState, "DRAFT" | "EXPORTED">;
type Run = {
  run_id: string;
  state: RunState;
  fixture?: string;
  created_at: string;
};
type EvidenceRef = {
  id: string;
  kind: "source" | "data";
  artifact_id: string;
  excerpt: string;
  sha256: string;
  locator: Record<string, unknown>;
};
type Source = {
  id: string;
  title: string;
  authors: string[];
  year: number;
  url_or_doi: string;
  locator: { section?: string; page?: number };
  untrusted_content: string;
  retrieval_provider: "openalex" | "arxiv";
  publication_status: "indexed_abstract" | "preprint";
};
type SourceRelevance = {
  source_id: string;
  verdict: "direct" | "contextual" | "limited";
  matched_terms: string[];
  reason: string;
};
type SourceAdjudication = {
  source_id: string;
  verdict: "direct" | "contextual" | "reject";
  rationale: string;
};
type RetrievalReview = {
  provider: string;
  status: "required" | "completed";
  candidate_count: number;
  direct_source_ids: string[];
  adjudications: SourceAdjudication[];
};
type SourceReview = {
  provider: string;
  adjudications: SourceAdjudication[];
  adjudicated_at: string;
};
type AuditEvent = {
  at: string;
  action: string;
  state: RunState;
  summary: string;
};
type Finding = {
  id: string;
  statement: string;
  status: "Established" | "Observed" | "Inferred" | "Unresolved";
  evidence_ref_ids: string[];
  reasoning: string;
  uncertainty?: string;
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
type Report = {
  run_id: string;
  claim: string;
  state: "EXPORTED";
  findings: Finding[];
  control: {
    confound: string;
    experiment: string;
    preconditions: string[];
    outcomes: { if?: string; if_?: string; then: string }[];
    priority: string;
    feasibility: string;
  };
  sources: Source[];
  source_relevance: SourceRelevance[];
  source_review?: SourceReview | null;
  dataset: Dataset;
  dataset_provenance: "USER_MEASUREMENT" | "LABELLED_DEMO" | "FIXTURE_DEMO";
  verdict: {
    label: "MECHANISM_NOT_ESTABLISHED";
    reason: string;
    blocking_finding_ids: string[];
  };
};
type Draft = {
  claim: { claim: string } | null;
  sources: Source[];
  source_relevance?: SourceRelevance[];
  methods: string;
  dataset_ready: boolean;
  retrieval_review?: RetrievalReview;
};
type Detail = {
  run: Run;
  timeline?: AuditEvent[];
  input_artifacts?: string[];
  draft?: Draft;
  packet?: {
    claim: { claim: string };
    sources: Source[];
    source_relevance?: SourceRelevance[];
    source_review?: SourceReview;
    dataset: Dataset;
    evidence_refs: EvidenceRef[];
  };
  report?: Report;
};
type TransientAudit = {
  analysis: {
    row_count: number;
    time_range_s: [number, number];
    voltage_range_v: [number, number];
    fit_window_s: [number, number];
    fit_point_count: number;
    fit_method: "ols_log_log";
    decay_exponent: number;
    log_log_r2: number;
    warnings: string[];
  };
  evidence_ref: EvidenceRef;
  scope: string;
};

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const bodyIsForm = init?.body instanceof FormData;
  const response = await fetch(
    `${import.meta.env.VITE_GROUNDLOOP_API_URL ?? ""}${path}`,
    {
      ...init,
      headers: {
        ...(bodyIsForm ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {}),
      },
    },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: { message?: string };
    } | null;
    throw new Error(
      body?.detail?.message ?? "GroundLoop local service is unavailable.",
    );
  }
  return response.json() as Promise<T>;
};

const stateLabel: Record<RunState, string> = {
  DRAFT: "Research setup",
  PACKET_READY: "Evidence packet ready",
  SOURCES_INSPECTED: "Sources inspected",
  DATA_ANALYZED: "Data analysed",
  FINDINGS_VALIDATED: "Findings validated",
  CONTROL_VALIDATED: "Control validated",
  EXPORTED: "Validated report",
};

const transportTerms = [
  "resistance",
  "conductivity",
  "transport",
  "temperature",
  "thermal",
  "current",
  "voltage",
  "two-wire",
  "four-wire",
  "electrical",
];

const resistanceDemoTrace = [
  { temperature_c: 20, two_wire_resistance_ohm: 120.0 },
  { temperature_c: 30, two_wire_resistance_ohm: 117.5 },
  { temperature_c: 40, two_wire_resistance_ohm: 113.2 },
  { temperature_c: 50, two_wire_resistance_ohm: 107.0 },
  { temperature_c: 60, two_wire_resistance_ohm: 98.4 },
  { temperature_c: 70, two_wire_resistance_ohm: 88.8 },
  { temperature_c: 80, two_wire_resistance_ohm: 77.1 },
  { temperature_c: 90, two_wire_resistance_ohm: 65.0 },
];

function transportFit(question: string) {
  const normalized = question.toLowerCase();
  const matched = transportTerms.filter((term) => normalized.includes(term));
  if (question.trim().length < 10) {
    return {
      label: "Describe the claim you want to test",
      detail:
        "The included executable demo evaluates a two-wire resistance-temperature sweep.",
      tone: "neutral",
    };
  }
  if (matched.length >= 2) {
    return {
      label: "Fits the included electrical-sweep demo",
      detail: `Matched demo terms: ${matched.slice(0, 3).join(", ")}. The runnable path expects a two-wire resistance-temperature CSV.`,
      tone: "ready",
    };
  }
  return {
    label: "Claim captured — check the demo fit",
    detail:
      "GroundLoop can frame and retrieve evidence for this claim, but this build's executable data path is the included two-wire resistance-temperature sweep.",
    tone: "review",
  };
}

function relevanceLabel(verdict: SourceRelevance["verdict"]) {
  return {
    direct: "Lexical match — review required",
    contextual: "Lexical context — review required",
    limited: "Lower lexical match — review required",
  }[verdict];
}

function sourceStatusLabel(source: Source) {
  return source.retrieval_provider === "arxiv"
    ? "arXiv preprint · not peer-reviewed"
    : "OpenAlex indexed abstract";
}

function sourceStatusNote(source: Source) {
  return source.retrieval_provider === "arxiv"
    ? "Preprint abstract only — not peer-reviewed; full paper was not inspected."
    : "Indexed abstract only — full paper was not inspected.";
}

function messageForApiError(error: unknown, fallback: string) {
  if (error instanceof TypeError && error.message === "Failed to fetch") {
    return "Local analysis service is unavailable. Retry the connection before continuing.";
  }
  return error instanceof Error ? error.message : fallback;
}

function App() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [question, setQuestion] = useState("");
  const [methods, setMethods] = useState("");
  const [datasetFile, setDatasetFile] = useState<File | null>(null);
  const [transientFile, setTransientFile] = useState<File | null>(null);
  const [transientAudit, setTransientAudit] = useState<TransientAudit | null>(null);
  const [notice, setNotice] = useState(
    "Start with a research question. GroundLoop will retrieve a small, traceable reference set for you.",
  );
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>("checking");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [handoffRunId, setHandoffRunId] = useState<string | null>(null);
  const [sourceReviewCopied, setSourceReviewCopied] = useState(false);
  const [sourceReviewRunId, setSourceReviewRunId] = useState<string | null>(null);
  const previousScreenKey = useRef<string | null>(null);
  const previousSourceReviewStatus = useRef<RetrievalReview["status"] | null>(null);

  const setCurrentDetail = useCallback((next: Detail | null) => {
    setDetail(next);
    if (next?.run.state === "DRAFT") {
      setQuestion(next.draft?.claim?.claim ?? "");
      setMethods(next.draft?.methods ?? "");
    }
  }, []);

  const refreshRuns = useCallback(async () => {
    try {
      const next = await api<Run[]>("/api/runs");
      setRuns(next);
      setServiceStatus("ready");
    } catch (error) {
      setServiceStatus("unavailable");
      throw error;
    }
  }, []);

  const retryConnection = useCallback(async () => {
    setServiceStatus("checking");
    try {
      await refreshRuns();
      setNotice("Local analysis service connected. You can start a new evidence check.");
    } catch {
      setNotice(
        "Local analysis service is not running. Start it with ./scripts/demo.sh, then retry the connection.",
      );
    }
  }, [refreshRuns]);

  const refresh = useCallback(
    async (runId?: string, options?: { quiet?: boolean }) => {
      if (!runId) return;
      const next = await api<Detail>(`/api/runs/${runId}`);
      setCurrentDetail(next);
      await refreshRuns();
      if (!options?.quiet) {
        setNotice(
          next.run.state === "EXPORTED"
            ? "Validated report ready. The evidence decision and next control are saved."
            : `Refreshed ${stateLabel[next.run.state]}.`,
        );
      }
    },
    [refreshRuns, setCurrentDetail],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void retryConnection();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [retryConnection]);

  const currentState = detail?.run.state;
  const screenKey = detail
    ? `${detail.run.run_id}:${detail.run.state}`
    : "new-run";
  const draft = detail?.draft;
  const report = detail?.report;
  const packet = detail?.packet;
  const sourceReviewStatus = draft?.retrieval_review?.status;
  const sourceHashByArtifact = useMemo(
    () =>
      new Map(
        packet?.evidence_refs
          .filter((item) => item.kind === "source")
          .map((item) => [item.artifact_id, item.sha256]),
      ),
    [packet],
  );
  const handoff = detail
    ? `Use the GroundLoop MCP for run ${detail.run.run_id}. This evidence packet is already frozen after semantic source review. Call inspect_sources, then analyze_dataset. Treat only the supplied excerpts, locators, and saved source-review rationales as source support; lexical ordering is never source support. Then validate exactly four findings—one Established, one Observed, one Inferred, and one Unresolved. Propose one atomic ControlFirst experiment, not a bundled follow-up, then export the report.`
    : "";
  const sourceReviewHandoff =
    detail && draft?.retrieval_review?.status === "required"
      ? `Use the GroundLoop MCP for run ${detail.run.run_id}. First call inspect_retrieved_sources and read every returned title, excerpt, locator, and provider status. Treat the lexical screen only as a reading order, never as source support. An arXiv item is a preprint, not peer-reviewed consensus. Then call adjudicate_sources with one direct, contextual, or reject decision and a brief rationale for every candidate. Mark direct only when the supplied excerpt addresses the claimed measurement, its confound, or the discriminating control. At least one direct source is required. Do not create the evidence packet yet.`
      : "";
  const handoffStarted = handoffRunId === detail?.run.run_id;
  const sourceReviewStarted = sourceReviewRunId === detail?.run.run_id;
  const setupReady = Boolean(
    draft?.sources.length &&
      draft?.dataset_ready &&
      methods.trim().length >= 20 &&
      draft?.retrieval_review?.status !== "required",
  );

  useEffect(() => {
    if (
      previousScreenKey.current !== null &&
      previousScreenKey.current !== screenKey
    ) {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    }
    previousScreenKey.current = screenKey;
  }, [screenKey]);

  useEffect(() => {
    const reviewJustCompleted =
      previousSourceReviewStatus.current === "required" &&
      sourceReviewStatus === "completed";
    previousSourceReviewStatus.current = sourceReviewStatus ?? null;
    if (!reviewJustCompleted || !detail) return;

    const selectedCount = detail.draft?.retrieval_review?.direct_source_ids.length ?? 0;
    setNotice(
      `Source review complete. ${selectedCount} decision source${selectedCount === 1 ? "" : "s"} selected; review the decisions below, then freeze the packet.`,
    );
    window.requestAnimationFrame(() => {
      document
        .getElementById("source-boundary-checkpoint")
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [detail, sourceReviewStatus]);

  const startResearch = async () => {
    if (question.trim().length < 10) {
      setNotice(
        "Enter a research question of at least 10 characters before searching.",
      );
      return;
    }
    setBusy(true);
    try {
      const runId =
        detail?.run.state === "DRAFT"
          ? detail.run.run_id
          : (await api<Run>("/api/runs", { method: "POST", body: "{}" }))
              .run_id;
      const next = await api<Detail>(`/api/runs/${runId}/gather-references`, {
        method: "POST",
        body: JSON.stringify({ research_question: question.trim() }),
      });
      setCurrentDetail(next);
      await refreshRuns();
      setNotice(
        "Candidate references were retrieved automatically. They are not evidence yet: copy the Codex source-review brief before locking the packet.",
      );
    } catch (error) {
      setNotice(messageForApiError(error, "Could not start the research run."));
    } finally {
      setBusy(false);
    }
  };

  const loadDemo = async () => {
    setBusy(true);
    try {
      const run = await api<Run>("/api/runs", {
        method: "POST",
        body: JSON.stringify({ fixture_name: "four_wire_contact_control_guided" }),
      });
      await refresh(run.run_id);
      setNotice(
        "Guided demo ready. This is a reproducible, clearly labelled fixture report; no MCP handoff is required to inspect the decision.",
      );
    } catch (error) {
      setNotice(messageForApiError(error, "Could not load the demo run."));
    } finally {
      setBusy(false);
    }
  };

  const saveMethods = async () => {
    if (!detail || methods.trim().length < 20) {
      setNotice(
        "Add at least one clear sentence about how the data were measured.",
      );
      return;
    }
    setBusy(true);
    try {
      await api<Run>(`/api/runs/${detail.run.run_id}/methods`, {
        method: "PUT",
        body: JSON.stringify({ methods: methods.trim() }),
      });
      await refresh(detail.run.run_id);
      setNotice("Method context saved locally.");
    } catch (error) {
      setNotice(messageForApiError(error, "Could not save the method context."));
    } finally {
      setBusy(false);
    }
  };

  const uploadDataset = async () => {
    if (!detail || !datasetFile) {
      setNotice("Choose a measurement CSV before importing.");
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", datasetFile);
      await api(`/api/runs/${detail.run.run_id}/dataset`, {
        method: "POST",
        body: form,
      });
      await refresh(detail.run.run_id);
      setNotice(
        "Measurement data stored locally and checked for deterministic analysis.",
      );
    } catch (error) {
      setNotice(messageForApiError(error, "Could not accept that measurement CSV."));
    } finally {
      setBusy(false);
    }
  };

  const loadDemoData = async () => {
    if (!detail) return;
    setBusy(true);
    try {
      await api<Detail>(`/api/runs/${detail.run.run_id}/demo-data`, {
        method: "POST",
        body: "{}",
      });
      await refresh(detail.run.run_id);
      setNotice(
        "Clearly labelled synthetic demonstration data added. Replace it with your measurement CSV before drawing a real conclusion.",
      );
    } catch (error) {
      setNotice(messageForApiError(error, "Could not add demo data."));
    } finally {
      setBusy(false);
    }
  };

  const auditTransient = async () => {
    if (!transientFile) {
      setNotice("Choose a Hioki SM7120 resistance export before running the transient check.");
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", transientFile);
      const result = await api<TransientAudit>("/api/transient-audit", {
        method: "POST",
        body: form,
      });
      setTransientAudit(result);
      setNotice(
        "Transient diagnostic complete. It is a local OLS check, not a mechanism conclusion or a replacement for a robust project fit.",
      );
    } catch (error) {
      setTransientAudit(null);
      setNotice(messageForApiError(error, "Could not audit that transient export."));
    } finally {
      setBusy(false);
    }
  };

  const prepare = async () => {
    if (!detail) return;
    setBusy(true);
    try {
      const next = await api<Detail>(`/api/runs/${detail.run.run_id}/prepare`, {
        method: "POST",
        body: "{}",
      });
      setCurrentDetail(next);
      await refreshRuns();
      setNotice(
        "Evidence packet frozen. Its sources and measurement data cannot change during review.",
      );
    } catch (error) {
      setNotice(messageForApiError(error, "Could not freeze the evidence packet."));
    } finally {
      setBusy(false);
    }
  };

  const copyHandoff = async () => {
    try {
      await navigator.clipboard.writeText(handoff);
      setCopied(true);
      setHandoffRunId(detail?.run.run_id ?? null);
      setNotice(
        "Analysis brief copied. Paste it into Codex; GroundLoop will check this run for a completed review.",
      );
    } catch {
      setNotice(
        "Clipboard access was unavailable. Copy the visible handoff text into Codex manually.",
      );
    }
  };

  const copySourceReview = async () => {
    if (!sourceReviewHandoff) return;
    try {
      await navigator.clipboard.writeText(sourceReviewHandoff);
      setSourceReviewCopied(true);
      setSourceReviewRunId(detail?.run.run_id ?? null);
      setNotice(
        "Source-review brief copied. Paste it into Codex; GroundLoop will only accept reviewed direct sources into the evidence packet.",
      );
    } catch {
      setNotice(
        "Clipboard access was unavailable. Copy the visible source-review brief into Codex manually.",
      );
    }
  };

  useEffect(() => {
    const runId = detail?.run.run_id;
    if (
      !runId ||
      !detail ||
      detail.run.state === "EXPORTED" ||
      (detail.run.state === "DRAFT" &&
        detail.draft?.retrieval_review?.status !== "required")
    ) {
      return;
    }
    const timer = window.setInterval(() => {
      void refresh(runId, { quiet: true }).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [detail, refresh]);

  const selectRun = async (runId: string) => {
    setBusy(true);
    try {
      const next = await api<Detail>(`/api/runs/${runId}`);
      setCurrentDetail(next);
      await refreshRuns();
      setNotice(`Opened ${stateLabel[next.run.state]}.`);
    } catch (error) {
      setNotice(messageForApiError(error, "Could not open that run."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen overflow-x-clip bg-[#fcfdfb] text-[#111214]">
      <header className="border-b border-[#17324d]/20 bg-white">
        <div className="mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <span className="grid size-8 place-items-center rounded-xl bg-[#17324d] text-white shadow-sm">
              <Layers3 className="size-4" />
            </span>
            <span className="brand-serif text-[21px] leading-none text-[#17324d]">
              GroundLoop
            </span>
            <span className="hidden border-l border-[#17324d]/25 pl-3 text-xs uppercase tracking-[0.12em] text-[#17324d]/70 sm:inline">
              ControlFirst · scientific red team
            </span>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {runs.length > 0 && (
              <label className="sr-only" htmlFor="run-picker">
                Open a saved research run
              </label>
            )}
            {runs.length > 0 && (
              <select
                id="run-picker"
                value={detail?.run.run_id ?? ""}
                onChange={(event) => void selectRun(event.target.value)}
                disabled={busy}
                className="h-9 max-w-44 rounded-full border border-[#17324d]/20 bg-white px-3 text-xs text-black/75 shadow-sm"
              >
                <option value="" disabled>
                  Open a saved run
                </option>
                {runs.map((run) => (
                  <option key={run.run_id} value={run.run_id}>
                    {stateLabel[run.state]} · {run.run_id.slice(0, 8)}
                  </option>
                ))}
              </select>
            )}
            <Button
              variant="outline"
              size="sm"
              className="control-action border-[#17324d]/25 bg-white px-4"
              onClick={() => {
                setCurrentDetail(null);
                setQuestion("");
                setMethods("");
                setDatasetFile(null);
                setTransientFile(null);
                setTransientAudit(null);
                setNotice(
                  "Start a new research question or open a deliberate saved run.",
                );
              }}
              disabled={busy}
            >
              <Plus className="size-3.5" /> New run
            </Button>
            {detail && (
              <Button
                variant="outline"
                size="sm"
                className="control-action border-[#17324d]/25 bg-white px-4"
                onClick={() => void refresh(detail.run.run_id)}
                disabled={busy}
              >
                <RefreshCw
                  className={busy ? "size-3.5 animate-spin" : "size-3.5"}
                />{" "}
                Refresh
              </Button>
            )}
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-[1320px] px-5 pb-16 pt-10 sm:px-8">
        <WorkflowRail state={currentState} />
        <div
          aria-live="polite"
          className={`mb-8 flex flex-wrap items-center justify-between gap-3 border-l-2 pl-3 text-sm leading-6 ${
            serviceStatus === "unavailable"
              ? "border-[#c8502a] bg-[#fff8f5] py-2 pr-3 text-[#8a301b]"
              : "border-[#17324d] text-black/70"
          }`}
        >
          <p>{notice}</p>
          {serviceStatus === "unavailable" && (
            <Button
              variant="outline"
              size="sm"
              className="shrink-0 rounded-none border-[#c8502a] bg-white text-[#8a301b] hover:bg-[#fff2ed] hover:text-[#8a301b]"
              onClick={() => void retryConnection()}
              disabled={busy}
            >
              <RefreshCw className="size-3.5" />
              Retry connection
            </Button>
          )}
        </div>

        {!detail && (
          <StartScreen
            question={question}
            setQuestion={setQuestion}
            busy={busy}
            onStart={() => void startResearch()}
            onDemo={() => void loadDemo()}
            transientFile={transientFile}
            transientAudit={transientAudit}
            onTransientFile={(file) => {
              setTransientFile(file);
              setTransientAudit(null);
            }}
            onAuditTransient={() => void auditTransient()}
          />
        )}
        {detail?.run.state === "DRAFT" && (
          <SetupScreen
            detail={detail}
            question={question}
            methods={methods}
            setMethods={setMethods}
            datasetFile={datasetFile}
            setDatasetFile={setDatasetFile}
            busy={busy}
            ready={setupReady}
            onSearch={() => void startResearch()}
            onSaveMethods={() => void saveMethods()}
            onUpload={() => void uploadDataset()}
            onDemoData={() => void loadDemoData()}
            onPrepare={() => void prepare()}
            sourceReviewHandoff={sourceReviewHandoff}
            sourceReviewCopied={sourceReviewCopied && sourceReviewStarted}
            sourceReviewStarted={sourceReviewStarted}
            onCopySourceReview={() => void copySourceReview()}
          />
        )}
        {detail &&
          detail.run.state !== "DRAFT" &&
          detail.run.state !== "EXPORTED" && (
            <ReviewScreen
              detail={detail}
              handoff={handoff}
              copied={copied && handoffStarted}
              handoffStarted={handoffStarted}
              serviceStatus={serviceStatus}
              busy={busy}
              onCopy={() => void copyHandoff()}
            />
          )}
        {report && (
          <ReportScreen
            report={report}
            packet={packet}
            sourceHashByArtifact={sourceHashByArtifact}
            timeline={detail?.timeline ?? []}
          />
        )}
      </section>
    </main>
  );
}

function WorkflowRail({ state }: { state?: RunState }) {
  const step =
    !state || state === "DRAFT"
      ? 1
      : state === "PACKET_READY"
        ? 3
        : state === "EXPORTED"
          ? 4
          : 3;
  const steps = [
    "Frame question",
    "Preserve evidence",
    "Check evidence",
    "Decide next test",
  ];
  return (
    <ol className="mb-10 grid gap-3 border-y border-[#17324d]/20 py-4 sm:grid-cols-4">
      {steps.map((label, index) => (
        <li
          key={label}
          className={`flex items-center gap-3 text-sm ${step === index + 1 ? "font-medium text-[#17324d]" : step > index + 1 ? "text-black/60" : "text-black/40"}`}
        >
          <span
            className={`grid size-6 place-items-center border font-mono text-[11px] ${step === index + 1 ? "border-[#17324d] bg-[#17324d] text-white" : step > index + 1 ? "border-[#17324d]/40 text-[#17324d]" : "border-black/15"}`}
          >
            {step > index + 1 ? <Check className="size-3.5" /> : index + 1}
          </span>
          {label}
        </li>
      ))}
    </ol>
  );
}

function AnalysisMap({
  claim,
  sources,
  dataReady,
  dataset,
  comparisonLabel,
  comparisonDetail,
  fixtureMode = false,
  sourceStage = "candidate",
  claimLabel = "1 · Claim & sources",
  recordLabel = "2 · Observed record",
}: {
  claim: string;
  sources: Source[];
  dataReady: boolean;
  dataset?: Dataset;
  comparisonLabel: string;
  comparisonDetail: string;
  fixtureMode?: boolean;
  sourceStage?: "candidate" | "frozen";
  claimLabel?: string;
  recordLabel?: string;
}) {
  const sourceSummary = fixtureMode
    ? `${sources.length} foundational measurement source${sources.length === 1 ? "" : "s"}`
    : sourceStage === "frozen"
      ? `${sources.length} reviewed source${sources.length === 1 ? "" : "s"} frozen for this decision`
    : sources.length
    ? `${sources.length} candidate${sources.length === 1 ? "" : "s"} awaiting semantic source review`
    : "References have not been collected yet.";
  const dataSummary = dataset
    ? `${dataset.row_count} rows · ${dataset.temperature_range_c[0]}–${dataset.temperature_range_c[1]} °C`
    : dataReady
      ? "CSV added locally · ready for deterministic analysis"
      : "Add the included temperature–resistance CSV";

  return (
    <section className="mt-8 border-y border-black/15 py-5 sm:py-6" aria-label="Control map">
      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_0.9fr] lg:gap-0">
        <article className="border-l-2 border-[#17324d] px-4 py-1 sm:px-5">
          <p className="eyebrow text-[#17324d]">{claimLabel}</p>
          <p className="mt-2 text-sm font-medium leading-6 text-[#17324d]">
            {claim || "Add the claim you want to test."}
          </p>
          <p className="mt-3 font-mono text-[11px] leading-5 text-black/55">
            {sourceSummary}
          </p>
        </article>
        <article className="border-l-2 border-[#355b3c] px-4 py-1 sm:px-5 lg:border-l lg:border-black/10">
          <p className="eyebrow text-[#355b3c]">{recordLabel}</p>
          <p className="mt-2 text-sm font-medium leading-6 text-[#355b3c]">
            What does the record actually show?
          </p>
          <p className="mt-3 font-mono text-[11px] leading-5 text-black/55">
            {dataSummary}
          </p>
        </article>
        <article className="border-l-2 border-[#c8502a] bg-[#fff7f3] px-4 py-3 sm:px-5 lg:border-l lg:border-black/10">
          <p className="eyebrow text-[#a13d25]">3 · Control decision</p>
          <p className="mt-2 text-sm font-medium leading-6 text-[#8a301b]">
            {comparisonLabel}
          </p>
          <p className="mt-2 text-xs leading-5 text-black/65">{comparisonDetail}</p>
        </article>
      </div>
    </section>
  );
}

function HandoffStatus({
  runId,
  state,
  handoffStarted,
  serviceStatus,
  timeline = [],
}: {
  runId: string;
  state: ReviewState;
  handoffStarted: boolean;
  serviceStatus: ServiceStatus;
  timeline?: AuditEvent[];
}) {
  const codexStage =
    state === "PACKET_READY"
      ? {
          label: handoffStarted ? "Waiting for Codex's first MCP call" : "Not sent to Codex yet",
          detail: handoffStarted
            ? "The brief is copied. Paste it into Codex to begin the recorded review."
            : "Copy the brief below, then paste it into a Codex conversation.",
        }
      : state === "SOURCES_INSPECTED"
        ? {
            label: "Codex saved source inspection",
            detail: "Next, Codex analyses the frozen measurement record.",
          }
        : state === "DATA_ANALYZED"
          ? {
              label: "Codex saved dataset analysis",
              detail: "Next, Codex validates the four-state findings.",
            }
          : state === "FINDINGS_VALIDATED"
            ? {
                label: "Codex saved four-state findings",
                detail: "Next, Codex proposes one discriminating control.",
              }
            : {
                label: "Codex saved the ControlFirst proposal",
                detail: "One export call will publish the report in this run.",
              };
  const localService =
    serviceStatus === "ready"
      ? "Connected"
      : serviceStatus === "checking"
        ? "Checking connection"
        : "Unavailable";

  return (
    <section
      className="border border-[#17324d]/20 bg-[#f5f8f5] p-5 sm:p-7"
      aria-live="polite"
      aria-label="Live GroundLoop and Codex handoff status"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Live handoff status</p>
          <h2 className="mt-3 text-xl font-medium tracking-[-0.03em]">
            Where this run is, and what happens next.
          </h2>
        </div>
        <span className="border border-[#17324d]/20 px-2 py-1 font-mono text-[10px] text-[#17324d]/70">
          RUN {runId.slice(0, 8)}
        </span>
      </div>
      <div className="mt-5 space-y-4">
        <div className="border-l-2 border-[#215f47] pl-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#215f47]">
            01 · GroundLoop local service · {localService}
          </p>
          <p className="mt-1 text-sm leading-6 text-black/65">
            The browser can read this run and will check for saved progress every 3 seconds.
          </p>
        </div>
        <div className="border-l-2 border-[#17324d]/50 pl-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#17324d]/75">
            02 · Browser to Codex · Manual handoff
          </p>
          <p className="mt-1 text-sm leading-6 text-black/65">
            This page does not start a Codex task itself. You paste one frozen brief into Codex; no claim or evidence is retyped.
          </p>
        </div>
        <div className="border-l-2 border-[#c8502a] bg-[#fff7f3] pl-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#a13d25]">
            03 · Codex MCP to GroundLoop · {codexStage.label}
          </p>
          <p className="mt-1 text-sm leading-6 text-black/65">{codexStage.detail}</p>
        </div>
      </div>
      <DecisionTimeline timeline={timeline} compact />
      <p className="mt-5 border-t border-black/10 pt-4 text-xs leading-5 text-black/55">
        A stage changes here only after Codex successfully saves that MCP operation to this exact run.
      </p>
    </section>
  );
}

function DecisionTimeline({
  timeline,
  compact = false,
}: {
  timeline: AuditEvent[];
  compact?: boolean;
}) {
  if (!timeline.length) {
    return (
      <p className="mt-5 text-xs leading-5 text-black/55">
        This older run has no recorded decision history.
      </p>
    );
  }
  const visible = compact ? timeline.slice(-4) : timeline;
  return (
    <section className="mt-5 border-t border-black/10 pt-4" aria-label="Decision history">
      <p className="eyebrow">Decision history</p>
      <ol className="mt-3 space-y-2">
        {visible.map((event) => (
          <li key={`${event.at}-${event.action}`} className="flex gap-3 text-xs leading-5 text-black/65">
            <span className="mt-1 size-1.5 shrink-0 rounded-full bg-[#17324d]" aria-hidden="true" />
            <span>{event.summary}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function SourceSummaryRow({
  source,
  relevance,
  fixtureMode = false,
}: {
  source: Source;
  relevance?: SourceRelevance;
  fixtureMode?: boolean;
}) {
  return (
    <article className="flex items-start justify-between gap-4 border-b border-black/10 py-3 last:border-b-0">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium" title={source.title}>
          {source.title}
        </p>
        <p className="mt-1 text-xs text-black/55">
          {source.authors[0] ?? "Unknown author"} · {source.year}
        </p>
        {!fixtureMode && (
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.06em] text-[#17324d]/70">
            {sourceStatusLabel(source)}
          </p>
        )}
      </div>
      {relevance && (
        <span
          className={`shrink-0 border px-2 py-1 font-mono text-[10px] uppercase ${
            relevance.verdict === "direct"
              ? "border-[#215f47] bg-[#edf8f1] text-[#215f47]"
              : relevance.verdict === "contextual"
                ? "border-[#805720] bg-[#fff7df] text-[#805720]"
                : "border-[#a13d25] bg-[#fff0eb] text-[#a13d25]"
          }`}
        >
          {fixtureMode && relevance.verdict === "contextual"
            ? "Measurement principle"
            : relevanceLabel(relevance.verdict)}
        </span>
      )}
    </article>
  );
}

function StartScreen({
  question,
  setQuestion,
  busy,
  onStart,
  onDemo,
  transientFile,
  transientAudit,
  onTransientFile,
  onAuditTransient,
}: {
  question: string;
  setQuestion: (value: string) => void;
  busy: boolean;
  onStart: () => void;
  onDemo: () => void;
  transientFile: File | null;
  transientAudit: TransientAudit | null;
  onTransientFile: (file: File | null) => void;
  onAuditTransient: () => void;
}) {
  const remainingCharacters = Math.max(0, 10 - question.trim().length);
  const fit = transportFit(question);
  return (
    <div className="controlfirst-start relative">
      <span className="controlfirst-wordmark" aria-hidden="true">
        ControlFirst
      </span>
      <section className="soft-stage grid gap-8 px-5 py-7 sm:px-8 sm:py-9 lg:grid-cols-[1.08fr_0.92fr] lg:gap-12 lg:px-10 lg:py-10">
        <div className="pt-1 lg:pt-2">
          <p className="eyebrow text-[#17324d]">
            Scientific red team · evidence-bound claim check
          </p>
          <h1 className="brand-serif mt-4 max-w-4xl text-[3rem] leading-[0.98] tracking-[-0.055em] text-[#102b49] sm:text-6xl lg:text-[4.6rem]">
            What does your evidence actually support?
          </h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-[#17324d]/75">
            GroundLoop separates a research claim from the evidence that bears
            on it, freezes the review boundary, then identifies the smallest
            control that could change the conclusion.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Button
              className="control-action h-12 bg-[#102b49] px-6 text-sm uppercase tracking-[0.08em] text-white hover:bg-[#17324d]"
              onClick={onDemo}
              disabled={busy}
            >
              {busy ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <ArrowRight className="size-4" />
              )}
              Open the guided demo
            </Button>
            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-[#17324d]/60">
              8 points · reproducible fixture · one decisive control
            </p>
          </div>
          <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-xs font-medium uppercase tracking-[0.12em] text-[#17324d]/65">
            <span>Claim</span>
            <span className="text-[#355b3c]">Evidence</span>
            <span className="text-[#c8502a]">Next control</span>
          </div>
        </div>
        <TracePreview />
      </section>

      <section className="soft-surface mt-8 grid gap-8 bg-white p-5 sm:p-7 lg:grid-cols-[1fr_0.38fr] lg:gap-12">
        <div>
          <p className="eyebrow text-[#17324d]">Research claim to test</p>
          <label htmlFor="research-question" className="sr-only">
            Describe the research claim you want to test
          </label>
          <textarea
            id="research-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            aria-describedby="research-question-help"
            placeholder={'For example: “The observed change is caused by …”'}
            className="claim-entry brand-serif mt-4 min-h-28 w-full resize-y border-x-0 border-b border-t-0 border-[#17324d]/55 bg-transparent px-0 py-3 text-2xl leading-tight tracking-[-0.035em] text-[#17324d] outline-none placeholder:text-[#17324d]/45 focus:border-[#17324d] sm:text-3xl"
          />
          <p id="research-question-help" className="mt-3 font-mono text-[11px] uppercase tracking-[0.08em] text-black/55">
            {remainingCharacters
              ? `${remainingCharacters} more character${remainingCharacters === 1 ? "" : "s"} needed to search.`
              : "Claim ready for reference discovery. Check the included demo fit below."}
          </p>
          <div
            className={`mt-4 border-l-2 px-3 py-2 text-xs leading-5 ${
              fit.tone === "ready"
                ? "border-[#355b3c] bg-[#f1f6f1] text-[#244e32]"
                : fit.tone === "review"
                  ? "border-[#805720] bg-[#fff7df] text-[#805720]"
                  : "border-[#17324d]/25 bg-[#f7f8f8] text-black/65"
            }`}
            aria-live="polite"
          >
            <span className="font-medium">{fit.label}</span>
            <span className="block">{fit.detail}</span>
          </div>
        </div>
        <aside className="rounded-2xl border border-[#c8502a]/25 bg-[#fff8f5] px-5 py-5 lg:mt-1">
          <p className="eyebrow text-[#c8502a]">Included demo control</p>
          <p className="brand-serif mt-4 text-2xl leading-tight tracking-[-0.035em] text-[#b34424]">
            A four-wire measurement is the decisive control in the included resistance-sweep example.
          </p>
          <Button
            variant="link"
            className="mt-5 h-auto px-0 text-sm text-[#b34424] hover:text-[#8a301b]"
            onClick={onDemo}
            disabled={busy}
          >
            Open the guided demo <ChevronRight className="size-4" />
          </Button>
        </aside>
      </section>

      <section className="grid gap-6 py-7 lg:grid-cols-[0.92fr_0.8fr] lg:items-center lg:justify-between">
        <p className="flex max-w-xl gap-3 text-xs leading-5 text-black/60">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-[#17324d]" />
          GroundLoop retrieves a small, bounded set from OpenAlex and arXiv.
          Retrieval guides the review; every source stays untrusted until Codex
          inspects its supplied excerpt in the MCP workflow.
        </p>
        <Button
          className="control-action h-14 w-full bg-[#102b49] text-sm uppercase tracking-[0.1em] text-white hover:bg-[#17324d] lg:justify-self-end lg:px-8"
          onClick={onStart}
          disabled={busy || question.trim().length < 10}
        >
          {busy ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : (
            <FileSearch className="size-4" />
          )}{" "}
          Build the evidence boundary <ArrowRight className="size-4" />
        </Button>
      </section>

      <details className="border-t border-[#17324d]/15 py-4 text-sm text-black/60">
        <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.08em] text-[#355b3c] marker:text-[#355b3c]">
          Technical preview · inspect a Hioki transient record
        </summary>
        <div className="pt-4">
          <TransientAuditCard
            file={transientFile}
            audit={transientAudit}
            busy={busy}
            onFile={onTransientFile}
            onAudit={onAuditTransient}
          />
        </div>
      </details>
    </div>
  );
}

function TransientAuditCard({
  file,
  audit,
  busy,
  onFile,
  onAudit,
}: {
  file: File | null;
  audit: TransientAudit | null;
  busy: boolean;
  onFile: (file: File | null) => void;
  onAudit: () => void;
}) {
  return (
    <section className="grid gap-5 border-b border-[#17324d]/25 py-7 lg:grid-cols-[0.84fr_1.16fr] lg:items-start">
      <div>
        <p className="eyebrow text-[#355b3c]">Additional local data check</p>
        <h2 className="brand-serif mt-3 text-3xl tracking-[-0.04em] text-[#17324d]">
          Inspect a transient current trace.
        </h2>
        <p className="mt-3 max-w-lg text-sm leading-6 text-black/65">
          For a Hioki SM7120 resistance-mode export, GroundLoop derives V/R and
          reports a bounded log–log diagnostic. This is a separate record check;
          it does not freeze a claim packet or establish a mechanism.
        </p>
        <p className="mt-3 font-mono text-[11px] leading-5 text-black/55">
          Accepted now: Hioki SM7120 · resistance mode · DATE, TIME, Voltage[V], Measurement value[ohm]
        </p>
      </div>
      <div className="border border-[#355b3c]/30 bg-[#f5f9f5] p-4 sm:p-5">
        <label
          htmlFor="transient-upload"
          className="flex cursor-pointer items-center justify-between gap-4 border border-dashed border-[#355b3c]/45 bg-white p-3 text-sm text-[#17324d]"
        >
          <span className="flex min-w-0 items-center gap-2">
            <Upload className="size-4 shrink-0" />
            <span className="truncate">{file ? file.name : "Choose Hioki transient CSV"}</span>
          </span>
          <span className="shrink-0 text-xs text-black/55">CSV only</span>
        </label>
        <input
          id="transient-upload"
          className="sr-only"
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => onFile(event.target.files?.[0] ?? null)}
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            className="rounded-none border-[#355b3c]/45 bg-white text-[#244e32] hover:bg-[#edf6ed] hover:text-[#244e32]"
            onClick={onAudit}
            disabled={busy || !file}
          >
            {busy ? <LoaderCircle className="size-4 animate-spin" /> : <FileSearch className="size-4" />}
            Check transient record
          </Button>
          <span className="text-xs leading-5 text-black/55">Processed locally; not saved as a GroundLoop run.</span>
        </div>
        {audit && (
          <div className="mt-5 border-t border-[#355b3c]/25 pt-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <TransientMetric label="OLS decay exponent" value={audit.analysis.decay_exponent.toFixed(3)} />
              <TransientMetric label="Log–log fit R²" value={audit.analysis.log_log_r2.toFixed(3)} />
              <TransientMetric label="Validated rows" value={String(audit.analysis.row_count)} />
            </div>
            <p className="mt-4 text-xs leading-5 text-black/65">
              Fit: {audit.analysis.fit_method.replaceAll("_", " ")} · {audit.analysis.fit_window_s[0]}–{audit.analysis.fit_window_s[1]} s · {audit.analysis.fit_point_count} points.
            </p>
            <p className="mt-2 text-xs leading-5 text-black/55">{audit.scope}</p>
            {audit.analysis.warnings.length > 0 && (
              <p className="mt-3 border-l-2 border-[#c8502a] bg-[#fff8f5] px-3 py-2 font-mono text-[11px] text-[#8a301b]">
                {audit.analysis.warnings.join(" · ")}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function TransientMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-black/50">{label}</p>
      <p className="mt-1 text-lg font-medium tracking-[-0.03em] text-[#244e32]">{value}</p>
    </div>
  );
}

function TracePreview() {
  return (
    <figure className="self-stretch rounded-[1.35rem] border border-[#17324d]/15 bg-white p-4 shadow-[0_14px_38px_rgba(23,50,77,0.05)] sm:p-5">
      <div className="flex items-center justify-between">
        <p className="eyebrow text-[#17324d]">Included resistance demo</p>
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#17324d]/55">
          two-wire · 8 points
        </span>
      </div>
      <div className="mt-5 min-w-0 rounded-xl border border-[#17324d]/20 bg-[#f8fafb] px-3 pb-3 pt-4" aria-label="Included two-wire resistance trace">
        <ResponsiveContainer width="100%" height={164} minWidth={0} minHeight={164}>
          <AreaChart data={resistanceDemoTrace} margin={{ top: 6, right: 8, bottom: 0, left: -22 }}>
            <defs>
              <linearGradient id="demoResistanceFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#355b3c" stopOpacity={0.28} />
                <stop offset="100%" stopColor="#355b3c" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="temperature_c"
              tickLine={false}
              axisLine={{ stroke: "#17324d", strokeOpacity: 0.3 }}
              tick={{ fill: "#17324d", fontSize: 10 }}
              tickFormatter={(value) => `${value}°`}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={34}
              tick={{ fill: "#17324d", fontSize: 10 }}
              domain={[60, 125]}
            />
            <Tooltip
              cursor={{ stroke: "#17324d", strokeDasharray: "3 3" }}
              contentStyle={{ borderRadius: 12, border: "1px solid rgba(23,50,77,.3)", fontSize: 11 }}
              formatter={(value) => [`${Number(value).toFixed(1)} Ω`, "Two-wire resistance"]}
              labelFormatter={(value) => `${value} °C`}
            />
            <Area
              type="monotone"
              dataKey="two_wire_resistance_ohm"
              stroke="#355b3c"
              strokeWidth={2.2}
              fill="url(#demoResistanceFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
        <div className="mt-2 grid gap-2 border-t border-[#17324d]/20 pt-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#355b3c]">Observed</p>
            <p className="mt-1 text-xs leading-5 text-black/70">Resistance decreases across the temperature sweep.</p>
          </div>
          <span className="border border-[#c8502a]/45 bg-[#fff8f5] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-[#a13d25]">
            Not mechanism proof
          </span>
        </div>
      </div>
      <div className="mt-3 flex justify-between border-t border-[#17324d]/40 pt-3 font-mono text-[10px] uppercase tracking-[0.08em] text-[#17324d]/65">
        <span>Observed: resistance falls</span>
        <span>Next: four-wire control</span>
      </div>
      <figcaption className="mt-3 max-w-sm text-xs leading-5 text-black/55">
        The full demo asks whether this two-wire trace proves a bulk conductivity transition. GroundLoop says what would need to change that conclusion.
      </figcaption>
    </figure>
  );
}

function SetupScreen({
  detail,
  question,
  methods,
  setMethods,
  datasetFile,
  setDatasetFile,
  busy,
  ready,
  onSearch,
  onSaveMethods,
  onUpload,
  onDemoData,
  onPrepare,
  sourceReviewHandoff,
  sourceReviewCopied,
  sourceReviewStarted,
  onCopySourceReview,
}: {
  detail: Detail;
  question: string;
  methods: string;
  setMethods: (value: string) => void;
  datasetFile: File | null;
  setDatasetFile: (value: File | null) => void;
  busy: boolean;
  ready: boolean;
  onSearch: () => void;
  onSaveMethods: () => void;
  onUpload: () => void;
  onDemoData: () => void;
  onPrepare: () => void;
  sourceReviewHandoff: string;
  sourceReviewCopied: boolean;
  sourceReviewStarted: boolean;
  onCopySourceReview: () => void;
}) {
  const draft = detail.draft;
  const sources = draft?.sources ?? [];
  const hasSources = sources.length > 0;
  const relevanceById = new Map(
    draft?.source_relevance?.map((item) => [item.source_id, item]),
  );
  const sourcesByRelevance = [...sources].sort(
    (left, right) => {
      const rank = { direct: 0, contextual: 1, limited: 2 } as const;
      return (
        rank[relevanceById.get(left.id)?.verdict ?? "limited"] -
        rank[relevanceById.get(right.id)?.verdict ?? "limited"]
      );
    },
  );
  const indexedAbstractCount = sources.filter(
    (source) => source.retrieval_provider !== "arxiv",
  ).length;
  const preprintCount = sources.filter(
    (source) => source.retrieval_provider === "arxiv",
  ).length;
  const directSources = sourcesByRelevance.filter(
    (source) => relevanceById.get(source.id)?.verdict === "direct",
  );
  const contextSources = sourcesByRelevance.filter(
    (source) => relevanceById.get(source.id)?.verdict !== "direct",
  );
  const primarySources = directSources.length ? directSources : sourcesByRelevance;
  const fixtureMode = detail.run.fixture === "four_wire_contact_control";
  const retrievalReview = draft?.retrieval_review;
  const sourceReviewRequired = retrievalReview?.status === "required";
  const reviewedDirectCount = retrievalReview?.direct_source_ids.length ?? 0;
  const adjudicationBySourceId = new Map(
    retrievalReview?.adjudications.map((item) => [item.source_id, item]),
  );
  const reviewedVerdictCount = (verdict: SourceAdjudication["verdict"]) =>
    retrievalReview?.adjudications.filter((item) => item.verdict === verdict)
      .length ?? 0;
  return (
    <div>
      <div className="max-w-3xl">
        <p className="eyebrow">Step 1 · research setup</p>
        <h1 className="mt-3 text-4xl font-medium tracking-[-0.05em] sm:text-5xl">
          Set up the included measurement check.
        </h1>
        <p className="mt-4 text-base leading-7 text-black/65">
          GroundLoop keeps the research claim, observed record, and proposed
          control separate. This executable path uses a two-wire
          resistance-temperature sweep.
        </p>
      </div>
      {!hasSources && (
        <div className="mt-8 max-w-2xl border border-black/15 bg-white p-5">
          <p className="text-sm font-medium">
            This run has no retrieved references yet.
          </p>
          <p className="mt-2 text-sm leading-6 text-black/60">
            Enter a question above, then start automatic reference discovery.
          </p>
          <Button
            className="mt-4 rounded-none bg-[#171717]"
            onClick={onSearch}
            disabled={busy || question.trim().length < 10}
          >
            <FileSearch className="size-4" /> Find references automatically
          </Button>
        </div>
      )}
      {hasSources && (
        <>
          <AnalysisMap
            claim={question}
            sources={sources}
            dataReady={Boolean(draft?.dataset_ready)}
            comparisonLabel={
              ready ? "Ready to lock this analysis." : "Comparison not ready yet."
            }
            comparisonDetail={
              ready
                ? "The local review will inspect this exact version of the sources, method, and data."
                : "Add the measurement context and CSV before starting the review."
            }
            fixtureMode={fixtureMode}
          />

          <section className="mt-8 grid gap-px border border-black/15 bg-black/10 lg:grid-cols-2">
            <div className="bg-white p-5 sm:p-6">
              <p className="eyebrow text-[#17324d]">Measurement context</p>
              <label
                htmlFor="methods"
                className="mt-3 block text-sm font-medium"
              >
                How was this sweep measured?
              </label>
              <textarea
                id="methods"
                value={methods}
                onChange={(event) => setMethods(event.target.value)}
                placeholder="Describe the sample, measurement mode, variables held fixed, and any relevant conditions."
                className="mt-3 min-h-40 w-full resize-y border border-black/20 bg-[#fbfbfa] p-3 text-sm leading-6 outline-none focus:border-black"
              />
              <Button
                variant="outline"
                className="mt-3 rounded-none"
                onClick={onSaveMethods}
                disabled={busy || methods.trim().length < 20}
              >
                Save measurement context
              </Button>
            </div>
            <div className="bg-[#fbfbfa] p-5 sm:p-6">
              <p className="eyebrow text-[#355b3c]">Measurement data</p>
              <p className="mt-3 text-sm font-medium">
                Add your resistance–temperature data
              </p>
              <p className="mt-2 text-sm leading-6 text-black/60">
                Upload the two-column CSV from your temperature sweep. It stays
                local and is never sent to the literature index.
              </p>
              <p className="mt-2 font-mono text-[11px] leading-5 text-black/55">
                Current template: temperature_c, two_wire_resistance_ohm
              </p>
              <label
                htmlFor="dataset"
                className="mt-5 flex cursor-pointer items-center justify-between border border-dashed border-black/30 bg-white p-3 text-sm"
              >
                <span className="flex items-center gap-2">
                  <Upload className="size-4" />
                  {datasetFile ? datasetFile.name : "Choose measurement CSV"}
                </span>
                <span className="text-xs text-black/55">CSV only</span>
              </label>
              <input
                id="dataset"
                className="sr-only"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) =>
                  setDatasetFile(event.target.files?.[0] ?? null)
                }
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  className="rounded-none"
                  onClick={onUpload}
                  disabled={busy || !datasetFile}
                >
                  Import measurement CSV
                </Button>
                <Button
                  variant="outline"
                  className="rounded-none"
                  onClick={onDemoData}
                  disabled={busy}
                >
                  Add labelled demo data
                </Button>
                <p className="basis-full text-xs leading-5 text-black/55">
                  Adds the demo CSV locally and keeps your saved measurement context.
                </p>
              </div>
              {draft?.dataset_ready && (
                <p className="mt-4 flex items-center gap-2 text-sm text-[#215f47]">
                  <Check className="size-4" /> Measurement data added locally.
                </p>
              )}
            </div>
          </section>
          <section className="mt-8 border border-black/15 bg-white p-5 sm:p-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="eyebrow">{fixtureMode ? "Measurement context" : "Retrieved candidates"}</p>
                <h2 className="mt-2 text-xl font-medium tracking-[-0.03em]">
                  {fixtureMode ? "What constrains this measurement claim?" : "What should Codex inspect before this is evidence?"}
                </h2>
                <p className="mt-2 text-sm leading-6 text-black/60">
                  {fixtureMode
                    ? "These sources establish the two-wire versus four-wire measurement boundary. They do not support the sample's proposed bulk mechanism."
                    : "OpenAlex indexed abstracts and arXiv preprint abstracts are candidates only. Codex must read each supplied excerpt and decide which sources may define the evidence boundary."}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                {fixtureMode ? (
                  <span className="border border-[#17324d]/40 bg-[#eef4f9] px-2 py-1 text-[#17324d]">
                    {sources.length} measurement principle{sources.length === 1 ? "" : "s"}
                  </span>
                ) : (
                  <>
                    <span className="border border-[#17324d]/40 bg-[#eef4f9] px-2 py-1 text-[#17324d]">
                      {indexedAbstractCount} indexed abstract{indexedAbstractCount === 1 ? "" : "s"}
                    </span>
                    <span className="border border-[#805720] bg-[#fff7df] px-2 py-1 text-[#805720]">
                      {preprintCount} preprint{preprintCount === 1 ? "" : "s"} · review status shown
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="mt-4">
              {primarySources.map((source) => (
                <SourceSummaryRow
                  key={source.id}
                  source={source}
                  relevance={relevanceById.get(source.id)}
                  fixtureMode={fixtureMode}
                />
              ))}
            </div>
            <details className="mt-4 border-t border-black/10 pt-4">
              <summary className="cursor-pointer text-sm font-medium text-black/70">
                Inspect retrieved reference details
              </summary>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {sourcesByRelevance.map((source) => (
                  <SourceCard
                    key={source.id}
                    source={source}
                    relevance={relevanceById.get(source.id)}
                  />
                ))}
              </div>
            </details>
            {directSources.length > 0 && contextSources.length > 0 && (
              <p className="mt-4 text-xs leading-5 text-black/55">
                Suggested reading order is lexical only. All {sources.length} candidates
                must receive a semantic review; only a reviewed direct source can
                define the evidence boundary.
              </p>
            )}
          </section>
          {retrievalReview && (
            <section
              id="source-boundary-checkpoint"
              className="mt-8 border border-[#17324d]/30 bg-[#f3f8fb] p-5 sm:p-6"
            >
              <div className="flex flex-wrap items-start justify-between gap-6">
                <div className="max-w-2xl">
                <p className="eyebrow text-[#17324d]">Source boundary checkpoint</p>
                <h2 className="mt-2 text-xl font-medium tracking-[-0.03em]">
                  {sourceReviewRequired
                    ? "Ask Codex to separate evidence from background."
                    : `Source review saved — ${reviewedDirectCount} decision source${reviewedDirectCount === 1 ? "" : "s"} selected.`}
                </h2>
                <p className="mt-2 text-sm leading-6 text-black/65">
                  {sourceReviewRequired
                    ? "This uses your local Codex MCP session, not a model API key or per-run API bill. Every candidate must be classified before the packet can be locked."
                    : "Next: freeze the reviewed sources, measurement context, and CSV together. The freeze is an explicit local action and will appear in this run's decision history."}
                </p>
                </div>
                {sourceReviewRequired ? (
                  <div className="shrink-0">
                  <Button
                    className="w-full rounded-none bg-[#17324d] text-white hover:bg-[#17324d]/90 sm:w-auto"
                    onClick={onCopySourceReview}
                    disabled={busy}
                  >
                    {sourceReviewCopied ? <Check className="size-4" /> : <Clipboard className="size-4" />}
                    {sourceReviewCopied ? "Source review brief copied" : "Copy Codex source review"}
                  </Button>
                  <p className="mt-2 max-w-xs text-xs leading-5 text-black/55">
                    {sourceReviewStarted
                      ? "Brief copied. Paste it into Codex; no source adjudication is saved yet."
                      : "One deliberate handoff; the browser never calls Codex on its own."}
                  </p>
                  <details className="mt-3 max-w-md text-xs leading-5 text-black/55">
                    <summary className="cursor-pointer text-black/70">Show the exact Codex brief</summary>
                    <p className="mt-2 font-mono">{sourceReviewHandoff}</p>
                  </details>
                  </div>
                ) : null}
              </div>
              {!sourceReviewRequired && (
                <div className="mt-6 border-t border-[#17324d]/15 pt-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="eyebrow text-[#215f47]">Codex review result</p>
                      <p className="mt-1 text-sm leading-6 text-black/65">
                        “Direct” means the supplied excerpt addresses this claim, its confound, or the deciding control. It does not mean peer-reviewed consensus.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.06em]">
                      <span className="border border-[#215f47]/35 bg-[#edf8f1] px-2 py-1 text-[#215f47]">
                        {reviewedVerdictCount("direct")} direct
                      </span>
                      <span className="border border-[#805720]/35 bg-[#fff7df] px-2 py-1 text-[#805720]">
                        {reviewedVerdictCount("contextual")} contextual
                      </span>
                      <span className="border border-[#a13d25]/30 bg-[#fff0eb] px-2 py-1 text-[#a13d25]">
                        {reviewedVerdictCount("reject")} rejected
                      </span>
                    </div>
                  </div>
                  <div className="mt-4 grid gap-3">
                    {sources.map((source) => {
                      const adjudication = adjudicationBySourceId.get(source.id);
                      if (!adjudication) return null;
                      const tone =
                        adjudication.verdict === "direct"
                          ? "border-[#215f47]/35 bg-white"
                          : adjudication.verdict === "contextual"
                            ? "border-[#805720]/35 bg-[#fffdf5]"
                            : "border-[#a13d25]/30 bg-[#fff9f7]";
                      return (
                        <article key={source.id} className={`border p-4 ${tone}`}>
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-medium">{source.title}</p>
                              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.06em] text-black/55">
                                {sourceStatusLabel(source)}
                              </p>
                            </div>
                            <span className="border border-current/25 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-[#17324d]">
                              {adjudication.verdict}
                            </span>
                          </div>
                          <p className="mt-3 text-xs leading-5 text-black/65">
                            {adjudication.rationale}
                          </p>
                          {source.publication_status === "preprint" && (
                            <p className="mt-3 border-l-2 border-[#805720] bg-[#fff7df] px-3 py-2 text-xs leading-5 text-[#805720]">
                              Preprint: this can be directly relevant, but it is not peer-reviewed consensus.
                            </p>
                          )}
                        </article>
                      );
                    })}
                  </div>
                </div>
              )}
            </section>
          )}
          <section className="mt-8 border border-black bg-[#171717] p-5 text-white sm:flex sm:items-center sm:justify-between sm:p-7">
            <div>
              <p className="eyebrow !text-white/60">Step 2 · freeze the reviewed boundary</p>
              <p className="mt-2 text-lg font-medium">
                Freeze this reviewed evidence packet.
              </p>
              <p className="mt-2 text-sm leading-6 text-white/65">
                {sourceReviewRequired
                  ? "First copy the Codex source-review brief. Candidate retrieval is not enough to define an evidence boundary."
                  : ready
                  ? "This is the explicit handoff from editable setup to an immutable decision record. After freezing, the next prompt asks Codex to inspect the selected sources and analyze this exact CSV."
                  : "Add a reference, measurement context, and local CSV first."}
              </p>
            </div>
            <Button
              className="mt-5 rounded-none bg-white text-black hover:bg-white/90 sm:mt-0"
              onClick={onPrepare}
              disabled={busy || !ready}
            >
              Freeze reviewed packet <ArrowRight className="size-4" />
            </Button>
          </section>
        </>
      )}
    </div>
  );
}

function SourceCard({
  source,
  sha256,
  relevance,
  adjudication,
}: {
  source: Source;
  sha256?: string;
  relevance?: SourceRelevance;
  adjudication?: SourceAdjudication;
}) {
  return (
    <article className="border border-black/15 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium leading-5">{source.title}</p>
          <p className="mt-1 text-xs leading-5 text-black/60">
            {source.authors.join(", ")} · {source.year}
          </p>
        </div>
        <ShieldCheck
          className="size-4 shrink-0 text-black/55"
          aria-label="Untrusted evidence"
        />
      </div>
      <p className="mt-3 line-clamp-5 text-sm leading-6 text-black/70">
        {source.untrusted_content}
      </p>
      <div className="mt-4 border-t border-black/10 pt-3">
        <a
          href={source.url_or_doi}
          target="_blank"
          rel="noreferrer"
          className="inline-flex max-w-full items-center gap-1 break-all text-xs text-black/70 underline underline-offset-4"
        >
          {source.url_or_doi}
          <ExternalLink className="size-3 shrink-0" />
        </a>
        <p className="mt-2 text-xs text-black/50">
          {source.locator.section ??
            (source.locator.page
              ? `Page ${source.locator.page}`
              : "Provided excerpt")}
        </p>
        <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.06em] text-[#17324d]/75">
          {sourceStatusLabel(source)}
        </p>
        {sha256 && (
          <p className="mt-2 break-all font-mono text-[11px] leading-4 text-black/50">
            SHA-256 {sha256}
          </p>
        )}
        {relevance && (
          <>
            <p
              className={`mt-2 font-mono text-[11px] uppercase ${
                relevance.verdict === "direct"
                  ? "text-[#215f47]"
                  : relevance.verdict === "contextual"
                    ? "text-[#805720]"
                    : "text-[#a13d25]"
              }`}
            >
              {relevanceLabel(relevance.verdict)}
            </p>
            <p className="mt-1 text-xs leading-5 text-black/55">
              Why it surfaced: {relevance.reason}
            </p>
          </>
        )}
        {adjudication && (
          <div className="mt-3 border-l-2 border-[#215f47] bg-[#edf8f1] px-3 py-2">
            <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#215f47]">
              Selected after source review
            </p>
            <p className="mt-1 text-xs leading-5 text-black/70">
              {adjudication.rationale}
            </p>
          </div>
        )}
        {(source.publication_status || source.locator.section?.includes("abstract")) && (
          <p className="mt-3 text-xs leading-5 text-[#805720]">
            {sourceStatusNote(source)}
          </p>
        )}
        <p className="mt-2 font-mono text-[11px] text-[#a13d25]">
          UNTRUSTED EVIDENCE
        </p>
      </div>
    </article>
  );
}

function ReviewScreen({
  detail,
  handoff,
  copied,
  handoffStarted,
  serviceStatus,
  busy,
  onCopy,
}: {
  detail: Detail;
  handoff: string;
  copied: boolean;
  handoffStarted: boolean;
  serviceStatus: ServiceStatus;
  busy: boolean;
  onCopy: () => void;
}) {
  const state = detail.run.state as ReviewState;
  const isReady = state === "PACKET_READY";
  const savedStep = stateLabel[state].toLowerCase();
  const nextCodexAction: Record<Exclude<ReviewState, "PACKET_READY">, string> = {
    SOURCES_INSPECTED: "Ask Codex to analyse the frozen measurement record.",
    DATA_ANALYZED: "Ask Codex to validate the four-state findings.",
    FINDINGS_VALIDATED: "Ask Codex to propose one discriminating ControlFirst experiment.",
    CONTROL_VALIDATED: "Ask Codex to export the report for this run.",
  };
  const nextSavedAction = state === "PACKET_READY" ? null : nextCodexAction[state];
  const sourceHashByArtifact = new Map(
    detail.packet?.evidence_refs
      .filter((item) => item.kind === "source")
      .map((item) => [item.artifact_id, item.sha256]),
  );
  const sourceReviewById = new Map(
    detail.packet?.source_review?.adjudications.map((item) => [item.source_id, item]),
  );
  return (
    <div>
      <div className="max-w-3xl">
        <p className="eyebrow">
          Step 3 · {stateLabel[state]}
        </p>
        <h1 className="mt-3 text-4xl font-medium tracking-[-0.05em] sm:text-5xl">
          {isReady
            ? "The evidence is locked. Send it to Codex."
            : "The decision record is taking shape."}
        </h1>
        <p className="mt-4 text-base leading-7 text-black/65">
          {isReady
            ? "Copy one brief, paste it into Codex, and keep this page open. Codex writes the validated decision back into this exact evidence record."
            : `Codex saved ${savedStep}. GroundLoop is waiting for the next recorded MCP step; it is not running a hidden analysis in the browser.`}
        </p>
      </div>
      <AnalysisMap
        claim={detail.packet?.claim.claim ?? "Frozen claim"}
        sources={detail.packet?.sources ?? []}
        dataReady={Boolean(detail.packet?.dataset)}
        dataset={detail.packet?.dataset}
        comparisonLabel={
          isReady ? "Next action: send packet to Codex." : `Saved: ${stateLabel[state]}.`
        }
        comparisonDetail={
          isReady
            ? "Codex reviews this frozen record and saves one evidence-linked report here."
            : nextSavedAction ?? "GroundLoop will keep observed data separate from inferred mechanism claims."
        }
        sourceStage="frozen"
        claimLabel="1 · Claim under review"
        recordLabel="2 · Frozen measurement"
      />
      <div className="mt-8 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="border border-black bg-[#171717] p-5 text-white sm:p-7">
          <p className="eyebrow !text-white/60">Continue with Codex</p>
          <h2 className="mt-3 font-serif text-2xl tracking-[-0.03em]">
            {isReady
              ? "Copy the frozen packet. Codex does the review."
              : `Codex saved ${savedStep}. Choose the next review step.`}
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-white/75">
            {isReady
              ? "You do not need to translate findings or fill out a verdict. GroundLoop supplies the frozen record; Codex submits the evidence-linked decision; this page changes to the report automatically."
              : "The evidence record remains immutable. GroundLoop is waiting for you to ask Codex to run the next MCP operation; the browser does not perform that work itself."}
          </p>
          {isReady ? (
            <Button
              className="mt-6 w-full rounded-none bg-white text-black hover:bg-white/90"
              onClick={onCopy}
              disabled={busy}
            >
              {copied ? (
                <Check className="size-4" />
              ) : (
                <Clipboard className="size-4" />
              )}
              {copied ? "Brief copied — paste into Codex" : "Copy brief to start review"}
            </Button>
          ) : (
            <div className="mt-6 flex items-center gap-2 border border-white/20 px-4 py-3 text-sm text-white/80">
              <ArrowRight className="size-4" />
              Next Codex action: {nextSavedAction}
            </div>
          )}
          <p className="mt-4 text-xs leading-5 text-white/60">
            {isReady
              ? handoffStarted
                ? "Brief copied. Paste it into Codex; no MCP step has been saved yet."
                : "Paste the brief into any Codex conversation. You can also paste the visible brief manually; GroundLoop will still detect the saved result."
              : "The last completed MCP step is saved. Keep this page open; it will update only after Codex saves the next step."}
          </p>
          <details className="mt-4 border-t border-white/15 pt-3 text-xs leading-5 text-white/55">
            <summary className="cursor-pointer text-white/75">Show the exact Codex brief</summary>
            <p className="mt-3 font-mono">{handoff}</p>
          </details>
        </section>
        <HandoffStatus
          runId={detail.run.run_id}
          state={state}
          handoffStarted={handoffStarted}
          serviceStatus={serviceStatus}
          timeline={detail.timeline}
        />
      </div>
      <details className="mt-8 border border-black/15 bg-white">
        <summary className="cursor-pointer px-5 py-4 text-sm font-medium text-black/70 sm:px-7">
          Inspect the frozen sources and locators
        </summary>
        <div className="grid gap-3 border-t border-black/15 p-5 lg:grid-cols-3 sm:p-7">
          {detail.packet?.sources.map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              sha256={sourceHashByArtifact.get(source.id)}
              adjudication={sourceReviewById.get(source.id)}
            />
          ))}
        </div>
      </details>
    </div>
  );
}

function ReportScreen({
  report,
  packet,
  sourceHashByArtifact,
  timeline,
}: {
  report: Report;
  packet?: Detail["packet"];
  sourceHashByArtifact: Map<string, string | undefined>;
  timeline: AuditEvent[];
}) {
  const [planCopied, setPlanCopied] = useState(false);
  const grouped = ["Established", "Observed", "Inferred", "Unresolved"].map(
    (status) => ({
      status: status as Finding["status"],
      finding: report.findings.find((item) => item.status === status),
    }),
  );
  const sourceReviewById = new Map(
    report.source_review?.adjudications.map((item) => [item.source_id, item]),
  );
  const observed = grouped.find((item) => item.status === "Observed")?.finding;
  const inferred = grouped.find((item) => item.status === "Inferred")?.finding;
  const unresolved = grouped.find(
    (item) => item.status === "Unresolved",
  )?.finding;
  const decisionFindings: Array<{
    status: Finding["status"];
    finding?: Finding;
  }> = [
    {
      status: "Established",
      finding: grouped.find((item) => item.status === "Established")?.finding,
    },
    { status: "Inferred", finding: inferred },
    { status: "Unresolved", finding: unresolved },
  ];
  const copyControlPlan = async () => {
    const outcomes = report.control.outcomes.map((outcome, index) => {
      const condition =
        outcome.if ?? outcome.if_ ?? "Outcome condition was not recorded.";
      const label =
        index === 0
          ? "If the primary control supports the interpretation"
          : "If the primary control challenges the interpretation";
      return `${label}\n- Observe: ${condition}\n- Interpret: ${outcome.then}`;
    });
    const plan = [
      "GroundLoop ControlFirst · next control plan",
      `Claim under test: ${report.claim}`,
      "",
      "Run",
      report.control.experiment,
      "",
      "Before you run it",
      ...report.control.preconditions.map((item) => `- ${item}`),
      "",
      "Decide from the result",
      ...outcomes,
    ].join("\n");

    try {
      await navigator.clipboard.writeText(plan);
      setPlanCopied(true);
      window.setTimeout(() => setPlanCopied(false), 2200);
    } catch {
      setPlanCopied(false);
    }
  };
  return (
    <div>
      <div className="max-w-3xl">
        <p className="eyebrow">Step 4 · validated report</p>
        <h1 className="mt-3 text-4xl font-medium tracking-[-0.05em] sm:text-5xl">
          The trace changed. The mechanism is not proven.
        </h1>
        <p className="mt-4 text-base leading-7 text-black/65">
          GroundLoop turns one plausible curve into a clear research decision:
          preserve what changed, name what remains mixed in, and run the one
          control that can separate them.
        </p>
        {report.dataset_provenance !== "USER_MEASUREMENT" && (
          <p className="mt-4 inline-flex border border-[#805720]/40 bg-[#fff7df] px-3 py-2 text-xs font-medium text-[#805720]">
            {report.dataset_provenance === "FIXTURE_DEMO"
              ? "Fixture demonstration data — not a research result"
              : "Labelled demonstration data — not a research result"}
          </p>
        )}
      </div>
      <section
        className="mt-7 grid gap-4 border-y border-[#17324d]/20 py-4 sm:grid-cols-2 sm:gap-0"
        aria-label="Report framing"
      >
        <div className="border-l-2 border-[#17324d] px-4 sm:px-5">
          <p className="eyebrow text-[#17324d]">Claim under test</p>
          <p className="mt-2 text-sm font-medium leading-6 text-[#17324d]">
            {report.claim}
          </p>
        </div>
        <div className="border-l-2 border-[#355b3c] px-4 sm:border-l sm:border-black/10 sm:px-5">
          <p className="eyebrow text-[#355b3c]">Frozen observation</p>
          <p className="mt-2 text-sm font-medium leading-6 text-[#355b3c]">
            {report.dataset.row_count} rows · {report.dataset.temperature_range_c[0]}–
            {report.dataset.temperature_range_c[1]} °C · two-wire total resistance
          </p>
        </div>
      </section>
      <section
        className="mt-8 rounded-[1.75rem] border border-[#17324d]/20 bg-[#e1e9e5] p-3 shadow-[0_20px_54px_rgba(23,50,77,0.09)]"
        aria-label="ControlFirst decision sequence"
      >
        <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1.12fr]">
          <div className="decision-card rounded-[1.2rem] bg-[#eff7f2] p-5 sm:p-7">
            <p className="eyebrow text-[#255330]">01 · We saw</p>
            <p className="mt-3 text-4xl font-semibold tracking-[-0.06em] text-[#17324d] sm:text-5xl">
              {report.dataset.percent_change.toFixed(1)}%
            </p>
            <p className="mt-2 text-sm font-medium leading-6 text-[#17324d]">
              two-wire resistance across the frozen temperature sweep
            </p>
            <p className="mt-4 border-t border-[#355b3c]/25 pt-3 text-xs leading-5 text-[#244e32]">
              The pattern is a real observation. It is not discarded.
            </p>
          </div>
          <div className="flex size-12 self-center justify-self-center items-center justify-center rounded-full bg-[#17324d] text-white shadow-[0_8px_20px_rgba(23,50,77,0.22)]">
            <ArrowRight className="size-5 rotate-90 lg:rotate-0" aria-hidden="true" />
          </div>
          <div className="decision-card rounded-[1.2rem] bg-[#fff0eb] p-5 sm:p-7">
            <p className="eyebrow text-[#a13d25]">02 · We cannot yet claim</p>
            <p className="brand-serif mt-3 text-3xl leading-[1.04] tracking-[-0.05em] text-[#8a301b] sm:text-4xl">
              A bulk conductivity transition.
            </p>
            <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.07em] text-[#8a301b]">
              Two-wire total = sample + contact + lead
            </p>
            <p className="mt-4 border-t border-[#c8502a]/25 pt-3 text-xs leading-5 text-[#8a301b]">
              The trace does not yet separate the sample from the measurement path.
            </p>
          </div>
          <div className="flex size-12 self-center justify-self-center items-center justify-center rounded-full bg-[#17324d] text-white shadow-[0_8px_20px_rgba(23,50,77,0.22)]">
            <ArrowRight className="size-5 rotate-90 lg:rotate-0" aria-hidden="true" />
          </div>
          <div className="decision-card rounded-[1.2rem] bg-white p-5 sm:p-7">
            <p className="eyebrow text-[#17324d]">03 · One test can decide</p>
            <p className="brand-serif mt-3 text-3xl leading-[1.04] tracking-[-0.05em] text-[#17324d] sm:text-4xl">
              Repeat the sweep in four-wire mode.
            </p>
            <p className="mt-3 text-sm leading-6 text-black/70">
              Hold the sample, current, mounting, and temperature program fixed.
            </p>
            <p className="mt-4 border-t border-[#17324d]/15 pt-3 text-xs font-medium leading-5 text-[#17324d]">
              This is the smallest next measurement that changes the decision.
            </p>
          </div>
        </div>
      </section>
      <section className="mt-8 rounded-[1.75rem] border border-[#a13d25]/65 bg-[#fff0eb] p-5 shadow-[0_18px_48px_rgba(200,80,42,0.10)] sm:p-7">
          <div className="grid gap-7 lg:grid-cols-[0.92fr_1.08fr] lg:items-start">
            <div>
              <p className="eyebrow text-[#a13d25]">Decision brief</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-[#8a301b]">
                {report.verdict.label.replaceAll("_", " ")}
              </h2>
              <p className="mt-3 text-sm leading-7 text-black/75">
                {report.verdict.reason}
              </p>
              <p className="mt-4 font-mono text-[11px] text-[#8a301b]">
                BLOCKED BY · TWO-WIRE CONTACT / LEAD CONTRIBUTION NOT SEPARATED
              </p>
            </div>
            <div className="border-l-0 border-[#de5632]/45 pl-0 lg:border-l-2 lg:pl-6">
              <p className="eyebrow text-[#a13d25]">
                Do next · priority {report.control.priority}
              </p>
              <h3 className="mt-2 text-xl font-medium tracking-[-0.04em]">
                {report.control.experiment}
              </h3>
              <p className="mt-3 text-sm leading-6 text-black/70">
                This is the smallest measurement that separates the current
                interpretation from the unresolved confound: {report.control.confound}
              </p>
              <Button
                type="button"
                variant="outline"
                onClick={() => void copyControlPlan()}
                className="control-action mt-5 border-[#a13d25] bg-transparent px-4 text-[#8a301b] hover:bg-[#fff8f5] hover:text-[#8a301b]"
              >
                {planCopied ? <Check className="size-4" /> : <Clipboard className="size-4" />}
                {planCopied ? "Control plan copied" : "Copy ControlFirst plan"}
              </Button>
            </div>
          </div>
          <div className="mt-7 grid gap-px overflow-hidden rounded-[1.2rem] border border-[#de5632]/35 bg-[#de5632]/20 md:grid-cols-2">
            {report.control.outcomes.map((outcome, index) => {
              const condition =
                outcome.if ??
                outcome.if_ ??
                "Outcome condition was not recorded.";
              const outcomeIsSupport = index === 0;
              return (
                <div
                  key={`${condition}-${outcome.then}-${index}`}
                  className={`h-full p-4 sm:p-5 ${
                    outcomeIsSupport ? "bg-[#f2f8f2]" : "bg-[#fff8f5]"
                  }`}
                >
                  <p className={`text-xs font-medium uppercase tracking-[0.1em] ${outcomeIsSupport ? "text-[#255330]" : "text-[#a13d25]"}`}>
                    {outcomeIsSupport
                      ? "If the trend persists"
                      : "If the trend weakens"}
                  </p>
                  <p className="mt-2 text-sm font-medium leading-6">{condition}</p>
                  <p className="mt-4 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.1em] text-black/55">
                    <ArrowRight className="size-3.5" aria-hidden="true" /> Interpretation
                  </p>
                  <p className="mt-2 text-sm leading-6 text-black/75">
                    {outcome.then}
                  </p>
                </div>
              );
            })}
          </div>
      </section>
      <section className="mt-8 grid gap-px border border-black/15 bg-black/10 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="bg-white p-5 sm:p-7">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="eyebrow">What the measurement shows</p>
              <span className="border border-[#355b3c]/40 bg-[#f2f8f2] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-[#255330]">
                Observed only · two-wire total resistance
              </span>
            </div>
            <div className="mt-4 h-64 min-w-0 w-full">
              <ResponsiveContainer width="100%" height={256} minWidth={0} minHeight={256}>
                <AreaChart
                  data={report.dataset.rows}
                  margin={{ top: 8, right: 10, bottom: 0, left: -18 }}
                >
                  <defs>
                    <linearGradient
                      id="resistanceFill"
                      x1="0"
                      x2="0"
                      y1="0"
                      y2="1"
                    >
                      <stop offset="0%" stopColor="#17324D" stopOpacity={0.18} />
                      <stop offset="100%" stopColor="#17324D" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="temperature_c"
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                    tick={{ fontSize: 11, fill: "#555" }}
                    label={{ value: "Temperature (°C)", position: "insideBottom", offset: -2, fontSize: 11, fill: "#555" }}
                  />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                    tick={{ fontSize: 11, fill: "#555" }}
                    label={{ value: "Resistance (Ω)", angle: -90, position: "insideLeft", offset: 12, fontSize: 11, fill: "#555" }}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 0,
                      border: "1px solid #aaa",
                      fontSize: 12,
                    }}
                    formatter={(value) => [
                      `${Number(value).toFixed(1)} Ω`,
                      "Two-wire resistance",
                    ]}
                    labelFormatter={(value) => `${value} °C`}
                  />
                  <Area
                    type="monotone"
                    dataKey="two_wire_resistance_ohm"
                    stroke="#17324D"
                    strokeWidth={2}
                    fill="url(#resistanceFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-5 grid grid-cols-3 gap-px border border-black/15 bg-black/10 text-center">
              <Metric label="Rows" value={String(report.dataset.row_count)} />
              <Metric
                label="Δ resistance"
                value={`${report.dataset.change_ohm.toFixed(1)} Ω`}
              />
              <Metric
                label="Change"
                value={`${report.dataset.percent_change.toFixed(1)}%`}
              />
            </div>
            <p className="mt-5 text-sm leading-7 text-black/75">
              {observed?.statement ??
                `Rows 2–${report.dataset.row_count + 1} record the frozen measurement trace.`}
            </p>
            <div className="mt-5 border-l-2 border-[#c8502a] bg-[#fff8f5] px-4 py-3">
              <p className="eyebrow text-[#a13d25]">Interpretation boundary</p>
              <p className="mt-2 text-sm leading-6 text-black/75">
                This trace does not separate sample resistance from lead or
                contact contribution. Treat it as a two-wire total-resistance
                observation until the matched four-wire sweep is complete.
              </p>
            </div>
          </div>
          <div className="bg-[#fbfbfa] p-5 sm:p-7">
            <p className="eyebrow">Why the claim is blocked</p>
            <p className="mt-3 text-lg leading-8 tracking-[-0.02em]">
              {report.claim}
            </p>
            <div className="mt-6 space-y-4 border-t border-black/10 pt-5">
              {decisionFindings.map(({ status, finding }) => (
                <article key={status}>
                  <span className={`status ${statusClass(status)}`}>
                    {status}
                  </span>
                  <p className="mt-2 text-sm leading-6">
                    {finding?.statement ?? "No validated finding submitted."}
                  </p>
                </article>
              ))}
            </div>
          </div>
      </section>
      <details className="mt-8 border border-black/15 bg-white">
        <summary className="cursor-pointer list-none px-5 py-4 sm:px-7">
          <span className="eyebrow">Audit trail</span>
          <span className="mt-1 block text-sm text-black/65">
            Open frozen sources, evidence identifiers, and the full four-state ledger.
          </span>
        </summary>
        <div className="border-t border-black/15 px-5 py-6 sm:px-7">
          <div className="grid gap-3 lg:grid-cols-2">
            {report.sources.map((source) => (
              <SourceCard
                key={source.id}
                source={source}
                sha256={sourceHashByArtifact.get(source.id)}
                adjudication={sourceReviewById.get(source.id)}
              />
            ))}
          </div>
          <DecisionTimeline timeline={timeline} />
          <div className="mt-6 grid divide-y divide-black/10 border border-black/15 md:grid-cols-2 md:divide-x md:divide-y-0">
            {grouped.map(({ status, finding }) => (
              <article key={status} className="p-5 sm:p-6">
                <span className={`status ${statusClass(status)}`}>{status}</span>
                <p className="mt-3 break-all font-mono text-[11px] leading-5 text-black/55">
                  {finding?.evidence_ref_ids.join(" · ") ??
                    "No submitted finding"}
                </p>
                <p className="mt-4 text-sm leading-6">
                  {finding?.statement ?? "No validated finding submitted."}
                </p>
                {finding?.uncertainty && (
                  <p className="mt-3 text-sm leading-6 text-black/65">
                    Uncertainty: {finding.uncertainty}
                  </p>
                )}
              </article>
            ))}
          </div>
        </div>
      </details>
      {packet && (
        <p className="mt-6 text-xs leading-5 text-black/55">
          Frozen packet: {packet.evidence_refs.length} evidence references ·
          report run {report.run_id}
        </p>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white px-2 py-3">
      <p className="text-[11px] uppercase tracking-[0.1em] text-black/60">
        {label}
      </p>
      <p className="mt-1 text-sm font-medium tracking-[-0.03em]">{value}</p>
    </div>
  );
}
function statusClass(status: Finding["status"]) {
  return {
    Established: "status-established",
    Observed: "status-observed",
    Inferred: "status-inferred",
    Unresolved: "status-unresolved",
  }[status];
}

export default App;
