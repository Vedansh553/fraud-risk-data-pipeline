-- Analytical views = the "data products" downstream teams would consume.

CREATE VIEW v_fraud_by_category AS
SELECT merchant_category,
       COUNT(*)                                   AS txns,
       SUM(is_fraud)                              AS fraud_txns,
       ROUND(100.0 * SUM(is_fraud) / COUNT(*), 3) AS fraud_rate_pct,
       ROUND(SUM(CASE WHEN is_fraud = 1 THEN amount END), 0) AS fraud_amount
FROM transactions
GROUP BY merchant_category;

CREATE VIEW v_fraud_by_hour AS
SELECT CAST(strftime('%H', transaction_ts) AS INTEGER) AS hour_of_day,
       COUNT(*)                                   AS txns,
       ROUND(100.0 * SUM(is_fraud) / COUNT(*), 3) AS fraud_rate_pct
FROM transactions
GROUP BY hour_of_day;

CREATE VIEW v_fraud_by_channel_geo AS
SELECT channel,
       CASE WHEN country <> home_country THEN 'foreign' ELSE 'domestic' END AS geo,
       COUNT(*)                                   AS txns,
       ROUND(100.0 * SUM(is_fraud) / COUNT(*), 3) AS fraud_rate_pct
FROM transactions
GROUP BY channel, geo;

-- Velocity: transactions per customer within 15 minutes of the previous one
CREATE VIEW v_rapid_fire_customers AS
WITH ordered AS (
  SELECT customer_id, transaction_id, transaction_ts, is_fraud,
         (julianday(transaction_ts) -
          julianday(LAG(transaction_ts) OVER (PARTITION BY customer_id ORDER BY transaction_ts))) * 1440
          AS minutes_since_prev
  FROM transactions
)
SELECT customer_id,
       COUNT(*)           AS rapid_txns,
       SUM(is_fraud)      AS fraud_in_rapid
FROM ordered
WHERE minutes_since_prev IS NOT NULL AND minutes_since_prev <= 15
GROUP BY customer_id;

-- Data quality: what did we quarantine and why
CREATE VIEW v_quarantine_summary AS
SELECT reject_reason, COUNT(*) AS rows_rejected
FROM quarantine
GROUP BY reject_reason;
