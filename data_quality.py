"""
Reusable data quality framework.

Each rule returns the number of failing rows. Rules are grouped by standard data
quality dimensions (Completeness, Uniqueness, Validity, Consistency), which is how
enterprise data governance teams usually report quality. Running the same rule set
before and after cleaning proves the cleaning actually worked.
"""
import pandas as pd
from config import *

AMOUNT_MAX = 1_000_000  # business rule: single card transaction above this is suspect


def _ts(df):
    return pd.to_datetime(df["transaction_ts"], errors="coerce")


def build_rules():
    """(rule_id, dimension, column, description, function returning boolean 'fails' mask)"""
    return [
        ("C1", "Completeness", "merchant_category", "merchant_category is not null",
         lambda d: d.merchant_category.isna()),
        ("C2", "Completeness", "country", "country is not null",
         lambda d: d.country.isna()),
        ("C3", "Completeness", "amount", "amount is not null",
         lambda d: d.amount.isna()),
        ("U1", "Uniqueness", "transaction_id", "transaction_id is unique",
         lambda d: d.duplicated("transaction_id", keep="first")),
        ("V1", "Validity", "amount", "amount is greater than 0",
         lambda d: d.amount.notna() & (d.amount <= 0)),
        ("V2", "Validity", "amount", f"amount is not above {AMOUNT_MAX:,} (outlier cap)",
         lambda d: d.amount.notna() & (d.amount > AMOUNT_MAX)),
        ("V3", "Validity", "transaction_ts", "transaction_ts is a parseable timestamp",
         lambda d: _ts(d).isna()),
        ("V4", "Validity", "card_present", "card_present is 0 or 1",
         lambda d: ~d.card_present.isin([0, 1])),
        ("V5", "Validity", "merchant_category", "merchant_category is in approved list (incl. governed 'unknown' sentinel)",
         lambda d: d.merchant_category.notna() & ~d.merchant_category.isin(VALID_CATEGORIES + ["unknown"])),
        ("V6", "Validity", "channel", "channel is in approved list",
         lambda d: ~d.channel.isin(VALID_CHANNELS)),
        ("V7", "Validity", "country", "country is a valid ISO-2 code",
         lambda d: d.country.notna() & ~d.country.isin(VALID_COUNTRIES)),
        ("K1", "Consistency", "card_present", "ecommerce transactions are never card-present",
         lambda d: (d.channel.astype(str).str.strip() == "ecommerce") & (d.card_present == 1)),
    ]


def run_checks(df: pd.DataFrame, stage: str) -> pd.DataFrame:
    rows = []
    n = len(df)
    for rid, dim, col, desc, fn in build_rules():
        failed = int(fn(df).sum())
        rows.append({
            "stage": stage, "rule_id": rid, "dimension": dim, "column": col,
            "rule": desc, "failed_rows": failed,
            "pass_rate_pct": round(100 * (1 - failed / n), 3),
        })
    return pd.DataFrame(rows)


def scorecard(results: pd.DataFrame) -> pd.DataFrame:
    """Average pass-rate per dimension plus an overall score."""
    s = results.groupby("dimension")["pass_rate_pct"].mean().round(2)
    s.loc["OVERALL"] = round(results["pass_rate_pct"].mean(), 2)
    return s.rename("score_pct").reset_index()
