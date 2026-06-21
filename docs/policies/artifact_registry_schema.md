# Artifact Registry Schema

Use `docs/registers/artifact_registry.csv` as a compact index for durable dataset, model, bundle, runtime, and report identity.

The registry is not proof by itself. It must point to run-local, bundle-local, attempt-local, or external evidence.

Minimum columns:

`artifact_id,run_id,bundle_id,attempt_id,artifact_type,path_or_uri,sha256,size_bytes,availability,producer_command,regeneration_command,source_of_truth,consumer,claim_boundary,notes`

Rules:

- Use repo-relative paths when the artifact is inside the workspace.
- Use URI plus hash when the artifact is external.
- Use `not_committed_tracked_by_hash` for heavy artifacts kept outside Git.
- Use `missing_with_reason` rather than inventing an artifact path.
- Registry rows must not claim selected baseline, runtime authority, economics pass, handoff complete, live readiness, reviewed, verified, pass, or Goal Achieve.
