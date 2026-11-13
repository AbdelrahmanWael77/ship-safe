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
  /** Present only when the import analysis was cut (Bitbucket scans read at most 200 files). */
  import_analysis_truncated?: boolean;
  import_files_skipped?: number;
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
  /** Added by the API beside the stored report (never part of it). Absent in old exports. */
  binding?: Binding;
  /** Frontend only: set on a canned report produced by the development mock mode. Never sent by the API. */
  mock?: true;
}
export type ScanHistory = Pick<Report, 'id' | 'created_at' | 'repo_name' | 'base_ref' | 'head_ref' | 'duration_ms' | 'summary' | 'binding'>;

// -- Bitbucket (Phase 2). Contract: docs/ARCHITECTURE.md, "Bitbucket routes";
// examples: docs/example-bitbucket-responses.json.

/** What a stored scan was bound to. Full 40-character SHAs live here. */
export interface Binding {
  provider: 'local-git' | 'bitbucket-cloud' | string;
  repository_id: string | null;
  pull_request_id: string | null;
  base_commit: string | null;
  head_commit: string | null;
  /** "merge-base" for pull request scans, "direct" otherwise. */
  comparison: 'direct' | 'merge-base';
  /** The stored marker: the scan's head differs from the pull request's head. */
  stale: boolean;
  stale_at: string | null;
  /** True only when THIS response compared the scan with Bitbucket's current head. */
  stale_checked: boolean;
}
export interface BitbucketStatus {
  configured: boolean;
  provider: string | null;
  workspace: string | null;
  repositories: string[];
}
export interface BitbucketRepository {
  id: string;
  slug: string;
  name: string;
  url: string;
  default_branch: string | null;
}
export type PullRequestState = 'open' | 'merged' | 'declined';
export interface PullRequest {
  provider: string;
  repository_id: string;
  id: string;
  title: string;
  state: PullRequestState;
  source_ref: string;
  target_ref: string;
  /** Full SHA, or null (always null in the list unless the pull request already has scans). */
  source_sha: string | null;
  target_sha: string | null;
  author: string | null;
  url: string;
  updated_at: string | null;
}
export interface PullRequestScan {
  id: string;
  created_at: string;
  summary: ScanSummary;
  binding: Binding;
}
export interface PullRequestListItem extends PullRequest {
  scan_count: number;
  latest_scan: PullRequestScan | null;
  stale_checked: boolean;
}
export interface PullRequestList {
  repository: BitbucketRepository;
  state: PullRequestState;
  pull_requests: PullRequestListItem[];
  /** True when Bitbucket has more pull requests in this state than the 200 returned. */
  truncated: boolean;
}
export interface PullRequestDetail extends PullRequest {
  repository: BitbucketRepository;
  scannable: boolean;
  not_scannable_code: string | null;
  not_scannable_reason: string | null;
  stale_checked: boolean;
  scans: PullRequestScan[];
}

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
  /** Review schema v2 only (absent in v1 reviews). */
  id?: string;
  /** Always "suspected": an imported review cannot verify anything. */
  status?: 'suspected';
  suggested_validation?: string;
  /** Text only. ShipSafe never applies it. */
  proposed_patch?: string | null;
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
  schema_version: 'shipsafe.ai-review.v1' | 'shipsafe.ai-review.v2';
  /** v2 only: what the review says it was made for (checked against the scan on import). */
  reviewed_source?: { provider: string | null; repository_id: string | null; pull_request_id: string | null; head_commit: string | null };
  /** v2 only: what the reviewer could not see. */
  missing_context?: string[];
  scan_id: string;
  context_digest: string;
  summary: string;
  recommendation: 'block_release' | 'manual_review' | 'insufficient_evidence';
  findings: AIReviewFinding[];
  test_ideas: AIReviewTestIdea[];
  limitations: string[];
}
