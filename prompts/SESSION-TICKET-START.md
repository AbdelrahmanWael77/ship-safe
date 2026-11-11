# Copy at start of each teammate's separate Claude Code task session

I am working on **ShipSafe**, phase `[N]`, ticket `[TICKET]`, branch `[BRANCH]`.
My human owner is `[NAME]`; assigned reviewer is `[NAME]`.
My owned file paths are `[PATHS]`; the following paths are owned by others and must not be edited: `[PATHS]`.

Read `CLAUDE.md`, `docs/TEAM_WORKFLOW.md`, the latest `docs/PHASE_HANDOFF.md`, the active file `prompts/PHASE-0N-....md`, and my ticket definition.

Inspect Git status. If you detect conflicting uncommitted changes or ambiguity about shared API contracts, stop and ask the human owner to coordinate. Work only on my ticket; do not start later phases or merge other members' branches.

Implement a small working solution with real tests and honest evidence. Keep code and fixtures synthetic unless approval for private code sharing has been recorded. Never access or reveal credentials. At the end, produce `templates/SESSION_HANDOFF.md` fields and stop for human PR review.
