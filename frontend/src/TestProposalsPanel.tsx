// Phase 4 task B: proposed regression tests for the scan on screen and the
// human decisions on them. A proposal is untrusted text: it is shown as inert
// text, never applied to a checkout and never run. Approval only records a
// decision; the Run control stays disabled until an isolated runner exists.
import { useState } from 'react'
import { AlertCircle, Ban, Check, FilePlus2, Play, RefreshCw, X } from 'lucide-react'
import { api, isApiError } from './api'
import { useLoad } from './bitbucket/useLoad'
import { Pill } from './components'
import type { TestProposal, TestRun } from './types'

const STATUS: Record<TestProposal['status'], { label: string; kind: string }> = {
  pending: { label: 'Pending decision', kind: 'muted' },
  approved: { label: 'Approved', kind: 'good' },
  rejected: { label: 'Rejected', kind: 'danger' },
}
const when = (iso: string) => new Date(iso).toLocaleString()
const message = (error: unknown) => (error instanceof Error ? error.message : String(error))
const post = <T,>(path: string, body: unknown) =>
  api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

/**
 * `runRefused`: the scan is not of the synthetic demo repository, so the API refuses every run
 * request (403) and records nothing. Unknown is treated as refused.
 */
export function TestProposalsPanel({ scanId, runRefused = false }: { scanId: string; runRefused?: boolean }) {
  const base = `/api/scans/${scanId}/tests/proposals`
  const list = useLoad(() => api<TestProposal[]>(base), `test-proposals:${scanId}`)
  const proposals = (list.data ?? []).filter(item => item.scan_id === scanId)

  const [form, setForm] = useState({ target_path: 'tests/test_', content: '', origin: 'human' as TestProposal['origin'], finding_ref: '', rationale: '' })
  const [adding, setAdding] = useState(false)
  const [addResult, setAddResult] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  const add = async () => {
    setAdding(true); setAddResult(null)
    try {
      const created = await post<TestProposal>(base, {
        target_path: form.target_path.trim(), content: form.content, origin: form.origin,
        ...(form.finding_ref.trim() ? { finding_ref: form.finding_ref.trim() } : {}),
        ...(form.rationale.trim() ? { rationale: form.rationale.trim() } : {}),
      })
      setAddResult({ kind: 'success', message: `Stored as a proposal for ${created.target_path}. It is pending a decision; nothing was applied or run.` })
      setForm(previous => ({ ...previous, content: '', finding_ref: '', rationale: '' }))
      list.reload()
    } catch (error) { setAddResult({ kind: 'error', message: `Not stored: ${message(error)}` }) }
    finally { setAdding(false) }
  }

  return (
    <section className="panel proposals-panel" aria-label="Proposed regression tests">
      <div className="panel-head">
        <div>
          <h3><FilePlus2 size={17} /> Proposed regression tests <Pill kind="warning">NOT APPLIED · NOT RUN</Pill></h3>
          <p>A proposal is a suggested new test file, kept as text and bound to this scan’s commits. Approving records a human decision only. Nothing is written to a repository and nothing is executed.</p>
        </div>
        <button className="secondary-button" onClick={list.reload} disabled={list.loading}><RefreshCw size={15} className={list.loading ? 'spin' : ''} /> Refresh</button>
      </div>

      {list.loading && !list.data && <div className="bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>Loading proposals…</h3></div></div>}
      {list.error && (
        <div className="bb-state bb-error" role="alert"><AlertCircle size={22} /><div><h3>Could not load the proposals</h3><p className="bb-error-message">{list.error.message}</p></div>
          <button className="secondary-button" onClick={list.reload}><RefreshCw size={15} /> Retry</button></div>
      )}
      {list.data && proposals.length === 0 && <div className="empty-state"><h3>No test has been proposed for this scan</h3><p>Add one below. It will wait for an explicit decision.</p></div>}

      {proposals.map(item => <Proposal key={item.id} proposal={item} base={base} onChanged={list.reload} runRefused={runRefused} />)}

      <details className="proposal-add">
        <summary>Propose a new test file</summary>
        <div className="proposal-form">
          <label><span className="micro-label">TARGET PATH (new file inside a tests directory)</span>
            <input aria-label="Target path" value={form.target_path} onChange={event => setForm({ ...form, target_path: event.target.value })} /></label>
          <label><span className="micro-label">WHO WROTE THE TEST TEXT</span>
            <select aria-label="Origin" value={form.origin} onChange={event => setForm({ ...form, origin: event.target.value as TestProposal['origin'] })}>
              <option value="human">A person</option><option value="imported_ai_review">An AI review (unverified)</option>
            </select></label>
          <label><span className="micro-label">FINDING ID (optional)</span>
            <input aria-label="Finding id" value={form.finding_ref} onChange={event => setForm({ ...form, finding_ref: event.target.value })} /></label>
          <label><span className="micro-label">WHY (optional)</span>
            <input aria-label="Rationale" value={form.rationale} onChange={event => setForm({ ...form, rationale: event.target.value })} /></label>
          <label className="proposal-form-wide"><span className="micro-label">TEST SOURCE (Python pytest only; stored as text, not run)</span>
            <textarea aria-label="Test source" rows={10} spellCheck={false} value={form.content} onChange={event => setForm({ ...form, content: event.target.value })} /></label>
          <div className="proposal-form-wide proposal-actions">
            <button className="primary-button" onClick={add} disabled={adding || !form.content.trim() || !form.target_path.trim()}>{adding ? 'Storing…' : 'Store proposal'}</button>
            {addResult && <p className={`ai-import-status ${addResult.kind}`} role={addResult.kind === 'error' ? 'alert' : 'status'}>{addResult.message}</p>}
          </div>
        </div>
      </details>
    </section>
  )
}

function Proposal({ proposal, base, onChanged, runRefused }: { proposal: TestProposal; base: string; onChanged: () => void; runRefused: boolean }) {
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const status = STATUS[proposal.status]
  const lines = proposal.content.split('\n')
  // Run requests of this proposal. In this build every one of them is BLOCKED: nothing runs.
  const runs = useLoad(() => api<TestRun[]>(`${base}/${proposal.id}/runs`), `test-runs:${proposal.id}`)
  const [runResult, setRunResult] = useState<string | null>(null)

  const requestRun = async () => {
    setBusy(true); setRunResult(null)
    try {
      await post<unknown>(`${base}/${proposal.id}/runs`, { requested_by: name })
      // No build of ShipSafe answers a run request with success; if one ever did, do not call it a result.
      setRunResult('The request was accepted, but this dashboard has no way to show an execution. Check the run history.')
    } catch (exc) {
      setRunResult(isApiError(exc, 'execution_unavailable') ? `BLOCKED. ${exc.message}` : `Run not requested: ${message(exc)}`)
    } finally { setBusy(false); runs.reload() }
  }

  const decide = async (decision: 'approved' | 'rejected') => {
    setBusy(true); setError(null)
    try {
      await post<TestProposal>(`${base}/${proposal.id}/decisions`, { decision, decided_by: name, ...(note.trim() ? { note: note.trim() } : {}) })
      setNote(''); onChanged()
    } catch (exc) { setError(`Decision not recorded: ${message(exc)}`) }
    finally { setBusy(false) }
  }

  return (
    <article className="proposal" aria-label={`Proposal ${proposal.target_path}`}>
      <div className="proposal-head">
        <div>
          <h4><code>{proposal.target_path}</code> <Pill kind={status.kind}>{status.label}</Pill>{proposal.stale && <Pill kind="danger">Stale · pull request has new commits</Pill>}</h4>
          <p>Proposed {when(proposal.created_at)} · text written by {proposal.origin === 'human' ? 'a person' : 'an AI review (unverified)'}{proposal.finding_ref ? <> · for finding <code>{proposal.finding_ref}</code></> : null} · commits <code>{proposal.base_commit.slice(0, 12)}</code> → <code>{proposal.head_commit.slice(0, 12)}</code></p>
          {proposal.rationale && <p>{proposal.rationale}</p>}
        </div>
        <button className="secondary-button" onClick={requestRun} disabled={busy || runRefused || !proposal.eligible_to_run || name.trim().length < 2}
          title={runRefused ? 'Not available for this repository: runs can only be requested for the synthetic demo repository.' : 'No verified isolated runner is available. A request is recorded as BLOCKED; nothing is run.'}><Play size={14} /> Run <Ban size={13} /> BLOCKED</button>
      </div>
      {runResult && <p className="proposal-run-result" role="status">{runResult}</p>}
      <p className="proposal-blocked">{runRefused
        ? 'Run is not available for this repository: ShipSafe only accepts run requests for the synthetic demo repository, and even there nothing is executed. Run this test in your own environment.'
        : <>Run is blocked: no verified isolated runner is available. {proposal.eligible_to_run ? 'This proposal is approved for these commits and would be allowed to run once one is.' : proposal.stale ? 'This proposal is stale and could not run even then.' : 'Only an approved proposal could run.'}</>}</p>

      <div className="diff-viewer proposal-diff">
        <div className="diff-toolbar"><span>New file · {proposal.target_path}</span><span className="diff-count"><b>+{lines.length}</b><em>-0</em></span></div>
        <div className="code-lines" role="region" aria-label={`Proposed content of ${proposal.target_path}`}>
          {lines.map((line, index) => <div className="code-line add" key={index}><span className="line-num">{index + 1}</span><span>+{line || ' '}</span></div>)}
        </div>
      </div>

      <div className="proposal-decisions">
        <div className="micro-label">DECISIONS (oldest first; never rewritten)</div>
        {proposal.decisions.length === 0 ? <p className="muted-small">No decision yet.</p> : (
          <ol>{proposal.decisions.map(item => <li key={item.id}><strong>{item.decision === 'approved' ? 'Approved' : 'Rejected'}</strong> by {item.decided_by} · {when(item.decided_at)}{item.note ? ` · ${item.note}` : ''}</li>)}</ol>
        )}
        <div className="proposal-decide">
          <input aria-label={`Your name, for ${proposal.target_path}`} placeholder="Your name" value={name} onChange={event => setName(event.target.value)} />
          <input aria-label={`Note, for ${proposal.target_path}`} placeholder="Note (optional)" value={note} onChange={event => setNote(event.target.value)} />
          <button className="secondary-button" onClick={() => decide('approved')} disabled={busy || name.trim().length < 2 || proposal.stale} title={proposal.stale ? 'A stale proposal cannot be approved' : undefined}><Check size={14} /> Approve</button>
          <button className="secondary-button" onClick={() => decide('rejected')} disabled={busy || name.trim().length < 2}><X size={14} /> Reject</button>
        </div>
        {error && <p className="ai-import-status error" role="alert">{error}</p>}
        <p className="muted-small">{proposal.identity_note}</p>
        {runs.data && runs.data.length > 0 && <>
          <div className="micro-label">RUN REQUESTS (newest first)</div>
          <ol className="proposal-runs">{runs.data.map(run => (
            <li key={run.id}><strong>{run.executed ? run.status : 'BLOCKED · not executed'}</strong> · requested by {run.requested_by} · {when(run.requested_at)} · runner: {run.runner}{run.reason ? ` · ${run.reason}` : ''}</li>
          ))}</ol>
        </>}
        {runs.error && <p className="muted-small">The run history could not be loaded.</p>}
      </div>
    </article>
  )
}
