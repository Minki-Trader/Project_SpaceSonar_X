# Branch Policy

Agent work uses `codex/` branches unless the user requests a different branch name.

Do not merge into `main` unless the user explicitly asks.

## Machine-Readable Boundary Policy

```yaml
codex_branch_policy:
  detailed_progress_commits_allowed: true

main_integration_policy:
  allowed_boundary_events:
    - campaign_open
    - campaign_close
    - wave_open
    - wave_close
    - control_plane_stabilization
  merge_mode: squash_only
  direct_push: forbidden
```

This stabilization patch uses the boundary event `control_plane_stabilization`.

## Worktree Fit Rule

Before file edits, check that the current branch/worktree matches the requested work item.

If the current branch belongs to another PR, experiment, governance task, runtime package, or data/materialization task, do not continue only because it is already open. Switch to the matching branch/worktree, create a new `codex/` branch from the right base, or stop and report the mismatch if switching would mix unrelated work.

Record the decision in work-item, run, or skill receipts:

- `branch_worktree_fit`: `fit`, `mismatch_resolved`, `mismatch_blocked`, or `unchecked_lowered_claim`
- `branch_action`: `keep_current_branch`, `switch_existing_branch`, `create_codex_branch`, `create_or_use_worktree`, or `block_and_report_mismatch`
- `mismatch_claim_effect`: how the branch decision lowers or blocks reproducible-run, bundle, runtime, handoff, pass, readiness, or Goal Achieve claims

Unknown git state is allowed for planning scaffold only. It cannot support reproducible-run, bundle, runtime, handoff, pass, readiness, or Goal Achieve claims.

## Commit And Main Push Cadence

Do not commit and push to `main` after every run by default.

The normal durable integration boundaries are:

- `campaign_open`
- `campaign_close`
- `wave_open`
- `wave_close`

At each boundary, prepare a coherent integration commit from the active `codex/` branch after the relevant manifests, receipts, registries, claim boundaries, and ignored-artifact hashes are updated.

Main push cadence follows the same boundary events. A main update must represent the whole boundary state, not a partial run fragment. Intermediate run work can remain branch-local, dirty, or branch-committed when useful, but it should not be treated as main-integrated evidence until the boundary commit/push is complete.

This cadence does not override the worktree fit rule. If the current branch/worktree does not match the boundary being opened or closed, resolve the mismatch before committing or pushing.

## Examples

- Do not continue unrelated model implementation on a handoff-package branch.
- Do not edit governance files on a runtime/code branch unless the user asked to combine those scopes.
- Do not mix two open PR scopes in one worktree unless explicitly requested.
