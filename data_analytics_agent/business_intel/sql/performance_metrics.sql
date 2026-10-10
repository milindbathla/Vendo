-- ============================================================================
-- Performance Metrics Aggregation for a Date Window
-- Parameters: :start_date, :end_date
-- ============================================================================
WITH daily_agg AS (
    SELECT 
        COUNT(*) AS recorded_days,
        COALESCE(SUM(units_sold), 0) AS units_sold,
        COALESCE(SUM(revenue), 0.0) AS revenue,
        COALESCE(SUM(cogs), 0.0) AS cogs,
        COALESCE(SUM(opex), 0.0) AS opex,
        COALESCE(SUM(net_profit), 0.0) AS net_profit,
        COALESCE(SUM(cash_inflow), 0.0) AS cash_inflow,
        COALESCE(SUM(cash_outflow), 0.0) AS cash_outflow
    FROM daily_metrics
    WHERE date BETWEEN :start_date AND :end_date
),
order_split AS (
    SELECT 
        COUNT(*) AS total_orders,
        COALESCE(SUM(CASE WHEN type = 'subscription' AND status IN ('delivered', 'confirmed') THEN units ELSE 0 END), 0) AS sub_units,
        COALESCE(SUM(CASE WHEN type = 'subscription' AND status IN ('delivered', 'confirmed') THEN amount ELSE 0.0 END), 0.0) AS sub_revenue,
        COALESCE(SUM(CASE WHEN type = 'one_off' AND status IN ('delivered', 'confirmed') THEN units ELSE 0 END), 0) AS one_off_units,
        COALESCE(SUM(CASE WHEN type = 'one_off' AND status IN ('delivered', 'confirmed') THEN amount ELSE 0.0 END), 0.0) AS one_off_revenue,
        COALESCE(SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_orders,
        COALESCE(SUM(CASE WHEN status = 'refunded' THEN 1 ELSE 0 END), 0) AS refunded_orders
    FROM orders
    WHERE date BETWEEN :start_date AND :end_date
),
latest_monthly AS (
    SELECT mrr, arr
    FROM monthly_metrics
    ORDER BY month DESC
    LIMIT 1
),
customer_flow AS (
    SELECT 
        COALESCE(SUM(new), 0) AS new_customers,
        COALESCE(SUM(churned), 0) AS churned_customers,
        (SELECT current_customers FROM customer_metrics WHERE date <= :end_date ORDER BY date DESC LIMIT 1) AS current_customers,
        (SELECT recurring_pct FROM customer_metrics WHERE date <= :end_date ORDER BY date DESC LIMIT 1) AS recurring_pct
    FROM customer_metrics
    WHERE date BETWEEN :start_date AND :end_date
),
ratings_agg AS (
    SELECT 
        ROUND(AVG(rating), 2) AS avg_internal_rating,
        COUNT(*) AS review_count
    FROM customer_reviews
    WHERE date BETWEEN :start_date AND :end_date
)
SELECT 
    d.recorded_days,
    d.units_sold,
    ROUND(d.revenue, 2) AS revenue,
    ROUND(d.cogs, 2) AS cogs,
    ROUND(d.revenue - d.cogs, 2) AS gross_profit,
    ROUND(CASE WHEN d.revenue > 0 THEN ((d.revenue - d.cogs) / d.revenue) * 100.0 ELSE 0.0 END, 1) AS gross_margin_pct,
    ROUND(d.opex, 2) AS opex,
    ROUND(d.net_profit, 2) AS net_profit,
    ROUND(CASE WHEN d.revenue > 0 THEN (d.net_profit / d.revenue) * 100.0 ELSE 0.0 END, 1) AS net_margin_pct,
    ROUND(CASE WHEN d.units_sold > 0 THEN d.revenue / d.units_sold ELSE 0.0 END, 2) AS avg_revenue_per_unit,
    ROUND(CASE WHEN d.recorded_days > 0 THEN CAST(d.units_sold AS REAL) / d.recorded_days ELSE 0.0 END, 1) AS avg_units_per_day,
    ROUND(CASE WHEN d.recorded_days > 0 THEN d.revenue / d.recorded_days ELSE 0.0 END, 2) AS avg_revenue_per_day,
    
    os.sub_units,
    ROUND(os.sub_revenue, 2) AS sub_revenue,
    os.one_off_units,
    ROUND(os.one_off_revenue, 2) AS one_off_revenue,
    ROUND(CASE WHEN (os.sub_units + os.one_off_units) > 0 THEN (CAST(os.sub_units AS REAL) / (os.sub_units + os.one_off_units)) * 100.0 ELSE 0.0 END, 1) AS sub_units_share_pct,
    ROUND(CASE WHEN (os.sub_revenue + os.one_off_revenue) > 0 THEN (os.sub_revenue / (os.sub_revenue + os.one_off_revenue)) * 100.0 ELSE 0.0 END, 1) AS sub_revenue_share_pct,
    
    os.cancelled_orders,
    os.refunded_orders,
    ROUND(CASE WHEN os.total_orders > 0 THEN (CAST(os.cancelled_orders + os.refunded_orders AS REAL) / os.total_orders) * 100.0 ELSE 0.0 END, 1) AS cancellation_refund_rate_pct,
    
    ROUND(d.cash_inflow, 2) AS cash_inflow,
    ROUND(d.cash_outflow, 2) AS cash_outflow,
    ROUND(d.cash_inflow - d.cash_outflow, 2) AS net_cash_flow,
    
    lm.mrr,
    lm.arr,
    
    cf.current_customers,
    cf.recurring_pct,
    cf.new_customers,
    cf.churned_customers,
    
    r.avg_internal_rating,
    r.review_count
FROM daily_agg d
CROSS JOIN order_split os
CROSS JOIN latest_monthly lm
CROSS JOIN customer_flow cf
CROSS JOIN ratings_agg r;

