import { useCallback, useEffect, useMemo, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
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
} from 'lucide-react'
import { Button } from '@/components/ui/button'

type RunState = 'DRAFT' | 'PACKET_READY' | 'SOURCES_INSPECTED' | 'DATA_ANALYZED' | 'FINDINGS_VALIDATED' | 'CONTROL_VALIDATED' | 'EXPORTED'
type Run = { run_id: string; state: RunState; fixture?: string; created_at: string }
type EvidenceRef = { id: string; kind: 'source' | 'data'; artifact_id: string; excerpt: string; sha256: string; locator: Record<string, unknown> }
type Source = { id: string; title: string; authors: string[]; year: number; url_or_doi: string; locator: { section?: string; page?: number }; untrusted_content: string }
type SourceRelevance = { source_id: string; verdict: 'direct' | 'contextual' | 'limited'; matched_terms: string[]; reason: string }
type Finding = { id: string; statement: string; status: 'Established' | 'Observed' | 'Inferred' | 'Unresolved'; evidence_ref_ids: string[]; reasoning: string; uncertainty?: string }
type Dataset = { row_count: number; temperature_range_c: [number, number]; first_resistance_ohm: number; last_resistance_ohm: number; change_ohm: number; percent_change: number; rows: { temperature_c: number; two_wire_resistance_ohm: number }[] }
type Report = { run_id: string; claim: string; state: 'EXPORTED'; findings: Finding[]; control: { confound: string; experiment: string; outcomes: { if: string; then: string }[]; priority: string; feasibility: string }; sources: Source[]; source_relevance: SourceRelevance[]; dataset: Dataset; verdict: { label: 'MECHANISM_NOT_ESTABLISHED'; reason: string; blocking_finding_ids: string[] } }
type Draft = { claim: { claim: string } | null; sources: Source[]; methods: string; dataset_ready: boolean }
type Detail = { run: Run; input_artifacts?: string[]; draft?: Draft; packet?: { claim: { claim: string }; sources: Source[]; source_relevance?: SourceRelevance[]; dataset: Dataset; evidence_refs: EvidenceRef[] }; report?: Report }

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const bodyIsForm = init?.body instanceof FormData
  const response = await fetch(`${import.meta.env.VITE_GROUNDLOOP_API_URL ?? ''}${path}`, {
    ...init,
    headers: { ...(bodyIsForm ? {} : { 'Content-Type': 'application/json' }), ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: { message?: string } } | null
    throw new Error(body?.detail?.message ?? 'GroundLoop local service is unavailable.')
  }
  return response.json() as Promise<T>
}

const stateLabel: Record<RunState, string> = {
  DRAFT: 'Research setup',
  PACKET_READY: 'Evidence packet ready',
  SOURCES_INSPECTED: 'Sources inspected',
  DATA_ANALYZED: 'Data analysed',
  FINDINGS_VALIDATED: 'Findings validated',
  CONTROL_VALIDATED: 'Control validated',
  EXPORTED: 'Validated report',
}

function App() {
  const [runs, setRuns] = useState<Run[]>([])
  const [detail, setDetail] = useState<Detail | null>(null)
  const [question, setQuestion] = useState('')
  const [methods, setMethods] = useState('')
  const [datasetFile, setDatasetFile] = useState<File | null>(null)
  const [notice, setNotice] = useState('Start with a research question. GroundLoop will retrieve a small, traceable reference set for you.')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const setCurrentDetail = useCallback((next: Detail | null) => {
    setDetail(next)
    if (next?.run.state === 'DRAFT') {
      setQuestion(next.draft?.claim?.claim ?? '')
      setMethods(next.draft?.methods ?? '')
    }
  }, [])

  const refreshRuns = useCallback(async () => {
    const next = await api<Run[]>('/api/runs')
    setRuns(next)
  }, [])

  const refresh = useCallback(async (runId?: string) => {
    if (!runId) return
    const next = await api<Detail>(`/api/runs/${runId}`)
    setCurrentDetail(next)
    await refreshRuns()
  }, [refreshRuns, setCurrentDetail])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void api<Run[]>('/api/runs').then(setRuns).catch(() => setNotice('Start the local API to create a research run.'))
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  const currentState = detail?.run.state
  const draft = detail?.draft
  const report = detail?.report
  const packet = detail?.packet
  const sourceHashByArtifact = useMemo(() => new Map(packet?.evidence_refs.filter((item) => item.kind === 'source').map((item) => [item.artifact_id, item.sha256])), [packet])
  const handoff = detail ? `Analyse GroundLoop run ${detail.run.run_id}. First inspect sources and analyse the dataset. Then validate the four-state findings and one ControlFirst proposal before exporting the report.` : ''
  const setupReady = Boolean(draft?.sources.length && draft?.dataset_ready && methods.trim().length >= 20)

  const startResearch = async () => {
    if (question.trim().length < 10) {
      setNotice('Enter a research question of at least 10 characters before searching.')
      return
    }
    setBusy(true)
    try {
      const runId = detail?.run.state === 'DRAFT' ? detail.run.run_id : (await api<Run>('/api/runs', { method: 'POST', body: '{}' })).run_id
      const next = await api<Detail>(`/api/runs/${runId}/gather-references`, { method: 'POST', body: JSON.stringify({ research_question: question.trim() }) })
      setCurrentDetail(next)
      await refreshRuns()
      setNotice('References were retrieved automatically. Review their provenance, then add the data artifact to test your question.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not start the research run.')
    } finally {
      setBusy(false)
    }
  }

  const loadDemo = async () => {
    setBusy(true)
    try {
      const run = await api<Run>('/api/runs', { method: 'POST', body: JSON.stringify({ fixture_name: 'four_wire_contact_control' }) })
      await refresh(run.run_id)
      setNotice('Demo run loaded. It is clearly marked as a fixture; freeze it only when you want to rehearse the Codex loop.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not load the demo run.')
    } finally {
      setBusy(false)
    }
  }

  const saveMethods = async () => {
    if (!detail || methods.trim().length < 20) {
      setNotice('Add at least one clear sentence about how the data were measured.')
      return
    }
    setBusy(true)
    try {
      await api<Run>(`/api/runs/${detail.run.run_id}/methods`, { method: 'PUT', body: JSON.stringify({ methods: methods.trim() }) })
      await refresh(detail.run.run_id)
      setNotice('Method context saved locally.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not save the method context.')
    } finally {
      setBusy(false)
    }
  }

  const uploadDataset = async () => {
    if (!detail || !datasetFile) {
      setNotice('Choose a CSV file before uploading.')
      return
    }
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', datasetFile)
      await api(`/api/runs/${detail.run.run_id}/dataset`, { method: 'POST', body: form })
      await refresh(detail.run.run_id)
      setNotice('CSV stored locally and checked for deterministic analysis.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not accept that CSV file.')
    } finally {
      setBusy(false)
    }
  }

  const loadDemoData = async () => {
    if (!detail) return
    setBusy(true)
    try {
      await api<Detail>(`/api/runs/${detail.run.run_id}/demo-data`, { method: 'POST', body: '{}' })
      await refresh(detail.run.run_id)
      setNotice('Clearly labelled synthetic demonstration data added. Replace it with your CSV before drawing a real conclusion.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not add demo data.')
    } finally {
      setBusy(false)
    }
  }

  const prepare = async () => {
    if (!detail) return
    setBusy(true)
    try {
      const next = await api<Detail>(`/api/runs/${detail.run.run_id}/prepare`, { method: 'POST', body: '{}' })
      setCurrentDetail(next)
      await refreshRuns()
      setNotice('Evidence packet frozen. Its sources and CSV cannot change during Codex review.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not freeze the evidence packet.')
    } finally {
      setBusy(false)
    }
  }

  const copyHandoff = async () => {
    await navigator.clipboard.writeText(handoff)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  const selectRun = async (runId: string) => {
    setBusy(true)
    try {
      await refresh(runId)
      setNotice(`Opened ${stateLabel[(await api<Detail>(`/api/runs/${runId}`)).run.state]}.`)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not open that run.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen bg-[#fbfbfa] text-[#111214]">
      <header className="border-b border-black/10 bg-white">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3"><span className="grid size-8 place-items-center bg-[#151515] text-white"><Layers3 className="size-4" /></span><span className="text-[17px] font-semibold tracking-[-0.03em]">GroundLoop</span><span className="hidden text-sm text-black/55 sm:inline">ControlFirst · scientific red team</span></div>
          <div className="flex items-center gap-2">
            {runs.length > 0 && <label className="sr-only" htmlFor="run-picker">Open a saved research run</label>}
            {runs.length > 0 && <select id="run-picker" value={detail?.run.run_id ?? ''} onChange={(event) => void selectRun(event.target.value)} disabled={busy} className="h-9 max-w-44 border border-black/15 bg-white px-2 text-xs text-black/75"><option value="" disabled>Open a saved run</option>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{stateLabel[run.state]} · {run.run_id.slice(0, 8)}</option>)}</select>}
            <Button variant="outline" size="sm" className="rounded-none" onClick={() => { setCurrentDetail(null); setQuestion(''); setMethods(''); setDatasetFile(null); setNotice('Start a new research question or open a deliberate saved run.'); }} disabled={busy}><Plus className="size-3.5" /> New run</Button>
            {detail && <Button variant="outline" size="sm" className="rounded-none" onClick={() => void refresh(detail.run.run_id)} disabled={busy}><RefreshCw className={busy ? 'size-3.5 animate-spin' : 'size-3.5'} /> Refresh</Button>}
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-[1180px] px-5 pb-16 pt-10 sm:px-8">
        <WorkflowRail state={currentState} />
        <p aria-live="polite" className="mb-8 border-l-2 border-black/80 pl-3 text-sm leading-6 text-black/70">{notice}</p>

        {!detail && <StartScreen question={question} setQuestion={setQuestion} busy={busy} onStart={() => void startResearch()} onDemo={() => void loadDemo()} />}
        {detail?.run.state === 'DRAFT' && <SetupScreen detail={detail} question={question} methods={methods} setMethods={setMethods} datasetFile={datasetFile} setDatasetFile={setDatasetFile} busy={busy} ready={setupReady} onSearch={() => void startResearch()} onSaveMethods={() => void saveMethods()} onUpload={() => void uploadDataset()} onDemoData={() => void loadDemoData()} onPrepare={() => void prepare()} />}
        {detail && detail.run.state !== 'DRAFT' && detail.run.state !== 'EXPORTED' && <ReviewScreen detail={detail} handoff={handoff} copied={copied} busy={busy} onCopy={() => void copyHandoff()} />}
        {report && <ReportScreen report={report} packet={packet} sourceHashByArtifact={sourceHashByArtifact} />}
      </section>
    </main>
  )
}

function WorkflowRail({ state }: { state?: RunState }) {
  const step = !state || state === 'DRAFT' ? 1 : state === 'PACKET_READY' ? 2 : state === 'EXPORTED' ? 4 : 3
  const steps = ['Question & references', 'Frozen packet', 'Codex review', 'Validated report']
  return <ol className="mb-10 grid gap-3 border-y border-black/10 py-4 sm:grid-cols-4">{steps.map((label, index) => <li key={label} className={`flex items-center gap-3 text-sm ${step === index + 1 ? 'font-medium text-black' : step > index + 1 ? 'text-black/60' : 'text-black/40'}`}><span className={`grid size-6 place-items-center border text-xs ${step === index + 1 ? 'border-black bg-black text-white' : step > index + 1 ? 'border-black/40' : 'border-black/15'}`}>{step > index + 1 ? <Check className="size-3.5" /> : index + 1}</span>{label}</li>)}</ol>
}

function StartScreen({ question, setQuestion, busy, onStart, onDemo }: { question: string; setQuestion: (value: string) => void; busy: boolean; onStart: () => void; onDemo: () => void }) {
  return <div className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-start"><div><p className="eyebrow">Scientific red team · transport evidence</p><h1 className="mt-3 max-w-3xl text-4xl font-medium tracking-[-0.05em] sm:text-6xl">Challenge the mechanism before you trust the trace.</h1><p className="mt-5 max-w-2xl text-base leading-7 text-black/65">GroundLoop tests an electrical or thermal transport interpretation against a frozen evidence packet, then asks Codex for the smallest control experiment that could change the conclusion.</p></div><div className="border border-black/15 bg-white p-5 sm:p-6"><label htmlFor="research-question" className="text-sm font-medium">Proposed mechanism or claim</label><textarea id="research-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="For example: This temperature-dependent resistance change demonstrates a bulk conductivity transition." className="mt-3 min-h-36 w-full resize-y border border-black/20 bg-[#fbfbfa] p-3 text-sm leading-6 outline-none focus:border-black" /><Button className="mt-4 w-full rounded-none bg-[#171717]" onClick={onStart} disabled={busy || question.trim().length < 10}>{busy ? <LoaderCircle className="size-4 animate-spin" /> : <FileSearch className="size-4" />} Build the evidence boundary <ArrowRight className="size-4" /></Button><div className="mt-5 border-t border-black/10 pt-4"><p className="text-xs leading-5 text-black/55">GroundLoop retrieves a bounded source set from the allowlisted OpenAlex index. Retrieval supports the red-team analysis; every result remains untrusted until inspected through the MCP workflow.</p><Button variant="link" className="mt-2 h-auto px-0 text-xs text-black/70" onClick={onDemo} disabled={busy}>Open the canonical four-wire control demo <ChevronRight className="size-3.5" /></Button></div></div></div>
}

function SetupScreen({ detail, question, methods, setMethods, datasetFile, setDatasetFile, busy, ready, onSearch, onSaveMethods, onUpload, onDemoData, onPrepare }: { detail: Detail; question: string; methods: string; setMethods: (value: string) => void; datasetFile: File | null; setDatasetFile: (value: File | null) => void; busy: boolean; ready: boolean; onSearch: () => void; onSaveMethods: () => void; onUpload: () => void; onDemoData: () => void; onPrepare: () => void }) {
  const draft = detail.draft
  const sources = draft?.sources ?? []
  const hasSources = sources.length > 0
  return <div><div className="max-w-3xl"><p className="eyebrow">Step 1 · research setup</p><h1 className="mt-3 text-4xl font-medium tracking-[-0.05em] sm:text-5xl">Build the packet before reasoning.</h1><p className="mt-4 text-base leading-7 text-black/65">References are collected automatically. You add only the measurement context and the CSV that should be tested against them.</p></div>{!hasSources && <div className="mt-8 max-w-2xl border border-black/15 bg-white p-5"><p className="text-sm font-medium">This run has no retrieved references yet.</p><p className="mt-2 text-sm leading-6 text-black/60">Enter a question above, then start automatic reference discovery.</p><Button className="mt-4 rounded-none bg-[#171717]" onClick={onSearch} disabled={busy || question.trim().length < 10}><FileSearch className="size-4" /> Find references automatically</Button></div>}{hasSources && <><section className="mt-10"><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="eyebrow">Automatically retrieved references</p><h2 className="mt-2 text-xl font-medium tracking-[-0.03em]">Selected for this evidence packet</h2></div><span className="border border-black/20 px-2 py-1 text-xs text-black/65">{sources.length} indexed abstracts</span></div><div className="mt-4 grid gap-3 lg:grid-cols-3">{sources.map((source) => <SourceCard key={source.id} source={source} />)}</div></section><section className="mt-8 grid gap-px border border-black/15 bg-black/10 lg:grid-cols-2"><div className="bg-white p-5 sm:p-6"><p className="eyebrow">Measurement context</p><label htmlFor="methods" className="mt-3 block text-sm font-medium">How was the data collected?</label><textarea id="methods" value={methods} onChange={(event) => setMethods(event.target.value)} placeholder="Describe the sample, measurement mode, variables held fixed, and any relevant conditions." className="mt-3 min-h-40 w-full resize-y border border-black/20 bg-[#fbfbfa] p-3 text-sm leading-6 outline-none focus:border-black" /><Button variant="outline" className="mt-3 rounded-none" onClick={onSaveMethods} disabled={busy || methods.trim().length < 20}>Save method context</Button></div><div className="bg-[#fbfbfa] p-5 sm:p-6"><p className="eyebrow">Measurement data</p><p className="mt-3 text-sm font-medium">Add the CSV to analyse</p><p className="mt-2 text-sm leading-6 text-black/60">The CSV stays local and is converted into a deterministic trace. No raw data is sent to the literature index.</p><label htmlFor="dataset" className="mt-5 flex cursor-pointer items-center justify-between border border-dashed border-black/30 bg-white p-3 text-sm"><span className="flex items-center gap-2"><Upload className="size-4" />{datasetFile ? datasetFile.name : 'Choose CSV file'}</span><span className="text-xs text-black/55">CSV only</span></label><input id="dataset" className="sr-only" type="file" accept=".csv,text/csv" onChange={(event) => setDatasetFile(event.target.files?.[0] ?? null)} /><div className="mt-3 flex flex-wrap gap-2"><Button variant="outline" className="rounded-none" onClick={onUpload} disabled={busy || !datasetFile}>Upload CSV</Button><Button variant="outline" className="rounded-none" onClick={onDemoData} disabled={busy}>Add labelled demo data</Button></div>{draft?.dataset_ready && <p className="mt-4 flex items-center gap-2 text-sm text-[#215f47]"><Check className="size-4" /> Local CSV is ready for analysis.</p>}</div></section><section className="mt-8 border border-black bg-[#171717] p-5 text-white sm:flex sm:items-center sm:justify-between sm:p-7"><div><p className="eyebrow !text-white/60">Ready to freeze?</p><p className="mt-2 text-lg font-medium">Freeze the exact sources, methods, and data that Codex may inspect.</p><p className="mt-2 text-sm leading-6 text-white/65">{ready ? 'All required artifacts are present.' : 'Add retrieved sources, a measurement context, and one CSV before freezing.'}</p></div><Button className="mt-5 rounded-none bg-white text-black hover:bg-white/90 sm:mt-0" onClick={onPrepare} disabled={busy || !ready}>Freeze evidence packet <ArrowRight className="size-4" /></Button></section></>}</div>
}

function SourceCard({ source, sha256, relevance }: { source: Source; sha256?: string; relevance?: SourceRelevance }) {
  return <article className="border border-black/15 bg-white p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-medium leading-5">{source.title}</p><p className="mt-1 text-xs leading-5 text-black/60">{source.authors.join(', ')} · {source.year}</p></div><ShieldCheck className="size-4 shrink-0 text-black/55" aria-label="Untrusted evidence" /></div><p className="mt-3 line-clamp-5 text-sm leading-6 text-black/70">{source.untrusted_content}</p><div className="mt-4 border-t border-black/10 pt-3"><a href={source.url_or_doi} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 break-all text-xs text-black/70 underline underline-offset-4">{source.url_or_doi}<ExternalLink className="size-3 shrink-0" /></a><p className="mt-2 text-xs text-black/50">{source.locator.section ?? (source.locator.page ? `Page ${source.locator.page}` : 'Provided excerpt')}</p>{sha256 && <p className="mt-2 break-all font-mono text-[11px] leading-4 text-black/50">SHA-256 {sha256}</p>}{relevance && <><p className="mt-2 font-mono text-[11px] uppercase text-[#285479]">Lexical screen · {relevance.verdict}</p><p className="mt-1 text-xs leading-5 text-black/55">{relevance.reason}</p></>}<p className="mt-2 font-mono text-[11px] text-[#a13d25]">UNTRUSTED EVIDENCE</p></div></article>
}

function ReviewScreen({ detail, handoff, copied, busy, onCopy }: { detail: Detail; handoff: string; copied: boolean; busy: boolean; onCopy: () => void }) {
  const state = detail.run.state
  const isReady = state === 'PACKET_READY'
  const sourceHashByArtifact = new Map(detail.packet?.evidence_refs.filter((item) => item.kind === 'source').map((item) => [item.artifact_id, item.sha256]))
  const sourceRelevanceById = new Map(detail.packet?.source_relevance?.map((item) => [item.source_id, item]))
  return <div><div className="max-w-3xl"><p className="eyebrow">Step {isReady ? '2' : '3'} · {stateLabel[state]}</p><h1 className="mt-3 text-4xl font-medium tracking-[-0.05em] sm:text-5xl">{isReady ? 'The evidence is frozen. Now ask Codex to inspect it.' : 'Codex review is in progress.'}</h1><p className="mt-4 text-base leading-7 text-black/65">{isReady ? 'No conclusion is shown here yet. GroundLoop waits for the MCP review to validate evidence status and the next control.' : 'Refresh after the MCP tool calls complete. Only an exported run renders a conclusion.'}</p></div><div className="mt-8 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]"><section className="border border-black bg-[#171717] p-5 text-white sm:p-7"><p className="eyebrow !text-white/60">Codex handoff · MCP only</p><p className="mt-3 font-mono text-sm leading-7 text-white/80">{handoff}</p><Button className="mt-6 w-full rounded-none bg-white text-black hover:bg-white/90" onClick={onCopy} disabled={busy}>{copied ? <Check className="size-4" /> : <Clipboard className="size-4" />}{copied ? 'Copied to clipboard' : 'Copy handoff for Codex'}</Button><p className="mt-4 text-xs leading-5 text-white/60">Codex must adjudicate every source separately. The lexical screen is a retrieval check, not source support.</p></section><section className="border border-black/15 bg-white p-5 sm:p-7"><p className="eyebrow">Review progress</p><ol className="mt-4 space-y-4">{['Evidence packet frozen', 'Sources inspected', 'Dataset analysed', 'Findings validated', 'Control validated', 'Report exported'].map((label, index) => { const completed = ['PACKET_READY', 'SOURCES_INSPECTED', 'DATA_ANALYZED', 'FINDINGS_VALIDATED', 'CONTROL_VALIDATED', 'EXPORTED'].indexOf(state) >= index; return <li key={label} className={`flex items-center gap-3 text-sm ${completed ? 'text-black' : 'text-black/40'}`}><span className={`grid size-6 place-items-center border ${completed ? 'border-[#215f47] bg-[#edf8f1] text-[#215f47]' : 'border-black/15'}`}>{completed ? <Check className="size-3.5" /> : index + 1}</span>{label}</li> })}</ol></section></div><section className="mt-8"><p className="eyebrow">Packet provenance</p><p className="mt-2 text-sm leading-6 text-black/60">Each source has a transparent lexical screen before Codex decides whether its excerpt actually supports a principle or confound.</p><div className="mt-4 grid gap-3 lg:grid-cols-3">{detail.packet?.sources.map((source) => <SourceCard key={source.id} source={source} sha256={sourceHashByArtifact.get(source.id)} relevance={sourceRelevanceById.get(source.id)} />)}</div></section></div>
}

function ReportScreen({ report, packet, sourceHashByArtifact }: { report: Report; packet?: Detail['packet']; sourceHashByArtifact: Map<string, string | undefined> }) {
  const grouped = ['Established', 'Observed', 'Inferred', 'Unresolved'].map((status) => ({ status: status as Finding['status'], finding: report.findings.find((item) => item.status === status) }))
  const sourceRelevanceById = new Map(report.source_relevance.map((item) => [item.source_id, item]))
  return <div><div className="max-w-3xl"><p className="eyebrow">Step 4 · validated report</p><h1 className="mt-3 text-4xl font-medium tracking-[-0.05em] sm:text-5xl">Separate what the data show from what the result means.</h1><p className="mt-4 text-base leading-7 text-black/65">This view is available only after the local MCP workflow validates and exports the report.</p></div><section className="mt-8 border-2 border-[#a13d25] bg-[#fff0eb] p-5 sm:p-7"><p className="eyebrow text-[#a13d25]">Scientific red-team verdict</p><h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-[#8a301b]">{report.verdict.label.replaceAll('_', ' ')}</h2><p className="mt-3 max-w-3xl text-sm leading-7 text-black/75">{report.verdict.reason}</p><p className="mt-3 font-mono text-[11px] text-[#8a301b]">BLOCKED BY · {report.verdict.blocking_finding_ids.join(' · ')}</p></section><section className="mt-10 grid gap-px border border-black/15 bg-black/10 xl:grid-cols-[1fr_1.1fr]"> <div className="bg-[#fbfbfa] p-5 sm:p-7"><p className="eyebrow">Research question</p><p className="mt-3 text-lg leading-8 tracking-[-0.02em]">{report.claim}</p><p className="mt-8 eyebrow">Foundational references</p><div className="mt-4 space-y-3">{report.sources.map((source) => <SourceCard key={source.id} source={source} sha256={sourceHashByArtifact.get(source.id)} relevance={sourceRelevanceById.get(source.id)} />)}</div></div><div className="bg-white p-5 sm:p-7"><p className="eyebrow">Deterministic measurement trace</p><div className="mt-4 h-64 w-full"><ResponsiveContainer width="100%" height="100%"><AreaChart data={report.dataset.rows} margin={{ top: 8, right: 10, bottom: 0, left: -18 }}><defs><linearGradient id="resistanceFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#151515" stopOpacity={0.18} /><stop offset="100%" stopColor="#151515" stopOpacity={0} /></linearGradient></defs><XAxis dataKey="temperature_c" tickLine={false} axisLine={false} tickMargin={8} tick={{ fontSize: 11, fill: '#555' }} /><YAxis tickLine={false} axisLine={false} tickMargin={8} tick={{ fontSize: 11, fill: '#555' }} /><Tooltip contentStyle={{ borderRadius: 0, border: '1px solid #aaa', fontSize: 12 }} formatter={(value) => [`${Number(value).toFixed(1)} Ω`, 'Two-wire resistance']} labelFormatter={(value) => `${value} °C`} /><Area type="monotone" dataKey="two_wire_resistance_ohm" stroke="#171717" strokeWidth={1.8} fill="url(#resistanceFill)" /></AreaChart></ResponsiveContainer></div><div className="mt-5 grid grid-cols-3 gap-px border border-black/15 bg-black/10 text-center"><Metric label="Rows" value={String(report.dataset.row_count)} /><Metric label="Δ resistance" value={`${report.dataset.change_ohm.toFixed(1)} Ω`} /><Metric label="Change" value={`${report.dataset.percent_change.toFixed(1)}%`} /></div><p className="mt-6 text-sm leading-7">Rows {report.dataset.row_count > 0 ? `2–${report.dataset.row_count + 1}` : ''}: resistance changes from {report.dataset.first_resistance_ohm.toFixed(1)} Ω to {report.dataset.last_resistance_ohm.toFixed(1)} Ω as temperature rises from {report.dataset.temperature_range_c[0]}°C to {report.dataset.temperature_range_c[1]}°C.</p></div></section><section className="mt-8 border border-black/15 bg-white"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-black/15 px-5 py-4 sm:px-7"><div><p className="eyebrow">Evidence ledger</p><p className="mt-1 text-sm text-black/65">Every conclusion retains its status and evidence references.</p></div><span className="border border-[#215f47] bg-[#edf8f1] px-2 py-1 text-xs font-medium text-[#215f47]">VALIDATED REPORT</span></div><div className="grid divide-y divide-black/10 md:grid-cols-2 md:divide-x md:divide-y-0">{grouped.map(({ status, finding }) => <article key={status} className="p-5 sm:p-6"><span className={`status ${statusClass(status)}`}>{status}</span><p className="mt-3 break-all font-mono text-[11px] leading-5 text-black/55">{finding?.evidence_ref_ids.join(' · ') ?? 'No submitted finding'}</p><p className="mt-4 text-base leading-7">{finding?.statement ?? 'No validated finding submitted.'}</p>{finding?.uncertainty && <p className="mt-3 text-sm leading-6 text-black/65">Uncertainty: {finding.uncertainty}</p>}</article>)}</div></section><section className="mt-8 border border-[#de5632] bg-[#fff6f2] p-5 sm:p-7"><p className="eyebrow text-[#a13d25]">ControlFirst · priority {report.control.priority}</p><h2 className="mt-3 text-2xl font-medium tracking-[-0.04em]">Resolve: {report.control.confound}</h2><p className="mt-4 max-w-3xl text-base leading-7 text-black/75">{report.control.experiment}</p><div className="mt-6 grid gap-4 md:grid-cols-2">{report.control.outcomes.map((outcome) => <div key={outcome.if} className="border-l-2 border-[#de5632] pl-4"><p className="text-xs font-medium uppercase tracking-[0.1em] text-[#a13d25]">If</p><p className="mt-2 text-sm leading-6">{outcome.if}</p><p className="mt-4 text-xs font-medium uppercase tracking-[0.1em] text-black/55">Then</p><p className="mt-2 text-sm leading-6 text-black/75">{outcome.then}</p></div>)}</div><p className="mt-6 text-sm leading-6 text-black/65">This is a discriminating next measurement, not a declaration that the claim is true.</p></section>{packet && <p className="mt-6 text-xs leading-5 text-black/55">Frozen packet: {packet.evidence_refs.length} evidence references · report run {report.run_id}</p>}</div>
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="bg-white px-2 py-3"><p className="text-[11px] uppercase tracking-[0.1em] text-black/60">{label}</p><p className="mt-1 text-sm font-medium tracking-[-0.03em]">{value}</p></div> }
function statusClass(status: Finding['status']) { return { Established: 'status-established', Observed: 'status-observed', Inferred: 'status-inferred', Unresolved: 'status-unresolved' }[status] }

export default App
