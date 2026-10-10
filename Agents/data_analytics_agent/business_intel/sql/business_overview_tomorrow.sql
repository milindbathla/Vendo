-- ============================================================================
-- Business Overview: Tomorrow's Orders, Forecast, and Delivery Slots
-- ============================================================================
WITH tomorrow_meta AS (
    SELECT value AS tomorrow_date FROM meta WHERE key = 'tomorrow_date'
),
confirmed_orders AS (
    SELECT 
        COUNT(*) AS confirmed_units,
        SUM(CASE WHEN type = 'subscription' THEN 1 ELSE 0 END) AS subscription_units,
        SUM(CASE WHEN type = 'one_off' THEN 1 ELSE 0 END) AS one_off_units
    FROM orders
    WHERE date = (SELECT tomorrow_date FROM tomorrow_meta)
      AND status = 'confirmed'
),
forecast_info AS (
    SELECT 
        df.units_forecast,
        df.lower,
        df.upper,
        df.confidence AS forecast_confidence,
        bp.safety_stock_pct,
        ROUND(df.units_forecast * (1.0 + bp.safety_stock_pct / 100.0), 1) AS effective_target
    FROM demand_forecast df
    CROSS JOIN business_policy bp
    WHERE df.date = (SELECT tomorrow_date FROM tomorrow_meta)
),
kitchen_cap AS (
    SELECT max_meals, cook_hours
    FROM capacity
    WHERE date = (SELECT tomorrow_date FROM tomorrow_meta)
)
SELECT 
    (SELECT tomorrow_date FROM tomorrow_meta) AS tomorrow_date,
    co.confirmed_units,
    co.subscription_units,
    co.one_off_units,
    fi.units_forecast,
    fi.lower,
    fi.upper,
    fi.forecast_confidence,
    fi.effective_target,
    kc.max_meals,
    kc.cook_hours
FROM confirmed_orders co
CROSS JOIN forecast_info fi
CROSS JOIN kitchen_cap kc;

