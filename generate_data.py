"""
Generate a realistic synthetic card-transaction dataset with fraud AND deliberately
injected data-quality problems (nulls, duplicates, bad formats, invalid values).

Why synthetic? Real card data is confidential. The generator encodes known fraud
patterns (night time, high amount, foreign country, e-commerce, velocity bursts)
so the model has genuine signal, and the injected defects give the data quality
framework something real to detect and fix.

To use a real dataset (e.g. Kaggle IEEE-CIS), replace RAW_CSV and adapt the
column mapping in clean.py.
"""
import numpy as np
import pandas as pd
from config import *


def generate() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    n = N_TRANSACTIONS

    n_customers = 6000
    customer_id = rng.integers(10_000, 10_000 + n_customers, n)
    home_country = rng.choice(VALID_COUNTRIES, n_customers, p=[0.7, 0.1, 0.05, 0.05, 0.05, 0.05])
    cust_home = dict(zip(range(10_000, 10_000 + n_customers), home_country))

    start = pd.Timestamp("2026-01-01")
    ts = start + pd.to_timedelta(rng.integers(0, 90 * 24 * 3600, n), unit="s")

    category = rng.choice(VALID_CATEGORIES, n, p=[.22, .12, .06, .14, .07, .1, .06, .08, .08, .07])
    channel = rng.choice(VALID_CHANNELS, n, p=[.45, .30, .05, .20])
    amount = np.round(rng.lognormal(mean=6.2, sigma=1.0, size=n), 2)
    merchant_id = rng.integers(1, 3000, n)
    country = np.array([cust_home[c] for c in customer_id], dtype=object)
    foreign = rng.random(n) < 0.04
    country[foreign] = rng.choice(VALID_COUNTRIES, foreign.sum())
    card_present = np.isin(channel, ["pos", "atm", "contactless"]).astype(int)

    df = pd.DataFrame({
        "transaction_id": np.arange(1, n + 1),
        "customer_id": customer_id,
        "transaction_ts": ts,
        "merchant_id": merchant_id,
        "merchant_category": category,
        "channel": channel,
        "amount": amount,
        "country": country,
        "home_country": [cust_home[c] for c in customer_id],
        "card_present": card_present,
    })

    # Fraud label from a hidden risk score (gives the model real signal)
    hour = df.transaction_ts.dt.hour
    risk = (
        -9.0
        + 2.2 * ((hour <= 4) | (hour >= 23))
        + 1.8 * (df.amount > df.amount.quantile(0.95))
        + 3.0 * (df.country != df.home_country)
        + 2.2 * (df.channel == "ecommerce")
        + 1.5 * df.merchant_category.isin(["electronics", "travel", "online_services"])
        + 1.0 * (df.card_present == 0)
        + rng.normal(0, 0.4, n)
    )
    p = 1 / (1 + np.exp(-risk))
    p = np.clip(p * (FRAUD_RATE / p.mean()), 0, 0.95)
    df["is_fraud"] = (rng.random(n) < p).astype(int)

    # Velocity bursts: some fraudulent cards get 2-4 rapid follow-up transactions
    fraud_idx = df.index[df.is_fraud == 1]
    burst_src = rng.choice(fraud_idx, size=min(150, len(fraud_idx)), replace=False)
    bursts = []
    for i in burst_src:
        base = df.loc[i].copy()
        for k in range(int(rng.integers(2, 5))):
            r = base.copy()
            r["transaction_ts"] = base["transaction_ts"] + pd.Timedelta(minutes=int(rng.integers(1, 12)) * (k + 1))
            r["amount"] = round(float(base["amount"]) * rng.uniform(0.3, 0.9), 2)
            bursts.append(r)
    df = pd.concat([df, pd.DataFrame(bursts)], ignore_index=True)
    df = df.sort_values("transaction_ts").reset_index(drop=True)
    df["transaction_id"] = np.arange(1, len(df) + 1)

    return inject_quality_issues(df, rng)


def inject_quality_issues(df: pd.DataFrame, rng) -> pd.DataFrame:
    """Corrupt a controlled share of the data, like real-world feeds."""
    df = df.copy()
    n = len(df)
    df["transaction_ts"] = df["transaction_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["merchant_category"] = df["merchant_category"].astype(object)
    df["channel"] = df["channel"].astype(object)
    df["country"] = df["country"].astype(object)
    df["amount"] = df["amount"].astype(float)

    # 1) missing values
    df.loc[rng.choice(n, int(n * 0.020), replace=False), "merchant_category"] = np.nan
    df.loc[rng.choice(n, int(n * 0.015), replace=False), "country"] = np.nan
    df.loc[rng.choice(n, int(n * 0.008), replace=False), "amount"] = np.nan

    # 2) inconsistent text formatting
    idx = rng.choice(n, int(n * 0.03), replace=False)
    df.loc[idx, "merchant_category"] = df.loc[idx, "merchant_category"].astype(str).str.upper().replace("NAN", np.nan)
    idx = rng.choice(n, int(n * 0.02), replace=False)
    df.loc[idx, "channel"] = " " + df.loc[idx, "channel"].astype(str) + " "
    df.loc[rng.choice(n, int(n * 0.01), replace=False), "country"] = "IND"   # alias for IN

    # 3) invalid values
    k = int(n * 0.004)
    df.loc[rng.choice(n, k, replace=False), "amount"] = -1.0 * rng.integers(1, 500, k)
    df.loc[rng.choice(n, 40, replace=False), "amount"] = rng.integers(5_000_000, 9_000_000, 40).astype(float)
    df.loc[rng.choice(n, int(n * 0.003), replace=False), "transaction_ts"] = "2027-13-45 99:99:99"
    df.loc[rng.choice(n, int(n * 0.002), replace=False), "card_present"] = 2

    # 4) consistency: e-commerce marked as card-present
    idx = df.index[df.channel.astype(str).str.strip() == "ecommerce"]
    df.loc[rng.choice(idx, int(len(idx) * 0.01), replace=False), "card_present"] = 1

    # 5) duplicates (same transaction ingested twice)
    dups = df.sample(int(n * 0.012), random_state=1)
    df = pd.concat([df, dups], ignore_index=True)
    return df.sample(frac=1, random_state=7).reset_index(drop=True)


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    out = generate()
    out.to_csv(RAW_CSV, index=False)
    print(f"Wrote {len(out):,} raw rows -> {RAW_CSV}")
