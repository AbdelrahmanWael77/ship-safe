import { useCallback, useEffect, useMemo, useState } from 'react'
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
import { api, API_BASE as API } from './api'
import { DiffViewer, Empty, FileIcon, FindingCard, Pill, Severity } from './components'
import { BitbucketSection } from './bitbucket/BitbucketSection'
import { getBitbucketStatus, isMockMode } from './bitbucket/client'
import { BITBUCKET_NAV, INITIAL_SELECTION, bitbucketNavEntry, bitbucketPageLabel, isBitbucketPage } from './bitbucket/pages'
import type { BitbucketNavigate, BitbucketPage, BitbucketSelection } from './bitbucket/pages'
import { StaleBadge } from './bitbucket/StaleBadge'
import { useLoad } from './bitbucket/useLoad'
import type { AIReview, DemoInfo, FileChange, Finding, Report, ScanHistory } from './types'

type Page = 'overview' | 'changes' | 'findings' | 'tests' | 'ai' | 'history' | 'settings' | BitbucketPage
const NAV: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'changes', label: 'Code changes', icon: GitCompareArrows },
  { id: 'findings', label: 'Risk findings', icon: ShieldAlert },
  { id: 'tests', label: 'Test intelligence', icon: FlaskConical },
  { id: 'ai', label: 'Claude Review', icon: Bot },
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

function StatCard({ icon: Icon, title, value, note, tone }: { icon: typeof Activity; title: string; value: string | number; note: string; tone: string }) {
  return <div className="stat-card panel">
    <div className="stat-top"><span className={`stat-icon tone-${tone}`}><Icon size={19} /></span><span className="stat-minigraph"><i/><i/><i/><i/><i/><i/></span></div>
    <div className="stat-value">{value}</div>
    <div className="stat-label">{title}</div>
    <div className="stat-note">{note}</div>
  </div>
}

export default function App() {
  const [page, setPage] = useState<Page>('overview')
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
  const [bitbucketSelection, setBitbucketSelection] = useState<BitbucketSelection>(INITIAL_SELECTION)
  const bitbucketNavigate: BitbucketNavigate = (next, change) => {
    if (change) setBitbucketSelection(previous => ({ ...previous, ...change }))
    setPage(next)
  }

  const refreshHistory = useCallback(async () => {
    const records = await api<ScanHistory[]>('/api/scans')
    setHistory(records)
    return records
  }, [])

  useEffect(() => {
    let active = true
    const init = async () => {
      try {
        const info = await api<DemoInfo>('/api/demo')
        if (!active) return
        setDemo(info)
        setHead(info.default_head)
        const records = await api<ScanHistory[]>('/api/scans')
        if (!active) return
        setHistory(records)
        if (records.length) {
          const previous = await api<Report>(`/api/scans/${records[0].id}`)
          if (active) { setReport(previous); setSelectedFile(previous.files[0]?.path || '') }
        } else {
          const initial = await api<Report>('/api/scans', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_ref: 'main', head_ref: info.default_head }) })
          if (active) { setReport(initial); setSelectedFile(initial.files[0]?.path || ''); await refreshHistory() }
        }
      } catch (exc) {
        if (active) setError(exc instanceof Error ? exc.message : String(exc))
      } finally { if (active) setLoading(false) }
    }
    init()
    return () => { active = false }
  }, [refreshHistory])

  useEffect(() => {
    if (!report) { setAIReviews([]); return }
    let active = true
    const scanID = report.id
    api<AIReview[]>(`/api/scans/${scanID}/ai/reviews`)
      .then(rows => { if (active) setAIReviews(rows) })
      .catch(exc => { if (active) setError(exc instanceof Error ? exc.message : String(exc)) })
    setAIFile(null)
    // Whether exporting this scan's source code needs an explicit confirmation.
    // Unknown (request failed, older backend) is treated as "needed".
    setShareAck(false); setShareAckRequired(true)
    api<{ acknowledgement_required?: boolean }>(`/api/scans/${scanID}/ai/context`)
      .then(context => { if (active) setShareAckRequired(context.acknowledgement_required !== false) })
      .catch(() => undefined)
    return () => { active = false }
  }, [report?.id])

  const importAIReview = async () => {
    if (!report || !aiFile) return
    if (aiFile.size > 256 * 1024) { setError('Review file is too large (max 256 KiB).'); return }
    setImportingAI(true); setNotice(null); setError(null)
    try {
      const source = await aiFile.text()
      const review = await api<AIReview>(`/api/scans/${report.id}/ai/reviews`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: source,
      })
      setAIReviews(previous => [review, ...previous])
      setAIFile(null)
      setNotice(`Review imported for scan ${report.id.slice(0, 8)}. AI analysis is unverified and no tests were run.`)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally { setImportingAI(false) }
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

  const openHistory = async (id: string) => {
    setLoading(true); setError(null)
    try {
      const old = await api<Report>(`/api/scans/${id}`)
      setReport(old); setHead(old.head_ref); setBase(old.base_ref)
      setSelectedFile(old.files[0]?.path || ''); setPage('overview')
      setNotice(`Loaded saved scan from ${new Date(old.created_at).toLocaleString()}.`)
    } catch (exc) { setError(exc instanceof Error ? exc.message : String(exc)) }
    finally { setLoading(false) }
  }

  const goFile = (path: string) => { setSelectedFile(path); setPage('changes') }
  const selected = useMemo(() => report?.files.find(f => f.path === selectedFile) || report?.files[0], [report, selectedFile])
  const pageName = NAV.find(n => n.id === page)?.label || bitbucketPageLabel(page) || 'Overview'
  // Asked once at start; a failure here never touches the demo flow or the error banner.
  const bitbucketStatus = useLoad(getBitbucketStatus, 'bitbucket-status')
  // A Bitbucket pull request scan is never labelled as the local demo.
  const pullRequestBinding = report?.binding && report.binding.provider === 'bitbucket-cloud' && report.binding.pull_request_id != null ? report.binding : null
  const latestAI = aiReviews[0]
  const filteredFindings = report?.findings.filter(f => `${f.title} ${f.category} ${f.file}`.toLowerCase().includes(search.toLowerCase())) || []

  return <div className="app-layout">
    <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <div className="brand"><Logo/><div><strong>ShipSafe<span className="brand-period">.</span></strong><small>RELEASE GUARDIAN</small></div></div>
      <div className="workspace-picker"><div className="workspace-symbol"><Layers3 size={16}/></div><div><strong>{pullRequestBinding ? 'Bitbucket' : 'Demo workspace'}</strong><small>{pullRequestBinding ? pullRequestBinding.repository_id : 'LedgerLite project'}</small></div><ChevronDown size={15}/></div>
      <div className="sidebar-section-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Primary navigation">
        {NAV.filter(item => item.id !== 'settings').map(item => <button className={`nav-item ${page === item.id ? 'active' : ''}`} key={item.id} onClick={() => { setPage(item.id); setSidebarOpen(false) }}><item.icon size={18}/><span>{item.label}</span>{item.id === 'findings' && !!report?.findings.length && <b className="nav-count">{report.findings.length}</b>}</button>)}
      </nav>
      <div className="sidebar-section-label tools-label">BITBUCKET</div>
      <nav className="nav-list" aria-label="Bitbucket navigation">
        {BITBUCKET_NAV.map(item => <button className={`nav-item ${bitbucketNavEntry(page) === item.id ? 'active' : ''}`} key={item.id} onClick={() => { setPage(item.id); setSidebarOpen(false) }}><item.icon size={18}/><span>{item.label}</span>{bitbucketStatus.data && !bitbucketStatus.data.configured && <b className="nav-tag" title="Bitbucket is not configured on the server">Off</b>}</button>)}
      </nav>
      <div className="sidebar-section-label tools-label">PREFERENCES</div>
      <nav className="nav-list"><button className={`nav-item ${page === 'settings' ? 'active' : ''}`} onClick={() => { setPage('settings'); setSidebarOpen(false) }}><Settings2 size={18}/><span>Configuration</span></button></nav>
      <div className="sidebar-bottom">
        <div className="help-box"><div className="help-icon"><BookOpen size={17}/></div><strong>Built for better releases</strong><p>Every finding should lead to better questions, not blind confidence.</p><button onClick={() => setPage('tests')}>Explore testing <ArrowRight size={13}/></button></div>
        <div className="sidebar-footer"><span className="online-dot"/> {demo ? 'API connected' : 'API unavailable'} <small>v0.2.0</small></div>
      </div>
    </aside>
    {sidebarOpen && <div className="backdrop" onClick={() => setSidebarOpen(false)}/>}
    <div className="main-wrap">
      <header className="topbar">
        <div className="topbar-left"><button className="menu-button" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle menu"><Menu size={22}/></button><span>Workspace</span><ChevronRight size={14}/><strong>{pageName}</strong></div>
        <div className="topbar-right"><span className="top-live"><span className="online-dot"/> {pullRequestBinding ? 'BITBUCKET SCAN' : 'LIVE DEMO'}</span><span className="divider-v"/><span className="header-icon"><CircleHelp size={18}/></span><div className="avatar">SS</div></div>
      </header>
      {import.meta.env.DEV && isMockMode() && <div className="mock-banner" role="status"><strong>MOCK DATA</strong> Development mock mode: everything on the Bitbucket screens is invented. Nothing is read from Bitbucket.</div>}`n      <main className="main-content">
        {error && <div className="alert alert-error"><AlertCircle size={18}/><span>{error}</span><button onClick={() => setError(null)}><X size={17}/></button></div>}
        {notice && <div className="alert alert-success"><CheckCircle2 size={18}/><span>{notice}</span><button onClick={() => setNotice(null)}><X size={17}/></button></div>}
        {loading && !report ? <div className="initial-load"><div className="spinner"/><h2>Connecting to Git analysis…</h2><p>Preparing the synthetic LedgerLite repository and loading your first scan.</p></div> : null}
        {page === 'overview' && <>
          <div className="page-heading dashboard-heading">
            <div><div className="eyebrow"><span className="eyebrow-line"/> RELEASE INTELLIGENCE</div><h1>Ship with confidence<span className="title-dot">.</span></h1><p>Understand what's changing, spot hidden risks, and release with evidence—not assumptions.</p></div>
            <div className="heading-actions">{pullRequestBinding ? <Pill kind="good" dot>BITBUCKET · READ-ONLY</Pill> : <Pill kind="demo" dot>LOCAL DEMO</Pill>}<button className="secondary-button" onClick={() => setPage('history')}><History size={16}/> View history</button></div>
          </div>
          <div className="hero-scan panel">
            <div className="hero-scan-copy"><div className="hero-title"><span className="hero-icon"><GitPullRequest size={21}/></span><div><h2>{pullRequestBinding ? 'Run a demo analysis' : 'Analyze a code change'}</h2><p>{pullRequestBinding ? 'This form scans the synthetic demo repository, not Bitbucket. The report below is a Bitbucket pull request scan.' : 'Compare real Git commits in the synthetic LedgerLite repository.'}</p></div></div></div>
            <div className="scan-form">
              <div className="scan-field"><label>BASE BRANCH</label><div className="select-shell"><GitBranch size={17}/><select value={base} onChange={e => setBase(e.target.value)}><option value="main">main</option>{demo?.branches.map(b => <option key={b.ref} value={b.ref}>{shortRef(b.ref)}</option>)}</select><ChevronDown size={15}/></div></div>
              <div className="compare-arrow"><ArrowRight size={18}/></div>
              <div className="scan-field head-field"><label>COMPARE BRANCH</label><div className="select-shell"><GitBranch size={17}/><select value={head} onChange={e => setHead(e.target.value)}><option value="main">main</option>{demo?.branches.map(b => <option key={b.ref} value={b.ref}>{shortRef(b.ref)}</option>)}</select><ChevronDown size={15}/></div></div>
              <button className="primary-button scan-button" disabled={scanning || !demo} onClick={startScan}>{scanning ? <RefreshCw className="spin" size={18}/> : <ScanSearch size={18}/>} {scanning ? 'Analyzing…' : 'Run analysis'} <ArrowRight size={16}/></button>
            </div>
            <div className="scan-foot"><LockKeyhole size={14}/><span>Scans only the trusted synthetic repo by default · No code is executed</span><span className="scan-foot-right">{report ? `Last scan ${relative(report.created_at)}` : 'Ready to analyze'}</span></div>
          </div>
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
            <div className="stat-grid">
              <StatCard icon={FileCode2} title="Files changed" value={report.summary.files_omitted ? `${report.summary.files_changed}+` : report.summary.files_changed} note={`+${report.summary.lines_added} additions · -${report.summary.lines_removed} deletions${report.summary.files_omitted ? ` · ${report.summary.files_omitted} more files not listed` : ''}`} tone="blue"/>
              <StatCard icon={ShieldAlert} title="Risk findings" value={report.summary.finding_count} note={report.summary.finding_count ? 'Requires engineering review' : 'No patterns flagged'} tone="red"/>
              <StatCard icon={GitCommitHorizontal} title="Affected importers" value={report.affected_modules.length} note="Direct Python import references" tone="purple"/>
              <StatCard icon={FlaskConical} title="Test execution" value="Not run" note="No untrusted code executed" tone="amber"/>
            </div>
            {report.summary.truncated && <div className="footnote" role="status"><AlertTriangle size={15}/> This report is incomplete: {report.summary.files_omitted ? `${report.summary.files_omitted} changed files beyond the first ${report.summary.files_changed} are not listed and are excluded from all counts` : ''}{report.summary.files_omitted && report.files.some(f => f.diff_truncated) ? '; ' : ''}{report.files.some(f => f.diff_truncated) ? `${report.files.filter(f => f.diff_truncated).length} diffs are cut at 140 lines (marked in Code changes)` : ''}. The Claude handoff package carries the same gaps.</div>}
            <div className="dashboard-grid">
              <div className="panel risk-panel"><div className="panel-head"><div><h3>Risk intelligence</h3><p>Potential issues detected in the diff</p></div><button className="ghost-button" onClick={() => setPage('findings')}>View all <ArrowUpRight size={15}/></button></div>
                {report.findings.length ? <div className="risk-list">{report.findings.slice(0, 4).map(f => <button className="risk-row" key={f.id} onClick={() => setPage('findings')}><span className={`risk-symbol ${f.severity}`}><AlertTriangle size={18}/></span><span className="risk-details"><strong>{f.title}</strong><small>{f.file} · {f.category}</small></span><Severity level={f.severity}/><ChevronRight size={16} className="risk-chevron"/></button>)}</div> : <Empty icon={ShieldCheck} title="No known patterns flagged" description="This is not a guarantee that the change is safe. Human review is still necessary."/>}
                <div className="risk-panel-footer"><Info size={15}/><span>Heuristic findings are leads for review, not verified defects.</span></div>
              </div>
              <div className="panel readiness-panel"><div className="panel-head"><div><h3>Release readiness</h3><p>Heuristic score, not an approval</p></div><MoreHorizontal size={20} className="dim"/></div><div className="readiness-inner"><ProgressRing score={report.summary.risk_score}/><div className="readiness-result"><Pill kind={riskColor(report.summary.risk_score)} dot>{report.summary.recommendation}</Pill><p>{report.findings.length ? 'Review the identified patterns and verify with regression tests before release.' : 'No high-risk patterns detected. Additional tests and review may still be required.'}</p></div></div><div className="readiness-footer"><ShieldQuestion size={17}/><div><strong>Human approval required</strong><span>ShipSafe never marks a release fully safe.</span></div></div></div>
            </div>
            <div className="dashboard-grid lower-grid">
              <div className="panel changes-panel"><div className="panel-head"><div><h3>Changed files</h3><p>Source-controlled changes from Git</p></div><button className="ghost-button" onClick={() => setPage('changes')}>Explore diff <ArrowUpRight size={15}/></button></div><div className="changed-files-list">{report.files.slice(0, 5).map(f => <button key={f.path} className="changed-file-row" onClick={() => goFile(f.path)}><FileIcon path={f.path}/><span className="file-name"><strong>{f.path.split('/').pop()}</strong><small>{f.path}</small></span><span className="file-bars"><i style={{width: Math.min(65, f.additions * 8 + 6)}}/><b style={{width: Math.min(40, f.deletions * 8 + 6)}}/></span><span className="line-changes"><em>+{f.additions}</em><b>-{f.deletions}</b></span></button>)}</div></div>
              <div className="panel insight-panel"><div className="panel-head"><div><h3>What this scan means</h3><p>Important next steps</p></div><Sparkles size={19} className="sparkle"/></div><div className="insight-item"><span className="insight-step">01</span><div><strong>Inspect the diff</strong><p>Review the exact lines that changed and their call sites.</p></div></div><div className="insight-item"><span className="insight-step">02</span><div><strong>Verify suspected risks</strong><p>Write a regression test before accepting a finding as confirmed.</p></div></div><div className="insight-item"><span className="insight-step">03</span><div><strong>Record your decision</strong><p>Export the report with known gaps and review notes.</p></div></div><button className="outline-button full" onClick={() => setPage('tests')}><FlaskConical size={16}/> Explore test scenarios <ArrowRight size={16}/></button></div>
            </div>
            <div className="panel ai-callout"><div className="ai-callout-icon"><Bot size={23}/></div><div><h3>Get a second opinion from Claude Code</h3><p>{latestAI ? `A manually imported review is available (${latestAI.findings.length} proposed findings).` : 'Export the Git evidence, review it in your own signed-in Claude Code session, then import the JSON.'}</p></div><button className="secondary-button" onClick={() => setPage('ai')}>Open Claude Review <ArrowRight size={16}/></button></div>
            <div className="footnote"><Info size={15}/> Git findings are heuristic. Imported AI suggestions are separate, unverified, and never change test execution status.</div>
          </>}
        </>}
        {isBitbucketPage(page) && <BitbucketSection page={page} status={bitbucketStatus} selection={bitbucketSelection} navigate={bitbucketNavigate} onScanned={() => { void refreshHistory().catch(() => undefined) }} onOpenReport={openHistory}/>}
        {page !== 'overview' && !isBitbucketPage(page) && <>
          <div className="subpage-heading"><div className="eyebrow"><span className="eyebrow-line"/> WORKSPACE / {page.toUpperCase()}</div><div className="subpage-title"><div><h1>{pageName}<span className="title-dot">.</span></h1><p>{({overview:'',changes:'Review actual changed files, functions, and Git patch details.',findings:'Investigate suspected problems and the evidence behind them.',tests:'Identify missing regression coverage. No tests are claimed as executed.',ai:'Human-mediated Claude Code review. No API keys, no direct model calls.',history:'Go back to previous local analysis reports.',settings:'Local-first setup, security boundaries, and data sources.'} as Record<Page,string>)[page]}</p></div>{report && page !== 'settings' && <a className="secondary-button export-link" href={`${API}/api/scans/${report.id}/export`} download><Download size={16}/> Export JSON</a>}</div></div>
          {page === 'changes' && report && <div className="code-layout">
            <div className="panel file-browser"><div className="panel-head"><div><h3>Repository files</h3><p>{report.summary.files_changed} changed in this compare{report.summary.files_omitted ? ` · ${report.summary.files_omitted} more not listed` : ''}</p></div><FolderGit2 size={18} className="dim"/></div>{report.files.map(file => <button className={`file-select ${selected?.path === file.path ? 'selected' : ''}`} key={file.path} onClick={() => setSelectedFile(file.path)}><FileIcon path={file.path}/><span><strong>{file.path.split('/').pop()}</strong><small>{file.path}</small></span><ChevronRight size={16}/></button>)}<div className="browser-foot"><GitCommitHorizontal size={14}/><span>{report.base_sha} → {report.head_sha}</span></div></div>
            <div className="code-main">{selected ? <><DiffViewer file={selected}/><div className="panel code-context"><div className="panel-head"><div><h3>Change context</h3><p>Static AST and import dependency observations</p></div></div><div className="context-grid"><div><span className="micro-label">CHANGED FUNCTIONS</span>{selected.changed_functions.length ? selected.changed_functions.map(fn => <span key={fn} className="code-chip"><Code2 size={13}/>{fn}()</span>) : <p className="muted-small">No changed function names detected</p>}</div><div><span className="micro-label">DIRECT IMPORTERS</span>{report.affected_modules.filter(m => m.imports_changed.some(mod => mod === selected.path.replace(/\.py$/, '').replace(/\//g, '.'))).map(m => <span key={m.path} className="code-chip"><Layers3 size={13}/>{m.path}</span>)}{!report.affected_modules.some(m => m.imports_changed.includes(selected.path.replace(/\.py$/, '').replace(/\//g, '.'))) && <p className="muted-small">No direct importers found</p>}</div></div></div></> : <Empty title="No changed files" description="Choose a branch with a code change to inspect its Git diff."/>}</div>
          </div>}
          {page === 'findings' && report && <><div className="findings-toolbar panel"><div className="findings-count"><ShieldAlert size={20}/><div><strong>{report.findings.length} suspected risk{report.findings.length !== 1 ? 's' : ''}</strong><small>Ordered by scan output</small></div></div><div className="search-field"><Search size={16}/><input placeholder="Search findings or files..." value={search} onChange={e => setSearch(e.target.value)} /></div></div><div className="findings-grid">{filteredFindings.length ? filteredFindings.map(f => <FindingCard key={f.id} finding={f} onOpenFile={goFile}/>) : <Empty icon={ShieldCheck} title={report.findings.length ? 'No findings match your search' : 'No risk patterns detected'} description={report.findings.length ? 'Try searching another file, category, or issue.' : 'Static analysis found no known patterns in this diff; that does not establish safety.'}/>}</div><div className="disclaimer-box"><Info size={18}/>{report.disclaimer}</div></>}
          {page === 'tests' && report && <div className="test-layout"><div className="panel test-main"><div className="test-status-banner"><span className="test-pictogram"><FlaskConical size={24}/></span><div><Pill kind="warning">NOT EXECUTED</Pill><h2>Test intelligence</h2><p>ShipSafe has produced candidate regression scenarios from actual diff findings. A test runner is planned for the next phase; this foundation does not execute repository code.</p></div></div><div className="panel-head test-list-head"><div><h3>Suggested regression scenarios</h3><p>Generated from observed risk categories</p></div><span className="light-count">{report.test_suggestions.length} suggestions</span></div>{report.test_suggestions.length ? report.test_suggestions.map((item, index) => <div className="test-item" key={`${item.file}-${index}`}><span className="test-number">{String(index + 1).padStart(2, '0')}</span><div><strong>{item.scenario}</strong><small><FileCode2 size={13}/>{item.file} · {item.category}</small></div><Pill kind="muted">Proposed</Pill></div>) : <Empty icon={CheckCircle2} title="No targeted scenarios yet" description="Try a risk-bearing demo branch. Normal engineering tests are still recommended."/>}</div><div className="test-right"><div className="panel"><div className="panel-head"><div><h3>Run the fixture suite</h3><p>Manual command on trusted code</p></div><Terminal size={18}/></div><div className="terminal-mini"><span className="terminal-dot-row"><i/><i/><i/></span><code>cd backend/demo-repo<br/>python -m pytest -q</code></div><p className="small-para">The fixture's existing happy-path tests intentionally miss the injected regressions. Passing them does not verify the flagged behavior.</p><div className="manual-tag"><LockKeyhole size={14}/> Only run code you explicitly trust.</div></div><div className="panel score-note"><ShieldQuestion size={22}/><h3>Evidence over confidence</h3><p>Suggested tests are hypotheses. A confirmed regression requires an executable test that fails before the fix and passes afterward.</p></div></div></div>}
          {page === 'ai' && report && <div className="ai-workspace">
            <div className="ai-intro panel">
              <div className="ai-intro-mark"><Bot size={27}/></div>
              <div><div className="eyebrow">OPTIONAL HUMAN-IN-THE-LOOP AI</div><h2>Bring your own Claude Code session.</h2><p>ShipSafe does not sign in, store tokens, call Claude's API, or run the Claude CLI on your behalf. You review the exported diff in Claude Code using your own Team account, then import structured findings.</p></div>
              <Pill kind="demo">NO API KEY IN SHIPSAFE</Pill>
            </div>
            <div className="ai-steps">
              <div className="panel ai-step"><div className="ai-step-top"><span className="ai-step-num">01</span><FileArchive size={19}/></div><h3>Export review package</h3><p>Download Git evidence, the structured JSON response template, and review instructions for scan <code>{report.id.slice(0, 8)}</code>.</p>{shareAckRequired && <label className="ai-share-ack"><input type="checkbox" checked={shareAck} onChange={e => setShareAck(e.target.checked)}/><span>This package contains source code that is not the synthetic demo. I am allowed to share it with Claude Code, and I will check it for secrets first (redaction is best-effort).</span></label>}{shareAckRequired && !shareAck ? <button className="secondary-button ai-action" disabled><Download size={16}/> Download handoff ZIP</button> : <a className="secondary-button ai-action" href={`${API}/api/scans/${report.id}/ai/handoff${shareAckRequired ? '?acknowledge_source_sharing=true' : ''}`} download><Download size={16}/> Download handoff ZIP</a>}</div>
              <div className="panel ai-step"><div className="ai-step-top"><span className="ai-step-num">02</span><Terminal size={19}/></div><h3>Review in Claude Code</h3><p>Extract the ZIP. Open a terminal in the extracted folder, run <code>claude</code>, and ask it to read the instructions and write <code>claude-review.json</code>.</p><div className="ai-command"><code>claude</code><button title="Copy CLI instruction" onClick={() => { void navigator.clipboard.writeText('Read REVIEW_INSTRUCTIONS.md and review-input.json in this directory. Follow the instructions and write claude-review.json. Do not run code or modify any other files.') ; setNotice('Copied instructions for Claude Code.') }}><Copy size={15}/></button></div></div>
              <div className="panel ai-step"><div className="ai-step-top"><span className="ai-step-num">03</span><UploadCloud size={19}/></div><h3>Import the JSON result</h3><p>Inspect Claude's output before importing. The backend checks its schema, scan ID, context digest, and referenced files.</p><label className="ai-file-label"><input type="file" accept=".json,application/json" onChange={e => setAIFile(e.target.files?.[0] || null)}/><UploadCloud size={15}/>{aiFile ? aiFile.name : 'Choose claude-review.json'}</label><button className="primary-button ai-action" disabled={!aiFile || importingAI} onClick={importAIReview}>{importingAI ? <RefreshCw size={16} className="spin"/> : <Check size={16}/>} {importingAI ? 'Importing…' : 'Import review'}</button></div>
            </div>
            <div className="ai-warning"><Info size={18}/><span><strong>Security & evidence boundary:</strong> The package contains source-code diffs. Only share authorized code with Claude. Import does not prove who authored the JSON, confirm vulnerabilities, run tests, or grant approval to release.</span></div>
            <div className="ai-report-heading"><div><h2>Imported AI review</h2><p>Associated only with {report.base_ref} → {report.head_ref} · context digest verified</p></div>{aiReviews.length > 0 && <Pill kind="muted">{aiReviews.length} import{aiReviews.length !== 1 ? 's' : ''}</Pill>}</div>
            {latestAI ? <>
              {latestAI.scan_binding?.stale && <div className="panel bb-state bb-warning-panel" role="alert"><AlertTriangle size={22}/><div><h3>This review is stale <StaleBadge binding={latestAI.scan_binding}/></h3><p>The pull request has new commits since the scan this review was made for (head <code>{latestAI.scan_binding.head_commit}</code>). It does not describe the current code. Scan the pull request again and review the new scan.</p></div></div>}
              <div className="panel ai-review-summary"><div className="ai-review-title"><div><Pill kind="warning">UNVERIFIED AI SUGGESTIONS</Pill><h3>{latestAI.recommendation === 'block_release' ? 'Suggested: Block release' : latestAI.recommendation === 'manual_review' ? 'Suggested: Manual review' : 'Insufficient evidence'}</h3><p>Imported {new Date(latestAI.imported_at).toLocaleString()} · Source provenance not verified</p></div><div className="ai-review-count"><strong>{latestAI.findings.length}</strong><span>AI findings</span></div></div><p className="ai-review-summary-text">{latestAI.summary}</p><div className="ai-verification-note"><ShieldQuestion size={16}/> No tests were executed as part of this import. This assessment cannot override the static scan, change risk score, or human review.</div></div>
              {latestAI.findings.length > 0 ? <div className="ai-findings-grid">{latestAI.findings.map((f,i) => <div className="panel ai-finding" key={`${i}-${f.title}`}><div className="ai-finding-head"><Severity level={f.severity}/><Pill kind="muted">{f.confidence} confidence</Pill>{f.id && <Pill kind="muted">{f.id}</Pill>}<Pill kind="warning">SUSPECTED · UNVERIFIED</Pill></div><h3>{f.title}</h3><p className="ai-finding-category">{f.category} · <button className="text-link" onClick={() => goFile(f.file)}>{f.file}{f.line ? `:${f.line}` : ''}<ArrowUpRight size={13}/></button></p><p>{f.rationale}</p><div className="evidence"><div className="micro-label"><Terminal size={13}/> Reported code evidence</div><code>{f.evidence}</code></div><div className="ai-advice"><Sparkles size={15}/><span>{f.recommendation}</span></div>{f.suggested_validation && <div className="ai-validation"><div className="micro-label"><FlaskConical size={13}/> How to validate (not done)</div><p>{f.suggested_validation}</p></div>}{f.proposed_patch && <div className="evidence ai-patch"><div className="micro-label"><FileDiff size={13}/> Proposed patch · unverified · not applied by ShipSafe</div><pre>{f.proposed_patch}</pre></div>}</div>)}</div> : <Empty icon={ShieldQuestion} title="No risks proposed in imported review" description="This does not establish that the code is safe. Check the review's limitations and independent testing."/>}
              <div className="ai-bottom-grid"><div className="panel ai-list-panel"><h3><FlaskConical size={18}/> Suggested regression tests <Pill kind="muted">NOT RUN</Pill></h3>{latestAI.test_ideas.map((idea,i) => <div className="ai-list-item" key={i}><strong>{idea.title}</strong><p>{idea.scenario}</p><small>Expected: {idea.expected_behavior}{idea.file ? ` · ${idea.file}` : ''}</small></div>)}{!latestAI.test_ideas.length && <p className="small-para">No test ideas provided.</p>}</div><div className="panel ai-list-panel"><h3><AlertCircle size={18}/> Review limitations</h3>{latestAI.limitations.map((item,i) => <div className="ai-limitation" key={i}><Info size={16}/><span>{item}</span></div>)}{!!latestAI.missing_context?.length && <><h3 className="ai-missing-head"><ShieldQuestion size={18}/> Context the reviewer did not have</h3>{latestAI.missing_context.map((item,i) => <div className="ai-limitation" key={`m${i}`}><Info size={16}/><span>{item}</span></div>)}</>}</div></div>
            </> : <div className="panel ai-empty"><div className="ai-empty-icon"><Bot size={32}/></div><h3>No Claude review imported yet</h3><p>Export this scan's handoff bundle and bring back the JSON file created in your own Claude Code session. Your Git analysis will stay intact.</p></div>}
          </div>}
          {page === 'history' && <div className="panel history-panel"><div className="panel-head"><div><h3>Recent analyses</h3><p>Stored in the local SQLite database</p></div><Pill kind="muted">{history.length} saved</Pill></div><div className="history-table-wrap"><table className="history-table"><thead><tr><th>Comparison</th><th>Scanned</th><th>Files</th><th>Findings</th><th>Risk level</th><th></th></tr></thead><tbody>{history.map(row => <tr key={row.id}><td><div className="comparison-cell"><GitPullRequest size={18}/><div><strong>{shortRef(row.head_ref)}</strong><small>{row.base_ref} → {row.head_ref}</small>{row.binding?.pull_request_id != null && <small className="bb-history-pr">Bitbucket · {row.binding.repository_id} · PR #{row.binding.pull_request_id} <StaleBadge binding={row.binding}/></small>}</div></div></td><td>{new Date(row.created_at).toLocaleString()}</td><td>{row.summary.files_changed}</td><td>{row.summary.finding_count}</td><td><Pill kind={riskColor(row.summary.risk_score)}>{row.summary.risk_score}/100</Pill></td><td><button className="table-action" onClick={() => openHistory(row.id)}>Open <ArrowRight size={14}/></button></td></tr>)}</tbody></table></div>{!history.length && <Empty icon={History} title="No saved scans" description="Run your first branch comparison to start building an evidence history."/>}</div>}
          {page === 'settings' && <div className="settings-grid"><div className="panel settings-panel"><div className="panel-head"><div><h3>Workspace configuration</h3><p>Active development environment</p></div><Settings2 size={18}/></div><div className="settings-row"><span>Workspace name</span><strong>ShipSafe Demo</strong></div><div className="settings-row"><span>Repository</span><strong className="mono smaller">{demo?.repository_path || 'Not connected'}</strong></div><div className="settings-row"><span>Default base</span><strong className="mono">main</strong></div><div className="settings-row"><span>Scanning mode</span><Pill kind="demo">Read-only</Pill></div><div className="settings-row"><span>Data storage</span><strong>Local SQLite</strong></div><div className="settings-row"><span>Test runner</span><Pill kind="warning">Not enabled</Pill></div><div className="settings-row"><span>AI handoff</span><Pill kind="demo">Manual · no API key</Pill></div></div><div className="panel settings-panel"><div className="panel-head"><div><h3>Security boundaries</h3><p>Designed for local, authorized source code</p></div><LockKeyhole size={19}/></div><div className="safe-rule"><CheckCircle2 size={17}/><span>Git commands use argument arrays, never shell interpolation.</span></div><div className="safe-rule"><CheckCircle2 size={17}/><span>Default allowlist includes only the generated synthetic repository.</span></div><div className="safe-rule"><CheckCircle2 size={17}/><span>Scans and JSON imports never execute repository code.</span></div><div className="safe-rule"><CheckCircle2 size={17}/><span>Reports make no claim that suspected vulnerabilities were verified.</span></div><div className="settings-explain">To scan an explicitly approved local repository, set <code>SHIPSAFE_ALLOWED_ROOT</code> in the backend environment and provide its path through the API. Don't grant broad access to untrusted directories.</div></div></div>}
        </>}
        <footer className="app-footer"><span><Logo size={22}/> ShipSafe <b>v0.2</b></span><span>Evidence-first release intelligence · {pullRequestBinding ? `Bitbucket · ${pullRequestBinding.repository_id}` : 'Synthetic demo repository'}</span></footer>
      </main>
    </div>
  </div>
}
