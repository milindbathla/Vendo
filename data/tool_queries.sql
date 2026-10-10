-- ============================================================================
-- Alexa Business Autopilot: Named Parameterised Tool Queries
-- Designed for the Orchestrator & Business MCP Server mock backend.
-- Each query outputs standard envelope attributes: (ok, confidence, source, warnings)
-- Source enum: 'db' | 'estimate' | 'simulated'. Rows from SUP-04 are marked 'simulated'.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- TOOL 1: get_inventory
-- Purpose: Inspect current on-hand stock, reorder levels, and last restock metadata.
-- Parameters: None (returns entire stock catalog)
-- ----------------------------------------------------------------------------
-- :name get_inventory
SELECT
    1 AS ok,
    i.item_id,
    i.name AS item_name,
    i.unit,
    i.procure_mode,
    s.stock_qty,
    i.reorder_point,
    i.par_level,
    s.last_restocked_date,
    s.last_restocked_qty,
    s.refresh_forecast_date,
    s.refresh_forecast_qty,
    s.as_of,
    1.0 AS confidence,
    'db' AS source,
    CASE 
        WHEN s.stock_qty < i.reorder_point THEN 'Current stock is below reorder point'
        WHEN s.stock_qty = 0 THEN 'Item is completely out of stock'
        ELSE NULL 
    END AS warnings
FROM items i
JOIN inventory_stock s ON i.item_id = s.item_id
ORDER BY (s.stock_qty < i.reorder_point) DESC, i.item_id;


-- ----------------------------------------------------------------------------
-- TOOL 2: get_cash_position
-- Purpose: Retrieve current bank/cash balance, policy buffer, and forecast headroom.
-- Parameters: None
-- ----------------------------------------------------------------------------
-- :name get_cash_position
SELECT
    1 AS ok,
    cp.as_of,
    cp.current_balance,
    cp.min_cash_buffer,
    vh.min_projected_balance,
    vh.cash_headroom,
    vh.lowest_balance_date,
    1.0 AS confidence,
    'db' AS source,
    CASE 
        WHEN vh.cash_headroom < 0 THEN 'Projected balance breaches mandatory minimum cash buffer'
        WHEN vh.cash_headroom < 2000 THEN 'Tight liquidity headroom over the next 7-14 days'
        ELSE NULL
    END AS warnings
FROM cash_position cp
CROSS JOIN v_cash_headroom vh
WHERE cp.as_of = (SELECT value FROM meta WHERE key = 'as_of');


-- ----------------------------------------------------------------------------
-- TOOL 3: get_upcoming_payments
-- Purpose: Query scheduled liabilities, salary dues, supplier dues and utilities.
-- Parameters: None (or optional :status, defaults to pending)
-- ----------------------------------------------------------------------------
-- :name get_upcoming_payments
SELECT
    1 AS ok,
    payment_id,
    payee,
    category,
    amount,
    due_date,
    status,
    0.95 AS confidence,
    'db' AS source,
    CASE 
        WHEN due_date <= '2026-10-12' THEN 'Payment due within 48 hours'
        ELSE NULL 
    END AS warnings
FROM upcoming_payments
WHERE status = 'pending'
ORDER BY due_date ASC;


-- ----------------------------------------------------------------------------
-- TOOL 4: forecast_demand
-- Purpose: Forecast meal demand for a target date with confidence bands and festival notes.
-- Parameters: :date (e.g. '2026-10-11')
-- ----------------------------------------------------------------------------
-- :name forecast_demand
SELECT
    1 AS ok,
    df.date,
    dd.day_of_week,
    dd.festival,
    dd.local_event,
    dd.weather_note,
    dd.subscription_pauses,
    df.units_forecast,
    df.lower,
    df.upper,
    bp.safety_stock_pct,
    ROUND(df.units_forecast * (1.0 + bp.safety_stock_pct / 100.0), 1) AS effective_meal_target,
    df.confidence,
    df.method,
    'estimate' AS source,
    CASE 
        WHEN df.confidence < 0.60 THEN 'Low forecast confidence due to festival or holiday shift; wide variance expected'
        ELSE NULL 
    END AS warnings
FROM demand_forecast df
JOIN demand_drivers dd ON df.date = dd.date
CROSS JOIN business_policy bp
WHERE df.date = COALESCE(:date, (SELECT value FROM meta WHERE key = 'tomorrow_date'));


-- ----------------------------------------------------------------------------
-- TOOL 5: assess_restock_need
-- Purpose: Compare on-hand inventory vs tomorrow's production requirement and reorder triggers.
-- Parameters: None
-- ----------------------------------------------------------------------------
-- :name assess_restock_need
SELECT
    1 AS ok,
    req.item_id,
    req.item_name,
    req.unit,
    req.procure_mode,
    req.current_stock,
    req.effective_requirement,
    COALESCE(st.shortfall_qty, 0.0) AS immediate_shortfall,
    CASE WHEN br.item_id IS NOT NULL THEN 1 ELSE 0 END AS will_breach_reorder_point,
    req.reorder_point,
    req.par_level,
    0.95 AS confidence,
    'db' AS source,
    CASE 
        WHEN COALESCE(st.shortfall_qty, 0.0) > 0 THEN 'CRITICAL: Immediate shortfall for tomorrow production!'
        WHEN br.item_id IS NOT NULL THEN 'Warning: Will breach reorder threshold after tomorrow production'
        ELSE 'Stock sufficient'
    END AS warnings
FROM v_item_requirement_tomorrow req
LEFT JOIN v_shortfall_tomorrow st ON req.item_id = st.item_id
LEFT JOIN v_below_reorder_after_tomorrow br ON req.item_id = br.item_id
ORDER BY immediate_shortfall DESC, will_breach_reorder_point DESC;


-- ----------------------------------------------------------------------------
-- TOOL 6: find_procurement_options
-- Purpose: Search catalogue for replacement/restock options across suppliers.
-- Parameters: :item_id (e.g. 'OIL-SUN-1L' or NULL for all shortfalls)
-- ----------------------------------------------------------------------------
-- :name find_procurement_options
SELECT
    1 AS ok,
    vso.item_id,
    vso.item_name,
    vso.supplier_id,
    vso.supplier_name,
    vso.pack_label,
    vso.pack_qty,
    vso.price_per_pack,
    vso.price_per_unit,
    vso.eta_minutes,
    vso.earliest_arrival,
    vso.deadline,
    vso.is_feasible_for_tomorrow,
    vso.item_in_stock,
    vso.delivery_fee,
    vso.free_delivery_threshold,
    0.95 AS confidence,
    CASE WHEN vso.is_simulated = 1 THEN 'simulated' ELSE 'db' END AS source,
    CASE 
        WHEN vso.item_in_stock = 0 THEN 'Supplier currently out of stock'
        WHEN vso.is_feasible_for_tomorrow = 0 THEN 'Supplier delivery arrives AFTER kitchen production deadline'
        ELSE 'Feasible for tomorrow delivery'
    END AS warnings
FROM v_supplier_options vso
WHERE (:item_id IS NULL OR vso.item_id = :item_id)
ORDER BY vso.item_id, vso.is_feasible_for_tomorrow DESC, vso.price_per_unit ASC;


-- ----------------------------------------------------------------------------
-- TOOL 7: analyze_purchase_affordability
-- Purpose: Evaluate whether a proposed procurement plan or cart amount breaches liquidity.
-- Parameters: :plan_id (e.g. 'REF-RECOMMENDED') OR :amount (e.g. 1675.0)
-- ----------------------------------------------------------------------------
-- :name analyze_purchase_affordability
WITH input_cost AS (
    SELECT 
        COALESCE(
            (SELECT total_cost FROM v_plan_cost WHERE plan_id = :plan_id),
            CAST(:amount AS REAL),
            0.0
        ) AS proposed_cost,
        COALESCE(:plan_id, 'CUSTOM-CART') AS evaluated_plan
)
SELECT
    1 AS ok,
    ic.evaluated_plan AS plan_ref,
    ic.proposed_cost,
    vh.current_balance,
    vh.min_projected_balance,
    vh.min_cash_buffer,
    (vh.min_projected_balance - ic.proposed_cost) AS min_balance_after_purchase,
    vh.cash_headroom,
    CASE 
        WHEN (vh.min_projected_balance - ic.proposed_cost) >= vh.min_cash_buffer THEN 1
        ELSE 0
    END AS is_affordable,
    0.95 AS confidence,
    'db' AS source,
    CASE 
        WHEN (vh.min_projected_balance - ic.proposed_cost) < vh.min_cash_buffer 
        THEN 'REJECT: Purchase reduces projected cash below the mandatory buffer of ₹' || CAST(ROUND(vh.min_cash_buffer) AS INT)
        ELSE 'APPROVED: Purchase maintains required minimum cash buffer'
    END AS warnings
FROM input_cost ic
CROSS JOIN v_cash_headroom vh;


-- ----------------------------------------------------------------------------
-- TOOL 8: get_capacity_status
-- Purpose: Check meal capacity, slot bookings, and unutilized delivery capacity.
-- Parameters: :date (e.g. '2026-10-11')
-- ----------------------------------------------------------------------------
-- :name get_capacity_status
SELECT
    1 AS ok,
    ds.date,
    ds.slot_id,
    ds.slot_label,
    ds.start_time,
    ds.end_time,
    ds.capacity_units,
    ds.booked_units,
    (ds.capacity_units - ds.booked_units) AS free_units,
    CASE WHEN ds.start_time >= '13:00' THEN 1 ELSE 0 END AS is_afternoon_slot,
    c.max_meals AS kitchen_daily_max_meals,
    (SELECT SUM(booked_units) FROM delivery_slots WHERE date = ds.date) AS total_daily_booked,
    1.0 AS confidence,
    'db' AS source,
    CASE 
        WHEN (ds.capacity_units - ds.booked_units) >= 6 THEN 'High unused slot capacity available for customer matching'
        ELSE NULL
    END AS warnings
FROM delivery_slots ds
JOIN capacity c ON ds.date = c.date
WHERE ds.date = COALESCE(:date, (SELECT value FROM meta WHERE key = 'tomorrow_date'))
ORDER BY ds.start_time;


-- ----------------------------------------------------------------------------
-- TOOL 9: identify_growth_opportunities
-- Purpose: Match unbooked delivery slots with local high-potential customer segments.
-- Parameters: :date (e.g. '2026-10-11')
-- ----------------------------------------------------------------------------
-- :name identify_growth_opportunities
WITH free_capacity AS (
    SELECT 
        SUM(capacity_units - booked_units) AS total_afternoon_free_units
    FROM delivery_slots
    WHERE date = COALESCE(:date, (SELECT value FROM meta WHERE key = 'tomorrow_date'))
      AND start_time >= '13:00'
)
SELECT
    1 AS ok,
    pcs.locality,
    pcs.segment,
    pcs.est_households,
    pcs.budget_per_meal,
    pcs.meal_time_pref,
    pcs.interest_score,
    pcs.distance_km,
    pcs.competitor_density,
    fc.total_afternoon_free_units,
    'Offer afternoon student lunch special in ' || pcs.locality || ' (' || CAST(fc.total_afternoon_free_units AS TEXT) || ' slots available)' AS recommendation,
    0.85 AS confidence,
    'estimate' AS source,
    'Targeting high-density coaching students in Kakadeo yields highest conversion for 13:00-15:00 delivery' AS warnings
FROM potential_customer_segments pcs
CROSS JOIN free_capacity fc
WHERE pcs.meal_time_pref IN ('afternoon_lunch', 'both_lunch_dinner')
ORDER BY pcs.interest_score DESC, pcs.distance_km ASC
LIMIT 5;


-- ----------------------------------------------------------------------------
-- TOOL 10: reconcile_document
-- Purpose: Extract uploaded vendor document, compare against PO and receipt records, flag discrepancies.
-- Parameters: :doc_id (e.g. 'INV-PKG-0245')
-- ----------------------------------------------------------------------------
-- :name reconcile_document
SELECT
    1 AS ok,
    bd.doc_id,
    bd.doc_type,
    bd.supplier_id,
    s.name AS supplier_name,
    bd.doc_date,
    bd.file_ref,
    bd.extraction_confidence,
    dl.item_id,
    dl.billed_qty,
    pol.ordered_qty,
    dl.unit_price AS billed_unit_price,
    pol.unit_price AS po_unit_price,
    dl.gst_rate_pct AS billed_gst_pct,
    pol.tax_rate_pct AS agreed_gst_pct,
    dl.total_line_amount AS billed_line_total,
    pol.line_total AS expected_line_total,
    ROUND(dl.total_line_amount - pol.line_total, 2) AS line_discrepancy_amount,
    COALESCE(gt.discrepancy_type, 'none') AS discrepancy_flag,
    COALESCE(gt.description, 'Clean match against purchase order and goods receipt') AS reconciliation_finding,
    bd.extraction_confidence AS confidence,
    'db' AS source,
    CASE 
        WHEN gt.truth_id IS NOT NULL THEN 'DISCREPANCY DETECTED: ' || gt.description
        ELSE 'Document matches PO and goods received cleanly'
    END AS warnings
FROM business_documents bd
JOIN suppliers s ON bd.supplier_id = s.supplier_id
JOIN document_lines dl ON bd.doc_id = dl.doc_id
LEFT JOIN purchase_order_lines pol ON bd.po_id = pol.po_id AND dl.item_id = pol.item_id
LEFT JOIN doc_ground_truth gt ON bd.doc_id = gt.doc_id
WHERE bd.doc_id = :doc_id;


-- ----------------------------------------------------------------------------
-- TOOL 11: get_business_memory
-- Purpose: Retrieve memory facts for a topic, highlighting conflicts between verified records and owner speech.
-- Parameters: :key (e.g. 'supplier.gupta.oil_price_per_l')
-- ----------------------------------------------------------------------------
-- :name get_business_memory
SELECT
    1 AS ok,
    bm.id,
    bm.key,
    bm.value,
    bm.source AS memory_source,
    bm.timestamp,
    bm.confidence,
    'db' AS source,
    CASE 
        WHEN (SELECT COUNT(DISTINCT value) FROM business_memory WHERE key = bm.key) > 1 
        THEN 'CONFLICT DETECTED: Owner statement differs from verified invoice record'
        ELSE 'Consistent knowledge record'
    END AS warnings
FROM business_memory bm
WHERE bm.key = :key
ORDER BY bm.confidence DESC, bm.timestamp DESC;


-- ----------------------------------------------------------------------------
-- TOOL 12: analyze_business_performance
-- Purpose: Summarize unit volumes, revenue, margin and recurring mix over a given period.
-- Parameters: :period ('last_30_days', 'last_90_days', 'mtd')
-- ----------------------------------------------------------------------------
-- :name analyze_business_performance
SELECT
    1 AS ok,
    'last_90_days' AS period,
    SUM(units_sold) AS total_units_sold,
    ROUND(SUM(revenue), 2) AS total_revenue,
    ROUND(AVG(revenue), 2) AS avg_daily_revenue,
    ROUND(SUM(cogs), 2) AS total_cogs,
    ROUND(SUM(opex), 2) AS total_opex,
    ROUND(SUM(net_profit), 2) AS total_net_profit,
    ROUND((SUM(net_profit) / SUM(revenue)) * 100.0, 1) AS net_profit_margin_pct,
    ROUND((SUM(revenue - cogs) / SUM(revenue)) * 100.0, 1) AS gross_margin_pct,
    0.95 AS confidence,
    'db' AS source,
    NULL AS warnings
FROM daily_metrics
WHERE date >= (SELECT date(value, '-90 days') FROM meta WHERE key = 'frozen_date');

