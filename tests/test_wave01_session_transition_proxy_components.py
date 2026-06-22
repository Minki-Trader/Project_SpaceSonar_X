from __future__ import annotations

import csv
from pathlib import Path

import yaml

from foundation.features.wave01_session_transition_features import build_wave01_session_transition_features
from foundation.labels.wave01_session_transition_labels import build_wave01_session_transition_labels
from foundation.pipelines.run_wave01_event_barrier_proxy_batch import load_row_membership


REPO_ROOT = Path(__file__).resolve().parents[1]


def _row_membership_frame():
    manifest_path = REPO_ROOT / "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8-sig"))
    return load_row_membership(manifest)


def test_session_transition_feature_and_label_components_are_matrix_driven() -> None:
    matrix_path = REPO_ROOT / "lab/campaigns/campaign_us100_session_transition_regime_surface_v0/first_batch_matrix.csv"
    matrix_row = next(csv.DictReader(matrix_path.open(encoding="utf-8-sig")))
    frame = _row_membership_frame()

    features, feature_schema = build_wave01_session_transition_features(frame, matrix_row["feature_family"])
    labels, label_schema = build_wave01_session_transition_labels(
        frame,
        {
            "label_surface": matrix_row["label_surface"],
            "horizon_bars": int(matrix_row["horizon_bars"]),
            "session_anchor": matrix_row["session_anchor"],
            "transition_window_bars": matrix_row["transition_window_bars"],
            "regime_label": matrix_row["regime_label"],
        },
    )

    assert feature_schema.feature_family == matrix_row["feature_family"]
    assert feature_schema.feature_recipe_id == "feature_wave01_us100_session_transition_regime_v0"
    assert len(feature_schema.feature_columns) == len(features.columns)
    assert len(feature_schema.feature_columns) != 58
    assert label_schema.label_surface == matrix_row["label_surface"]
    assert int(labels["same_role_horizon_ok"].sum()) > 1000
    assert labels.loc[labels["same_role_horizon_ok"], "target_continuous"].notna().all()
