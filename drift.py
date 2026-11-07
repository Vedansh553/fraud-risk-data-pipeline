"""Population Stability Index (PSI) drift monitoring.
Rule of thumb used in credit/fraud risk: PSI < 0.1 stable, 0.1-0.2 watch, > 0.2 significant shift."""
import numpy as np
import pandas as pd


def psi(expected: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    e, a = expected.astype(float).values, actual.astype(float).values
    edges = np.unique(np.quantile(e, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:                                  # binary / near-constant feature
        edges = np.array([-np.inf, np.median(e), np.inf]) if e.min() != e.max() else np.array([-np.inf, np.inf])
    edges[0], edges[-1] = -np.inf, np.inf
    ep = np.histogram(e, edges)[0] / len(e)
    ap = np.histogram(a, edges)[0] / len(a)
    ep, ap = np.clip(ep, 1e-4, None), np.clip(ap, 1e-4, None)
    return float(np.sum((ap - ep) * np.log(ap / ep)))


def psi_table(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    rows = [{"feature": c, "psi": round(psi(train[c], test[c]), 4)} for c in train.columns]
    out = pd.DataFrame(rows).sort_values("psi", ascending=False).reset_index(drop=True)
    out["status"] = pd.cut(out.psi, [-1, 0.1, 0.2, 99], labels=["stable", "watch", "shift"])
    return out
