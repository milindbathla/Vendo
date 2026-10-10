-- ============================================================================
-- Performance Anomalies & Day-of-Week Profile
-- Parameters: :start_date, :end_date
-- ============================================================================
SELECT 
    dm.date,
    dd.day_of_week,
    dm.units_sold,
    dm.revenue,
    dm.net_profit,
    (
        SELECT AVG(sub.revenue) 
        FROM daily_metrics sub 
        WHERE sub.date < dm.date 
          AND sub.date >= date(dm.date, '-28 days')
    ) AS trailing_mean_revenue,
    (
        SELECT AVG(sub.units_sold) 
        FROM daily_metrics sub 
        WHERE sub.date < dm.date 
          AND sub.date >= date(dm.date, '-28 days')
    ) AS trailing_mean_units
FROM daily_metrics dm
JOIN demand_drivers dd ON dm.date = dd.date
WHERE dm.date BETWEEN :start_date AND :end_date
ORDER BY dm.date ASC;

