// Presentational pieces shared by the dashboard (App.tsx) and the Bitbucket
// screens. Moved out of App.tsx unchanged so both can render a report the
// same way; nothing here fetches or holds state.
import type { ReactNode } from 'react'
import { AlertTriangle, ArrowUpRight, CircleHelp, Code2, FileDiff, FileText, ShieldCheck, Sparkles, Terminal } from 'lucide-react'
import type { FileChange, Finding } from './types'

export function Pill({ kind = 'neutral', children, dot = false }: { kind?: string; children: ReactNode; dot?: boolean }) {
  return <span className={`pill pill-${kind}`}>{dot && <span className="pill-dot" />}{children}</span>
}

export function Severity({ level }: { level: string }) {
  return <Pill kind={level}>{level.toUpperCase()}</Pill>
}

export function Empty({ icon: Icon = ShieldCheck, title, description }: { icon?: typeof ShieldCheck; title: string; description: string }) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={26} /></div><h3>{title}</h3><p>{description}</p></div>
}

export function FileIcon({ path }: { path: string }) {
  return <span className={`file-icon ${path.endsWith('.py') ? 'python' : 'doc'}`}>
    {path.endsWith('.py') ? <Code2 size={17}/> : <FileText size={17}/>}
  </span>
}

export function DiffViewer({ file }: { file: FileChange }) {
  const lines = file.diff.split('\n')
  return <div className="diff-viewer">
    <div className="diff-toolbar"><span><FileDiff size={16}/> {file.path}</span><span className="diff-count">{file.diff_truncated && <Pill kind="warning">Diff truncated · {file.diff_lines_omitted ?? 0} lines not shown</Pill>}<b>+{file.additions}</b><em>-{file.deletions}</em></span></div>
    <div className="code-lines" role="region" aria-label={`Git diff for ${file.path}${file.diff_truncated ? ' (truncated)' : ''}`}>
      {lines.map((line, index) => {
        let klass = 'normal'
        if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff --git') || line.startsWith('index ')) klass = 'meta'
        else if (line.startsWith('@@') || line.startsWith('... [')) klass = 'hunk'
        else if (line.startsWith('+')) klass = 'add'
        else if (line.startsWith('-')) klass = 'remove'
        return <div className={`code-line ${klass}`} key={index}><span className="line-num">{index + 1}</span><span>{line || ' '}</span></div>
      })}
    </div>
  </div>
}

export function FindingCard({ finding, onOpenFile }: { finding: Finding; onOpenFile: (path: string) => void }) {
  return <div className="finding-card panel">
    <div className="finding-top">
      <div className={`finding-icon finding-${finding.severity}`}><AlertTriangle size={20}/></div>
      <div className="finding-heading"><div className="finding-title-row"><h3>{finding.title}</h3><Severity level={finding.severity}/></div><div className="finding-meta"><span>{finding.category}</span><span>•</span><button className="text-link" onClick={() => onOpenFile(finding.file)}>{finding.file}{finding.line != null ? `:${finding.line}` : ''}<ArrowUpRight size={12}/></button></div></div>
    </div>
    <p className="finding-description">{finding.explanation}</p>
    <div className="evidence"><div className="micro-label"><Terminal size={13}/> Code evidence</div><code>{finding.evidence}</code></div>
    <div className="recommendation"><span><Sparkles size={15}/> Suggested next step</span><p>{finding.recommendation}</p></div>
    <div className="finding-bottom"><Pill kind="muted"><CircleHelp size={12}/> Unverified suspicion</Pill>{finding.source === 'pattern-rules'
      ? <span title="A line pattern matched this change. Counted as a static finding; not part of the risk score.">Pattern rule · <code>{(finding.rule_id ?? '').replace(/^shipsafe\./, '')}</code>{finding.language ? ` · ${finding.language}` : ''} · not in the score</span>
      : <span>Static analysis</span>}</div>
  </div>
}
