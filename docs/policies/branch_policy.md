# Branch Policy

Agent work uses `codex/` branches unless the user requests a different branch name.

Do not merge into `main` unless the user explicitly asks.

## Worktree Fit Rule

Before file edits, check that the current branch/worktree matches the requested work item.

If the current branch belongs to another PR, experiment, governance task, runtime package, or data/materialization task, do not continue only because it is already open. Switch to the matching branch/worktree, create a new `codex/` branch from the right base, or stop and report the mismatch if switching would mix unrelated work.

Record the decision in work-item, run, or skill receipts:

- `branch_worktree_fit`: `fit`, `mismatch_resolved`, `mismatch_blocked`, or `unchecked_lowered_claim`
- `branch_action`: `keep_current_branch`, `switch_existing_branch`, `create_codex_branch`, `create_or_use_worktree`, or `block_and_report_mismatch`
- `mismatch_claim_effect`: how the branch decision lowers or blocks reproducible-run, bundle, runtime, handoff, pass, readiness, or Goal Achieve claims

Unknown git state is allowed for planning scaffold only. It cannot support reproducible-run, bundle, runtime, handoff, pass, readiness, or Goal Achieve claims.

## Examples

- Do not continue unrelated model implementation on a handoff-package branch.
- Do not edit governance files on a runtime/code branch unless the user asked to combine those scopes.
- Do not mix two open PR scopes in one worktree unless explicitly requested.
