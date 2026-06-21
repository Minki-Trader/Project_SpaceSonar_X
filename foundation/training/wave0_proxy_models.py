from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class ProxyFit:
    model: Pipeline
    task_kind: str
    target_name: str
    threshold_policy: str
    target_threshold: float | None
    score_low_threshold: float | None
    score_high_threshold: float | None
    train_score_summary: dict[str, float]
    model_summary: dict[str, Any]


def _as_float_array(series: pd.Series) -> np.ndarray:
    return series.astype(float).to_numpy()


def _quantile(values: np.ndarray, q: float) -> float:
    clean = values[np.isfinite(values)]
    if clean.size == 0:
        return float("nan")
    return float(np.quantile(clean, q))


def _binary_from_train_threshold(
    labels: pd.DataFrame,
    train_mask: pd.Series,
    *,
    target_family: str,
    model_family: str,
) -> tuple[pd.Series, float | None, str]:
    if target_family == "tradeability_or_no_trade_regime":
        train_values = labels.loc[train_mask, "target_continuous"].astype(float)
        threshold = float(train_values.quantile(0.60))
        return (labels["target_continuous"].astype(float) >= threshold).astype(int), threshold, "target_continuous_train_q60"
    if target_family == "path_quality_mfe_mae_payoff_suitability" and model_family != "linear_or_ridge_rank_scout":
        train_values = labels.loc[train_mask, "target_continuous"].astype(float)
        threshold = float(train_values.quantile(0.60))
        return (labels["target_continuous"].astype(float) >= threshold).astype(int), threshold, "target_continuous_train_q60"
    return labels["target_binary_raw"].astype(int), None, "target_binary_raw"


def build_model_target(
    labels: pd.DataFrame,
    train_mask: pd.Series,
    *,
    target_family: str,
    model_family: str,
) -> tuple[pd.Series, str, str, float | None]:
    if model_family == "linear_or_ridge_rank_scout":
        return labels["target_continuous"].astype(float), "regression", "target_continuous", None
    if model_family in {"logistic_classification_scout", "onnx_realistic_tree_or_boosted_scout"}:
        target, threshold, target_name = _binary_from_train_threshold(
            labels,
            train_mask,
            target_family=target_family,
            model_family=model_family,
        )
        return target, "classification", target_name, threshold
    raise ValueError(f"unsupported Wave0 model_family: {model_family}")


def fit_proxy_model(
    features: pd.DataFrame,
    target: pd.Series,
    train_mask: pd.Series,
    *,
    model_family: str,
    target_name: str,
    threshold_policy: str,
    target_threshold: float | None,
) -> ProxyFit:
    x_train = features.loc[train_mask]
    y_train = target.loc[train_mask]
    if len(x_train) < 1000:
        raise ValueError(f"not enough train rows for Wave0 proxy model: {len(x_train)}")

    if model_family == "linear_or_ridge_rank_scout":
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("ridge", Ridge(alpha=1.0)),
            ]
        )
        task_kind = "regression"
    elif model_family == "logistic_classification_scout":
        unique = sorted(set(y_train.dropna().astype(int).tolist()))
        if len(unique) < 2:
            raise ValueError(f"classification target has one train class: {unique}")
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("logistic", LogisticRegression(max_iter=500, class_weight="balanced", solver="lbfgs")),
            ]
        )
        task_kind = "classification"
    elif model_family == "onnx_realistic_tree_or_boosted_scout":
        unique = sorted(set(y_train.dropna().astype(int).tolist()))
        if len(unique) < 2:
            raise ValueError(f"classification target has one train class: {unique}")
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "hist_gradient_boosting",
                    HistGradientBoostingClassifier(
                        max_iter=60,
                        learning_rate=0.05,
                        max_leaf_nodes=15,
                        l2_regularization=0.1,
                        random_state=0,
                    ),
                ),
            ]
        )
        task_kind = "classification"
    else:
        raise ValueError(f"unsupported Wave0 model_family: {model_family}")

    model.fit(x_train, y_train)
    train_scores = score_model(model, x_train, task_kind)
    low = high = None
    if threshold_policy == "coarse_density_bands_train_only":
        low = _quantile(train_scores, 0.20)
        high = _quantile(train_scores, 0.80)
    return ProxyFit(
        model=model,
        task_kind=task_kind,
        target_name=target_name,
        threshold_policy=threshold_policy,
        target_threshold=target_threshold,
        score_low_threshold=low,
        score_high_threshold=high,
        train_score_summary={
            "min": float(np.nanmin(train_scores)),
            "p20": _quantile(train_scores, 0.20),
            "median": _quantile(train_scores, 0.50),
            "p80": _quantile(train_scores, 0.80),
            "max": float(np.nanmax(train_scores)),
        },
        model_summary={
            "model_family": model_family,
            "task_kind": task_kind,
            "target_name": target_name,
            "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
            "threshold_policy": threshold_policy,
            "score_threshold_fit_scope": "train_only" if low is not None else "not_applicable",
            "preprocessing_fit_scope": "train_only",
            "calibration": "none",
            "selector": "none",
        },
    )


def score_model(model: Pipeline, features: pd.DataFrame, task_kind: str) -> np.ndarray:
    if task_kind == "classification":
        if hasattr(model, "predict_proba"):
            return model.predict_proba(features)[:, 1].astype(float)
        return model.decision_function(features).astype(float)
    return model.predict(features).astype(float)


def diagnostic_metrics(target: pd.Series, score: np.ndarray, task_kind: str) -> dict[str, Any]:
    y = target.astype(float)
    metrics: dict[str, Any] = {
        "row_count": int(len(y)),
        "score_mean": float(np.nanmean(score)),
        "score_std": float(np.nanstd(score)),
    }
    if task_kind == "classification":
        y_int = y.astype(int)
        pred = (score >= 0.5).astype(int)
        metrics["accuracy"] = float(accuracy_score(y_int, pred))
        metrics["balanced_accuracy"] = float(balanced_accuracy_score(y_int, pred))
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_int, score))
        except ValueError:
            metrics["roc_auc"] = None
        try:
            metrics["average_precision"] = float(average_precision_score(y_int, score))
        except ValueError:
            metrics["average_precision"] = None
        try:
            clipped = np.clip(score, 1e-6, 1.0 - 1e-6)
            metrics["log_loss"] = float(log_loss(y_int, clipped))
        except ValueError:
            metrics["log_loss"] = None
        metrics["positive_rate"] = float(np.mean(y_int))
    else:
        metrics["mae"] = float(mean_absolute_error(y, score))
        metrics["rmse"] = float(mean_squared_error(y, score) ** 0.5)
        score_series = pd.Series(score, index=y.index)
        metrics["pearson_corr"] = float(score_series.corr(y, method="pearson"))
        metrics["spearman_corr"] = float(score_series.corr(y, method="spearman"))
        metrics["target_mean"] = float(y.mean())
        metrics["target_std"] = float(y.std())
    return metrics


def decision_metrics(
    *,
    decision_family: str,
    score: np.ndarray,
    labels: pd.DataFrame,
    fit: ProxyFit,
) -> dict[str, Any]:
    future_return = _as_float_array(labels["future_return"])
    metrics: dict[str, Any] = {
        "decision_family": decision_family,
        "threshold_policy": fit.threshold_policy,
        "threshold_fit_scope": "train_only" if fit.score_high_threshold is not None else "not_applicable",
    }
    if decision_family == "diagnostic_rank_only" or fit.threshold_policy == "none_diagnostic":
        metrics["trade_count"] = 0
        metrics["trade_density"] = 0.0
        metrics["proxy_boundary"] = "diagnostic_only_no_trade_proxy"
        return metrics

    high = fit.score_high_threshold
    low = fit.score_low_threshold
    if high is None or low is None or not np.isfinite(high) or not np.isfinite(low):
        metrics["trade_count"] = 0
        metrics["trade_density"] = 0.0
        metrics["proxy_boundary"] = "threshold_unavailable"
        return metrics

    if decision_family == "abstain_capable_long_short":
        side = np.zeros(len(score), dtype=float)
        side[score >= high] = 1.0
        side[score <= low] = -1.0
        gross_proxy_return = side * future_return
        active = side != 0.0
        metrics["long_count"] = int(np.sum(side > 0.0))
        metrics["short_count"] = int(np.sum(side < 0.0))
        metrics["directional_accuracy"] = (
            float(np.mean(np.sign(future_return[active]) == side[active])) if np.any(active) else None
        )
        metrics["proxy_boundary"] = "gross_future_return_direction_proxy_no_cost_no_execution"
    elif decision_family == "abstain_capable_direction_agnostic_tradeability":
        active = score >= high
        gross_proxy_return = np.abs(future_return[active])
        if fit.target_threshold is not None:
            event = labels["target_continuous"].astype(float).to_numpy() >= fit.target_threshold
        else:
            event = labels["target_binary_raw"].fillna(0.0).astype(float).to_numpy() > 0.5
        metrics["hit_rate"] = float(np.mean(event[active])) if np.any(active) else None
        metrics["proxy_boundary"] = "direction_agnostic_future_abs_return_proxy_no_cost_no_execution"
    else:
        active = np.zeros(len(score), dtype=bool)
        gross_proxy_return = np.array([], dtype=float)
        metrics["proxy_boundary"] = "unsupported_decision_family_no_trade_proxy"

    positives = gross_proxy_return[gross_proxy_return > 0.0]
    negatives = gross_proxy_return[gross_proxy_return < 0.0]
    metrics["trade_count"] = int(np.sum(active))
    metrics["trade_density"] = float(np.mean(active)) if len(active) else 0.0
    metrics["gross_proxy_mean_return"] = float(np.mean(gross_proxy_return)) if gross_proxy_return.size else None
    metrics["gross_proxy_profit_factor"] = (
        float(np.sum(positives) / abs(np.sum(negatives))) if negatives.size and abs(np.sum(negatives)) > 0.0 else None
    )
    metrics["score_low_threshold"] = float(low)
    metrics["score_high_threshold"] = float(high)
    return metrics


def judge_proxy_result(model_metrics: dict[str, Any], decision: dict[str, Any], task_kind: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if model_metrics.get("row_count", 0) < 1000:
        return "invalid", ["too_few_validation_rows"]

    if task_kind == "classification":
        auc = model_metrics.get("roc_auc")
        if isinstance(auc, float):
            if auc >= 0.53:
                reasons.append(f"validation_auc_preserved_clue_{auc:.4f}")
            elif auc <= 0.48:
                reasons.append(f"validation_auc_negative_{auc:.4f}")
    else:
        spearman = model_metrics.get("spearman_corr")
        if isinstance(spearman, float):
            if abs(spearman) >= 0.04:
                reasons.append(f"validation_abs_spearman_preserved_clue_{spearman:.4f}")
            elif spearman < -0.01:
                reasons.append(f"validation_spearman_negative_{spearman:.4f}")

    trade_count = decision.get("trade_count") or 0
    gross_pf = decision.get("gross_proxy_profit_factor")
    if isinstance(gross_pf, float) and trade_count >= 500 and gross_pf >= 1.10:
        reasons.append(f"gross_proxy_pf_preserved_clue_{gross_pf:.4f}")

    if any("preserved_clue" in reason for reason in reasons):
        return "preserved_clue", reasons
    if reasons:
        return "negative", reasons
    return "inconclusive", ["valid_proxy_run_no_repeated_or_strong_surface_clue_yet"]
