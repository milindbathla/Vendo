-- ============================================================================
-- Cost Trends: Item Unit Price Trajectories & Volatility
-- Parameters: :cutoff_date
-- ============================================================================
WITH price_events AS (
    -- Combine price history observations
    SELECT 
        sph.item_id,
        sph.supplier_id,
        sph.effective_date AS obs_date,
        sph.price_per_unit
    FROM supplier_price_history sph
    WHERE sph.effective_date >= :cutoff_date

    UNION ALL

    -- Purchase history actuals
    SELECT 
        ph.item_id,
        ph.supplier_id,
        ph.purchase_date AS obs_date,
        ph.unit_price AS price_per_unit
    FROM purchase_history ph
    WHERE ph.purchase_date >= :cutoff_date
),
ranked_prices AS (
    SELECT 
        item_id,
        supplier_id,
        obs_date,
        price_per_unit,
        ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY obs_date ASC) AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY obs_date DESC) AS rn_last
    FROM price_events
),
item_stats AS (
    SELECT 
        item_id,
        COUNT(*) AS observation_count,
        ROUND(MIN(price_per_unit), 2) AS min_price,
        ROUND(MAX(price_per_unit), 2) AS max_price,
        ROUND(AVG(price_per_unit), 2) AS avg_price
    FROM price_events
    GROUP BY item_id
),
first_last AS (
    SELECT 
        f.item_id,
        f.price_per_unit AS first_price,
        f.obs_date AS first_date,
        l.price_per_unit AS last_price,
        l.obs_date AS last_date
    FROM (SELECT item_id, price_per_unit, obs_date FROM ranked_prices WHERE rn_first = 1) f
    JOIN (SELECT item_id, price_per_unit, obs_date FROM ranked_prices WHERE rn_last = 1) l
      ON f.item_id = l.item_id
)
SELECT 
    i.item_id,
    i.name AS item_name,
    i.unit,
    i.procure_mode,
    COALESCE(rb.qty_per_tiffin, 0.0) AS bom_qty,
    fl.first_date,
    fl.first_price,
    fl.last_date,
    fl.last_price,
    ROUND(fl.last_price - fl.first_price, 2) AS absolute_change,
    ROUND(CASE WHEN fl.first_price > 0 THEN ((fl.last_price - fl.first_price) / fl.first_price) * 100.0 ELSE 0.0 END, 2) AS pct_change,
    s.min_price,
    s.max_price,
    s.avg_price,
    s.observation_count,
    ROUND(COALESCE(rb.qty_per_tiffin, 0.0) * (fl.last_price - fl.first_price), 4) AS margin_impact_per_tiffin,
    CASE WHEN ((fl.last_price - fl.first_price) / fl.first_price) * 100.0 > 5.0 THEN 1 ELSE 0 END AS is_rising
FROM items i
JOIN first_last fl ON i.item_id = fl.item_id
JOIN item_stats s ON i.item_id = s.item_id
LEFT JOIN recipe_bom rb ON i.item_id = rb.item_id
ORDER BY margin_impact_per_tiffin DESC, pct_change DESC;

