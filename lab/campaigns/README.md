# Campaigns

Campaigns group related sweeps without creating legacy inheritance.

A campaign may define axis tags, budget, stop conditions, and output expectations.

Preferred shape:

- `campaign_manifest.yaml`: campaign objective, axis tags, budget, and claim boundary.
- `surfaces/<surface_id>/surface_manifest.yaml`: problem shape and recipe refs.
- `surfaces/<surface_id>/sweeps/<sweep_id>/sweep_manifest.yaml`: controlled broad, extreme, WFO, or diagnostic sweep.
- `surfaces/<surface_id>/sweeps/<sweep_id>/run_refs.csv`: references to run-local evidence under `lab/runs/<run_id>/`.

Campaigns allocate and organize experiments. They do not contain durable proof by themselves.
