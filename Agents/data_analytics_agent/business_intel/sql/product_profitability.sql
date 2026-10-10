-- ============================================================================
-- Product Profitability: Unit Economics Per Standard Veg Tiffin
-- ============================================================================
WITH blended_pricing AS (
    SELECT 
        ROUND(AVG(amount / units), 2) AS realized_blended_price,
        ROUND(AVG(CASE WHEN type = 'one_off' THEN amount / units ELSE NULL END), 2) AS realized_one_off_price,
        ROUND(AVG(CASE WHEN type = 'subscription' THEN amount / units ELSE NULL END), 2) AS realized_subscriber_price
    FROM orders
    WHERE status IN ('delivered', 'confirmed')
      AND date >= (SELECT date(value, '-30 days') FROM meta WHERE key = 'frozen_date')
),
latest_costs AS (
    SELECT 
        rb.item_id,
        i.name AS item_name,
        i.unit,
        rb.qty_per_tiffin,
        i.procure_mode,
        CASE 
            -- Vegetables from average mandi purchase
            WHEN i.item_id = 'VEG-MIX' THEN 
                (SELECT ROUND(AVG(unit_price), 2) FROM purchase_history WHERE item_id = 'VEG-MIX')
            -- Regular catalogue price from regular supplier
            ELSE 
                (SELECT c.price_per_unit FROM catalogue c WHERE c.item_id = rb.item_id AND c.is_simulated = 0 ORDER BY c.price_per_unit ASC LIMIT 1)
        END AS unit_cost,
        CASE 
            -- Fast delivery simulated pricing from SUP-04
            WHEN i.item_id = 'VEG-MIX' THEN 
                (SELECT ROUND(AVG(unit_price), 2) FROM purchase_history WHERE item_id = 'VEG-MIX')
            ELSE 
                COALESCE((SELECT c.price_per_unit FROM catalogue c WHERE c.item_id = rb.item_id AND c.supplier_id = 'SUP-04'), 
                         (SELECT c.price_per_unit FROM catalogue c WHERE c.item_id = rb.item_id ORDER BY c.price_per_unit ASC LIMIT 1))
        END AS simulated_fast_unit_cost
    FROM recipe_bom rb
    JOIN items i ON rb.item_id = i.item_id
),
itemized_cogs AS (
    SELECT 
        item_id,
        item_name,
        unit,
        qty_per_tiffin,
        procure_mode,
        unit_cost,
        ROUND(qty_per_tiffin * unit_cost, 2) AS cost_per_tiffin,
        ROUND(qty_per_tiffin * simulated_fast_unit_cost, 2) AS simulated_cost_per_tiffin
    FROM latest_costs
),
opex_summary AS (
    SELECT 
        ROUND(AVG(opex), 2) AS avg_daily_opex,
        ROUND(AVG(units_sold), 1) AS avg_daily_units,
        ROUND(AVG(cogs * 100.0 / revenue), 1) AS reported_cogs_pct
    FROM daily_metrics
    WHERE date >= (SELECT date(value, '-30 days') FROM meta WHERE key = 'frozen_date')
)
SELECT 
    bp.realized_blended_price,
    bp.realized_one_off_price,
    bp.realized_subscriber_price,
    os.avg_daily_opex,
    os.avg_daily_units,
    os.reported_cogs_pct
FROM blended_pricing bp
CROSS JOIN opex_summary os;

