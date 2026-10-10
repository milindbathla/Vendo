-- ============================================================================
-- Product Profitability: Itemized Breakdown per BOM Ingredient
-- ============================================================================
WITH latest_costs AS (
    SELECT 
        rb.item_id,
        i.name AS item_name,
        i.unit,
        rb.qty_per_tiffin,
        i.procure_mode,
        CASE 
            WHEN i.item_id = 'VEG-MIX' THEN 
                (SELECT ROUND(AVG(unit_price), 2) FROM purchase_history WHERE item_id = 'VEG-MIX')
            ELSE 
                (SELECT c.price_per_unit FROM catalogue c WHERE c.item_id = rb.item_id AND c.is_simulated = 0 ORDER BY c.price_per_unit ASC LIMIT 1)
        END AS unit_cost,
        CASE 
            WHEN i.item_id = 'VEG-MIX' THEN 
                (SELECT ROUND(AVG(unit_price), 2) FROM purchase_history WHERE item_id = 'VEG-MIX')
            ELSE 
                COALESCE((SELECT c.price_per_unit FROM catalogue c WHERE c.item_id = rb.item_id AND c.supplier_id = 'SUP-04'), 
                         (SELECT c.price_per_unit FROM catalogue c WHERE c.item_id = rb.item_id ORDER BY c.price_per_unit ASC LIMIT 1))
        END AS simulated_fast_unit_cost
    FROM recipe_bom rb
    JOIN items i ON rb.item_id = i.item_id
)
SELECT 
    item_id,
    item_name,
    unit,
    qty_per_tiffin,
    procure_mode,
    unit_cost,
    ROUND(qty_per_tiffin * unit_cost, 2) AS cost_per_tiffin,
    ROUND(qty_per_tiffin * simulated_fast_unit_cost, 2) AS simulated_cost_per_tiffin,
    CASE WHEN item_id IN ('CONT-750', 'BAG-CARRY') THEN 'packaging' ELSE 'ingredient' END AS item_category
FROM latest_costs
ORDER BY cost_per_tiffin DESC;

