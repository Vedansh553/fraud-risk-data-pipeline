-- Example analyst queries to run against data/fraud_risk.db

-- 1. Which category/channel combos carry the highest fraud rate (min volume 300)?
SELECT merchant_category, channel, COUNT(*) AS txns,
       ROUND(100.0 * SUM(is_fraud) / COUNT(*), 2) AS fraud_rate_pct
FROM transactions
GROUP BY merchant_category, channel
HAVING txns >= 300
ORDER BY fraud_rate_pct DESC
LIMIT 10;

-- 2. Share of total fraud loss coming from the top 5% of transactions by amount
WITH ranked AS (
  SELECT amount, is_fraud, NTILE(20) OVER (ORDER BY amount DESC) AS bucket FROM transactions
)
SELECT ROUND(100.0 * SUM(CASE WHEN bucket = 1 AND is_fraud = 1 THEN amount END)
             / SUM(CASE WHEN is_fraud = 1 THEN amount END), 1) AS pct_fraud_loss_in_top5pct_txns
FROM ranked;

-- 3. Daily fraud rate with a 7-day moving average (trend monitoring)
WITH daily AS (
  SELECT date(transaction_ts) AS d, 100.0 * SUM(is_fraud) / COUNT(*) AS rate
  FROM transactions GROUP BY d
)
SELECT d, ROUND(rate, 3) AS daily_rate_pct,
       ROUND(AVG(rate) OVER (ORDER BY d ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 3) AS ma7_pct
FROM daily ORDER BY d;
