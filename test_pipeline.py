import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import numpy as np
import pandas as pd
import pytest
import clean as cleaner
import data_quality as dq
import generate_data
from drift import psi
from train_model import build_features


@pytest.fixture(scope="module")
def raw():
    generate_data.N_TRANSACTIONS = 8000
    return generate_data.generate()


def test_raw_data_has_quality_problems(raw):
    res = dq.run_checks(raw, "raw")
    assert res.failed_rows.sum() > 0
    assert res.loc[res.rule_id == "U1", "failed_rows"].iloc[0] > 0


def test_cleaning_fixes_every_rule(raw):
    clean_df, quarantine, log = cleaner.clean(raw)
    assert dq.run_checks(clean_df, "clean").failed_rows.sum() == 0
    assert log["raw_rows"] == log["duplicates_removed"] + log["quarantined_rows"] + log["clean_rows"]


def test_quarantine_has_reason_for_every_row(raw):
    _, quarantine, _ = cleaner.clean(raw)
    assert (quarantine.reject_reason != "").all()


def test_cleaning_is_idempotent(raw):
    once, _, _ = cleaner.clean(raw)
    twice, q2, _ = cleaner.clean(once.assign(transaction_ts=once.transaction_ts.astype(str)))
    assert len(twice) == len(once) and len(q2) == 0


def test_features_use_only_past_data(raw):
    """Changing a customer's FUTURE transaction must not change an earlier row's features."""
    clean_df, _, _ = cleaner.clean(raw)
    d1, f1 = build_features(clean_df)
    cust = clean_df.customer_id.value_counts().index[0]
    rows = clean_df[clean_df.customer_id == cust].sort_values("transaction_ts")
    last = rows.index[-1]
    mod = clean_df.copy()
    mod.loc[last, "amount"] = mod.loc[last, "amount"] * 1000
    d2, f2 = build_features(mod)
    first_id = rows.iloc[0].transaction_id
    a = f1[d1.transaction_id == first_id].drop(columns=[]).iloc[0]
    b = f2[d2.transaction_id == first_id].iloc[0]
    assert a.equals(b)


def test_psi_zero_for_identical_and_positive_for_shifted():
    x = pd.Series(np.random.default_rng(0).normal(size=5000))
    assert psi(x, x) < 0.01
    assert psi(x, x + 2) > 0.2


def test_velocity_features_are_in_seconds(raw):
    """Regression test: timestamps must be converted to seconds. A unit bug once made
    ~83% of rows look like rapid-fire; real rapid-fire activity should be rare."""
    clean_df, _, _ = cleaner.clean(raw)
    d, f = build_features(clean_df)
    assert f.rapid_fire.mean() < 0.05
    assert f.secs_since_prev.median() > 3600          # typical gap is hours or days, not seconds
    assert f.secs_since_prev.max() <= 7 * 24 * 3600   # clipped at one week
