export interface DemoBranch { ref: string; label: string; kind: string }
export interface DemoInfo {
  repository_path: string;
  name: string;
  base_ref: string;
  default_head: string;
  branches: DemoBranch[];
  note: string;
}
export interface FileChange {
  path: string;
  status: string;
  additions: number;
  deletions: number;
  changed_functions: string[];
  diff: string;
  /** Optional: absent in reports stored before truncation reporting existed; treat as false / 0. */
  diff_truncated?: boolean;
  diff_lines_omitted?: number;
}
export interface Finding {
  id: string;
  category: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  file: string;
  line: number | null;
  status: string;
  evidence: string;
  explanation: string;
  recommendation: string;
}
export interface ScanSummary {
  files_changed: number;
  lines_added: number;
  lines_removed: number;
  finding_count: number;
  risk_score: number;
  recommendation: string;
  test_status: string;
  /** Optional: absent in reports stored before truncation reporting existed; treat as false / 0. */
  truncated?: boolean;
  files_omitted?: number;
}
export interface ImpactedModule { path: string; imports_changed: string[] }
export interface TestSuggestion { category: string; file: string; scenario: string }
export interface Report {
  id: string;
  created_at: string;
  repo_name: string;
  repository_path: string;
  base_ref: string;
  head_ref: string;
  base_sha: string;
  head_sha: string;
  duration_ms: number;
  summary: ScanSummary;
  files: FileChange[];
  findings: Finding[];
  affected_modules: ImpactedModule[];
  test_suggestions: TestSuggestion[];
  disclaimer: string;
}
export type ScanHistory = Pick<Report, 'id' | 'created_at' | 'repo_name' | 'base_ref' | 'head_ref' | 'duration_ms' | 'summary'>;

export interface AIReviewFinding {
  title: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  category: string;
  file: string;
  line: number | null;
  evidence: string;
  rationale: string;
  recommendation: string;
  confidence: 'low' | 'medium' | 'high';
  related_static_finding_ids: string[];
}
export interface AIReviewTestIdea {
  title: string;
  scenario: string;
  expected_behavior: string;
  file: string | null;
}
export interface AIReview {
  id: string;
  imported_at: string;
  source: 'user_imported_json_unverified_provenance';
  verification_status: 'not_independently_verified';
  tests_executed: false;
  schema_version: 'shipsafe.ai-review.v1';
  scan_id: string;
  context_digest: string;
  summary: string;
  recommendation: 'block_release' | 'manual_review' | 'insufficient_evidence';
  findings: AIReviewFinding[];
  test_ideas: AIReviewTestIdea[];
  limitations: string[];
}
