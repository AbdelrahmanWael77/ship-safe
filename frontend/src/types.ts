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
  /** Present only on pattern-rule findings (Phase 7). Absent on the Python heuristics. */
  source?: 'pattern-rules';
  rule_id?: string;
  language?: string;
}
export interface ScanSummary {
  /** Present only when the change has files the pattern rules can read. Their findings are counted, not scored. */
  pattern_rules?: { engine: string; rule_count: number; files_analysed: number; files_skipped: number; finding_count: number; in_risk_score: false };
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
/** GET /api/ai/gemini/status. The API key itself never reaches the browser. */
export interface GeminiStatus {
  configured: boolean;
  model: string | null;
}

export type AIProviderName = 'gemini' | 'openai'
/** GET /api/ai/providers: the AI review providers the server can call. Never includes a key. */
export interface AIProvider {
  provider: AIProviderName;
  label: string;
  configured: boolean;
  model: string | null;
  pricing_known: boolean;
}

export interface AIReview {
  id: string;
  imported_at: string;
  /** Manual Claude Code import, or generated server-side through the Gemini or OpenAI API. All are unverified. */
  source: 'user_imported_json_unverified_provenance' | 'gemini_api_generated_unverified' | 'openai_api_generated_unverified';
  /** Model reviews only: which model produced it, what it cost and how long it took. */
  generator?: {
    provider: AIProviderName;
    model: string;
    usage?: { input_tokens: number; output_tokens: number; reasoning_tokens: number; cached_input_tokens?: number };
    duration_ms?: number;
    /** OpenAI models with a known published price only. */
    estimated_cost_usd?: number;
    prices_as_of?: string;
  };
  verification_status: 'not_independently_verified';
  tests_executed: false;
  schema_version: 'shipsafe.ai-review.v1' | 'shipsafe.ai-review.v2';
  /** v2 only: what the review says it was made for (checked against the scan on import). */
  reviewed_source?: { provider: string | null; repository_id: string | null; pull_request_id: string | null; head_commit: string | null };
  /** Served beside the review, never stored in it: the binding of the scan the review was made for.
   *  `stale: true` means the pull request has new commits since, so the review is outdated. */
  scan_binding?: Binding;
  /** History route only: whether the review belongs to the scan that was asked about. */
  current_scan?: boolean;
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

// -- Phase 4 task A: static test discovery (nothing is executed) -------------
export type DiscoveryReason =
  | { kind: 'imports_changed_module'; changed_file: string }
  | { kind: 'mentions_changed_function'; changed_file: string; function: string };
export interface TestCandidate {
  test_id: string;
  file: string;
  name: string;
  line: number;
  changed_in_this_scan: boolean;
  reasons: DiscoveryReason[];
  related_static_finding_ids: string[];
  related_ai_finding_ids: string[];
}
export interface TestDiscovery {
  scan_id: string;
  ai_review_id: string | null;
  commit: string;
  method: 'static-ast';
  /** Always false: discovery never runs anything. */
  executed: false;
  test_files_found: number;
  test_files_read: number;
  test_files_unread: number;
  unparsed_test_files: string[];
  tests_found: number;
  candidate_count: number;
  candidates: TestCandidate[];
  coverage_gaps: { changed_file: string; reason: string; static_finding_ids: string[]; ai_finding_ids: string[] }[];
  incomplete: boolean;
  heuristics: string[];
  disclaimer: string;
}

// -- Phase 4 task B: proposed tests and human decisions (never applied or run here)
export interface TestProposalDecision {
  id: string;
  decision: 'approved' | 'rejected';
  decided_at: string;
  /** Self-declared name: ShipSafe has no authentication. */
  decided_by: string;
  note: string | null;
}
export interface TestProposal {
  id: string;
  scan_id: string;
  created_at: string;
  target_path: string;
  /** Untrusted test source. Render as text only. */
  content: string;
  content_digest: string;
  origin: 'human' | 'imported_ai_review';
  finding_ref: string | null;
  rationale: string | null;
  base_commit: string;
  head_commit: string;
  decisions: TestProposalDecision[];
  status: 'pending' | 'approved' | 'rejected';
  /** The scan's pull request has new commits. */
  stale: boolean;
  /** Approved and not stale. Says the human gate is passed, not that anything ran. */
  eligible_to_run: boolean;
  applied: false;
  executed: false;
  identity_note: string;
}

// -- Phase 4 task C: run requests. This build executes nothing, so every run is "blocked".
export interface TestRun {
  id: string;
  proposal_id: string;
  scan_id: string;
  requested_at: string;
  requested_by: string;
  status: string;
  reason: string | null;
  runner: string;
  base_commit: string;
  head_commit: string;
  /** All null when nothing ran. */
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  output: string | null;
  executed: boolean;
}

// -- Phase 5: evidence-based release assessment (arranges stored evidence; never says "safe")
export type AssessmentState = 'assessment_unavailable' | 'stale' | 'confirmed_regression' | 'tests_incomplete' | 'review_required';
interface AssessedFinding { id?: string | null; severity: string; category: string; title: string; file: string; line: number | null; confidence?: string }
export interface ReleaseAssessment {
  scan_id: string;
  generated_at: string;
  state: AssessmentState;
  state_label: string;
  states: AssessmentState[];
  statement: string;
  identity: {
    repo_name: string; provider: string; repository_id: string | null; pull_request_id: string | null;
    base_ref: string; head_ref: string; base_commit: string | null; head_commit: string | null;
    comparison: string; scanned_at: string; stale: boolean; stale_at: string | null;
  };
  static: { label: string; finding_count: number; by_severity: Record<string, number>; risk_score: number; recommendation: string; files_changed: number; findings: (AssessedFinding & { id: string })[] };
  ai_reviews: {
    label: string; count: number;
    /** Reviews the API server got from OpenAI or Gemini, and reviews a person imported as JSON. */
    model_generated: number; manually_imported: number;
    latest: null | {
      id: string; imported_at: string; schema_version: string; recommendation: string; finding_count: number; findings: AssessedFinding[];
      origin: 'model' | 'import'; source: string | null; provider: 'openai' | 'gemini' | null; model: string | null;
    };
  };
  tests: {
    label: string;
    repository_test_status: string;
    proposals: { count: number; by_status: { pending: number; approved: number; rejected: number };
      items: { id: string; target_path: string; status: string; finding_ref: string | null; origin: string; decisions: { decision: string; decided_by: string; decided_at: string; note: string | null }[] }[] };
    runs: { requested: number; blocked: number; executed: number; confirmed_regressions: number; items: Partial<TestRun>[] };
  };
  /** Manual QC results of the newest test suite of the scan, as testers recorded them. */
  manual_tests?: null | {
    label: string; suite_id: string; created_at: string; total: number;
    counts: Record<QcStatus, number>;
    failed: { id: string; title: string; priority: string; finding_id: string | null; bug_title_if_fails: string; tester: string | null; note: string | null }[];
  };
  unknowns: string[];
}

export type QcStatus = 'passed' | 'failed' | 'blocked' | 'not_run'

export interface QcResult { status: QcStatus; tester: string; note: string | null; recorded_at: string }

/** A manual test case written by an AI model from an AI review finding. ShipSafe never runs it. */
export interface QcTestCase {
  id: string; title: string; priority: 'critical' | 'high' | 'medium' | 'low'; area: string;
  finding_id: string | null; file: string | null;
  preconditions: string[]; test_data: string[]; steps: string[]; expected: string; bug_title_if_fails: string;
  status: QcStatus; result: QcResult | null; results: QcResult[];
}

export interface QcTestSuite {
  id: string; scan_id: string; review_id: string; created_at: string; review_origin: string | null;
  cases: QcTestCase[]; counts: Record<QcStatus, number>; total: number; limitations: string[];
  executed_by_shipsafe: false;
  generator: { provider: AIProviderName; model: string; usage?: { input_tokens: number; output_tokens: number; reasoning_tokens: number }; duration_ms?: number; estimated_cost_usd?: number };
}
