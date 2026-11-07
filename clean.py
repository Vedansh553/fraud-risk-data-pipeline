"""
Cleaning and standardization stage.

Principle: never silently drop data. Rows that cannot be fixed safely go to a
quarantine table with a reason code, so a data owner can review them. This mirrors
how governed enterprise pipelines handle bad records.
"""
import numpy as np
import pandas as pd
from config import *
from data_quality import AMOUNT_MAX


def clean(raw: pd.DataFrame):
    df = raw.copy()
    log = {"raw_rows": len(df)}

    # 1) Standardize text
    df["merchant_category"] = df["merchant_category"].astype("string").str.strip().str.lower()
    df["channel"] = df["channel"].astype("string").str.strip().str.lower()
    df["country"] = df["country"].astype("string").str.strip().str.upper().replace({"IND": "IN"})

    # 2) Remove exact duplicate ingestions (same transaction_id)
    before = len(df)
    df = df.drop_duplicates("transaction_id", keep="first")
    log["duplicates_removed"] = before - len(df)

    # 3) Parse timestamps
    df["transaction_ts"] = pd.to_datetime(df["transaction_ts"], errors="coerce")

    # 4) Quarantine rows that cannot be safely repaired
    reason = pd.Series("", index=df.index)
    reason[df.transaction_ts.isna()] = "unparseable_timestamp"
    reason[df.amount.isna()] = "missing_amount"
    reason[df.amount <= 0] = "non_positive_amount"
    reason[df.amount > AMOUNT_MAX] = "amount_outlier"
    quarantine = df[reason != ""].assign(reject_reason=reason[reason != ""])
    df = df[reason == ""].copy()
    log["quarantined_rows"] = len(quarantine)
    log["quarantine_breakdown"] = quarantine.reject_reason.value_counts().to_dict()

    # 5) Impute / repair what can be fixed with a defensible rule
    df["merchant_category"] = df["merchant_category"].fillna("unknown")
    n_cat_unknown = int((df.merchant_category == "unknown").sum())
    n_country_fixed = int(df.country.isna().sum())
    df["country"] = df["country"].fillna(df["home_country"])      # assume home country when missing
    # card_present is fully derivable from channel
    df["card_present"] = (df["channel"] != "ecommerce").astype(int)
    log["category_imputed_unknown"] = n_cat_unknown
    log["country_imputed_from_home"] = n_country_fixed

    df = df.sort_values("transaction_ts").reset_index(drop=True)
    log["clean_rows"] = len(df)
    return df, quarantine, log
