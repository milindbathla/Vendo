-- ============================================================================
-- Business Overview: Cash, Projections and 7-day Obligations
-- ============================================================================
WITH current_cash AS (
    SELECT 
        cp.current_balance,
        cp.min_cash_buffer
    FROM cash_position cp
    WHERE cp.as_of = (SELECT value FROM meta WHERE key = 'as_of')
),
min_proj AS (
    SELECT 
        projected_balance AS min_projected_balance,
        date AS min_projected_date,
        confidence AS balance_confidence
    FROM forecasted_balance
    ORDER BY projected_balance ASC, date ASC
    LIMIT 1
),
obligations_next_7d AS (
    SELECT 
        COALESCE(SUM(amount), 0.0) AS total_obligations,
        COUNT(*) AS obligation_count
    FROM upcoming_payments
    WHERE due_date BETWEEN (SELECT date(value) FROM meta WHERE key = 'tomorrow_date')
                       AND (SELECT date(value, '+7 days') FROM meta WHERE key = 'tomorrow_date')
      AND status = 'pending'
)
SELECT 
    c.current_balance,
    c.min_cash_buffer,
    p.min_projected_balance,
    p.min_projected_date,
    p.balance_confidence,
    ROUND(p.min_projected_balance - c.min_cash_buffer, 2) AS headroom_over_buffer,
    o.total_obligations,
    o.obligation_count
FROM current_cash c
CROSS JOIN min_proj p
CROSS JOIN obligations_next_7d o;

