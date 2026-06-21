# Lab

ONNX experiment workspace.

Use this root for active hypotheses, campaigns, run receipts, candidate summaries, and templates.

Storage:

- `lab/waves/<wave_id>/wave_allocation.yaml`
- `lab/waves/<wave_id>/campaign_refs.csv`
- `lab/campaigns/<campaign_id>/campaign_manifest.yaml`
- `lab/hypotheses/<idea_id>.yaml` or `lab/hypotheses/<hypothesis_id>.yaml`
- `lab/surfaces/<surface_id>/surface_manifest.yaml`
- `lab/runs/<run_id>/run_manifest.json`
- `lab/runs/<run_id>/experiment_receipt.yaml`
- `lab/runs/<run_id>/artifact_lineage.json`
- `lab/runs/<run_id>/metrics.json`
- `lab/candidates/<candidate_id>/candidate_summary.yaml`

Generated artifacts belong in run-local ignored folders or `runtime/packages/<bundle_id>/` with manifests and hashes.

Waves allocate campaigns by reference. Campaigns remain centrally stored under `lab/campaigns/<campaign_id>/`; do not copy or nest campaign source-of-truth folders under `lab/waves/`.
