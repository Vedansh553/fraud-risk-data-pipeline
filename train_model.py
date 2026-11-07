"""
Feature engineering + fraud model + cost-based threshold selection.

Key design choices (these are the interview talking points):
  * TIME-BASED split (train -> validation -> test), never random, to avoid leakage.
  * Behavioural features computed only from a customer's PAST transactions.
  * Class imbalance handled with class weights; judged by PR-AUC, not accuracy.
  * Decision threshold chosen on validation by minimising business cost:
    missed fraud costs the transaction amount, a false decline costs a fixed
    customer-friction amount. Final numbers are reported on the untouched test set.
"""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.inspection import permutation_importance
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             precision_recall_curve, precision_score, recall_score)
from config import *

WEEK = 7 * 24 * 3600


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["transaction_ts", "transaction_id"]).copy()
    g = df.groupby("customer_id")
    # force seconds explicitly: the default datetime unit differs across pandas versions
    df["_ts"] = df.transaction_ts.astype("datetime64[s]").astype("int64")

    # velocity: seconds since previous and since 2nd previous txn by same customer
    prev1 = g["_ts"].shift(1)
    prev2 = g["_ts"].shift(2)
    df["secs_since_prev"] = (df["_ts"] - prev1).fillna(WEEK).clip(upper=WEEK)
    df["secs_since_prev2"] = (df["_ts"] - prev2).fillna(WEEK).clip(upper=WEEK)
    df["rapid_fire"] = (df["secs_since_prev2"] < 3600).astype(int)

    # amount relative to customer's own history (expanding mean of PAST txns only)
    past_mean = g["amount"].transform(lambda s: s.shift(1).expanding().mean())
    df["amount_vs_cust_mean"] = (df["amount"] / past_mean).fillna(1.0).clip(upper=50)

    hour = df.transaction_ts.dt.hour
    df["hour"] = hour
    df["is_night"] = ((hour <= 4) | (hour >= 23)).astype(int)
    df["is_foreign"] = (df.country != df.home_country).astype(int)
    df["log_amount"] = np.log1p(df.amount)
    df["is_weekend"] = (df.transaction_ts.dt.dayofweek >= 5).astype(int)

    feats = df[["log_amount", "hour", "is_night", "is_weekend", "is_foreign", "card_present",
                "secs_since_prev", "secs_since_prev2", "rapid_fire", "amount_vs_cust_mean"]].copy()
    feats = pd.concat([feats,
                       pd.get_dummies(df.merchant_category, prefix="cat", dtype=int),
                       pd.get_dummies(df.channel, prefix="ch", dtype=int)], axis=1)
    return df, feats


def total_cost(y, pred, amount):
    missed = amount[(y == 1) & (pred == 0)].sum()
    false_declines = ((y == 0) & (pred == 1)).sum() * COST_FALSE_DECLINE
    return float(missed + false_declines)


def best_threshold(y, score, amount):
    grid = np.linspace(0.01, 0.99, 99)
    costs = [total_cost(y, (score >= t).astype(int), amount) for t in grid]
    return float(grid[int(np.argmin(costs))])


def run(clean_df: pd.DataFrame):
    df, X = build_features(clean_df)
    y = df["is_fraud"].values
    amount = df["amount"].values
    n = len(df)
    i1, i2 = int(n * 0.6), int(n * 0.8)       # chronological split
    sl_tr, sl_va, sl_te = slice(0, i1), slice(i1, i2), slice(i2, n)

    models = {
        "logistic_regression": make_pipeline(StandardScaler(),
                                             LogisticRegression(max_iter=1000, class_weight="balanced")),
        "gradient_boosting": HistGradientBoostingClassifier(
            max_depth=5, learning_rate=0.08, max_iter=250, class_weight="balanced", random_state=SEED),
    }

    results, scores = {}, {}
    for name, m in models.items():
        m.fit(X.iloc[sl_tr], y[sl_tr])
        s_va = m.predict_proba(X.iloc[sl_va])[:, 1]
        s_te = m.predict_proba(X.iloc[sl_te])[:, 1]
        thr = best_threshold(y[sl_va], s_va, amount[sl_va])
        pred = (s_te >= thr).astype(int)
        yt, at = y[sl_te], amount[sl_te]
        cost_model = total_cost(yt, pred, at)
        cost_none = total_cost(yt, np.zeros_like(yt), at)         # approve everything
        results[name] = {
            "roc_auc": round(roc_auc_score(yt, s_te), 4),
            "pr_auc": round(average_precision_score(yt, s_te), 4),
            "threshold": round(thr, 2),
            "precision": round(precision_score(yt, pred, zero_division=0), 4),
            "recall": round(recall_score(yt, pred), 4),
            "false_decline_rate_pct": round(100 * ((yt == 0) & (pred == 1)).sum() / (yt == 0).sum(), 3),
            "fraud_amount_caught_pct": round(100 * at[(yt == 1) & (pred == 1)].sum() / at[yt == 1].sum(), 1),
            "cost_with_model": round(cost_model),
            "cost_no_model": round(cost_none),
            "cost_reduction_pct": round(100 * (1 - cost_model / cost_none), 1),
        }
        scores[name] = s_te

    out = pd.DataFrame({
        "transaction_id": df["transaction_id"].values[sl_te],
        "transaction_ts": df["transaction_ts"].values[sl_te],
        "customer_id": df["customer_id"].values[sl_te],
        "merchant_category": df["merchant_category"].values[sl_te],
        "channel": df["channel"].values[sl_te],
        "amount": amount[sl_te],
        "is_fraud": y[sl_te],
        "score": scores["gradient_boosting"],
    })
    out.to_csv(DATA_DIR / "test_scores.csv", index=False)

    # drift check: compare train vs test feature distributions (PSI)
    from drift import psi_table
    psi = psi_table(X.iloc[sl_tr], X.iloc[sl_te])
    psi.to_csv(REPORT_DIR / "drift_psi.csv", index=False)
    drifted = psi[psi.psi > 0.2].feature.tolist()

    results["_meta"] = {
        "features_with_drift_psi_gt_0.2": drifted,
        "rows_total": n, "train_rows": i1, "val_rows": i2 - i1, "test_rows": n - i2,
        "fraud_rate_pct_test": round(100 * y[sl_te].mean(), 3),
        "false_decline_cost": COST_FALSE_DECLINE,
    }

    # ---------- charts ----------
    REPORT_DIR.mkdir(exist_ok=True)
    yt = y[sl_te]
    plt.figure(figsize=(6.5, 4.5))
    for name, s in scores.items():
        p, r, _ = precision_recall_curve(yt, s)
        plt.plot(r, p, label=f"{name} (PR-AUC {results[name]['pr_auc']})")
    plt.axhline(yt.mean(), ls="--", c="grey", label=f"random ({yt.mean():.3f})")
    plt.xlabel("Recall"); plt.ylabel("Precision"); plt.title("Precision-Recall on held-out test set")
    plt.legend(); plt.grid(alpha=.3); plt.tight_layout()
    plt.savefig(REPORT_DIR / "pr_curve.png", dpi=140); plt.close()

    rng = np.random.default_rng(SEED)
    samp = rng.choice(np.arange(i2, n), size=min(15000, n - i2), replace=False)
    pi = permutation_importance(models["gradient_boosting"], X.iloc[samp], y[samp],
                                scoring="average_precision", n_repeats=3, random_state=SEED)
    imp = pd.Series(pi.importances_mean, index=X.columns).sort_values().tail(10)
    plt.figure(figsize=(6.5, 4.5))
    imp.plot(kind="barh", color="#2b6cb0")
    plt.title("Top drivers of fraud score (permutation importance)")
    plt.xlabel("Drop in PR-AUC when feature is shuffled"); plt.tight_layout()
    plt.savefig(REPORT_DIR / "feature_importance.png", dpi=140); plt.close()
    results["_meta"]["top_features"] = list(imp.index[::-1][:5])

    (REPORT_DIR / "model_metrics.json").write_text(json.dumps(results, indent=2))
    return results
