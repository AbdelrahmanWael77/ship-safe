// Phase 6: manual QC test cases written by an AI model from the AI review of the scan on
// screen, and the results testers record. ShipSafe runs nothing: a case is text for a
// person to execute, and a result is what that person says happened.
import { useState } from 'react'
import { AlertCircle, Ban, Check, ClipboardList, Download, RefreshCw, Sparkles, X } from 'lucide-react'
import { API_BASE, api } from './api'
import { PROVIDER_COMPANY, reviewOrigin } from './aiReview'
import { useLoad } from './bitbucket/useLoad'
import { Pill, Severity } from './components'
import type { AIProvider, AIProviderName, AIReview, QcStatus, QcTestCase, QcTestSuite } from './types'

const STATUS: Record<QcStatus, { label: string; kind: string }> = {
  passed: { label: 'Passed', kind: 'good' },
  failed: { label: 'Failed', kind: 'danger' },
  blocked: { label: 'Blocked', kind: 'warning' },
  not_run: { label: 'Not run', kind: 'muted' },
}
const message = (error: unknown) => (error instanceof Error ? error.message : String(error))
const post = <T,>(path: string, body: unknown) =>
  api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const readTester = () => { try { return window.localStorage.getItem('shipsafe.tester') ?? '' } catch { return '' } }
const saveTester = (value: string) => { try { window.localStorage.setItem('shipsafe.tester', value) } catch { /* storage unavailable */ } }

export function QcTestCasesPanel({ scanId, review, providers, shareAckRequired, onOpenReview }: {
  scanId: string
  /** The newest AI review of the scan, if any: the cases are written from its findings. */
  review: AIReview | undefined
  /** Configured AI providers of the API server. */
  providers: AIProvider[]
  /** The scan is not of the synthetic demo: sending it needs the person's confirmation. */
  shareAckRequired: boolean
  onOpenReview: () => void
}) {
  const base = `/api/scans/${scanId}/qc/test-suites`
  const suites = useLoad(() => api<QcTestSuite[]>(base), `qc-suites:${scanId}`)
  const latest = (suites.data ?? []).find(item => item.scan_id === scanId) ?? null
  const [chosen, setChosen] = useState<AIProviderName | null>(null)
  const provider = providers.find(item => item.provider === chosen) ?? providers.find(item => item.provider === 'openai') ?? providers[0] ?? null
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)
  const [tester, setTester] = useState(readTester)
  const [suite, setSuite] = useState<QcTestSuite | null>(null)
  const shown = suite && suite.scan_id === scanId ? suite : latest

  const generate = async () => {
    if (!provider || !review) return
    setBusy(true); setResult(null)
    try {
      const created = await post<QcTestSuite>(base, { provider: provider.provider, review_id: review.id, acknowledge_source_sharing: shareAckRequired ? ack : false })
      setSuite(created); suites.reload()
      setResult({ kind: 'success', message: `${created.total} test case${created.total !== 1 ? 's' : ''} written by ${provider.label} from ${review.findings.length} finding${review.findings.length !== 1 ? 's' : ''}. Check each case before executing it; ShipSafe runs nothing.` })
    } catch (error) { setResult({ kind: 'error', message: `Test cases not written: ${message(error)}` }) }
    finally { setBusy(false) }
  }

  const record = async (testCase: QcTestCase, status: QcStatus, note: string) => {
    if (!shown) return
    const updated = await post<QcTestSuite>(`${base}/${shown.id}/results`, { case_id: testCase.id, status, tester: tester.trim(), ...(note.trim() ? { note: note.trim() } : {}) })
    setSuite(updated)
  }

  return (
    <section className="panel qc-panel" aria-label="QC test cases">
      <div className="panel-head">
        <div>
          <h3><ClipboardList size={17} /> QC test cases <Pill kind="warning">MANUAL · SHIPSAFE RUNS NOTHING</Pill></h3>
          <p>Step-by-step test cases a tester can execute on the running app to confirm or rule out each AI finding. Written by an AI model; check them before use.</p>
        </div>
        {shown && <div className="bb-head-actions">
          <a className="secondary-button" href={`${API_BASE}${base}/${shown.id}/export?format=csv`} download><Download size={15} /> CSV</a>
          <a className="secondary-button" href={`${API_BASE}${base}/${shown.id}/export?format=markdown`} download><Download size={15} /> Markdown</a>
        </div>}
      </div>

      {!review ? (
        <div className="qc-empty"><p>Test cases are written from an AI review of this scan, and there is none yet.</p>
          <button className="secondary-button" onClick={onOpenReview}><Sparkles size={15} /> Run an AI review</button></div>
      ) : !review.findings.length ? (
        <p className="qc-empty">The AI review of this scan proposed no findings, so there is nothing to write test cases for.</p>
      ) : !provider ? (
        <p className="qc-empty">No AI model is configured on the API server (SHIPSAFE_OPENAI_API_KEY or SHIPSAFE_GEMINI_API_KEY).</p>
      ) : (
        <div className="qc-generate">
          <p>From the {reviewOrigin(review)} review: {review.findings.length} finding{review.findings.length !== 1 ? 's' : ''}.</p>
          {providers.length > 1 && <label className="bb-field ai-provider-select"><span className="micro-label">MODEL</span><span className="select-shell">
            <select aria-label="Model for test cases" value={provider.provider} onChange={event => { setChosen(event.target.value as AIProviderName); setAck(false) }}>
              {providers.map(item => <option key={item.provider} value={item.provider}>{item.label} · {item.model}</option>)}
            </select></span></label>}
          {shareAckRequired && <label className="ai-share-ack"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />
            <span>This scan contains source code that is not the synthetic demo. I am allowed to send it to {PROVIDER_COMPANY[provider.provider]} (redaction is best-effort).</span></label>}
          <button className="primary-button" disabled={busy || (shareAckRequired && !ack)} onClick={() => { void generate() }}>
            {busy ? <RefreshCw size={16} className="spin" /> : <Sparkles size={16} />} {busy ? `${provider.label} is writing test cases…` : shown ? `Write new test cases with ${provider.label}` : `Write test cases with ${provider.label}`}
          </button>
        </div>
      )}
      {result && <p className={`ai-import-status ${result.kind}`} role={result.kind === 'error' ? 'alert' : 'status'}>{result.message}</p>}
      {suites.error && <p className="ai-import-status error" role="alert"><AlertCircle size={14} /> Could not load the test cases: {suites.error.message}</p>}

      {shown && <>
        <div className="qc-summary" role="status" aria-label="Test case results">
          <strong>{shown.total} test case{shown.total !== 1 ? 's' : ''}</strong>
          {(['failed', 'passed', 'blocked', 'not_run'] as QcStatus[]).map(status => <Pill key={status} kind={STATUS[status].kind}>{shown.counts[status]} {STATUS[status].label.toLowerCase()}</Pill>)}
          <span className="qc-meta">Written {new Date(shown.created_at).toLocaleString()} by {shown.generator.provider === 'openai' ? 'OpenAI' : 'Gemini'} · {shown.generator.model}</span>
        </div>
        <label className="qc-tester"><span className="micro-label">YOUR NAME (recorded with each result)</span>
          <input aria-label="Tester name" value={tester} placeholder="Your name" onChange={event => { setTester(event.target.value); saveTester(event.target.value) }} /></label>
        <div className="qc-cases">{shown.cases.map(item => <CaseCard key={item.id} testCase={item} canRecord={tester.trim().length >= 2} onRecord={record} />)}</div>
        <ul className="qc-limitations">{shown.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
      </>}
    </section>
  )
}

function CaseCard({ testCase, canRecord, onRecord }: {
  testCase: QcTestCase
  canRecord: boolean
  onRecord: (testCase: QcTestCase, status: QcStatus, note: string) => Promise<void>
}) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const status = STATUS[testCase.status]
  const mark = async (next: QcStatus) => {
    setBusy(true); setError(null)
    try { await onRecord(testCase, next, note); setNote('') } catch (exc) { setError(`Not recorded: ${message(exc)}`) } finally { setBusy(false) }
  }
  return (
    <article className={`qc-case qc-${testCase.status}`} aria-label={`Test case ${testCase.id}`}>
      <details>
        <summary>
          <span className="qc-id">{testCase.id}</span><Severity level={testCase.priority} />
          <span className="qc-title"><strong>{testCase.title}</strong><small>{testCase.area}{testCase.finding_id ? ` · finding ${testCase.finding_id}` : ''}</small></span>
          <Pill kind={status.kind}>{status.label}</Pill>
        </summary>
        <div className="qc-body">
          {testCase.preconditions.length > 0 && <><div className="micro-label">PRECONDITIONS</div><ul>{testCase.preconditions.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
          {testCase.test_data.length > 0 && <><div className="micro-label">TEST DATA</div><ul>{testCase.test_data.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
          <div className="micro-label">STEPS</div><ol>{testCase.steps.map((item, index) => <li key={index}>{item}</li>)}</ol>
          <div className="micro-label">EXPECTED RESULT</div><p>{testCase.expected}</p>
          <div className="micro-label">BUG TITLE IF IT FAILS</div><p className="qc-bug">{testCase.bug_title_if_fails}</p>
          {testCase.file && <p className="muted-small">Code: <code>{testCase.file}</code></p>}
          <div className="qc-record">
            <input aria-label={`Note for ${testCase.id}`} placeholder="Note (optional): what you saw" value={note} onChange={event => setNote(event.target.value)} />
            <button className="secondary-button qc-pass" disabled={busy || !canRecord} onClick={() => { void mark('passed') }}><Check size={14} /> Passed</button>
            <button className="secondary-button qc-fail" disabled={busy || !canRecord} onClick={() => { void mark('failed') }}><X size={14} /> Failed</button>
            <button className="secondary-button" disabled={busy || !canRecord} onClick={() => { void mark('blocked') }}><Ban size={14} /> Blocked</button>
          </div>
          {!canRecord && <p className="muted-small">Type your name above to record a result.</p>}
          {error && <p className="ai-import-status error" role="alert">{error}</p>}
          {testCase.results.length > 0 && <ol className="qc-history">{testCase.results.slice().reverse().map((item, index) => <li key={index}><strong>{STATUS[item.status].label}</strong> · {item.tester} · {new Date(item.recorded_at).toLocaleString()}{item.note ? ` · ${item.note}` : ''}</li>)}</ol>}
        </div>
      </details>
    </article>
  )
}
