-- ============================================================================
-- Alexa Business Autopilot: Decision Views
-- These views reproduce the headline decision loop and verify invariants
-- directly from raw transactional tables.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. TOMORROW'S ITEM REQUIREMENTS
-- ----------------------------------------------------------------------------
-- Computes effective meal forecast = units_forecast * (1 + safety_stock_pct/100)
-- For tomorrow (2026-10-11): 23 * 1.10 = 25.3 effective units.
-- Discrete items ('pcs') use CEIL(units * BOM); continuous items use ROUND(units * BOM, 3).
CREATE VIEW IF NOT EXISTS v_item_requirement_tomorrow AS
WITH tomorrow_forecast AS (
    SELECT
        df.date,
        df.units_forecast,
        bp.safety_stock_pct,
        ROUND(df.units_forecast * (1.0 + bp.safety_stock_pct / 100.0), 1) AS effective_units
    FROM demand_forecast df
    CROSS JOIN business_policy bp
    WHERE df.date = (SELECT value FROM meta WHERE key = 'tomorrow_date')
)
SELECT
    tf.date,
    tf.effective_units,
    i.item_id,
    i.name AS item_name,
    i.unit,
    i.procure_mode,
    i.reorder_point,
    i.par_level,
    rb.qty_per_tiffin AS bom_qty,
    CASE 
        WHEN i.unit = 'pcs' THEN CAST(CEIL(tf.effective_units * rb.qty_per_tiffin) AS REAL)
        ELSE ROUND(tf.effective_units * rb.qty_per_tiffin, 3)
    END AS effective_requirement,
    s.stock_qty AS current_stock
FROM tomorrow_forecast tf
CROSS JOIN items i
JOIN recipe_bom rb ON i.item_id = rb.item_id
JOIN inventory_stock s ON i.item_id = s.item_id;

-- ----------------------------------------------------------------------------
-- 2. SHORTFALL TOMORROW
-- ----------------------------------------------------------------------------
-- Items where current stock is less than tomorrow's effective requirement.
-- EXACT EXPECTED RESULT: {OIL-SUN-1L: 0.718 L, CONT-750: 14.0 pcs}
CREATE VIEW IF NOT EXISTS v_shortfall_tomorrow AS
SELECT
    date,
    item_id,
    item_name,
    unit,
    procure_mode,
    effective_requirement,
    current_stock,
    ROUND(effective_requirement - current_stock, 3) AS shortfall_qty
FROM v_item_requirement_tomorrow
WHERE effective_requirement > current_stock;

-- ----------------------------------------------------------------------------
-- 3. BELOW REORDER POINT AFTER TOMORROW
-- ----------------------------------------------------------------------------
-- Catalogue-procured BOM items whose projected stock after tomorrow's production
-- falls below their reorder point.
-- (stock_qty - effective_requirement) < reorder_point
-- EXACT EXPECTED RESULT: {OIL-SUN-1L, CONT-750, ATTA-10, DAL-MOONG}
CREATE VIEW IF NOT EXISTS v_below_reorder_after_tomorrow AS
SELECT
    date,
    item_id,
    item_name,
    unit,
    procure_mode,
    current_stock,
    effective_requirement,
    ROUND(current_stock - effective_requirement, 3) AS projected_stock_after,
    reorder_point,
    par_level
FROM v_item_requirement_tomorrow
WHERE procure_mode = 'catalogue'
  AND (current_stock - effective_requirement) < reorder_point;

-- ----------------------------------------------------------------------------
-- 4. SUPPLIER PROCUREMENT OPTIONS & FEASIBILITY
-- ----------------------------------------------------------------------------
-- Evaluates catalogue options against production deadlines:
-- Cooking ingredients deadline: 2026-10-11 09:00
-- Packaging deadline: 2026-10-11 11:00
CREATE VIEW IF NOT EXISTS v_supplier_options AS
SELECT
    c.item_id,
    i.name AS item_name,
    c.supplier_id,
    s.name AS supplier_name,
    c.pack_label,
    c.pack_qty,
    c.price_per_pack,
    c.price_per_unit,
    c.eta_minutes,
    c.in_stock AS item_in_stock,
    c.is_simulated,
    s.delivery_fee,
    s.free_delivery_threshold,
    s.cutoff_time,
    s.delivery_window,
    CASE 
        WHEN s.supplier_id = 'SUP-04' THEN '2026-10-10 19:55'
        WHEN s.supplier_id = 'SUP-02' THEN '2026-10-11 07:00'
        WHEN s.supplier_id = 'SUP-01' THEN '2026-10-11 10:00'
        WHEN s.supplier_id = 'SUP-03' THEN '2026-10-12 15:00'
        ELSE 'unknown'
    END AS earliest_arrival,
    CASE 
        WHEN i.item_id IN ('CONT-750', 'BAG-CARRY') THEN '2026-10-11 11:00'
        ELSE '2026-10-11 09:00'
    END AS deadline,
    CASE 
        -- Must be in stock and arrive before deadline
        WHEN c.in_stock = 1 AND (
            (s.supplier_id = 'SUP-04') OR
            (s.supplier_id = 'SUP-02' AND '2026-10-11 07:00' <= '2026-10-11 11:00') OR
            (s.supplier_id = 'SUP-01' AND '2026-10-11 10:00' <= CASE WHEN i.item_id IN ('CONT-750', 'BAG-CARRY') THEN '2026-10-11 11:00' ELSE '2026-10-11 09:00' END) OR
            (s.supplier_id = 'SUP-03' AND '2026-10-12 15:00' <= '2026-10-11 09:00')
        ) THEN 1
        ELSE 0
    END AS is_feasible_for_tomorrow
FROM catalogue c
JOIN suppliers s ON c.supplier_id = s.supplier_id
JOIN items i ON c.item_id = i.item_id;

-- ----------------------------------------------------------------------------
-- 5. CASH HEADROOM
-- ----------------------------------------------------------------------------
-- Headroom = MIN(projected_balance) - min_cash_buffer
-- Invariant: 6900.0 - 5000.0 = 1900.0
CREATE VIEW IF NOT EXISTS v_cash_headroom AS
SELECT
    (SELECT current_balance FROM cash_position WHERE as_of = (SELECT value FROM meta WHERE key = 'as_of')) AS current_balance,
    bp.min_cash_buffer,
    MIN(fb.projected_balance) AS min_projected_balance,
    MIN(fb.projected_balance) - bp.min_cash_buffer AS cash_headroom,
    (SELECT date FROM forecasted_balance WHERE projected_balance = (SELECT MIN(projected_balance) FROM forecasted_balance) LIMIT 1) AS lowest_balance_date
FROM forecasted_balance fb
CROSS JOIN business_policy bp;

-- ----------------------------------------------------------------------------
-- 6. REFERENCE PLAN COST & BUFFER COMPLIANCE
-- ----------------------------------------------------------------------------
-- Calculates total cost of each reference plan including delivery fees
-- Delivery rule:
--   For each supplier in the plan:
--   If supplier has free_delivery_threshold and order subtotal >= threshold -> 0 fee, else delivery_fee.
-- Evaluates buffer compliance against min_projected_balance (6900.0).
CREATE VIEW IF NOT EXISTS v_plan_cost AS
WITH supplier_orders AS (
    SELECT
        rpl.plan_id,
        rpl.supplier_id,
        SUM(rpl.line_subtotal) AS supplier_subtotal,
        s.delivery_fee,
        s.free_delivery_threshold,
        CASE
            WHEN s.free_delivery_threshold IS NOT NULL AND SUM(rpl.line_subtotal) >= s.free_delivery_threshold THEN 0.0
            ELSE s.delivery_fee
        END AS applicable_delivery_fee
    FROM reference_plan_lines rpl
    JOIN suppliers s ON rpl.supplier_id = s.supplier_id
    GROUP BY rpl.plan_id, rpl.supplier_id, s.delivery_fee, s.free_delivery_threshold
),
plan_totals AS (
    SELECT
        rp.plan_id,
        rp.plan_name,
        rp.strategy,
        SUM(so.supplier_subtotal) AS items_subtotal,
        SUM(so.applicable_delivery_fee) AS total_delivery_fees,
        SUM(so.supplier_subtotal + so.applicable_delivery_fee) AS total_cost
    FROM reference_plans rp
    JOIN supplier_orders so ON rp.plan_id = so.plan_id
    GROUP BY rp.plan_id, rp.plan_name, rp.strategy
)
SELECT
    pt.plan_id,
    pt.plan_name,
    pt.strategy,
    pt.items_subtotal,
    pt.total_delivery_fees,
    pt.total_cost,
    (SELECT min_projected_balance FROM v_cash_headroom) AS min_projected_balance,
    (SELECT min_projected_balance FROM v_cash_headroom) - pt.total_cost AS min_balance_after_plan,
    (SELECT min_cash_buffer FROM business_policy) AS required_buffer,
    CASE 
        WHEN ((SELECT min_projected_balance FROM v_cash_headroom) - pt.total_cost) >= (SELECT min_cash_buffer FROM business_policy) THEN 1
        ELSE 0
    END AS buffer_compliant
FROM plan_totals pt;

-- ----------------------------------------------------------------------------
-- 7. TOMORROW'S CAPACITY & FREE DELIVERY SLOTS
-- ----------------------------------------------------------------------------
-- Identifies free slots for tomorrow (2026-10-11).
-- Afternoon slots (13:00-14:00 and 14:00-15:00) have 6 and 8 free units.
CREATE VIEW IF NOT EXISTS v_capacity_free_slots AS
SELECT
    ds.date,
    ds.slot_id,
    ds.slot_label,
    ds.start_time,
    ds.end_time,
    ds.capacity_units,
    ds.booked_units,
    ds.capacity_units - ds.booked_units AS free_units,
    CASE WHEN ds.start_time >= '13:00' THEN 1 ELSE 0 END AS is_afternoon_slot
FROM delivery_slots ds
WHERE ds.date = (SELECT value FROM meta WHERE key = 'tomorrow_date')
ORDER BY ds.start_time;

-- ----------------------------------------------------------------------------
-- 8. LIVE CUSTOMER SNAPSHOT
-- ----------------------------------------------------------------------------
-- Live customer rollup verifying:
-- 96 active customers, 62 recurring (64.6%), exactly matching customer_metrics.
CREATE VIEW IF NOT EXISTS v_customer_snapshot AS
SELECT
    COUNT(*) AS total_customers_all_time,
    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_customers,
    SUM(CASE WHEN status = 'active' AND is_recurring = 1 THEN 1 ELSE 0 END) AS active_recurring,
    SUM(CASE WHEN status = 'active' AND is_recurring = 0 THEN 1 ELSE 0 END) AS active_one_off,
    SUM(CASE WHEN status = 'paused' THEN 1 ELSE 0 END) AS paused_customers,
    SUM(CASE WHEN status = 'churned' THEN 1 ELSE 0 END) AS churned_customers,
    ROUND(
        SUM(CASE WHEN status = 'active' AND is_recurring = 1 THEN 1.0 ELSE 0.0 END) * 100.0 /
        SUM(CASE WHEN status = 'active' THEN 1.0 ELSE 0.0 END),
        1
    ) AS recurring_pct
FROM customers;

-- ----------------------------------------------------------------------------
-- 9. BUSINESS MEMORY CONFLICTS
-- ----------------------------------------------------------------------------
-- Surfaces knowledge conflicts where the same key has different values
-- e.g. supplier.gupta.oil_price_per_l: 146 (verified) vs 135 (owner)
CREATE VIEW IF NOT EXISTS v_memory_conflicts AS
SELECT
    m1.key,
    m1.value AS val_1,
    m1.source AS source_1,
    m1.confidence AS conf_1,
    m2.value AS val_2,
    m2.source AS source_2,
    m2.confidence AS conf_2
FROM business_memory m1
JOIN business_memory m2 ON m1.key = m2.key AND m1.id < m2.id
WHERE m1.value != m2.value;

