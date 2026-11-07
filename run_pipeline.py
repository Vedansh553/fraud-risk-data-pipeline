"""End-to-end pipeline:  raw CSV -> DQ checks -> clean/quarantine -> DQ re-check -> SQL -> model."""
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import *
import generate_data, data_quality, clean as cleaner, load_sql, train_model


def main():
    DATA_DIR.mkdir(exist_ok=True); REPORT_DIR.mkdir(exist_ok=True)

    if not RAW_CSV.exists():
        generate_data.DATA_DIR.mkdir(exist_ok=True)
        generate_data.generate().to_csv(RAW_CSV, index=False)
    raw = pd.read_csv(RAW_CSV)
    print(f"[1/5] Loaded raw data: {len(raw):,} rows")

    before = data_quality.run_checks(raw, "before_cleaning")
    print("[2/5] Data quality BEFORE cleaning:")
    print(data_quality.scorecard(before).to_string(index=False))

    clean_df, quarantine, log = cleaner.clean(raw)
    clean_df.to_csv(CLEAN_CSV, index=False)
    quarantine.to_csv(DATA_DIR / "quarantine.csv", index=False)
    after = data_quality.run_checks(clean_df, "after_cleaning")
    print("[3/5] Data quality AFTER cleaning:")
    print(data_quality.scorecard(after).to_string(index=False))
    print("     cleaning log:", json.dumps(log))

    pd.concat([before, after]).to_csv(REPORT_DIR / "data_quality_results.csv", index=False)
    sb, sa = data_quality.scorecard(before), data_quality.scorecard(after)
    cmp = sb.merge(sa, on="dimension", suffixes=("_before", "_after"))
    cmp.to_csv(REPORT_DIR / "data_quality_scorecard.csv", index=False)
    (REPORT_DIR / "cleaning_log.json").write_text(json.dumps(log, indent=2))

    ax = cmp.set_index("dimension")[["score_pct_before", "score_pct_after"]].plot(
        kind="bar", figsize=(7, 4.5), color=["#c53030", "#2f855a"], ylim=(95, 100.2))
    ax.set_ylabel("Pass rate (%)"); ax.set_title("Data quality score by dimension")
    ax.legend(["Before cleaning", "After cleaning"]); plt.xticks(rotation=20); plt.tight_layout()
    plt.savefig(REPORT_DIR / "dq_scorecard.png", dpi=140); plt.close()

    con = load_sql.load(clean_df, quarantine)
    print("[4/5] Loaded SQLite DB. Fraud by category:")
    print(pd.read_sql("SELECT * FROM v_fraud_by_category ORDER BY fraud_rate_pct DESC LIMIT 5", con).to_string(index=False))
    con.close()

    res = train_model.run(clean_df)
    print("[5/5] Model results (held-out test set):")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
