import { useCallback, useEffect, useMemo, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  ArrowRight,
  Check,
  Clipboard,
  Database,
  ExternalLink,
  FileText,
  FlaskConical,
  Layers3,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

type RunState =
  | 'DRAFT'
  | 'PACKET_READY'
  | 'SOURCES_INSPECTED'
  | 'DATA_ANALYZED'
  | 'FINDINGS_VALIDATED'
  | 'CONTROL_VALIDATED'
  | 'EXPORTED'

type Run = { run_id: string; state: RunState; fixture?: string; created_at: string }
type EvidenceRef = { id: string; kind: 'source' | 'data'; artifact_id: string; excerpt: string; sha256: string; locator: Record<string, unknown> }
type Source = { id: string; title: string; authors: string[]; year: number; url_or_doi: string; locator: { section?: string; page?: number }; untrusted_content: string }
type Finding = { id: string; statement: string; status: 'Established' | 'Observed' | 'Inferred' | 'Unresolved'; evidence_ref_ids: string[]; reasoning: string; uncertainty?: string; alternative_explanation?: string }
type Report = { run_id: string; claim: string; state: 'EXPORTED'; findings: Finding[]; control: { confound: string; experiment: string; preconditions: string[]; outcomes: { if: string; then: string }[]; priority: string; feasibility: string }; sources: Source[]; dataset: Dataset }
type Dataset = { row_count: number; temperature_range_c: [number, number]; first_resistance_ohm: number; last_resistance_ohm: number; change_ohm: number; percent_change: number; rows: { temperature_c: number; two_wire_resistance_ohm: number }[] }
type Detail = { run: Run; input_artifacts?: string[]; packet?: { claim: { claim: string }; sources: Source[]; dataset: Dataset; evidence_refs: EvidenceRef[] }; report?: Report }

const previewDataset: Dataset = {
  row_count: 8,
  temperature_range_c: [20, 90],
  first_resistance_ohm: 120,
  last_resistance_ohm: 65,
  change_ohm: -55,
  percent_change: -45.8,
  rows: [
    { temperature_c: 20, two_wire_resistance_ohm: 120 },
    { temperature_c: 30, two_wire_resistance_ohm: 117.5 },
    { temperature_c: 40, two_wire_resistance_ohm: 113.2 },
    { temperature_c: 50, two_wire_resistance_ohm: 107 },
    { temperature_c: 60, two_wire_resistance_ohm: 98.4 },
    { temperature_c: 70, two_wire_resistance_ohm: 88.8 },
    { temperature_c: 80, two_wire_resistance_ohm: 77.1 },
    { temperature_c: 90, two_wire_resistance_ohm: 65 },
  ],
}

const previewSources: Source[] = [
  { id: 'src-four-wire-principle', title: 'How to Measure Resistance Using Four-Wire Measurement', authors: ['Keysight Technologies'], year: 2026, url_or_doi: 'Keysight reference', locator: { section: 'Removing the effects of cable resistance' }, untrusted_content: 'Four-wire measurement sources current through one terminal pair and independently senses voltage through another, limiting lead and contact error.' },
  { id: 'src-contact-contribution', title: 'Using the DMM Series to Make Simple and Accurate Resistance Measurements', authors: ['Tektronix'], year: 2026, url_or_doi: 'Tektronix application note', locator: { section: 'Application-note summary' }, untrusted_content: 'Two-wire resistance measurement is convenient but can cause measurement error; four-wire sensing is presented as a way to avoid this error source.' },
]

const previewFindings: Finding[] = [
  { id: 'principle', status: 'Established', statement: 'Four-terminal sensing separates current delivery from voltage sensing.', evidence_ref_ids: ['src-four-wire-principle:evidence'], reasoning: 'Source-backed measurement principle.' },
  { id: 'trace', status: 'Observed', statement: 'The supplied two-wire resistance decreases from 120 Ω to 65 Ω over the recorded sweep.', evidence_ref_ids: ['data-001:rows-2-9'], reasoning: 'Deterministic CSV calculation.' },
  { id: 'bulk', status: 'Inferred', statement: 'The trend is consistent with, but does not establish, a bulk conductivity transition.', evidence_ref_ids: ['src-four-wire-principle:evidence', 'data-001:rows-2-9'], reasoning: 'Interpretation constrained by the input packet.', uncertainty: 'The trace is two-terminal.', alternative_explanation: 'Temperature-dependent leads or contacts can change the trace.' },
  { id: 'contact', status: 'Unresolved', statement: 'Contact and lead contributions remain unresolved without a matched four-terminal measurement.', evidence_ref_ids: ['src-contact-contribution:evidence', 'data-001:rows-2-9'], reasoning: 'The supplied data do not isolate the device voltage drop.' },
]

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${import.meta.env.VITE_GROUNDLOOP_API_URL ?? ''}${path}`, { headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }, ...init })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: { message?: string } } | null
    throw new Error(body?.detail?.message ?? 'GroundLoop local service is unavailable.')
  }
  return response.json() as Promise<T>
}

function statusClass(status: Finding['status']) {
  return { Established: 'status-established', Observed: 'status-observed', Inferred: 'status-inferred', Unresolved: 'status-unresolved' }[status]
}

function App() {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [notice, setNotice] = useState('Load the local fixture to begin a bounded evidence run.')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const report = detail?.report
  const packet = detail?.packet
  const dataset = report?.dataset ?? packet?.dataset ?? previewDataset
  const sources = report?.sources ?? packet?.sources ?? previewSources
  const findings = report?.findings ?? previewFindings
  const claim = report?.claim ?? packet?.claim.claim ?? 'The temperature-dependent resistance change in the sample demonstrates a bulk conductivity transition.'
  const control = report?.control
  const state = detail?.run.state ?? 'REFERENCE'
  const handoff = detail ? `Analyse GroundLoop run ${detail.run.run_id}. Call inspect_sources and analyze_dataset first, then validate findings and one ControlFirst proposal before exporting the report.` : 'Load the fixture to create a run-specific Codex handoff.'

  const grouped = useMemo(() => ['Established', 'Observed', 'Inferred', 'Unresolved'].map((status) => ({ status: status as Finding['status'], finding: findings.find((item) => item.status === status) })), [findings])

  const refresh = useCallback(async (runId?: string) => {
    if (!runId) return
    const next = await api<Detail>(`/api/runs/${runId}`)
    setDetail(next)
    setNotice(next.run.state === 'EXPORTED' ? 'Validated report loaded from the local run store.' : `Run is ${next.run.state.replaceAll('_', ' ')}. Continue through the Codex handoff.`)
  }, [])

  useEffect(() => {
    void api<Run[]>('/api/runs').then((runs) => runs[0] && refresh(runs[0].run_id)).catch(() => setNotice('Start the local API to connect a saved run; the reference fixture remains visible.'))
  }, [refresh])

  const loadFixture = async () => {
    setBusy(true)
    try {
      const run = await api<Run>('/api/runs', { method: 'POST', body: JSON.stringify({ fixture_name: 'four_wire_contact_control' }) })
      await refresh(run.run_id)
      setNotice('Fixture loaded as a new DRAFT. Prepare it to freeze the evidence packet.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not create the fixture run.')
    } finally {
      setBusy(false)
    }
  }

  const prepare = async () => {
    if (!detail) return
    setBusy(true)
    try {
      const next = await api<Detail>(`/api/runs/${detail.run.run_id}/prepare`, { method: 'POST', body: '{}' })
      setDetail(next)
      setNotice('Evidence packet is immutable. Copy the Codex handoff to continue the reasoning loop.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not prepare the evidence packet.')
    } finally {
      setBusy(false)
    }
  }

  const copyHandoff = async () => {
    await navigator.clipboard.writeText(handoff)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  return (
    <main className="min-h-screen bg-[#fbfbfa] text-[#101112]">
      <header className="border-b border-black/10 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3"><span className="grid size-8 place-items-center bg-[#151515] text-white"><Layers3 className="size-4" /></span><span className="text-[17px] font-semibold tracking-[-0.03em]">GroundLoop</span><span className="hidden text-xs text-black/45 sm:inline">ControlFirst · local evidence workflow</span></div>
          <div className="flex items-center gap-3 text-xs"><span className="hidden text-black/45 sm:inline">{state === 'REFERENCE' ? 'REFERENCE FIXTURE' : state.replaceAll('_', ' ')}</span><Button variant="outline" size="sm" className="rounded-none" onClick={() => void refresh(detail?.run.run_id)} disabled={!detail || busy}><RefreshCw className="size-3.5" /> Refresh</Button></div>
        </div>
      </header>

      <section className="mx-auto max-w-[1440px] px-5 pb-12 pt-9 sm:px-8">
        <div className="mb-9 grid gap-5 border-b border-black/10 pb-7 lg:grid-cols-[1fr_auto] lg:items-end">
          <div><p className="eyebrow">REPORT · {report ? 'EXPORTED' : 'CONTROLLED PREVIEW'}</p><h1 className="mt-3 max-w-3xl text-3xl font-medium tracking-[-0.045em] sm:text-5xl">Separate what the data show from what the result means.</h1><p className="mt-4 max-w-2xl text-sm leading-6 text-black/60">{notice}</p></div>
          <div className="flex flex-wrap gap-2"><Button className="rounded-none bg-[#171717]" onClick={() => void loadFixture()} disabled={busy}><Database className="size-4" /> Load fixture</Button>{detail?.run.state === 'DRAFT' && <Button variant="outline" className="rounded-none" onClick={() => void prepare()} disabled={busy}>Prepare evidence <ArrowRight className="size-4" /></Button>}</div>
        </div>

        <div className="grid gap-px overflow-hidden border border-black/10 bg-black/10 xl:grid-cols-[1fr_1.12fr_1fr]">
          <section className="bg-[#fbfbfa] p-5 sm:p-7"><SectionTitle icon={<FileText />} label="Top-down · source theory" /><p className="claim-text">{claim}</p><div className="mt-7 space-y-3">{sources.map((source) => <article key={source.id} className="source-card"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-medium">{source.title}</p><p className="mt-1 text-[11px] text-black/45">{source.authors.join(', ')} · {source.year} · {source.locator.section ?? `p. ${source.locator.page}`}</p></div><ShieldCheck className="size-4 shrink-0 text-black/45" /></div><p className="mt-3 text-xs leading-5 text-black/65">{source.untrusted_content}</p><p className="mt-3 font-mono text-[10px] text-black/40">UNTRUSTED INPUT · {source.id}</p></article>)}</div><p className="mt-6 border-l-2 border-black/80 pl-3 text-sm leading-6">Two-wire sensing can contain lead/contact contribution. Four-wire sensing tests whether the pattern survives isolation.</p></section>

          <section className="bg-white p-5 sm:p-7"><SectionTitle icon={<Database />} label="Bottom-up · measurement data" /><div className="mt-4 h-48 w-full"><ResponsiveContainer width="100%" height="100%"><AreaChart data={dataset.rows} margin={{ top: 8, right: 10, bottom: 0, left: -18 }}><defs><linearGradient id="resistanceFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#151515" stopOpacity={0.18} /><stop offset="100%" stopColor="#151515" stopOpacity={0} /></linearGradient></defs><XAxis dataKey="temperature_c" tickLine={false} axisLine={false} tickMargin={8} tick={{ fontSize: 10, fill: '#666' }} /><YAxis tickLine={false} axisLine={false} tick={{ fontSize: 10, fill: '#666' }} /><Tooltip contentStyle={{ borderRadius: 0, border: '1px solid #ddd', fontSize: 12 }} formatter={(value) => [`${Number(value).toFixed(1)} Ω`, 'Two-wire R']} labelFormatter={(value) => `${value} °C`} /><Area type="monotone" dataKey="two_wire_resistance_ohm" stroke="#171717" strokeWidth={1.8} fill="url(#resistanceFill)" /></AreaChart></ResponsiveContainer></div><div className="mt-4 grid grid-cols-3 gap-px border border-black/10 bg-black/10 text-center"><Metric label="Rows" value={String(dataset.row_count)} /><Metric label="Δ resistance" value={`${dataset.change_ohm.toFixed(1)} Ω`} /><Metric label="Change" value={`${dataset.percent_change.toFixed(1)}%`} /></div><div className="mt-7"><p className="eyebrow">Deterministic trace</p><p className="mt-2 text-sm leading-6">Rows 2–{dataset.row_count + 1}: two-wire resistance changes from {dataset.first_resistance_ohm.toFixed(1)} Ω to {dataset.last_resistance_ohm.toFixed(1)} Ω as temperature rises from {dataset.temperature_range_c[0]}°C to {dataset.temperature_range_c[1]}°C.</p></div></section>

          <section className="bg-[#fbfbfa] p-5 sm:p-7"><SectionTitle icon={<FlaskConical />} label="ControlFirst" /><div className="mt-4 border border-[#de5632] bg-[#fff6f2] p-4"><p className="eyebrow text-[#b64020]">Priority · high</p><h2 className="mt-2 text-lg font-medium tracking-[-0.03em]">Resolve the contact / lead contribution.</h2><p className="mt-3 text-sm leading-6 text-black/70">{control?.experiment ?? 'Repeat the same temperature sweep in four-terminal mode while holding the sample, current, mounting, and temperature program fixed.'}</p></div><div className="mt-5 space-y-3"><Outcome ifText={control?.outcomes[0]?.if ?? 'The trend persists in four-terminal mode'} thenText={control?.outcomes[0]?.then ?? 'Support for a bulk contribution increases.'} /><Outcome ifText={control?.outcomes[1]?.if ?? 'The trend weakens substantially in four-terminal mode'} thenText={control?.outcomes[1]?.then ?? 'A contact or lead contribution becomes more plausible.'} /></div><p className="mt-6 text-xs leading-5 text-black/50">This is a discriminating next measurement, not a declaration that the claim is true.</p></section>
        </div>

        <section className="mt-8 border border-black/10 bg-white"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-black/10 px-5 py-4 sm:px-7"><div><p className="eyebrow">Evidence ledger</p><p className="mt-1 text-sm text-black/60">Every conclusion retains its status and evidence references.</p></div><span className="border border-black/15 px-2 py-1 font-mono text-[10px]">{report ? 'VALIDATED REPORT' : 'REFERENCE PREVIEW'}</span></div><div className="grid divide-y divide-black/10 md:grid-cols-2 md:divide-x md:divide-y-0">{grouped.map(({ status, finding }) => <article key={status} className="p-5 sm:p-6"><div className="flex items-center justify-between"><span className={`status ${statusClass(status)}`}>{status}</span><span className="font-mono text-[10px] text-black/35">{finding?.evidence_ref_ids.join(' · ') ?? 'not submitted'}</span></div><p className="mt-4 text-sm leading-6">{finding?.statement ?? 'No validated finding submitted.'}</p>{finding?.uncertainty && <p className="mt-3 text-xs leading-5 text-black/50">Uncertainty: {finding.uncertainty}</p>}</article>)}</div></section>

        <section className="mt-8 grid gap-px border border-black/10 bg-black/10 lg:grid-cols-[1fr_auto]"><div className="bg-[#fbfbfa] p-5 sm:p-7"><p className="eyebrow">Codex handoff · MCP only</p><p className="mt-3 max-w-3xl font-mono text-xs leading-6 text-black/70">{handoff}</p><p className="mt-3 text-xs leading-5 text-black/45">GroundLoop never calls a model. Codex supplies bounded reasoning through the local MCP tools; the local API stores only validated artifacts.</p></div><div className="flex items-center bg-white p-5"><Button variant="outline" className="w-full rounded-none" onClick={() => void copyHandoff()} disabled={!detail}>{copied ? <Check className="size-4" /> : <Clipboard className="size-4" />}{copied ? 'Copied' : 'Copy handoff'}</Button></div></section>

        <footer className="flex flex-wrap items-center justify-between gap-4 pt-6 text-[11px] text-black/40"><span>Local-only · no API key · no URL fetching · no external actions</span><span className="inline-flex items-center gap-1">Evidence-first research workflow <ExternalLink className="size-3" /></span></footer>
      </section>
    </main>
  )
}

function SectionTitle({ icon, label }: { icon: React.ReactNode; label: string }) { return <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-black/50">{icon}<span>{label}</span></div> }
function Metric({ label, value }: { label: string; value: string }) { return <div className="bg-white px-2 py-3"><p className="text-[10px] uppercase tracking-[0.1em] text-black/45">{label}</p><p className="mt-1 text-sm font-medium tracking-[-0.03em]">{value}</p></div> }
function Outcome({ ifText, thenText }: { ifText: string; thenText: string }) { return <div className="border-l-2 border-[#de5632] pl-3"><p className="text-[11px] font-medium uppercase tracking-[0.1em] text-[#b64020]">If</p><p className="mt-1 text-xs leading-5">{ifText}</p><p className="mt-2 text-[11px] font-medium uppercase tracking-[0.1em] text-black/45">Then</p><p className="mt-1 text-xs leading-5 text-black/70">{thenText}</p></div> }

export default App
