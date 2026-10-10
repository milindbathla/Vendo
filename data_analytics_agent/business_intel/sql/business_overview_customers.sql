-- ============================================================================
-- Business Overview: Customers, Subscriptions & 30-Day Growth
-- ============================================================================
WITH customer_snapshot AS (
    SELECT 
        COUNT(*) AS total_customers_all_time,
        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS current_customers,
        SUM(CASE WHEN status = 'active' AND is_recurring = 1 THEN 1 ELSE 0 END) AS recurring_customers,
        SUM(CASE WHEN status = 'active' AND is_recurring = 0 THEN 1 ELSE 0 END) AS one_off_customers,
        ROUND(
            SUM(CASE WHEN status = 'active' AND is_recurring = 1 THEN 1.0 ELSE 0.0 END) * 100.0 /
            NULLIF(SUM(CASE WHEN status = 'active' THEN 1.0 ELSE 0.0 END), 0),
            1
        ) AS recurring_pct
    FROM customers
),
growth_30d AS (
    SELECT 
        COALESCE(SUM(new), 0) AS new_30d,
        COALESCE(SUM(churned), 0) AS churned_30d
    FROM customer_metrics
    WHERE date >= (SELECT date(value, '-30 days') FROM meta WHERE key = 'frozen_date')
)
SELECT 
    cs.current_customers,
    cs.recurring_customers,
    cs.one_off_customers,
    cs.recurring_pct,
    g.new_30d,
    g.churned_30d
FROM customer_snapshot cs
CROSS JOIN growth_30d g;

