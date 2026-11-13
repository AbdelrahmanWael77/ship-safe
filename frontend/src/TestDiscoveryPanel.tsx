// Phase 4 task A: existing tests that may exercise the change of the scan on
// screen, as GET /api/scans/{id}/tests/discovery returns them. The API finds
// them by parsing test files; nothing is collected or run, and this panel
// never says otherwise.
import { AlertCircle, FlaskConical, RefreshCw, SearchCode } from 'lucide-react'
import { useRef } from 'react'
import { api } from './api'
import { useLoad } from './bitbucket/useLoad'
import { Pill } from './components'
import type { TestDiscovery } from './types'

const reasonText = (reason: TestDiscovery['candidates'][number]['reasons'][number]) =>
  reason.kind === 'mentions_changed_function'
    ? `mentions changed function ${reason.function}() of ${reason.changed_file}`
    : `its file imports ${reason.changed_file}`

// One discovery per scan for this page load: it reads up to 60 test files from Bitbucket, so
// coming back to the page reuses the answer. Refresh (and Retry) always ask the API again.
const cache = new Map<string, TestDiscovery>()
/** Tests only: forget every cached discovery. */
export const clearDiscoveryCache = () => cache.clear()

export function TestDiscoveryPanel({ scanId }: { scanId: string }) {
  const force = useRef(false)
  const discovery = useLoad(() => {
    const hit = cache.get(scanId)
    if (hit && !force.current) return Promise.resolve(hit)
    force.current = false
    return api<TestDiscovery>(`/api/scans/${scanId}/tests/discovery`).then(answer => { cache.set(scanId, answer); return answer })
  }, `test-discovery:${scanId}`)
  const refresh = () => { force.current = true; discovery.reload() }
  // While another scan is loading, the previous answer must not be shown as if it were the new one.
  const found = discovery.data && discovery.data.scan_id === scanId ? discovery.data : null

  return (
    <section className="panel discovery-panel" aria-label="Existing tests for this change">
      <div className="panel-head">
        <div>
          <h3><SearchCode size={17} /> Existing tests that may exercise this change <Pill kind="warning">NOT RUN</Pill></h3>
          <p>Found by reading test files at the scanned commit. Nothing was collected or executed; a listed test is not known to cover the change.</p>
        </div>
        <button className="secondary-button" onClick={refresh} disabled={discovery.loading}>
          <RefreshCw size={15} className={discovery.loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      {discovery.loading && !found && <div className="bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>Looking for existing tests…</h3><p>Reading test files at the scanned commit. For a Bitbucket pull request this can take 10–30 seconds.</p></div></div>}
      {discovery.error && (
        <div className="bb-state bb-error" role="alert">
          <AlertCircle size={22} />
          <div><h3>Could not discover tests</h3><p className="bb-error-message">{discovery.error.message}</p></div>
          <button className="secondary-button" onClick={refresh}><RefreshCw size={15} /> Retry</button>
        </div>
      )}

      {found && <>
        <p className="discovery-summary">
          {found.test_files_found} test {found.test_files_found === 1 ? 'file' : 'files'} · {found.tests_found} {found.tests_found === 1 ? 'test' : 'tests'} · {found.candidate_count} {found.candidate_count === 1 ? 'candidate' : 'candidates'} · commit <code>{found.commit.slice(0, 12)}</code>
        </p>
        {found.incomplete && (
          <p className="bb-footnote" role="note">
            Incomplete discovery.
            {found.test_files_unread > 0 && <> {found.test_files_unread} test {found.test_files_unread === 1 ? 'file was' : 'files were'} not read (limit reached).</>}
            {found.unparsed_test_files.length > 0 && <> Could not be read or parsed: {found.unparsed_test_files.join(', ')}.</>}
            {found.candidate_count > found.candidates.length && <> Only the first {found.candidates.length} candidates are listed.</>}
          </p>
        )}

        {found.candidates.length === 0 ? (
          <div className="empty-state"><h3>No existing test was matched to this change</h3><p>{found.tests_found === 0 ? 'No test file was found at this commit (Python test_*.py / *_test.py, Dart *_test.dart).' : 'No discovered test file imports a changed module.'} That is a gap in coverage, not a sign of safety.</p></div>
        ) : (
          <div className="history-table-wrap">
            <table className="history-table bb-table">
              <thead><tr><th>Test</th><th>Why it was selected</th><th>Related findings</th><th>Status</th></tr></thead>
              <tbody>
                {found.candidates.map(item => (
                  <tr key={item.test_id}>
                    <td><div className="comparison-cell"><FlaskConical size={17} /><div><strong>{item.name}</strong><small>{item.file}:{item.line}{item.changed_in_this_scan ? ' · changed in this scan' : ''}</small></div></div></td>
                    <td><ul className="discovery-reasons">{item.reasons.map((reason, index) => <li key={index}>{reasonText(reason)}</li>)}</ul></td>
                    <td>
                      {item.related_static_finding_ids.length + item.related_ai_finding_ids.length === 0 ? <span className="bb-muted">None</span> : <>
                        {item.related_static_finding_ids.length > 0 && <span className="discovery-related">{item.related_static_finding_ids.length} static</span>}
                        {item.related_ai_finding_ids.length > 0 && <span className="discovery-related">{item.related_ai_finding_ids.length} AI (unverified)</span>}
                      </>}
                    </td>
                    <td><Pill kind="muted">Suggested · not run</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="discovery-gaps">
          <h4>Coverage gaps</h4>
          {found.coverage_gaps.length === 0 ? <p className="muted-small">Every changed file is imported by at least one discovered test file. That does not mean the changed behaviour is tested.</p> : (
            <ul>{found.coverage_gaps.map(gap => (
              <li key={gap.changed_file}><code>{gap.changed_file}</code> — {gap.reason}{gap.static_finding_ids.length + gap.ai_finding_ids.length > 0 && <strong> {gap.static_finding_ids.length + gap.ai_finding_ids.length} finding{gap.static_finding_ids.length + gap.ai_finding_ids.length !== 1 ? 's' : ''} here with no matched test.</strong>}</li>
            ))}</ul>
          )}
        </div>
        <details className="discovery-heuristics"><summary>How tests are selected</summary><ul>{found.heuristics.map((line, index) => <li key={index}>{line}</li>)}</ul></details>
      </>}
    </section>
  )
}
