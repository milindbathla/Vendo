-- ============================================================================
-- Business Overview: Inventory Stock, Tomorrow's Requirement & Shortfall Alerts
-- ============================================================================
WITH tomorrow_target AS (
    SELECT 
        ROUND(df.units_forecast * (1.0 + bp.safety_stock_pct / 100.0), 1) AS effective_units
    FROM demand_forecast df
    CROSS JOIN business_policy bp
    WHERE df.date = (SELECT value FROM meta WHERE key = 'tomorrow_date')
)
SELECT 
    i.item_id,
    i.name AS item_name,
    i.unit,
    i.procure_mode,
    s.stock_qty,
    i.reorder_point,
    i.par_level,
    rb.qty_per_tiffin AS bom_qty,
    CASE 
        WHEN i.unit = 'pcs' THEN CAST(CEIL((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin) AS REAL)
        ELSE ROUND((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin, 3)
    END AS tomorrow_requirement,
    ROUND(MAX(0.0, 
        CASE 
            WHEN i.unit = 'pcs' THEN CAST(CEIL((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin) AS REAL)
            ELSE ROUND((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin, 3)
        END - s.stock_qty
    ), 3) AS shortfall_qty,
    ROUND(s.stock_qty - 
        CASE 
            WHEN i.unit = 'pcs' THEN CAST(CEIL((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin) AS REAL)
            ELSE ROUND((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin, 3)
        END, 3
    ) AS projected_stock_after,
    CASE 
        WHEN s.stock_qty < (
            CASE 
                WHEN i.unit = 'pcs' THEN CAST(CEIL((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin) AS REAL)
                ELSE ROUND((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin, 3)
            END
        ) THEN 1
        WHEN (s.stock_qty - (
            CASE 
                WHEN i.unit = 'pcs' THEN CAST(CEIL((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin) AS REAL)
                ELSE ROUND((SELECT effective_units FROM tomorrow_target) * rb.qty_per_tiffin, 3)
            END
        )) < i.reorder_point THEN 1
        ELSE 0
    END AS is_alert
FROM items i
JOIN recipe_bom rb ON i.item_id = rb.item_id
JOIN inventory_stock s ON i.item_id = s.item_id
ORDER BY shortfall_qty DESC, is_alert DESC, i.item_id ASC;

