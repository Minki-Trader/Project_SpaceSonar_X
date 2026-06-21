# Campaigns

Campaigns group related sweeps without creating legacy inheritance.

A campaign may define axis tags, budget, stop conditions, and output expectations.

Research campaigns should open unexplored or underexplored surfaces. They must not become feature-only, label-only, model-only, threshold-only, or repair-only tracks. A campaign can emphasize one unknown, but it must record companion label/target, feature/input, model/training, decision, and evaluation/runtime axes.

Campaigns are centrally stored here even when a wave funds them. Waves link to campaigns through `lab/waves/<wave_id>/campaign_refs.csv` and `wave_allocation.yaml`; campaign folders are not copied under waves.

Preferred shape:

- `campaign_manifest.yaml`: campaign objective, axis tags, budget, and claim boundary.
- `surfaces/<surface_id>/surface_manifest.yaml`: problem shape and recipe refs.
- `surfaces/<surface_id>/sweeps/<sweep_id>/sweep_manifest.yaml`: controlled broad, extreme, WFO, or diagnostic sweep.
- `surfaces/<surface_id>/sweeps/<sweep_id>/run_refs.csv`: references to run-local evidence under `lab/runs/<run_id>/`.

Campaigns allocate and organize experiments. They do not contain durable proof by themselves.

A campaign is not a parking place for one candidate's endless repairs. Candidate-local fixes must stay bounded to a run or sweep. If the fix does not generalize into a surface clue, parity rule, prevention memory, or divergence hypothesis, close it and rotate.

Do not move unfinished repair into a later campaign as if it were a new hypothesis. A later campaign can continue only a recorded new surface, divergence, or prevention-memory question.

Neighborhood perturbation is bounded to meaningful adjacent variables. Once it becomes generic micro-tuning around one candidate, close or reclassify it.

Bounded synthesis campaigns are campaign-local previous-material mixing runs. They use ingredient cards and a mix queue under `lab/campaigns/<campaign_id>/synthesis/`, may produce preserved clues or new surface questions, and must not decide the next wave/campaign direction.
