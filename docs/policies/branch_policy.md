# Branch Policy

Agent work uses `main` by default under the current user operating override.
Do not create routine `codex/` work branches unless the user explicitly asks for
a separate branch.

Do not push to `origin/main` after each run. Push `origin/main` only at campaign
closeout, wave closeout, or an explicit user-approved stabilization boundary.

## Machine-Readable Boundary Policy

```yaml
codex_branch_policy:
  routine_branches_allowed: false
  branch_creation_requires_explicit_user_request: true

main_integration_policy:
  allowed_boundary_events:
    - campaign_close
    - wave_close
    - control_plane_stabilization
  working_branch: main
  merge_mode: not_applicable_main_first
  direct_push: allowed_only_at_user_approved_boundary
```

This policy keeps experiment throughput on `main` while preventing run-by-run
remote churn.

## Scoped Campaign Closeout CI

Campaign-local closeout PRs may use scoped partial CI when the changed
paths are limited to campaign evidence, campaign closeout records, clue memory,
negative memory, and the approved campaign-local registries.

The CI policy uses two layers:

- `ci-scope-gate` is a required check for pull requests and protected pushes.
- `full-regression` remains a manual `workflow_dispatch` workflow for protected
  changes that need a complete `uv run pytest -q` record.

The scope gate must require full regression for shared-control, evaluator,
policy, registry, workspace, wave, goal, runtime-truth, dependency, workflow, or
protected-claim changes. A missing manual full-regression run cannot silently
pass.

## Worktree Fit Rule

Before file edits, check that the current branch/worktree matches the requested work item.

If the current branch belongs to another PR, experiment, governance task,
runtime package, or data/materialization task, do not continue only because it
is already open. Switch back to `main`, switch to an explicitly user-requested
branch, or stop and report the mismatch if switching would mix unrelated work.

Record the decision in work-item, run, or skill receipts:

- `branch_worktree_fit`: `fit`, `mismatch_resolved`, `mismatch_blocked`, or `unchecked_lowered_claim`
- `branch_action`: `keep_current_branch`, `switch_existing_branch`,
  `switch_to_main`, `create_user_requested_branch`, `create_or_use_worktree`, or
  `block_and_report_mismatch`
- `mismatch_claim_effect`: how the branch decision lowers or blocks reproducible-run, bundle, runtime, handoff, pass, readiness, or Goal Achieve claims

Unknown git state is allowed for planning scaffold only. It cannot support reproducible-run, bundle, runtime, handoff, pass, readiness, or Goal Achieve claims.

## Commit And Main Push Cadence

Do not commit and push to `main` after every run by default.

The normal durable integration boundaries are:

- `campaign_open`
- `campaign_close`
- `wave_open`
- `wave_close`

At each boundary, prepare a coherent `main` commit after the relevant manifests,
receipts, registries, claim boundaries, and ignored-artifact hashes are updated.

Main push cadence follows the same boundary events. A main update must represent
the whole boundary state, not a partial run fragment. Intermediate run work can
remain unpushed local `main` commits or dirty working-tree output when useful,
but it should not be treated as remote main-integrated evidence until the
boundary commit/push is complete.

This cadence does not override the worktree fit rule. If the current branch/worktree does not match the boundary being opened or closed, resolve the mismatch before committing or pushing.

## Examples

- Do not continue unrelated model implementation on a handoff-package branch.
- Do not edit governance files on a runtime/code branch unless the user asked to combine those scopes.
- Do not mix two open PR scopes in one worktree unless explicitly requested.
