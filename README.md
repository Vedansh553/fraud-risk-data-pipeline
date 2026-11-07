# Fraud Risk Data Pipeline: Data Quality, Governance, Fraud Model and Monitoring

An end-to-end project that mirrors how a Credit and Fraud Risk data team works: ingest messy card-transaction data, **measure and fix its quality**, publish it as governed SQL data products, build a **cost-aware fraud model**, and **monitor** it through a dashboard and drift checks.

**Stack:** Python (pandas, scikit-learn), SQL (SQLite and BigQuery, window functions, views), Streamlit, pytest.

> **Note on data:** real card data is confidential, so the project generates a synthetic dataset (about 122k raw transactions, about 1.2% base fraud) with realistic fraud patterns and deliberately injected quality defects. Model metrics therefore reflect how the data was simulated, not real-world performance. To use real data (for example Kaggle IEEE-CIS), replace `data/transactions_raw.csv` and adjust the column names.

## Quick start
```bash
pip install -r requirements.txt
cd src && python run_pipeline.py      # generates data, cleans, loads SQL, trains, writes reports
cd .. && python -m pytest tests -q    # 7 tests
streamlit run app/dashboard.py        # monitoring dashboard
```

## Pipeline
```
generate_data.py -> data_quality.py (12 rules, BEFORE) -> clean.py (repair + quarantine)
  -> data_quality.py (same rules, AFTER) -> load_sql.py (constraints + views)
  -> train_model.py (features, 2 models, cost-based threshold) -> drift.py (PSI)
  -> app/dashboard.py   |   bigquery_load.py (optional)
```

## 1. Data quality and governance
Injected defects: missing values, duplicate ingestions, inconsistent case and whitespace, country aliases, negative and absurd amounts, unparseable timestamps, invalid flags, e-commerce marked card-present.

| Dimension | Before | After |
|---|---|---|
| Completeness | 98.57% | 100% |
| Uniqueness | 98.81% | 100% |
| Validity | 99.02% | 100% |
| Consistency | 99.70% | 100% |
| **Overall** | **98.95%** | **100%** |

- 1,445 duplicates removed; 1,839 unrepairable rows **quarantined with reason codes** (missing amount 963, non-positive amount 481, bad timestamp 355, outlier 40). Nothing is silently dropped.
- Data dictionary with definitions, allowed values, owners and sensitivity: `docs/data_dictionary.md`.
- The SQL table enforces the same rules with `NOT NULL` and `CHECK` constraints.

![DQ scorecard](reports/dq_scorecard.png)

## 2. SQL data products
`sql/views.sql` builds views for fraud by category, hour, channel and geography, rapid-fire customers (`LAG()` window function) and a quarantine summary. `sql/analysis_queries.sql` has analyst queries using `NTILE`, moving averages and `HAVING`. `sql/bigquery_views.sql` holds BigQuery versions.

Example insight: online_services, electronics and travel run at about 3.3% to 3.6% fraud versus about 1.2% overall.

## 3. Fraud model
- **Chronological split** 60/20/20 to avoid leakage; a unit test proves features use only past data.
- **Features:** time since previous transactions (velocity), rapid-fire flag, amount versus the customer's own history, night-time, foreign country, card-present, category, channel.
- **Imbalance** handled with class weights; judged by PR-AUC, not accuracy.
- **Threshold chosen by business cost** on validation data: a missed fraud costs the transaction amount, a false decline costs 25 (assumed, configurable).

Held-out test set (23,720 transactions, 1.61% fraud):

| Model | ROC-AUC | PR-AUC | Recall | Precision | Good txns declined | Fraud value caught | Cost reduction vs approve-all |
|---|---|---|---|---|---|---|---|
| Logistic regression | 0.933 | 0.472 | 79.6% | 12.2% | 9.4% | 80.4% | 68.5% |
| Gradient boosting | 0.933 | 0.506 | 87.2% | 9.1% | 14.2% | 91.0% | 72.9% |

Gradient boosting catches more fraud value but declines more good customers; the better choice depends on the false-decline cost, which the dashboard lets you vary.

![PR curve](reports/pr_curve.png) ![Importance](reports/feature_importance.png)

## 4. Monitoring
- **Dashboard** (`streamlit run app/dashboard.py`): data quality scorecard and rule results, fraud explorer with a read-only SQL box, interactive threshold and cost simulator, drift monitor.
- **Drift** (`src/drift.py`): Population Stability Index per feature between train and test. Below 0.1 stable, 0.1 to 0.2 watch, above 0.2 shift. All features are currently stable.

## 5. Tests
`tests/test_pipeline.py` (7 tests): defects exist in raw data, cleaning satisfies every rule, every quarantined row has a reason, cleaning is idempotent, features use only past data, PSI behaves correctly, and a regression test for the timestamp unit bug below.

## 6. BigQuery (optional)
`src/bigquery_load.py` loads the cleaned tables and creates the views in a BigQuery dataset. It needs your own Google Cloud project and credentials, and was not run in the build environment, so test it on your account before claiming it.

## A bug the monitoring caught (good interview story)
In an earlier run the drift check flagged `rapid_fire` with a PSI of 0.94 (83% of training rows versus 99.9% of test rows), which is impossible for a rare behaviour. Cause: in pandas 3 the default timestamp unit is no longer nanoseconds, so my "seconds since previous transaction" feature was scaled wrongly. I fixed the conversion to explicit seconds and added a regression test. Lesson: monitor your features, not just your model.

## Limitations and next steps
- Synthetic data: results show the method works, not production accuracy.
- Precision is low in absolute terms (normal for rare fraud); a real system would add a manual-review tier between approve and decline.
- Cost parameters are assumptions; the best threshold moves with them.
- Next: run on a real public dataset, add label-delay handling, add an LLM natural-language-to-SQL assistant over the views.

## Interview talking points
1. Time-based split and how leakage could creep in.
2. PR-AUC and cost, not accuracy, at a 1% fraud rate.
3. Threshold as a trade-off between fraud loss and customer friction.
4. Quarantine rather than delete (auditability, data ownership).
5. The drift-monitor bug story above.
6. What changes with real data: label delay, concept drift, adversaries adapting.
