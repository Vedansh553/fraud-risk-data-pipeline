"""
OPTIONAL: load the cleaned data into Google BigQuery.

Requires a Google Cloud project (the free sandbox tier works) and credentials:
    pip install google-cloud-bigquery pandas-gbq db-dtypes
    gcloud auth application-default login
    export GCP_PROJECT=your-project-id
    python bigquery_load.py

Creates dataset `fraud_risk` with tables `transactions` and `quarantine`
and the analytical views from sql/bigquery_views.sql.
NOTE: written against the BigQuery client API but not executed in the build
environment (no GCP credentials there), so test it once on your own account.
"""
import os
import pandas as pd
from config import *


def main():
    from google.cloud import bigquery
    project = os.environ["GCP_PROJECT"]
    client = bigquery.Client(project=project)
    dataset = f"{project}.fraud_risk"
    client.create_dataset(bigquery.Dataset(dataset), exists_ok=True)

    clean = pd.read_csv(CLEAN_CSV, parse_dates=["transaction_ts"])
    quarantine = pd.read_csv(DATA_DIR / "quarantine.csv")
    cfg = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    for name, frame in [("transactions", clean), ("quarantine", quarantine)]:
        client.load_table_from_dataframe(frame, f"{dataset}.{name}", job_config=cfg).result()
        print(f"Loaded {len(frame):,} rows -> {dataset}.{name}")

    ddl = (ROOT / "sql" / "bigquery_views.sql").read_text().replace("{dataset}", dataset)
    for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
        client.query(stmt).result()
    print("Views created.")


if __name__ == "__main__":
    main()
