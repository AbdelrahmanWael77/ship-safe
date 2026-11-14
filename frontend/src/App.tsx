import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import {
  Activity, AlertCircle, AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight,
  BookOpen, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight,
  CircleHelp, Clock3, Code2, Copy, Database, Download, ExternalLink,
  FileCode2, FileDiff, FileJson2, FileText, FlaskConical, FolderGit2,
  Gauge, GitBranch, GitCommitHorizontal, GitCompareArrows, GitPullRequest,
  History, Info, Layers3, LayoutDashboard, LockKeyhole, Menu,
  MoreHorizontal, Play, Plus, RefreshCw, ScanSearch, Search, Settings2,
  Shield, ShieldAlert, ShieldCheck, ShieldQuestion, UploadCloud, Bot, FileArchive, SlidersHorizontal,
  Sparkles, Terminal, TrendingUp, X, Zap,
} from 'lucide-react'
import { api, API_BASE as API, SCAN_LIST_LIMIT, SCAN_LIST_PATH } from './api'
import { DiffViewer, Empty, FileIcon, FindingCard, Pill, Severity } from './components'
import { PATTERN_LANGUAGES, isPatternFile, isPatternFinding, isUnanalysed } from './patternRules'
import { ReleaseAssessmentPanel } from './ReleaseAssessmentPanel'
import { TestDiscoveryPanel } from './TestDiscoveryPanel'
import { QcTestCasesPanel } from './QcTestCasesPanel'
import { TestProposalsPanel } from './TestProposalsPanel'
import { BitbucketSection } from './bitbucket/BitbucketSection'
import { getBitbucketStatus, isMockMode } from './bitbucket/client'
import { BITBUCKET_NAV, INITIAL_SELECTION, bitbucketNavEntry, bitbucketPageLabel, isBitbucketPage } from './bitbucket/pages'
import type { BitbucketNavigate, BitbucketPage, BitbucketSelection } from './bitbucket/pages'
import { StaleBadge } from './bitbucket/StaleBadge'
import { useLoad } from './bitbucket/useLoad'
import type { AIProviderName, AIReview, DemoInfo, FileChange, Finding, Report, ScanHistory } from './types'
import { PROVIDER_COMPANY, getAIProviders, isModelReview, reviewOrigin, runModelReview, usageText } from './aiReview'

type Page = 'overview' | 'changes' | 'findings' | 'tests' | 'ai' | 'assessment' | 'history' | 'settings' | BitbucketPage
const NAV: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'changes', label: 'Code changes', icon: GitCompareArrows },
  { id: 'findings', label: 'Risk findings', icon: ShieldAlert },
  { id: 'tests', label: 'Test intelligence', icon: FlaskConical },
  { id: 'ai', label: 'Claude Review', icon: Bot },
  { id: 'assessment', label: 'Release assessment', icon: ShieldCheck },
  { id: 'history', label: 'Scan history', icon: History },
  { id: 'settings', label: 'Configuration', icon: Settings2 },
]
const relative = (date: string) => {
  const seconds = Math.round((Date.now() - new Date(date).getTime()) / 1000)
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return new Date(date).toLocaleDateString()
}
const shortRef = (value: string) => value.replace(/^feature\//, '')
/** A scan of a Bitbucket pull request (as opposed to a local or demo scan). */
const isPullRequestScan = (item: Pick<ScanHistory, 'binding'>) => item.binding?.provider === 'bitbucket-cloud' && item.binding.pull_request_id != null
/** Branches of a change, written the way its source writes them: a pull request as source → target (as Bitbucket shows it), a local comparison as base → compared branch. */
const changeText = (baseRef: string, headRef: string, pullRequest: boolean) => pullRequest ? `${headRef} → ${baseRef}` : `${baseRef} → ${headRef}`
const aiRecommendation = (value: string) => value === 'block_release' ? 'suggests Block release' : value === 'manual_review' ? 'suggests Manual review' : 'Insufficient evidence'
/** "2 critical, 6 high" from a review's findings. */
const severityCounts = (findings: { severity: string }[]) => ['critical', 'high', 'medium', 'low']
  .map(level => [level, findings.filter(item => item.severity === level).length] as const)
  .filter(([, count]) => count > 0).map(([level, count]) => `${count} ${level}`).join(', ')
const riskColor = (score: number) => score >= 65 ? 'danger' : score >= 25 ? 'warning' : 'good'

function Logo({ size = 38 }: { size?: number }) {
  return <div className="logo-mark" style={{ width: size, height: size }}>
    <ShieldCheck size={size * .62} strokeWidth={2.7} />
  </div>
}

function ProgressRing({ score }: { score: number }) {
  const category = riskColor(score)
  return <div className={`progress-ring ${category}`} style={{ '--score': `${score}%` } as CSSProperties}>
    <div className="progress-ring-inner">
      <span className="progress-number">{score}</span>
      <span className="progress-label">/ 100</span>
    </div>
  </div>
}

/** What the built-in static rules cover (backend/app/scanner.py analyze_risks). */
const STATIC_RULES_SCOPE = 'Static rules check 3 patterns in Python (.py) files only: a removed permission or ownership check, Decimal money arithmetic replaced by float, and keys removed from an API response. Other languages and other kinds of bugs are not checked, so 0 suspected risks does not mean the change is safe. Use an AI review and human review for the rest.'

function StatCard({ icon: Icon, title, value, note, tone }: { icon: typeof Activity; title: string; value: string | number; note: string; tone: string }) {
  return <div className="stat-card panel">
    <div className="stat-top"><span className={`stat-icon tone-${tone}`}><Icon size={19} /></span></div>
    <div className="stat-value">{value}</div>
    <div className="stat-label">{title}</div>
    <div className="stat-note">{note}</div>
  </div>
}

export default function App() {
  const [page, setPage] = useState<Page>('overview')
  // 'live' when the server has Bitbucket settings: the dashboard then shows only
  // Bitbucket pull request scans and never touches the synthetic demo. 'demo'
  // otherwise (not configured, or the status cannot be read). Decided once at start.
  const [mode, setMode] = useState<'demo' | 'live' | null>(null)
  const [apiConnected, setApiConnected] = useState(false)
  const [demo, setDemo] = useState<DemoInfo | null>(null)
  const [head, setHead] = useState('feature/release-candidate')
  const [base, setBase] = useState('main')
  const [report, setReport] = useState<Report | null>(null)
  const [history, setHistory] = useState<ScanHistory[]>([])
  const [selectedFile, setSelectedFile] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [aiReviews, setAIReviews] = useState<AIReview[]>([])
  const [aiFile, setAIFile] = useState<File | null>(null)
  const [importingAI, setImportingAI] = useState(false)
  const [shareAckRequired, setShareAckRequired] = useState(true)
  const [shareAck, setShareAck] = useState(false)
  const [reviewHistory, setReviewHistory] = useState<AIReview[] | null>(null)
  const [shownReviewId, setShownReviewId] = useState<string | null>(null)
  const [importStatus, setImportStatus] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)
  const [modelAck, setModelAck] = useState(false)
  // Bumped to read the reviews of the scan on screen again (a review was added elsewhere, or the scan was reopened).
  const [reviewsTick, setReviewsTick] = useState(0)
  // Copy button on the Claude Review page. The clipboard can refuse (no permission,
  // or a page not served from localhost/https), so a failure is shown, never thrown.
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const copyInstruction = async (text: string) => {
    try {
      if (!navigator.clipboard) throw new Error('Clipboard not available')
      await navigator.clipboard.writeText(text)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }
  const [modelRunning, setModelRunning] = useState(false)
  const [modelResult, setModelResult] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)
  const aiProviders = useLoad(getAIProviders, 'ai-providers')
  const configuredProviders = (Array.isArray(aiProviders.data) ? aiProviders.data : []).filter(item => item.configured)
  const [chosenProvider, setChosenProvider] = useState<AIProviderName | null>(null)
  // OpenAI first when both are configured; the person can switch.
  const activeProvider = configuredProviders.find(item => item.provider === chosenProvider)
    ?? configuredProviders.find(item => item.provider === 'openai') ?? configuredProviders[0] ?? null
  const [bitbucketSelection, setBitbucketSelection] = useState<BitbucketSelection>(INITIAL_SELECTION)
  const bitbucketNavigate: BitbucketNavigate = (next, change) => {
    if (change) setBitbucketSelection(previous => ({ ...previous, ...change }))
    setPage(next)
  }

  const refreshHistory = useCallback(async () => {
    const records = await api<ScanHistory[]>(SCAN_LIST_PATH)
    setHistory(records)
    return records
  }, [])

  // Asked once at start; a failure here never touches the demo flow or the error banner.
  const bitbucketStatus = useLoad(getBitbucketStatus, 'bitbucket-status')
  const started = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  // Starts once the Bitbucket status is known (or failed). A later Retry of the
  // status does not start the dashboard again.
  useEffect(() => {
    if (bitbucketStatus.loading || started.current) return
    started.current = true
    // Mock mode fakes only the Bitbucket screens: its invented "configured" status
    // must not switch the dashboard to live mode, which would hide the synthetic
    // demo and label invented data as live Bitbucket.
    const live = !isMockMode() && bitbucketStatus.data?.configured === true
    setMode(live ? 'live' : 'demo')
    const initLive = async () => {
      try {
        const records = await api<ScanHistory[]>(SCAN_LIST_PATH)
        if (!mounted.current) return
        setApiConnected(true); setHistory(records)
        const latest = records.find(isPullRequestScan)
        if (latest) {
          const previous = await api<Report>(`/api/scans/${latest.id}`)
          if (mounted.current) { setReport(previous); setSelectedFile(previous.files[0]?.path || '') }
        }
      } catch (exc) {
        if (mounted.current) setError(exc instanceof Error ? exc.message : String(exc))
      } finally { if (mounted.current) setLoading(false) }
    }
    // The synthetic demo, exactly as before Bitbucket was configured.
    const initDemo = async () => {
      try {
        const info = await api<DemoInfo>('/api/demo')
        if (!mounted.current) return
        setDemo(info); setApiConnected(true)
        setHead(info.default_head)
        const records = await api<ScanHistory[]>(SCAN_LIST_PATH)
        if (!mounted.current) return
        setHistory(records)
        if (records.length) {
          const previous = await api<Report>(`/api/scans/${records[0].id}`)
          if (mounted.current) { setReport(previous); setSelectedFile(previous.files[0]?.path || '') }
        } else {
          const initial = await api<Report>('/api/scans', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_ref: 'main', head_ref: info.default_head }) })
          if (mounted.current) { setReport(initial); setSelectedFile(initial.files[0]?.path || ''); await refreshHistory() }
        }
      } catch (exc) {
        if (mounted.current) setError(exc instanceof Error ? exc.message : String(exc))
      } finally { if (mounted.current) setLoading(false) }
    }
    void (live ? initLive() : initDemo())
  }, [bitbucketStatus.loading, bitbucketStatus.data, refreshHistory])

  useEffect(() => {
    if (!report) { setAIReviews([]); return }
    let active = true
    const scanID = report.id
    api<AIReview[]>(`/api/scans/${scanID}/ai/reviews`)
      .then(rows => { if (active) setAIReviews(rows) })
      .catch(exc => { if (active) setError(exc instanceof Error ? exc.message : String(exc)) })
    setAIFile(null)
    // Reviews of every stored scan of the same pull request (or of this scan only).
    // If this cannot be read, the page falls back to the reviews of this scan.
    setReviewHistory(null); setShownReviewId(null); setImportStatus(null)
    api<AIReview[]>(`/api/scans/${scanID}/ai/reviews/history`)
      .then(rows => { if (active && Array.isArray(rows)) setReviewHistory(rows) })
      .catch(() => undefined)
    // Whether exporting this scan's source code needs an explicit confirmation.
    // Unknown (request failed, older backend) is treated as "needed".
    setShareAck(false); setShareAckRequired(true); setModelAck(false); setModelResult(null)
    api<{ acknowledgement_required?: boolean }>(`/api/scans/${scanID}/ai/context`)
      .then(context => { if (active) setShareAckRequired(context.acknowledgement_required !== false) })
      .catch(() => undefined)
    return () => { active = false }
  }, [report?.id, reviewsTick])

  const importAIReview = async () => {
    if (!report || !aiFile) return
    // The result is shown next to the import control, not in the page banner.
    if (aiFile.size > 256 * 1024) { setImportStatus({ kind: 'error', message: 'Not imported: the review file is too large (max 256 KiB).' }); return }
    setImportingAI(true); setImportStatus(null)
    try {
      const source = await aiFile.text()
      const review = await api<AIReview>(`/api/scans/${report.id}/ai/reviews`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: source,
      })
      setAIReviews(previous => [review, ...previous])
      setReviewHistory(previous => (previous ? [{ ...review, current_scan: true }, ...previous] : previous))
      setShownReviewId(null)
      setAIFile(null)
      setImportStatus({ kind: 'success', message: `Imported for scan ${report.id.slice(0, 8)}: ${review.findings.length} proposed finding${review.findings.length !== 1 ? 's' : ''}. The review is unverified and no tests were run.` })
    } catch (exc) {
      setImportStatus({ kind: 'error', message: `Not imported: ${exc instanceof Error ? exc.message : String(exc)}` })
    } finally { setImportingAI(false) }
  }

  // Sends this scan's (secret-redacted) review context to the chosen AI provider through
  // the API server, which holds the keys. Non-demo code needs the confirmation.
  const runAIModelReview = async () => {
    if (!report || !activeProvider) return
    const scanID = report.id
    const label = activeProvider.label
    setModelRunning(true); setModelResult(null)
    try {
      const review = await runModelReview(scanID, activeProvider.provider, shareAckRequired ? modelAck : false)
      if (review.scan_id !== scanID) return
      setAIReviews(previous => [review, ...previous])
      setReviewHistory(previous => (previous ? [{ ...review, current_scan: true }, ...previous] : previous))
      setShownReviewId(null)
      const usage = usageText(review)
      setModelResult({ kind: 'success', message: `${label} review stored: ${review.findings.length} proposed finding${review.findings.length !== 1 ? 's' : ''}${usage ? ` (${usage})` : ''}. It is unverified and no tests were run.` })
    } catch (exc) {
      setModelResult({ kind: 'error', message: `${label} review failed: ${exc instanceof Error ? exc.message : String(exc)}` })
    } finally { setModelRunning(false) }
  }

  const startScan = async () => {
    setScanning(true); setNotice(null); setError(null)
    try {
      const next = await api<Report>('/api/scans', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repository_path: demo?.repository_path, base_ref: base, head_ref: head }),
      })
      setReport(next); setSelectedFile(next.files[0]?.path || ''); await refreshHistory()
      setPage('overview'); setNotice(`Scan completed: ${next.summary.files_changed} files examined, ${next.summary.finding_count} potential risks identified.`)
    } catch (exc) { setError(exc instanceof Error ? exc.message : String(exc)) }
    finally { setScanning(false) }
  }

  const openHistory = async (id: string, target: Page = 'overview') => {
    setLoading(true); setError(null)
    try {
      const old = await api<Report>(`/api/scans/${id}`)
      setReport(old); setReviewsTick(tick => tick + 1); setHead(old.head_ref); setBase(old.base_ref)
      setSelectedFile(old.files[0]?.path || ''); setPage(target)
      setNotice(`Loaded saved scan from ${new Date(old.created_at).toLocaleString()}.`)
    } catch (exc) { setError(exc instanceof Error ? exc.message : String(exc)) }
    finally { setLoading(false) }
  }

  // A scan shown on the PR analysis page (new or stored) becomes the dashboard's scan too, so
  // Overview, Risk findings, Test intelligence and the other pages never show an older one.
  const showInDashboard = (next: Report) => {
    setReport(previous => (previous?.id === next.id ? previous : next))
    setSelectedFile(next.files[0]?.path || '')
  }

  const goFile = (path: string) => { setSelectedFile(path); setPage('changes') }
  const selected = useMemo(() => report?.files.find(f => f.path === selectedFile) || report?.files[0], [report, selectedFile])
  const pageName = NAV.find(n => n.id === page)?.label || bitbucketPageLabel(page) || 'Overview'
  // A Bitbucket pull request scan is never labelled as the local demo.
  const pullRequestBinding = report?.binding && report.binding.provider === 'bitbucket-cloud' && report.binding.pull_request_id != null ? report.binding : null
  const live = mode === 'live'
  const workspaceName = bitbucketStatus.data?.workspace ?? null
  // In live mode the history lists Bitbucket pull request scans only; demo and local scans stay in the database, unlisted.
  const visibleHistory = live ? history.filter(isPullRequestScan) : history
  const latestAI = aiReviews[0]
  // Claude Review page: every known review (across the pull request's scans when the
  // history could be read), and the one on screen. By default that is the newest review
  // of THIS scan; a review of an earlier scan is shown only when the person picks it.
  const reviewList = reviewHistory ?? aiReviews
  const shownAI = reviewList.find(item => item.id === shownReviewId) ?? latestAI
  const shownIsOfThisScan = !!shownAI && shownAI.scan_id === report?.id
  const staticTitles = new Map((report?.findings ?? []).map(item => [item.id, item.title]))
  const raisedByReview = new Set(shownIsOfThisScan ? shownAI.findings.flatMap(item => item.related_static_finding_ids) : [])
  // The static rules only understand Python. Say which changed files they did not analyse
  // instead of implying that a diff with no static findings is clean.
  const staticUnanalysed = report?.files.filter(file => isUnanalysed(file.path)) ?? []
  const unanalysedTypes = [...new Set(staticUnanalysed.map(file => file.path.match(/\.[^./]+$/)?.[0] ?? 'no extension'))].join(', ')
  const coverageNote = report && staticUnanalysed.length
    ? `The static rules read Python, ${PATTERN_LANGUAGES} files: ${staticUnanalysed.length} of ${report.files.length} changed file${report.files.length !== 1 ? 's' : ''} (${unanalysedTypes}) ${staticUnanalysed.length === 1 ? 'was' : 'were'} not analysed by them. Use an AI review for these.`
    : null
  // Newest AI review of the scan on screen (Gemini or imported Claude), shown beside the static results.
  const aiOfScan = aiReviews[0]
  // Overview figures. The static rules apply only when the change has Python files.
  const pythonFiles = report?.files.filter(file => file.path.endsWith('.py')) ?? []
  const staticApplies = pythonFiles.length > 0
  // Pattern rules (Dart, JS/TS, Kotlin, Java): counted with the static findings, never scored.
  const patternFiles = report?.files.filter(file => isPatternFile(file.path)) ?? []
  const patternCount = report?.findings.filter(isPatternFinding).length ?? 0
  const rulesApply = staticApplies || patternFiles.length > 0
  const staticCount = report?.findings.length ?? 0
  const aiCount = aiOfScan?.findings.length ?? 0
  const severityRank: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }
  const combinedRisks = [
    ...(report?.findings ?? []).map(item => ({ key: `s-${item.id}`, title: item.title, file: item.file, severity: item.severity, category: item.category, ai: false })),
    ...(aiOfScan?.findings ?? []).map((item, index) => ({ key: `a-${index}`, title: item.title, file: item.file, severity: item.severity, category: item.category, ai: true })),
  ].sort((first, second) => (severityRank[first.severity] ?? 9) - (severityRank[second.severity] ?? 9))
  const topRisks = combinedRisks.slice(0, 5)
  const allRisks = combinedRisks.length
  const verdict: { tone: 'danger' | 'warning' | 'good' | 'muted'; title: string; detail: string; action?: 'ai' | 'findings' } = !report ? { tone: 'muted', title: '', detail: '' }
    : report.files.length === 0 ? { tone: 'good', title: 'No changes between these commits', detail: 'There is nothing to review.' }
    : staticCount + aiCount > 0 ? {
        tone: [...report.findings, ...(aiOfScan?.findings ?? [])].some(item => item.severity === 'critical') ? 'danger' : 'warning',
        title: `${staticCount + aiCount} possible problem${staticCount + aiCount !== 1 ? 's' : ''} found`,
        detail: [aiOfScan ? `${aiCount} from the AI review (${aiOfScan.findings.length ? severityCounts(aiOfScan.findings) + ', ' : ''}unverified; ${aiRecommendation(aiOfScan.recommendation)})` : 'no AI review yet', rulesApply ? `${staticCount} from the static rules` : 'static rules not applicable to these files'].join(' · ') + '. Suspicions to check, not confirmed defects.',
        action: 'findings' }
    : aiOfScan ? { tone: 'good', title: 'No problem flagged', detail: `Neither the AI review${rulesApply ? ' nor the static rules' : ''} flagged anything${rulesApply ? '' : ' (the static rules do not read these files)'}. Not proof of safety: review and test as usual.` }
    : rulesApply && !coverageNote ? { tone: 'muted', title: 'No static pattern flagged · no AI review yet', detail: staticApplies && !patternFiles.length ? 'The 3 static rules found nothing. Run an AI review for a broader check.' : 'The static rules found nothing in the files they read. They cover a small set of patterns; run an AI review for a broader check.', action: 'ai' }
    : { tone: 'warning', title: 'Not checked yet', detail: `The static rules do not read these file types, so ${staticUnanalysed.length} of ${report.files.length} changed file${report.files.length !== 1 ? 's' : ''} (${unanalysedTypes}) ${staticUnanalysed.length === 1 ? 'was' : 'were'} not checked. Run an AI review to check them.`, action: 'ai' }
  const filteredFindings = report?.findings.filter(f => `${f.title} ${f.category} ${f.file}`.toLowerCase().includes(search.toLowerCase())) || []

  return <div className="app-layout">
    <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <div className="brand"><Logo/><div><strong>ShipSafe<span className="brand-period">.</span></strong><small>RELEASE GUARDIAN</small></div></div>
      <div className="workspace-picker"><div className="workspace-symbol"><Layers3 size={16}/></div><div><strong>{pullRequestBinding || live ? 'Bitbucket' : 'Demo workspace'}</strong><small>{pullRequestBinding ? pullRequestBinding.repository_id : live ? workspaceName ?? 'Bitbucket Cloud' : 'LedgerLite project'}</small></div><ChevronDown size={15}/></div>
      <div className="sidebar-section-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Primary navigation">
        {NAV.filter(item => item.id !== 'settings').map(item => <button className={`nav-item ${page === item.id ? 'active' : ''}`} key={item.id} onClick={() => { setPage(item.id); setSidebarOpen(false) }}><item.icon size={18}/><span>{item.label}</span>{item.id === 'findings' && staticCount + aiCount > 0 && <b className="nav-count" title={`${staticCount} static · ${aiCount} AI (unverified)`}>{staticCount + aiCount}</b>}</button>)}
      </nav>
      <div className="sidebar-section-label tools-label">BITBUCKET</div>
      <nav className="nav-list" aria-label="Bitbucket navigation">
        {BITBUCKET_NAV.map(item => <button className={`nav-item ${bitbucketNavEntry(page) === item.id ? 'active' : ''}`} key={item.id} onClick={() => { setPage(item.id); setSidebarOpen(false) }}><item.icon size={18}/><span>{item.label}</span>{bitbucketStatus.data && !bitbucketStatus.data.configured && <b className="nav-tag" title="Bitbucket is not configured on the server">Off</b>}</button>)}
      </nav>
      <div className="sidebar-section-label tools-label">PREFERENCES</div>
      <nav className="nav-list"><button className={`nav-item ${page === 'settings' ? 'active' : ''}`} onClick={() => { setPage('settings'); setSidebarOpen(false) }}><Settings2 size={18}/><span>Configuration</span></button></nav>
      <div className="sidebar-bottom">
        <div className="help-box"><div className="help-icon"><BookOpen size={17}/></div><strong>Built for better releases</strong><p>Every finding should lead to better questions, not blind confidence.</p><button onClick={() => setPage('tests')}>Explore testing <ArrowRight size={13}/></button></div>
        <div className="sidebar-footer"><span className="online-dot"/> {apiConnected ? 'API connected' : 'API unavailable'} <small>v0.2.0</small></div>
      </div>
    </aside>
    {sidebarOpen && <div className="backdrop" onClick={() => setSidebarOpen(false)}/>}
    <div className="main-wrap">
      <header className="topbar">
        <div className="topbar-left"><button className="menu-button" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle menu"><Menu size={22}/></button><span>Workspace</span><ChevronRight size={14}/><strong>{pageName}</strong></div>
        <div className="topbar-right"><span className="top-live"><span className="online-dot"/> {pullRequestBinding ? 'BITBUCKET SCAN' : live ? 'BITBUCKET LIVE' : 'LIVE DEMO'}</span><span className="divider-v"/><span className="header-icon"><CircleHelp size={18}/></span><div className="avatar">SS</div></div>
      </header>
      {import.meta.env.DEV && isMockMode() && <div className="mock-banner" role="status"><strong>MOCK DATA</strong> Development mock mode: everything on the Bitbucket screens is invented. Nothing is read from Bitbucket.</div>}
      <main className="main-content">
        {error && <div className="alert alert-error"><AlertCircle size={18}/><span>{error}</span><button onClick={() => setError(null)}><X size={17}/></button></div>}
        {notice && <div className="alert alert-success"><CheckCircle2 size={18}/><span>{notice}</span><button onClick={() => setNotice(null)}><X size={17}/></button></div>}
        {loading && !report ? <div className="initial-load"><div className="spinner"/><h2>Connecting to Git analysis…</h2><p>{mode === 'demo' ? 'Preparing the synthetic LedgerLite repository and loading your first scan.' : 'Checking the Bitbucket connection and loading your scans.'}</p></div> : null}
        {page === 'overview' && <>
          <div className="page-heading dashboard-heading">
            <div><div className="eyebrow"><span className="eyebrow-line"/> RELEASE INTELLIGENCE</div><h1>Ship with confidence<span className="title-dot">.</span></h1><p>Understand what's changing, spot hidden risks, and release with evidence—not assumptions.</p></div>
            <div className="heading-actions">{pullRequestBinding || live ? <Pill kind="good" dot>BITBUCKET · READ-ONLY</Pill> : <Pill kind="demo" dot>LOCAL DEMO</Pill>}<button className="secondary-button" onClick={() => setPage('history')}><History size={16}/> View history</button></div>
          </div>
          {live && <div className="hero-scan panel" role="region" aria-label="Analyze a pull request">
            <div className="hero-scan-copy"><div className="hero-title"><span className="hero-icon"><GitPullRequest size={21}/></span><div><h2>Analyze a pull request</h2><p>Pick a pull request from {workspaceName ? <code>{workspaceName}</code> : 'your Bitbucket workspace'} and scan it. ShipSafe only reads from Bitbucket; it never comments, approves or merges.</p></div></div></div>
            <div className="scan-form"><button className="primary-button scan-button" onClick={() => bitbucketNavigate('pull-requests')}><GitPullRequest size={18}/> Choose a pull request <ArrowRight size={16}/></button></div>
            <div className="scan-foot"><LockKeyhole size={14}/><span>Read-only Bitbucket access · No code is executed</span><span className="scan-foot-right">{report ? `Last scan ${relative(report.created_at)}` : 'No pull request scanned yet'}</span></div>
          </div>}
          {live && !report && !loading && <div className="panel"><Empty icon={GitPullRequest} title="No pull request scanned yet" description="Open Pull requests, pick one and scan it. Its report will appear here."/></div>}
          {!live && <div className="hero-scan panel">
            <div className="hero-scan-copy"><div className="hero-title"><span className="hero-icon"><GitPullRequest size={21}/></span><div><h2>{pullRequestBinding ? 'Run a demo analysis' : 'Analyze a code change'}</h2><p>{pullRequestBinding ? 'This form scans the synthetic demo repository, not Bitbucket. The report below is a Bitbucket pull request scan.' : 'Compare real Git commits in the synthetic LedgerLite repository.'}</p></div></div></div>
            <div className="scan-form">
              <div className="scan-field"><label>BASE BRANCH</label><div className="select-shell"><GitBranch size={17}/><select value={base} onChange={e => setBase(e.target.value)}><option value="main">main</option>{demo?.branches.map(b => <option key={b.ref} value={b.ref}>{shortRef(b.ref)}</option>)}</select><ChevronDown size={15}/></div></div>
              <div className="compare-arrow"><ArrowRight size={18}/></div>
              <div className="scan-field head-field"><label>COMPARE BRANCH</label><div className="select-shell"><GitBranch size={17}/><select value={head} onChange={e => setHead(e.target.value)}><option value="main">main</option>{demo?.branches.map(b => <option key={b.ref} value={b.ref}>{shortRef(b.ref)}</option>)}</select><ChevronDown size={15}/></div></div>
              <button className="primary-button scan-button" disabled={scanning || !demo} onClick={startScan}>{scanning ? <RefreshCw className="spin" size={18}/> : <ScanSearch size={18}/>} {scanning ? 'Analyzing…' : 'Run analysis'} <ArrowRight size={16}/></button>
            </div>
            <div className="scan-foot"><LockKeyhole size={14}/><span>Scans only the trusted synthetic repo by default · No code is executed</span><span className="scan-foot-right">{report ? `Last scan ${relative(report.created_at)}` : 'Ready to analyze'}</span></div>
          </div>}
          {report && <>
            {pullRequestBinding && <div className="panel bb-state bb-source" role="region" aria-label="Scan source">
              <GitPullRequest size={22}/>
              <div>
                <h3>Bitbucket pull request #{pullRequestBinding.pull_request_id} · <code>{pullRequestBinding.repository_id}</code> <StaleBadge binding={pullRequestBinding}/></h3>
                <p><code>{report.head_ref}</code> → <code>{report.base_ref}</code> · scanned {new Date(report.created_at).toLocaleString()} · read-only, nothing was written to Bitbucket</p>
                <p>Base ({pullRequestBinding.comparison === 'merge-base' ? 'merge base' : 'direct'}) <code>{pullRequestBinding.base_commit}</code> → head <code>{pullRequestBinding.head_commit}</code></p>
              </div>
              <button className="secondary-button" onClick={() => bitbucketNavigate('pr-analysis', { slug: pullRequestBinding.repository_id?.split('/').pop() ?? null, pullRequestId: pullRequestBinding.pull_request_id })}>Open pull request <ArrowRight size={15}/></button>
            </div>}
            <div className="section-heading"><div><h2>Release overview</h2><p>Actual results from <code>{report.base_sha}</code> → <code>{report.head_sha}</code></p></div><span className="subtle-time"><Clock3 size={15}/>{report.duration_ms} ms analysis</span></div>
            <div className={`panel overview-verdict verdict-${verdict.tone}`} role="status" aria-label="At a glance">
              <span className="verdict-icon">{verdict.tone === 'good' ? <ShieldCheck size={22}/> : verdict.tone === 'muted' ? <ShieldQuestion size={22}/> : <ShieldAlert size={22}/>}</span>
              <div><strong>{verdict.title}</strong><p>{verdict.detail}</p></div>
              {verdict.action && <button className="secondary-button" onClick={() => setPage(verdict.action === 'ai' ? 'ai' : 'findings')}>{verdict.action === 'ai' ? <><Sparkles size={15}/> Run an AI review</> : <>See the findings <ArrowRight size={15}/></>}</button>}
            </div>
            <div className="stat-grid">
              <StatCard icon={FileCode2} title="Files changed" value={report.summary.files_omitted ? `${report.summary.files_changed}+` : report.summary.files_changed} note={`+${report.summary.lines_added} additions · -${report.summary.lines_removed} deletions${report.summary.files_omitted ? ` · ${report.summary.files_omitted} more files not listed` : ''}`} tone="blue"/>
              <StatCard icon={Sparkles} title="AI findings" value={aiOfScan ? aiOfScan.findings.length : '—'} note={aiOfScan ? (aiOfScan.findings.length ? `${severityCounts(aiOfScan.findings)} · unverified · ${reviewOrigin(aiOfScan)}` : `None proposed by ${reviewOrigin(aiOfScan)} · not proof of safety`) : 'No AI review of this scan yet'} tone="red"/>
              <StatCard icon={ShieldAlert} title="Static findings" value={rulesApply ? report.summary.finding_count : 'N/A'} note={patternFiles.length && (patternCount || !staticApplies) ? `${patternCount} from pattern rules in ${patternFiles.length} ${patternFiles.length === 1 ? 'file' : 'files'} · suspected · not in the score${report.summary.pattern_rules?.files_skipped ? ` · ${report.summary.pattern_rules.files_skipped} not read` : ''}` : !staticApplies ? `Rules read Python only ·${staticUnanalysed.length} ${unanalysedTypes} file${staticUnanalysed.length !== 1 ? 's' : ''} not analysed` : report.summary.finding_count ? `${severityCounts(report.findings)} · 3 Python rules · suspected` : coverageNote ? `None in ${pythonFiles.length} Python file${pythonFiles.length !== 1 ? 's' : ''} · ${staticUnanalysed.length} other file${staticUnanalysed.length !== 1 ? 's' : ''} not analysed` : 'No pattern of the 3 Python rules found'} tone="amber"/>
              <StatCard icon={GitCommitHorizontal} title="Affected importers" value={staticApplies ? report.affected_modules.length : 'N/A'} note={staticApplies ? 'Python files that import a changed module' : 'Traced for Python imports only'} tone="purple"/>
              <StatCard icon={FlaskConical} title="Tests executed" value={0} note="ShipSafe never runs repository code or tests" tone="blue"/>
            </div>
            {report.summary.truncated && <div className="footnote" role="status"><AlertTriangle size={15}/> This report is incomplete: {report.summary.files_omitted ? `${report.summary.files_omitted} changed files beyond the first ${report.summary.files_changed} are not listed and are excluded from all counts` : ''}{report.summary.files_omitted && report.files.some(f => f.diff_truncated) ? '; ' : ''}{report.files.some(f => f.diff_truncated) ? `${report.files.filter(f => f.diff_truncated).length} diffs are cut at 140 lines (marked in Code changes)` : ''}. The Claude handoff package carries the same gaps.</div>}
            <div className="dashboard-grid">
              <div className="panel risk-panel"><div className="panel-head"><div><h3>Risk intelligence</h3><p>Static rules and AI review together. AI findings are unverified.</p></div><button className="ghost-button" onClick={() => setPage('findings')}>View all <ArrowUpRight size={15}/></button></div>
                {topRisks.length ? <div className="risk-list">{topRisks.map(item => <button className="risk-row" key={item.key} onClick={() => setPage('findings')}><span className={`risk-symbol ${item.severity}`}><AlertTriangle size={18}/></span><span className="risk-details"><strong>{item.title}</strong><small>{item.file}{item.ai ? ' · AI review · unverified' : ` · ${item.category} · static rule`}</small></span><Severity level={item.severity}/><ChevronRight size={16} className="risk-chevron"/></button>)}</div> : <Empty icon={aiOfScan ? ShieldCheck : ShieldQuestion} title={aiOfScan ? 'No problem found' : coverageNote ? 'Not checked yet' : 'No known patterns flagged'} description={aiOfScan ? 'Neither the static rules nor the AI review flagged anything. That is not a guarantee; human review is still necessary.' : `${coverageNote ?? 'This is not a guarantee that the change is safe.'} Run an AI review on the Claude Review page.`}/>}
                {allRisks > topRisks.length && <p className="risk-more">{allRisks - topRisks.length} more on Risk findings</p>}
                <div className="risk-panel-footer"><Info size={15}/><span>Findings are leads for review, not verified defects. The static rules read Python files only.</span></div>
              </div>
              <div className="panel readiness-panel"><div className="panel-head"><div><h3>Release readiness</h3><p>Static heuristic score, not an approval</p></div><MoreHorizontal size={20} className="dim"/></div><div className="readiness-inner">{staticApplies ? <ProgressRing score={report.summary.risk_score}/> : <div className="progress-ring na" aria-label="Static score not applicable"><div className="progress-ring-inner"><span className="progress-number">N/A</span><span className="progress-label">static score</span></div></div>}<div className="readiness-result"><Pill kind={staticApplies ? riskColor(report.summary.risk_score) : 'muted'} dot>{staticApplies ? report.summary.recommendation : 'Static rules not applicable'}</Pill><p>{!staticApplies ? `The static score covers Python files only; this change has none${unanalysedTypes ? ` (${unanalysedTypes})` : ''}.${patternCount ? ` ${patternCount} pattern-rule finding${patternCount !== 1 ? 's are' : ' is'} listed under Risk findings and not included in this score.` : ''}` : report.findings.length ? 'Review the identified patterns and verify with regression tests before release.' : coverageNote ? 'No static pattern flagged, but the static rules read Python files only. This score says nothing about the other changed files.' : 'No static pattern flagged. Additional tests and review may still be required.'}</p>{aiOfScan ? <p className="readiness-ai" role="note"><strong>AI review ({reviewOrigin(aiOfScan)}, unverified):</strong> {aiRecommendation(aiOfScan.recommendation)}{aiOfScan.findings.length ? ` · ${severityCounts(aiOfScan.findings)}` : ' · no findings'}. Not included in this score.</p> : <p className="readiness-ai muted">No AI review yet.</p>}</div></div><div className="readiness-footer"><ShieldQuestion size={17}/><div><strong>Human approval required</strong><span>ShipSafe never marks a release fully safe.</span></div></div></div>
            </div>
            <div className="dashboard-grid lower-grid">
              <div className="panel changes-panel"><div className="panel-head"><div><h3>Changed files</h3><p>Source-controlled changes from Git</p></div><button className="ghost-button" onClick={() => setPage('changes')}>Explore diff <ArrowUpRight size={15}/></button></div><div className="changed-files-list">{report.files.slice(0, 5).map(f => <button key={f.path} className="changed-file-row" onClick={() => goFile(f.path)}><FileIcon path={f.path}/><span className="file-name"><strong>{f.path.split('/').pop()}</strong><small>{f.path}</small></span><span className="file-bars"><i style={{width: Math.min(65, f.additions * 8 + 6)}}/><b style={{width: Math.min(40, f.deletions * 8 + 6)}}/></span><span className="line-changes"><em>+{f.additions}</em><b>-{f.deletions}</b></span></button>)}</div></div>
              <div className="panel insight-panel"><div className="panel-head"><div><h3>What this scan means</h3><p>Important next steps</p></div><Sparkles size={19} className="sparkle"/></div><div className="insight-item"><span className="insight-step">01</span><div><strong>Inspect the diff</strong><p>Review the exact lines that changed and their call sites.</p></div></div><div className="insight-item"><span className="insight-step">02</span><div><strong>Verify suspected risks</strong><p>Write a regression test before accepting a finding as confirmed.</p></div></div><div className="insight-item"><span className="insight-step">03</span><div><strong>Record your decision</strong><p>Export the report with known gaps and review notes.</p></div></div><button className="outline-button full" onClick={() => setPage('tests')}><FlaskConical size={16}/> Explore test scenarios <ArrowRight size={16}/></button></div>
            </div>
            <div className="panel ai-callout"><div className="ai-callout-icon"><Bot size={23}/></div><div><h3>Get an AI second opinion</h3><p>{latestAI ? (isModelReview(latestAI) ? `An AI model review by ${reviewOrigin(latestAI)} is available (${latestAI.findings.length} proposed finding${latestAI.findings.length !== 1 ? 's' : ''}, unverified).` : `A manually imported Claude Code review is available (${latestAI.findings.length} proposed finding${latestAI.findings.length !== 1 ? 's' : ''}, unverified).`) : 'Run an OpenAI or Gemini review through the API server (when its key is configured), or export the Git evidence for your own Claude Code session and import the JSON.'}</p></div><button className="secondary-button" onClick={() => setPage('ai')}>Open Claude Review <ArrowRight size={16}/></button></div>
            <div className="footnote"><Info size={15}/> Git findings are heuristic. Imported AI suggestions are separate, unverified, and never change test execution status.</div>
          </>}
        </>}
        {isBitbucketPage(page) && <BitbucketSection page={page} status={bitbucketStatus} selection={bitbucketSelection} navigate={bitbucketNavigate} onScanned={() => { void refreshHistory().catch(() => undefined) }} onShown={showInDashboard} onReviewed={id => { if (id === report?.id) setReviewsTick(tick => tick + 1) }} onOpenReport={(id, target) => { void openHistory(id, target) }} providers={Array.isArray(aiProviders.data) ? aiProviders.data : aiProviders.error ? [] : null}/>}
        {page !== 'overview' && !isBitbucketPage(page) && <>
          <div className="subpage-heading"><div className="eyebrow"><span className="eyebrow-line"/> WORKSPACE / {page.toUpperCase()}</div><div className="subpage-title"><div><h1>{pageName}<span className="title-dot">.</span></h1><p>{({overview:'',changes:'Review actual changed files, functions, and Git patch details.',findings:'Investigate suspected problems and the evidence behind them.',tests:'Identify missing regression coverage. No tests are claimed as executed.',ai:'Two ways to get an unverified AI review: the API server sends the scan to OpenAI or Gemini (when its key is configured on the server), or you review it in your own Claude Code session and import the JSON. ShipSafe never calls Claude directly.',assessment:'Stored evidence for this scan, kept apart by kind. Not an approval to release.',history:'Go back to previous local analysis reports.',settings:'Local-first setup, security boundaries, and data sources.'} as Record<Page,string>)[page]}</p></div>{report && page !== 'settings' && <a className="secondary-button export-link" href={`${API}/api/scans/${report.id}/export`} download><Download size={16}/> Export JSON</a>}</div></div>
          {page === 'changes' && report && <div className="code-layout">
            <div className="panel file-browser"><div className="panel-head"><div><h3>Repository files</h3><p>{report.summary.files_changed} changed in this compare{report.summary.files_omitted ? ` · ${report.summary.files_omitted} more not listed` : ''}</p></div><FolderGit2 size={18} className="dim"/></div>{report.files.map(file => <button className={`file-select ${selected?.path === file.path ? 'selected' : ''}`} key={file.path} onClick={() => setSelectedFile(file.path)}><FileIcon path={file.path}/><span><strong>{file.path.split('/').pop()}</strong><small>{file.path}</small></span><ChevronRight size={16}/></button>)}<div className="browser-foot"><GitCommitHorizontal size={14}/><span>{report.base_sha} → {report.head_sha}</span></div></div>
            <div className="code-main">{selected ? <><DiffViewer file={selected}/><div className="panel code-context"><div className="panel-head"><div><h3>Change context</h3><p>Static AST and import dependency observations</p></div></div><div className="context-grid"><div><span className="micro-label">CHANGED FUNCTIONS</span>{selected.changed_functions.length ? selected.changed_functions.map(fn => <span key={fn} className="code-chip"><Code2 size={13}/>{fn}()</span>) : <p className="muted-small">No changed function names detected</p>}</div><div><span className="micro-label">DIRECT IMPORTERS</span>{report.affected_modules.filter(m => m.imports_changed.some(mod => mod === selected.path.replace(/\.py$/, '').replace(/\//g, '.'))).map(m => <span key={m.path} className="code-chip"><Layers3 size={13}/>{m.path}</span>)}{!report.affected_modules.some(m => m.imports_changed.includes(selected.path.replace(/\.py$/, '').replace(/\//g, '.'))) && <p className="muted-small">No direct importers found</p>}</div></div></div></> : <Empty title="No changed files" description="Choose a branch with a code change to inspect its Git diff."/>}</div>
          </div>}
          {page === 'findings' && report && <><div className="findings-toolbar panel"><div className="findings-count"><ShieldAlert size={20}/><div><strong>{report.findings.length} suspected risk{report.findings.length !== 1 ? 's' : ''}</strong><small>Static rules · Python files only</small></div></div><div className="search-field"><Search size={16}/><input placeholder="Search findings or files..." value={search} onChange={e => setSearch(e.target.value)} /></div></div><div className="findings-grid">{filteredFindings.length ? filteredFindings.map(f => <FindingCard key={f.id} finding={f} onOpenFile={goFile}/>) : <Empty icon={ShieldCheck} title={report.findings.length ? 'No findings match your search' : coverageNote ? 'No static findings' : 'No risk patterns detected'} description={report.findings.length ? 'Try searching another file, category, or issue.' : coverageNote ?? 'Static analysis found no known patterns in this diff; that does not establish safety.'}/>}</div>
            {!!report.findings.length && coverageNote && <div className="footnote" role="note"><Info size={15}/> {coverageNote}</div>}
            <div className="footnote" role="note" aria-label="What the static rules check"><Info size={15}/> {STATIC_RULES_SCOPE}</div>
            <div className="panel ai-risk-section" role="region" aria-label="AI review findings">
              <div className="panel-head"><div><h3>AI review findings <Pill kind="warning">UNVERIFIED AI SUGGESTIONS</Pill></h3><p>{aiOfScan ? `${reviewOrigin(aiOfScan)} · ${new Date(aiOfScan.imported_at).toLocaleString()} · suspicions from the diff, not confirmed defects` : 'No AI review of this scan yet.'}</p></div>{aiOfScan && <Pill kind="muted">{aiOfScan.findings.length} AI finding{aiOfScan.findings.length !== 1 ? 's' : ''}</Pill>}</div>
              {aiOfScan ? (aiOfScan.findings.length ? <div className="ai-risk-list">{aiOfScan.findings.map((f, i) => <div className="ai-risk-row" key={`${i}-${f.title}`}><Severity level={f.severity}/><div><strong>{f.id ? `${f.id} · ` : ''}{f.title}</strong><button className="text-link" onClick={() => goFile(f.file)}>{f.file}{f.line ? `:${f.line}` : ''}<ArrowUpRight size={13}/></button><p>{f.rationale}</p>{f.suggested_validation && <small>How to validate (not done): {f.suggested_validation}</small>}</div></div>)}</div> : <p className="small-para">The AI review proposed no findings. That does not establish safety.</p>)
                : <div className="ai-risk-empty"><p className="small-para">Run an AI model review (OpenAI or Gemini) or import a Claude Code review; its findings appear here, labelled as unverified.</p><button className="secondary-button" onClick={() => setPage('ai')}><Bot size={16}/> Open Claude Review</button></div>}
            </div>
            <div className="disclaimer-box"><Info size={18}/>{report.disclaimer}</div></>}
          {page === 'tests' && report && <div className="test-layout"><div className="panel test-main"><div className="test-status-banner"><span className="test-pictogram"><FlaskConical size={24}/></span><div><Pill kind="warning">NOT EXECUTED</Pill><h2>Test intelligence</h2><p>Candidate regression scenarios come from the static findings of this diff. You can write a test proposal below and approve it, but no test is ever executed: ShipSafe has no verified isolated runner. For the synthetic demo repository a run request is recorded as BLOCKED; for any other repository, including Bitbucket pull requests, Run is not available. Existing tests are found in Python (pytest) and Dart/Flutter (*_test.dart) files; proposals accept Python (pytest) files only.</p></div></div><div className="panel-head test-list-head"><div><h3>Suggested regression scenarios</h3><p>Generated from observed risk categories</p></div><span className="light-count">{report.test_suggestions.length} suggestions</span></div>{report.test_suggestions.length ? report.test_suggestions.map((item, index) => <div className="test-item" key={`${item.file}-${index}`}><span className="test-number">{String(index + 1).padStart(2, '0')}</span><div><strong>{item.scenario}</strong><small><FileCode2 size={13}/>{item.file} · {item.category}</small></div><Pill kind="muted">Proposed</Pill></div>) : <Empty icon={CheckCircle2} title="No targeted scenarios yet" description={coverageNote ?? (live ? 'No risk patterns were flagged in this pull request. Normal engineering tests are still recommended.' : 'Try a risk-bearing demo branch. Normal engineering tests are still recommended.')}/>}
            <div className="ai-test-ideas" role="region" aria-label="AI test ideas">
              <div className="panel-head test-list-head"><div><h3>Test ideas from the AI review <Pill kind="warning">AI · NOT RUN</Pill></h3><p>{aiOfScan ? `${reviewOrigin(aiOfScan)} · hypotheses to turn into real tests` : 'No AI review of this scan yet.'}</p></div><span className="light-count">{aiOfScan?.test_ideas.length ?? 0} ideas</span></div>
              {aiOfScan?.test_ideas.length ? aiOfScan.test_ideas.map((idea, index) => <div className="test-item" key={`ai-${index}`}><span className="test-number">AI{index + 1}</span><div><strong>{idea.title}</strong><p className="ai-test-scenario">{idea.scenario}</p><small>Expected: {idea.expected_behavior}{idea.file ? ` · ${idea.file}` : ''}</small></div><Pill kind="muted">Not run</Pill></div>)
                : <p className="small-para ai-test-empty">{aiOfScan ? 'The AI review proposed no test ideas.' : 'Run an AI model review (OpenAI or Gemini) or import a Claude Code review on the Claude Review page; its test ideas appear here.'}</p>}
            </div></div><div className="test-right">{!live && <div className="panel"><div className="panel-head"><div><h3>Run the fixture suite</h3><p>Manual command on trusted code</p></div><Terminal size={18}/></div><div className="terminal-mini"><span className="terminal-dot-row"><i/><i/><i/></span><code>cd backend/demo-repo<br/>python -m pytest -q</code></div><p className="small-para">The fixture's existing happy-path tests intentionally miss the injected regressions. Passing them does not verify the flagged behavior.</p><div className="manual-tag"><LockKeyhole size={14}/> Only run code you explicitly trust.</div></div>}<div className="panel score-note"><ShieldQuestion size={22}/><h3>Evidence over confidence</h3><p>Suggested tests are hypotheses. A confirmed regression requires an executable test that fails before the fix and passes afterward.</p></div></div></div>}
          {page === 'assessment' && report && <ReleaseAssessmentPanel scanId={report.id}/>}
          {page === 'tests' && report && <QcTestCasesPanel scanId={report.id} review={aiOfScan} providers={configuredProviders} shareAckRequired={shareAckRequired} onOpenReview={() => setPage('ai')}/>}
          {page === 'tests' && report && <TestDiscoveryPanel scanId={report.id}/>}
          {page === 'tests' && report && <TestProposalsPanel scanId={report.id} runRefused={shareAckRequired}/>}
          {page === 'ai' && report && <div className="ai-workspace">
            <div className="ai-intro panel">
              <div className="ai-intro-mark"><Bot size={27}/></div>
              <div><div className="eyebrow">OPTIONAL HUMAN-IN-THE-LOOP AI</div><h2>Bring your own Claude Code session.</h2><p>ShipSafe does not sign in, store tokens, call Claude's API, or run the Claude CLI on your behalf. You review the exported diff in Claude Code using your own Team account, then import structured findings.</p></div>
              <Pill kind="demo">{activeProvider ? 'NO CLAUDE KEY · AI KEYS ON SERVER' : 'NO API KEY IN SHIPSAFE'}</Pill>
            </div>
            <div className="panel ai-gemini" role="region" aria-label="Review with an AI model">
              <div className="ai-gemini-head"><span className="ai-gemini-icon"><Sparkles size={20}/></span><div><h3>Review with an AI model</h3><p>{activeProvider ? <>The API server sends this scan's diffs and static findings (secret-redacted, best effort) to {PROVIDER_COMPANY[activeProvider.provider]} <code>{activeProvider.model}</code> and stores the answer as an unverified AI review, with its token usage{activeProvider.pricing_known ? ' and cost' : ''}. Nothing is executed or applied.</> : aiProviders.loading ? 'Checking which AI models are configured…' : <>No AI model is configured. Set <code>SHIPSAFE_OPENAI_API_KEY</code> or <code>SHIPSAFE_GEMINI_API_KEY</code> on the API server and restart it.</>}</p></div>{activeProvider && <Pill kind="muted">SERVER-SIDE KEY</Pill>}</div>
              {activeProvider && <>
                {configuredProviders.length > 1 && <label className="bb-field ai-provider-select"><span className="micro-label">MODEL</span><span className="select-shell"><select aria-label="AI model" value={activeProvider.provider} onChange={e => { setChosenProvider(e.target.value as AIProviderName); setModelAck(false) }}>{configuredProviders.map(item => <option key={item.provider} value={item.provider}>{item.label} · {item.model}</option>)}</select><ChevronDown size={15}/></span></label>}
                {shareAckRequired && <label className="ai-share-ack"><input type="checkbox" checked={modelAck} onChange={e => setModelAck(e.target.checked)}/><span>This scan contains source code that is not the synthetic demo. I am allowed to send it to {PROVIDER_COMPANY[activeProvider.provider]} (redaction is best-effort).</span></label>}
                <button className="primary-button ai-action" disabled={modelRunning || (shareAckRequired && !modelAck)} onClick={() => { void runAIModelReview() }}>{modelRunning ? <RefreshCw size={16} className="spin"/> : <Sparkles size={16}/>} {modelRunning ? `${activeProvider.label} is reviewing…` : `Run ${activeProvider.label} review`}</button>
              </>}
              {modelResult && <p className={`ai-import-status ${modelResult.kind}`} role={modelResult.kind === 'error' ? 'alert' : 'status'}>{modelResult.message}</p>}
            </div>
            <div className="ai-steps">
              <div className="panel ai-step"><div className="ai-step-top"><span className="ai-step-num">01</span><FileArchive size={19}/></div><h3>Export review package</h3><p>Download Git evidence, the structured JSON response template, and review instructions for scan <code>{report.id.slice(0, 8)}</code>.</p>{shareAckRequired && <label className="ai-share-ack"><input type="checkbox" checked={shareAck} onChange={e => setShareAck(e.target.checked)}/><span>This package contains source code that is not the synthetic demo. I am allowed to share it with Claude Code, and I will check it for secrets first (redaction is best-effort).</span></label>}{shareAckRequired && !shareAck ? <button className="secondary-button ai-action" disabled><Download size={16}/> Download handoff ZIP</button> : <a className="secondary-button ai-action" href={`${API}/api/scans/${report.id}/ai/handoff${shareAckRequired ? '?acknowledge_source_sharing=true' : ''}`} download><Download size={16}/> Download handoff ZIP</a>}</div>
              <div className="panel ai-step"><div className="ai-step-top"><span className="ai-step-num">02</span><Terminal size={19}/></div><h3>Review in Claude Code</h3><p>Extract the ZIP. Open a terminal in the extracted folder, run <code>claude</code>, and ask it to read the instructions and write <code>claude-review.json</code>.</p><div className="ai-command"><code>claude</code><button title="Copy CLI instruction" aria-label="Copy the Claude Code instruction" onClick={() => copyInstruction('Read REVIEW_INSTRUCTIONS.md and review-input.json in this directory. Follow the instructions and write claude-review.json. Do not run code or modify any other files.')}>{copyState === 'copied' ? <CheckCircle2 size={15}/> : <Copy size={15}/>}</button>{copyState === 'failed' && <small className="copy-failed" role="status">Copy failed: select the text in REVIEW_INSTRUCTIONS.md instead.</small>}</div></div>
              <div className="panel ai-step"><div className="ai-step-top"><span className="ai-step-num">03</span><UploadCloud size={19}/></div><h3>Import the JSON result</h3><p>Inspect Claude's output before importing. The backend checks its schema, scan ID, context digest, and referenced files.</p><label className="ai-file-label"><input type="file" accept=".json,application/json" onChange={e => { setAIFile(e.target.files?.[0] || null); e.target.value = '' /* lets the same file be chosen again after an import */ }}/><UploadCloud size={15}/>{aiFile ? aiFile.name : 'Choose claude-review.json'}</label><button className="primary-button ai-action" disabled={!aiFile || importingAI} onClick={importAIReview}>{importingAI ? <RefreshCw size={16} className="spin"/> : <Check size={16}/>} {importingAI ? 'Importing…' : 'Import review'}</button>{importStatus && <p className={`ai-import-status ${importStatus.kind}`} role={importStatus.kind === 'error' ? 'alert' : 'status'}>{importStatus.message}</p>}</div>
            </div>
            <div className="ai-warning"><Info size={18}/><span><strong>Security & evidence boundary:</strong> The package contains source-code diffs. Only share authorized code with Claude. Import does not prove who authored the JSON, confirm vulnerabilities, run tests, or grant approval to release.</span></div>
            {reviewList.length > 0 && <div className="panel ai-history" role="region" aria-label="Previous reviews">
              <div className="panel-head"><div><h3>Previous reviews</h3><p>Every AI review (model-generated or imported) is kept. A review belongs to the scan it was made for and goes stale with it.</p></div><Pill kind="muted">{reviewList.length} review{reviewList.length !== 1 ? 's' : ''}</Pill></div>
              <div className="history-table-wrap"><table className="history-table bb-table"><thead><tr><th>Imported</th><th>Scan</th><th>Suggestion</th><th>AI findings</th><th>State</th><th><span className="visually-hidden">Actions</span></th></tr></thead><tbody>
                {reviewList.map(item => <tr key={item.id} className={shownAI?.id === item.id ? 'bb-row-open' : ''}>
                  <td>{new Date(item.imported_at).toLocaleString()}<small className="bb-muted ai-origin">{reviewOrigin(item)}</small></td>
                  <td>{item.scan_id === report.id ? 'This scan' : <>Earlier scan · head <code>{item.scan_binding?.head_commit?.slice(0, 12) ?? 'unknown'}</code></>}</td>
                  <td>{item.recommendation === 'block_release' ? 'Block release' : item.recommendation === 'manual_review' ? 'Manual review' : 'Insufficient evidence'}</td>
                  <td>{item.findings.length}</td>
                  <td>{item.scan_binding?.pull_request_id != null ? <StaleBadge binding={item.scan_binding}/> : <span className="bb-muted">Local scan</span>}</td>
                  <td><button className="table-action" disabled={shownAI?.id === item.id} onClick={() => setShownReviewId(item.id)}>{shownAI?.id === item.id ? 'Shown below' : 'Show'}<span className="visually-hidden"> review imported {new Date(item.imported_at).toLocaleString()}</span></button></td>
                </tr>)}
              </tbody></table></div>
            </div>}
            <div className="ai-report-heading"><div><h2>AI review</h2><p>{shownAI && !shownIsOfThisScan ? 'From an earlier scan of this pull request. It does not describe the scan on screen.' : `Associated only with ${changeText(report.base_ref, report.head_ref, !!pullRequestBinding)} · context digest verified`}</p></div>{aiReviews.length > 0 && <Pill kind="muted">{aiReviews.length} review{aiReviews.length !== 1 ? 's' : ''} for this scan</Pill>}</div>
            {shownAI ? <>
              {shownAI.scan_binding?.stale && <div className="panel bb-state bb-warning-panel" role="alert"><AlertTriangle size={22}/><div><h3>This review is stale <StaleBadge binding={shownAI.scan_binding}/></h3><p>The pull request has new commits since the scan this review was made for (head <code>{shownAI.scan_binding.head_commit}</code>). It does not describe the current code. Scan the pull request again and review the new scan.</p></div></div>}
              <div className="panel ai-review-summary"><div className="ai-review-title"><div><Pill kind="warning">UNVERIFIED AI SUGGESTIONS</Pill><h3>{shownAI.recommendation === 'block_release' ? 'Suggested: Block release' : shownAI.recommendation === 'manual_review' ? 'Suggested: Manual review' : 'Insufficient evidence'}</h3><p>{isModelReview(shownAI) ? `Generated by ${reviewOrigin(shownAI)} · ${new Date(shownAI.imported_at).toLocaleString()} · not verified${usageText(shownAI) ? ` · ${usageText(shownAI)}` : ''}` : `Imported ${new Date(shownAI.imported_at).toLocaleString()} · Source provenance not verified`}</p></div><div className="ai-review-count"><strong>{shownAI.findings.length}</strong><span>AI findings</span></div></div><p className="ai-review-summary-text">{shownAI.summary}</p><div className="ai-verification-note"><ShieldQuestion size={16}/> No tests were executed as part of this import. This assessment cannot override the static scan, change risk score, or human review.</div></div>
              {shownAI.findings.length > 0 ? <div className="ai-findings-grid">{shownAI.findings.map((f,i) => <div className="panel ai-finding" key={`${i}-${f.title}`}><div className="ai-finding-head"><Severity level={f.severity}/><Pill kind="muted">{f.confidence} confidence</Pill>{f.id && <Pill kind="muted">{f.id}</Pill>}<Pill kind="warning">SUSPECTED · UNVERIFIED</Pill></div><h3>{f.title}</h3><p className="ai-finding-category">{f.category} · <button className="text-link" onClick={() => goFile(f.file)}>{f.file}{f.line ? `:${f.line}` : ''}<ArrowUpRight size={13}/></button></p><p>{f.rationale}</p><div className="evidence"><div className="micro-label"><Terminal size={13}/> Reported code evidence</div><code>{f.evidence}</code></div><div className="ai-advice"><Sparkles size={15}/><span>{f.recommendation}</span></div>{f.suggested_validation && <div className="ai-validation"><div className="micro-label"><FlaskConical size={13}/> How to validate (not done)</div><p>{f.suggested_validation}</p></div>}{f.proposed_patch && <div className="evidence ai-patch"><div className="micro-label"><FileDiff size={13}/> Proposed patch · unverified · not applied by ShipSafe</div><pre>{f.proposed_patch}</pre></div>}</div>)}</div> : <Empty icon={ShieldQuestion} title="No risks proposed in imported review" description="This does not establish that the code is safe. Check the review's limitations and independent testing."/>}
              <div className="ai-bottom-grid"><div className="panel ai-list-panel"><h3><FlaskConical size={18}/> Suggested regression tests <Pill kind="muted">NOT RUN</Pill></h3>{shownAI.test_ideas.map((idea,i) => <div className="ai-list-item" key={i}><strong>{idea.title}</strong><p>{idea.scenario}</p><small>Expected: {idea.expected_behavior}{idea.file ? ` · ${idea.file}` : ''}</small></div>)}{!shownAI.test_ideas.length && <p className="small-para">No test ideas provided.</p>}</div><div className="panel ai-list-panel"><h3><AlertCircle size={18}/> Review limitations</h3>{shownAI.limitations.map((item,i) => <div className="ai-limitation" key={i}><Info size={16}/><span>{item}</span></div>)}{!!shownAI.missing_context?.length && <><h3 className="ai-missing-head"><ShieldQuestion size={18}/> Context the reviewer did not have</h3>{shownAI.missing_context.map((item,i) => <div className="ai-limitation" key={`m${i}`}><Info size={16}/><span>{item}</span></div>)}</>}</div></div>
              <div className="panel ai-compare" role="region" aria-label="Static scan and AI review">
                <div className="panel-head"><div><h3>Static scan and AI review, side by side</h3><p>Neither column is verified. Test evidence: none. No tests were run by ShipSafe or by the review.</p></div></div>
                <div className="ai-compare-grid">
                  <div><div className="micro-label">STATIC SUSPICIONS · HEURISTIC SCAN</div>
                    {!shownIsOfThisScan ? <p className="muted-small">This review belongs to an earlier scan; the static findings of the scan on screen are not what it was compared with.</p>
                      : report.findings.length ? report.findings.map(item => <div className="ai-compare-item" key={item.id}><Severity level={item.severity}/><span><strong>{item.title}</strong><small>{item.file}{item.line != null ? `:${item.line}` : ''}</small></span>{raisedByReview.has(item.id) && <Pill kind="muted">Referenced by the review</Pill>}</div>)
                      : <p className="muted-small">No static pattern flagged.</p>}
                  </div>
                  <div><div className="micro-label">AI FINDINGS · UNVERIFIED</div>
                    {shownAI.findings.length ? shownAI.findings.map((item, index) => {
                      const related = shownIsOfThisScan ? item.related_static_finding_ids.map(id => staticTitles.get(id)).filter(Boolean) : []
                      return <div className="ai-compare-item" key={`${index}-${item.title}`}><Severity level={item.severity}/><span><strong>{item.title}</strong><small>{item.file}{item.line ? `:${item.line}` : ''}{related.length ? ` · relates to static: ${related.join('; ')}` : ''}</small></span>{!item.related_static_finding_ids.length && <Pill kind="muted">Not in the static scan</Pill>}</div>
                    }) : <p className="muted-small">The review proposed no finding.</p>}
                  </div>
                </div>
              </div>
            </> : <div className="panel ai-empty"><div className="ai-empty-icon"><Bot size={32}/></div><h3>No AI review of this scan yet</h3><p>Export this scan's handoff bundle and bring back the JSON file created in your own Claude Code session. Your Git analysis will stay intact.</p></div>}
          </div>}
          {page === 'history' && <div className="panel history-panel"><div className="panel-head"><div><h3>Recent analyses</h3><p>Stored in the local SQLite database</p></div><Pill kind="muted">{visibleHistory.length} saved{history.length >= SCAN_LIST_LIMIT ? ` · newest ${SCAN_LIST_LIMIT} shown` : ''}</Pill></div><div className="history-table-wrap"><table className="history-table"><thead><tr><th>Comparison</th><th>Scanned</th><th>Files</th><th>Static findings</th><th>Static risk</th><th></th></tr></thead><tbody>{visibleHistory.map(row => <tr key={row.id}><td><div className="comparison-cell"><GitPullRequest size={18}/><div><strong>{shortRef(row.head_ref)}</strong><small>{changeText(row.base_ref, row.head_ref, row.binding?.pull_request_id != null)}</small>{row.binding?.pull_request_id != null && <small className="bb-history-pr">Bitbucket · {row.binding.repository_id} · PR #{row.binding.pull_request_id} <StaleBadge binding={row.binding}/></small>}</div></div></td><td>{new Date(row.created_at).toLocaleString()}</td><td>{row.summary.files_changed}</td><td>{row.summary.finding_count}</td><td><Pill kind={riskColor(row.summary.risk_score)}>{row.summary.risk_score}/100</Pill></td><td><button className="table-action" onClick={() => openHistory(row.id)}>Open <ArrowRight size={14}/></button></td></tr>)}</tbody></table></div>{!visibleHistory.length && <Empty icon={History} title="No saved scans" description={live ? 'Scan a Bitbucket pull request to start building an evidence history.' : 'Run your first branch comparison to start building an evidence history.'}/>}</div>}
          {page === 'settings' && <div className="settings-grid"><div className="panel settings-panel"><div className="panel-head"><div><h3>Workspace configuration</h3><p>Active development environment</p></div><Settings2 size={18}/></div><div className="settings-row"><span>Workspace name</span><strong>{live ? `Bitbucket · ${workspaceName ?? 'unknown'}` : 'ShipSafe Demo'}</strong></div><div className="settings-row"><span>{live ? 'Approved repositories' : 'Repository'}</span><strong className="mono smaller">{live ? (bitbucketStatus.data?.repositories.join(', ') || 'None') : demo?.repository_path || 'Not connected'}</strong></div><div className="settings-row"><span>Default base</span><strong className="mono">{live ? 'PR destination' : 'main'}</strong></div><div className="settings-row"><span>Scanning mode</span><Pill kind="demo">Read-only</Pill></div><div className="settings-row"><span>Data storage</span><strong>Local SQLite</strong></div><div className="settings-row"><span>Test runner</span><Pill kind="warning">Not enabled</Pill></div><div className="settings-row"><span>AI handoff</span><Pill kind="demo">Claude manual · no API key</Pill></div><div className="settings-row"><span>AI review models</span>{configuredProviders.length ? <span className="ai-provider-pills">{configuredProviders.map(item => <Pill key={item.provider} kind="good">{item.label} · {item.model}</Pill>)}</span> : <Pill kind="muted">Not configured</Pill>}</div></div><div className="panel settings-panel"><div className="panel-head"><div><h3>Security boundaries</h3><p>Designed for local, authorized source code</p></div><LockKeyhole size={19}/></div><div className="safe-rule"><CheckCircle2 size={17}/><span>Git commands use argument arrays, never shell interpolation.</span></div><div className="safe-rule"><CheckCircle2 size={17}/><span>Default allowlist includes only the generated synthetic repository.</span></div><div className="safe-rule"><CheckCircle2 size={17}/><span>Scans and JSON imports never execute repository code.</span></div><div className="safe-rule"><CheckCircle2 size={17}/><span>Reports make no claim that suspected vulnerabilities were verified.</span></div><div className="settings-explain">To scan an explicitly approved local repository, set <code>SHIPSAFE_ALLOWED_ROOT</code> in the backend environment and provide its path through the API. Don't grant broad access to untrusted directories.</div></div></div>}
        </>}
        <footer className="app-footer"><span><Logo size={22}/> ShipSafe <b>v0.2</b></span><span>Evidence-first release intelligence · {pullRequestBinding ? `Bitbucket · ${pullRequestBinding.repository_id}` : live ? `Bitbucket · ${workspaceName ?? 'not configured'}` : 'Synthetic demo repository'}</span></footer>
      </main>
    </div>
  </div>
}
