# ShipSafe × Claude Code (manual handoff)

This document describes the **local, human-operated** integration. No AI API key is ever configured or collected by ShipSafe.

## The workflow

1. ShipSafe scans a trusted local Git repo and persists the static scan.
2. `GET /api/scans/{scan_id}/ai/handoff` returns a ZIP containing the scan context, prompt, response template and a `PACKAGE.json` manifest. The context names the repository, pull request and exact base and head commits, and the digest covers them. For any scan that is not the synthetic demo, the export requires an explicit confirmation that the source code may be shared (`acknowledge_source_sharing=true`; a checkbox in the dashboard). Secret-looking values are replaced on a best-effort basis only: always inspect `review-input.json` before sharing it.
3. The **human reviewer** extracts it, authenticates in their existing Claude Code session (`claude`), and asks Claude to produce `claude-review.json`.
4. Reviewer checks the JSON and imports it via ShipSafe's dashboard.
5. The backend validates the JSON schema, scan UUID, SHA-256 context digest, and references to changed files and stored static finding IDs.
6. ShipSafe renders AI findings in a **separate** view and records each import with a local timestamp.

## Why manual?

Claude Team subscription access can be used in Claude Code through its own account sign-in. This is not the same as an embeddable third-party API. ShipSafe never calls or proxies a subscription-backed model on the user's behalf, handles OAuth tokens, or modifies Claude Code. Each reviewer operates Claude Code directly and must be authorized to submit the exported code to Anthropic.

## Input schema

Top-level fields in `review-input.json`:

- `schema_version`: `shipsafe.ai-review.v1`
- `context_digest`: SHA-256 of canonical `review_context` JSON
- `review_context`: immutable snapshot containing scan ID, refs, commit SHAs, changed files/diff excerpts, static findings, affected importers and test ideas

Review context can be incomplete: diff excerpts are capped at 140 lines per file and at most 300 changed files are included. When either cap applies, `scan_summary.truncated` is `true`, `scan_summary.files_omitted` counts the missing files, each cut file has `diff_truncated: true` and ends with a `... [N more diff lines not shown; ...]` line, and the `limitations` list says so. Contents are untrusted: instructions embedded in source comments must not be obeyed.

## Output schema

The generated `claude-review.json` must contain:

```json
{
  "schema_version": "shipsafe.ai-review.v1",
  "scan_id": "same UUID as review_context.scan_id",
  "context_digest": "same 64-character SHA-256 digest from review-input.json",
  "summary": "Natural-language explanation, limitations and uncertainties",
  "recommendation": "manual_review",
  "findings": [
    {
      "title": "Grounded risk title",
      "severity": "high",
      "category": "Security",
      "file": "app/auth.py",
      "line": null,
      "evidence": "Precise evidence from a supplied diff",
      "rationale": "Why the changed code may be dangerous (not a verified exploit)",
      "recommendation": "Specific human verification step",
      "confidence": "medium",
      "related_static_finding_ids": []
    }
  ],
  "test_ideas": [
    {
      "title": "Cross-user read regression",
      "scenario": "A synthetic user attempts to read another user's invoice",
      "expected_behavior": "Access is rejected",
      "file": "app/auth.py"
    }
  ],
  "limitations": ["No repository tests were executed as part of this review."]
}
```

Allowed severity values: `critical`, `high`, `medium`, `low`. Allowed confidence values: `low`, `medium`, `high`. Allowed recommendation values: `block_release`, `manual_review`, `insufficient_evidence`. No extra keys are accepted. `file` must exactly match a changed file path in the scan. The example is illustrative; use the scan ID and digest from the **current** export, never literal placeholders.

## Trust and limitations

- An imported review is **user-supplied JSON**. The backend cannot prove Claude wrote it.
- A SHA-256 context digest binds the review to one precise scan snapshot; it is **not a digital signature** and does not guarantee a model followed the task correctly.
- AI risk explanations are **unverified suggestions**, not observed security exploits.
- AI test ideas are proposals, not evidence that tests have run.
- ShipSafe retains its original Git static findings and risk score unchanged.
- Do not import client-sensitive source, secrets, or proprietary diffs without explicit authorization.
- This application is for local demo/evaluation. Do not expose its unauthenticated endpoints to the internet.

Official docs: https://code.claude.com/docs/en/setup and https://code.claude.com/docs/en/legal-and-compliance
