import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowLeft, ArrowRight, ArrowUpRight, ChevronDown, ExternalLink, FlaskConical, GitCommitHorizontal, GitPullRequest, Info, RefreshCw, ScanSearch, ShieldAlert, Sparkles } from 'lucide-react'
import { api, isApiError } from '../api'
import { PROVIDER_COMPANY, reviewOrigin, runModelReview, usageText } from '../aiReview'
import { DiffViewer, FileIcon, FindingCard, Pill, Severity } from '../components'
import type { AIProvider, AIProviderName, AIReview, BitbucketStatus, PullRequestDetail, Report } from '../types'
import { getPullRequest, getScan, scanPullRequest } from './client'
import { ConnectionStatus, NotConfigured } from './ConnectionStatus'
import { ErrorPanel } from './ErrorPanel'
import type { BitbucketNavigate, BitbucketSelection } from './pages'
import { StaleBadge } from './StaleBadge'
import type { Loaded } from './useLoad'
import { useLoad } from './useLoad'

const when = (iso: string | null) => {
  if (!iso) return 'Not reported'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? 'Not reported' : date.toLocaleString()
}
const short = (sha: string | null) => (sha ? sha.slice(0, 12) : 'unknown')
const Sha = ({ value }: { value: string | null }) => (value ? <code className="bb-sha">{value}</code> : <span className="bb-muted">Not available</span>)

// "Also review with AI" is the person's confirmation that this repository's code may be sent
// to the chosen provider. The provider is remembered per repository in this browser only.
const autoReviewKey = (repositoryId: string) => `shipsafe.ai-review:${repositoryId}`
const readAutoReview = (repositoryId: string): AIProviderName | null => {
  try {
    const value = window.localStorage.getItem(autoReviewKey(repositoryId))
    return value === 'openai' || value === 'gemini' ? value : null
  } catch { return null }
}
const writeAutoReview = (repositoryId: string, value: AIProviderName | null) => {
  try { if (value) window.localStorage.setItem(autoReviewKey(repositoryId), value); else window.localStorage.removeItem(autoReviewKey(repositoryId)) } catch { /* storage unavailable */ }
}

/**
 * One pull request: what Bitbucket says about it now, its stored scans, and a
 * scan report (a new scan, or a stored one). A scan is sent with the head
 * commit shown on this page, so the API refuses it (409 `head_changed`) when
 * the pull request has moved on; the page then reloads the pull request.
 */
export function PrAnalysisPage({ status, selection, navigate, onScanned, onOpenReport, providers = null, onShown, onReviewed }: {
  status: Loaded<BitbucketStatus>
  selection: BitbucketSelection
  navigate: BitbucketNavigate
  /** A scan was stored: the app refreshes its scan history. */
  onScanned: () => void
  /** Open a stored scan in the existing dashboard pages, optionally on a given page. */
  onOpenReport: (id: string, page?: 'findings' | 'tests') => void
  /** A stored (not mock) report is now on screen: the dashboard pages follow it. */
  onShown?: (report: Report) => void
  /** An AI review of a stored scan was just stored. */
  onReviewed?: (scanId: string) => void
  /** The AI review providers of the API server (null while unknown). */
  providers?: AIProvider[] | null
}) {
  const configured = status.data?.configured === true
  const { slug, pullRequestId } = selection
  const chosen = slug !== null && pullRequestId !== null
  const detail = useLoad(() => getPullRequest(slug as string, pullRequestId as string), `pull-request:${slug}:${pullRequestId}`, configured && chosen)
  // While another pull request is loading, the previous one must not be shown as if it were the new one.
  const pull: PullRequestDetail | null = detail.data && detail.data.id === pullRequestId && detail.data.repository.slug === slug ? detail.data : null

  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState<'scan' | 'open' | null>(null)
  const [failure, setFailure] = useState<{ error: Error; retry: () => void; title: string } | null>(null)
  const [headChanged, setHeadChanged] = useState(false)
  const [selectedFile, setSelectedFile] = useState('')
  const diffRef = useRef<HTMLDivElement>(null)
  const [aiReview, setAIReview] = useState<AIReview | null>(null)
  const [aiState, setAIState] = useState<{ kind: 'running'; label: string } | { kind: 'error'; message: string; provider: AIProvider } | null>(null)
  // The provider the person confirmed for this repository, or null (nothing is sent).
  const [autoReview, setAutoReview] = useState<AIProviderName | null>(null)
  const [pickedProvider, setPickedProvider] = useState<AIProviderName | null>(null)
  const configuredProviders = (providers ?? []).filter(item => item.configured)
  const aiOn = configuredProviders.length > 0
  const reviewProvider = configuredProviders.find(item => item.provider === (autoReview ?? pickedProvider))
    ?? configuredProviders.find(item => item.provider === 'openai') ?? configuredProviders[0] ?? null
  const autoProvider = autoReview ? configuredProviders.find(item => item.provider === autoReview) ?? null : null

  // A different pull request: nothing from the previous one may stay on screen.
  const current = useRef('')
  const identity = `${slug}:${pullRequestId}`
  useEffect(() => {
    current.current = identity
    setReport(null); setBusy(null); setFailure(null); setHeadChanged(false); setSelectedFile('')
    setAIReview(null); setAIState(null)
  }, [identity])
  const repositoryId = pull?.repository.id ?? null
  useEffect(() => { setAutoReview(repositoryId ? readAutoReview(repositoryId) : null) }, [repositoryId])

  if (!configured) return <ConnectionStatus status={status} />
  if (isApiError(detail.error, 'bitbucket_not_configured')) {
    return <NotConfigured onRetry={() => { status.reload(); detail.reload() }} />
  }
  const back = <button className="secondary-button" onClick={() => navigate('pull-requests')}><ArrowLeft size={15} /> Pull requests</button>
  if (!chosen) {
    return (
      <div className="panel"><div className="empty-state">
        <h3>No pull request selected</h3>
        <p>Choose a pull request from the list to see its scans or scan it.</p>
        <p>{back}</p>
      </div></div>
    )
  }

  const show = (next: Report) => { setReport(next); setSelectedFile(next.files[0]?.path ?? ''); setAIReview(null); setAIState(null); if (!next.mock) onShown?.(next) }

  /** Send a stored scan to the confirmed AI provider (the person ticked the checkbox). */
  const reviewWithAI = async (scanId: string, provider: AIProvider) => {
    const started = identity
    setAIState({ kind: 'running', label: provider.label })
    try {
      const review = await runModelReview(scanId, provider.provider, true)
      onReviewed?.(scanId)
      if (current.current !== started) return
      setAIReview(review); setAIState(null)
    } catch (error) {
      if (current.current === started) setAIState({ kind: 'error', message: error instanceof Error ? error.message : String(error), provider })
    }
  }

  /** The newest AI review (OpenAI, Gemini or imported Claude) of a stored scan, if any. */
  const loadReview = async (scanId: string) => {
    const started = identity
    try {
      const reviews = await api<AIReview[]>(`/api/scans/${encodeURIComponent(scanId)}/ai/reviews`)
      if (current.current === started && Array.isArray(reviews)) setAIReview(reviews[0] ?? null)
    } catch { /* the scan report is still shown without it */ }
  }

  const scan = async () => {
    if (!pull || !pull.source_sha) return
    const started = identity
    setBusy('scan'); setFailure(null); setHeadChanged(false)
    try {
      const next = await scanPullRequest(slug, pullRequestId, pull.source_sha)
      if (current.current !== started) return
      show(next); detail.reload(); onScanned()
      if (autoProvider && !next.mock) void reviewWithAI(next.id, autoProvider)
    } catch (error) {
      if (current.current !== started) return
      if (isApiError(error, 'head_changed')) { setHeadChanged(true); setReport(null); detail.reload() }
      else setFailure({ error: error instanceof Error ? error : new Error(String(error)), retry: scan, title: 'The scan failed' })
    } finally { if (current.current === started) setBusy(null) }
  }

  const openStored = async (id: string) => {
    const started = identity
    setBusy('open'); setFailure(null)
    try {
      const stored = await getScan(id)
      if (current.current === started) { show(stored); if (!stored.mock) void loadReview(stored.id) }
    } catch (error) {
      if (current.current === started) setFailure({ error: error instanceof Error ? error : new Error(String(error)), retry: () => openStored(id), title: 'Could not open the stored scan' })
    } finally { if (current.current === started) setBusy(null) }
  }

  // The pull request's own scan list was compared with Bitbucket just now; the
  // stored-scan route never is. Prefer the checked binding for the same scan.
  const binding = report ? pull?.scans.find(item => item.id === report.id)?.binding ?? report.binding ?? null : null
  const selected = report?.files.find(file => file.path === selectedFile) ?? report?.files[0]
  const openFile = (path: string) => { setSelectedFile(path); diffRef.current?.scrollIntoView?.({ block: 'start' }) }

  return (
    <>
      <div className="bb-back-row">{back}</div>
      {detail.loading && !pull && (
        <div className="panel bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>Loading pull request {pullRequestId} from Bitbucket…</h3></div></div>
      )}
      {detail.error && <ErrorPanel title="Could not load the pull request" error={detail.error} onRetry={detail.reload} />}

      {pull && (
        <div className="panel bb-pr">
          <div className="panel-head">
            <div>
              <h3><GitPullRequest size={17} /> #{pull.id} {pull.title} <Pill kind="muted">{pull.state.toUpperCase()}</Pill></h3>
              <p>{pull.author ?? 'Author not reported'} · <code>{pull.source_ref}</code> → <code>{pull.target_ref}</code> · <code>{pull.repository.id}</code> · updated {when(pull.updated_at)}</p>
            </div>
            <div className="bb-head-actions">
              <a className="secondary-button" href={pull.url} target="_blank" rel="noopener noreferrer">
                Open in Bitbucket <ExternalLink size={14} /><span className="visually-hidden"> (opens in a new tab)</span>
              </a>
              <button className="secondary-button" onClick={detail.reload} disabled={detail.loading || busy !== null}>
                <RefreshCw size={15} className={detail.loading ? 'spin' : ''} /> Reload
              </button>
              <button className="primary-button" onClick={scan} disabled={!pull.scannable || !pull.source_sha || busy !== null || detail.loading || aiState?.kind === 'running'}>
                {busy === 'scan' ? <RefreshCw size={16} className="spin" /> : <ScanSearch size={16} />} {busy === 'scan' ? 'Scanning…' : autoProvider ? 'Scan this pull request + AI review' : 'Scan this pull request'}
              </button>
            </div>
          </div>
          {aiOn && reviewProvider && (
            <div className="bb-ai-toggle-row">
              {configuredProviders.length > 1 && (
                <label className="bb-field ai-provider-select">
                  <span className="micro-label">AI MODEL</span>
                  <span className="select-shell">
                    <select aria-label="AI model" value={reviewProvider.provider} onChange={event => {
                      const next = event.target.value as AIProviderName
                      setPickedProvider(next)
                      // A different company: the confirmation must be given again.
                      if (autoReview && autoReview !== next) { setAutoReview(null); writeAutoReview(pull.repository.id, null) }
                    }}>
                      {configuredProviders.map(item => <option key={item.provider} value={item.provider}>{item.label} · {item.model}</option>)}
                    </select>
                    <ChevronDown size={15} />
                  </span>
                </label>
              )}
              <label className="ai-share-ack bb-ai-toggle">
                <input type="checkbox" checked={autoProvider !== null} onChange={event => {
                  const next = event.target.checked ? reviewProvider.provider : null
                  setAutoReview(next); writeAutoReview(pull.repository.id, next)
                }} />
                <span><strong><Sparkles size={13} /> Also review with AI</strong> ({reviewProvider.label} <code>{reviewProvider.model}</code>) after scanning. I am allowed to send this repository's changed code (secret-redacted, best effort) to {PROVIDER_COMPANY[reviewProvider.provider]}. Remembered for <code>{pull.repository.id}</code> in this browser.</span>
              </label>
            </div>
          )}
          <dl className="bb-facts">
            <div><dt>Head commit (source)</dt><dd><Sha value={pull.source_sha} /></dd></div>
            <div><dt>Target branch tip</dt><dd><Sha value={pull.target_sha} /></dd></div>
          </dl>
          {(() => {
            const sameHead = pull.source_sha ? pull.scans.find(item => item.binding.head_commit === pull.source_sha) : undefined
            return sameHead ? (
              <p className="bb-footnote" role="note" aria-label="Already scanned">
                Already scanned at this head commit ({when(sameHead.created_at)}). Scanning again gives the same static result{autoProvider ? ` and sends the code to ${autoProvider.label} again for another paid review` : ''}. Use View in the list below to open it.
              </p>
            ) : null
          })()}
          <p className="bb-note">A scan reads from Bitbucket only. It compares the merge base of the two branches with the head commit above and is stored bound to both full commit ids. Static analysis only: no code is run.</p>
          {!pull.scannable && (
            <p className="bb-footnote" role="note">This pull request cannot be scanned: {pull.not_scannable_reason ?? 'Bitbucket did not report its commits.'}{pull.not_scannable_code && <> (<code>{pull.not_scannable_code}</code>)</>}</p>
          )}
        </div>
      )}

      {busy === 'scan' && (
        <div className="panel bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>Scanning pull request {pullRequestId}…</h3><p>ShipSafe is reading the changed files from Bitbucket. A large pull request can take a while; there is no progress report.</p></div></div>
      )}
      {headChanged && (
        <div className="panel bb-state bb-warning-panel" role="alert">
          <AlertTriangle size={22} />
          <div>
            <h3>The pull request has new commits</h3>
            <p>Its head moved after this page loaded it, so nothing was scanned. The pull request has been reloaded: check the head commit above, then scan again.</p>
          </div>
        </div>
      )}
      {failure && <ErrorPanel title={failure.title} error={failure.error} onRetry={failure.retry} />}

      {pull && (
        <div className="panel">
          <div className="panel-head">
            <div><h3>Scans of this pull request</h3><p>{pull.stale_checked ? 'Compared with the pull request’s head just now.' : 'Not compared with Bitbucket: the head commit could not be read.'}</p></div>
            <span className="pill pill-muted">{pull.scans.length} {pull.scans.length === 1 ? 'scan' : 'scans'}</span>
          </div>
          {pull.scans.length === 0 ? (
            <div className="empty-state"><h3>Not scanned yet</h3><p>No scan of this pull request is stored.{pull.scannable ? ' Use “Scan this pull request”.' : ''}</p></div>
          ) : (
            <div className="history-table-wrap">
              <table className="history-table bb-table">
                <thead><tr><th>Scanned</th><th>Commits (base → head)</th><th>Findings</th><th>Risk</th><th>State</th><th><span className="visually-hidden">Actions</span></th></tr></thead>
                <tbody>
                  {pull.scans.map(item => (
                    <tr key={item.id} className={report?.id === item.id ? 'bb-row-open' : ''}>
                      <td>{when(item.created_at)}</td>
                      <td><code title={`${item.binding.base_commit} → ${item.binding.head_commit}`}>{short(item.binding.base_commit)}</code> → <code>{short(item.binding.head_commit)}</code></td>
                      <td>{item.summary.finding_count}</td>
                      <td>{item.summary.risk_score}/100</td>
                      <td><StaleBadge binding={item.binding} /></td>
                      <td>
                        <button className="table-action" onClick={() => openStored(item.id)} disabled={busy !== null}>
                          {report?.id === item.id ? 'Shown below' : 'View'}<span className="visually-hidden"> scan of {when(item.created_at)}</span> <ArrowRight size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {report && (
        <section aria-label="Scan report" className="bb-report">
          <div className="panel">
            <div className="panel-head">
              <div>
                <h3>Scan report {report.mock && <Pill kind="warning">MOCK DATA</Pill>} <StaleBadge binding={binding} /></h3>
                <p>Scanned {when(report.created_at)} · {report.summary.files_changed} {report.summary.files_changed === 1 ? 'file' : 'files'} · +{report.summary.lines_added} −{report.summary.lines_removed} · {report.summary.finding_count} {report.summary.finding_count === 1 ? 'finding' : 'findings'} · risk {report.summary.risk_score}/100 · {report.summary.recommendation}</p>
              </div>
              {!report.mock && (
                <button className="secondary-button" onClick={() => onOpenReport(report.id)}>Open in dashboard <ArrowRight size={15} /></button>
              )}
            </div>
            <dl className="bb-facts">
              <div><dt><GitCommitHorizontal size={13} /> Base commit ({binding?.comparison === 'merge-base' ? 'merge base' : 'direct'})</dt><dd><Sha value={binding?.base_commit ?? null} /></dd></div>
              <div><dt><GitCommitHorizontal size={13} /> Head commit</dt><dd><Sha value={binding?.head_commit ?? null} /></dd></div>
            </dl>
            {(report.summary.truncated || report.summary.import_analysis_truncated) && (
              <p className="bb-footnote" role="note">
                Incomplete report.
                {report.summary.truncated && <> {report.summary.files_omitted ?? 0} changed {report.summary.files_omitted === 1 ? 'file is' : 'files are'} not listed.</>}
                {report.summary.import_analysis_truncated && <> The import analysis was cut: {report.summary.import_files_skipped ?? 0} files were not read, so affected modules may be missing.</>}
              </p>
            )}
          </div>

          <h2 className="bb-subhead">Findings <span className="pill pill-muted">Static suspicions, not verified</span></h2>
          {report.findings.length ? (
            <div className="findings-grid">{report.findings.map(finding => <FindingCard key={finding.id} finding={finding} onOpenFile={openFile} />)}</div>
          ) : (
            <div className="panel"><div className="empty-state"><h3>No static findings</h3><p>{report.files.some(file => !file.path.endsWith('.py')) ? 'Static rules cover Python files only; the other changed files were not analysed by them. Use the AI review below.' : 'Static analysis found no known patterns in this diff; that does not establish safety.'}</p></div></div>
          )}

          {!report.mock && (
            <section className="panel bb-ai" aria-label="AI review">
              <div className="panel-head">
                <div>
                  <h3><Sparkles size={17} /> AI review <Pill kind="warning">UNVERIFIED AI SUGGESTIONS</Pill></h3>
                  <p>{aiReview ? `${reviewOrigin(aiReview)} · ${when(aiReview.imported_at)} · suspicions from the diff; nothing was executed` : 'Risks and test ideas proposed by an AI model from this scan’s diff.'}</p>
                  {aiReview && usageText(aiReview) && <p className="bb-ai-usage">{usageText(aiReview)}</p>}
                </div>
                {aiReview && (
                  <div className="bb-head-actions">
                    <button className="secondary-button" onClick={() => onOpenReport(report.id, 'findings')}><ShieldAlert size={15} /> Risk findings</button>
                    <button className="secondary-button" onClick={() => onOpenReport(report.id, 'tests')}><FlaskConical size={15} /> Test intelligence</button>
                  </div>
                )}
              </div>
              {aiState?.kind === 'running' && <div className="bb-state" role="status"><div className="spinner bb-spinner" /><div><h3>{aiState.label} is reviewing the changes…</h3><p>This usually takes 10–60 seconds.</p></div></div>}
              {aiState?.kind === 'error' && <div role="alert" className="bb-ai-error"><p><AlertTriangle size={15} /> {aiState.provider.label} review failed: {aiState.message}</p><button className="secondary-button" onClick={() => reviewWithAI(report.id, aiState.provider)}><RefreshCw size={14} /> Try again</button></div>}
              {aiReview && aiState?.kind !== 'running' && (
                <>
                  <p className="bb-ai-summary"><strong>{aiReview.recommendation === 'block_release' ? 'Suggested: Block release' : aiReview.recommendation === 'manual_review' ? 'Suggested: Manual review' : 'Insufficient evidence'}</strong> · {aiReview.summary}</p>
                  <h4 className="bb-ai-subhead">Risks ({aiReview.findings.length})</h4>
                  {aiReview.findings.length ? <div className="ai-risk-list">{aiReview.findings.map((finding, index) => (
                    <div className="ai-risk-row" key={`${index}-${finding.title}`}>
                      <Severity level={finding.severity} />
                      <div>
                        <strong>{finding.id ? `${finding.id} · ` : ''}{finding.title}</strong>
                        <button className="text-link" onClick={() => openFile(finding.file)}>{finding.file}{finding.line ? `:${finding.line}` : ''}<ArrowUpRight size={13} /></button>
                        <p>{finding.rationale}</p>
                      </div>
                    </div>
                  ))}</div> : <p className="small-para">The AI review proposed no risks. That does not establish safety.</p>}
                  <h4 className="bb-ai-subhead">Test ideas ({aiReview.test_ideas.length}) <Pill kind="muted">NOT RUN</Pill></h4>
                  {aiReview.test_ideas.length ? <ul className="bb-ai-tests">{aiReview.test_ideas.map((idea, index) => <li key={index}><strong>{idea.title}</strong> — {idea.expected_behavior}</li>)}</ul> : <p className="small-para">No test ideas proposed.</p>}
                </>
              )}
              {!aiReview && !aiState && (
                aiOn
                  ? (autoProvider
                      ? <button className="primary-button" onClick={() => reviewWithAI(report.id, autoProvider)}><Sparkles size={16} /> Review this scan with {autoProvider.label}</button>
                      : <p className="small-para">Tick “Also review with AI” above to send this scan to an AI model, or import a Claude Code review from the dashboard’s Claude Review page.</p>)
                  : <p className="small-para">{providers ? 'No AI model is configured on the API server (SHIPSAFE_OPENAI_API_KEY or SHIPSAFE_GEMINI_API_KEY). Import a Claude Code review from the dashboard’s Claude Review page instead.' : 'Checking which AI models are available…'}</p>
              )}
            </section>
          )}

          <h2 className="bb-subhead" ref={diffRef}>Diff</h2>
          {selected ? (
            <div className="code-layout">
              <div className="panel file-browser">
                <div className="panel-head"><div><h3>Changed files</h3><p>{report.files.length} listed</p></div></div>
                {report.files.map(file => (
                  <button className={`file-select ${selected.path === file.path ? 'selected' : ''}`} key={file.path} aria-pressed={selected.path === file.path} onClick={() => setSelectedFile(file.path)}>
                    <FileIcon path={file.path} /><span><strong>{file.path.split('/').pop()}</strong><small>{file.path}</small></span>
                  </button>
                ))}
              </div>
              <div className="code-main"><DiffViewer file={selected} /></div>
            </div>
          ) : (
            <div className="panel"><div className="empty-state"><h3>No changed files</h3><p>The scan listed no file changes between the two commits.</p></div></div>
          )}
          <div className="disclaimer-box"><Info size={18} />{report.disclaimer}</div>
        </section>
      )}
    </>
  )
}
