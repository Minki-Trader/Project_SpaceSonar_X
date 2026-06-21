# Campaigns

Campaigns group related sweeps without creating legacy inheritance.

A campaign may define axis tags, budget, stop conditions, and output expectations.

Campaigns are centrally stored here even when a wave funds them. Waves link to campaigns through `lab/waves/<wave_id>/campaign_refs.csv` and `wave_allocation.yaml`; campaign folders are not copied under waves.

Preferred shape:

- `campaign_manifest.yaml`: campaign objective, axis tags, budget, and claim boundary.
- `surfaces/<surface_id>/surface_manifest.yaml`: problem shape and recipe refs.
- `surfaces/<surface_id>/sweeps/<sweep_id>/sweep_manifest.yaml`: controlled broad, extreme, WFO, or diagnostic sweep.
- `surfaces/<surface_id>/sweeps/<sweep_id>/run_refs.csv`: references to run-local evidence under `lab/runs/<run_id>/`.

Campaigns allocate and organize experiments. They do not contain durable proof by themselves.

A campaign is not a parking place for one candidate's endless repairs. Candidate-local fixes must stay bounded to a run or sweep. If the fix does not generalize into a surface clue, parity rule, prevention memory, or divergence hypothesis, close it and rotate.
