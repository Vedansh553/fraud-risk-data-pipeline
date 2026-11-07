-- BigQuery (GoogleSQL) versions of the main views. {dataset} is substituted by bigquery_load.py.
CREATE OR REPLACE VIEW `{dataset}.v_fraud_by_category` AS
SELECT merchant_category,
       COUNT(*) AS txns,
       SUM(is_fraud) AS fraud_txns,
       ROUND(100 * SUM(is_fraud) / COUNT(*), 3) AS fraud_rate_pct
FROM `{dataset}.transactions`
GROUP BY merchant_category;

CREATE OR REPLACE VIEW `{dataset}.v_fraud_by_hour` AS
SELECT EXTRACT(HOUR FROM transaction_ts) AS hour_of_day,
       COUNT(*) AS txns,
       ROUND(100 * SUM(is_fraud) / COUNT(*), 3) AS fraud_rate_pct
FROM `{dataset}.transactions`
GROUP BY hour_of_day;

CREATE OR REPLACE VIEW `{dataset}.v_rapid_fire_customers` AS
WITH ordered AS (
  SELECT customer_id, is_fraud,
         TIMESTAMP_DIFF(transaction_ts,
           LAG(transaction_ts) OVER (PARTITION BY customer_id ORDER BY transaction_ts), MINUTE) AS minutes_since_prev
  FROM `{dataset}.transactions`
)
SELECT customer_id, COUNT(*) AS rapid_txns, SUM(is_fraud) AS fraud_in_rapid
FROM ordered
WHERE minutes_since_prev IS NOT NULL AND minutes_since_prev <= 15
GROUP BY customer_id;
