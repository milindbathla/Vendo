-- ============================================================================
-- Alexa Business Autopilot: Invariant Verification Queries (A1..A16)
-- Each query returns: (id, expected, actual, status)
-- build_db.py executes this script and asserts that all status values are 'PASS'.
-- ============================================================================

-- A1: Tomorrow confirmed units = 20; slot split 6/8/4/2; exactly 2 afternoon slots with free capacity (6 and 8).
SELECT 
    'A1' AS id,
    'confirmed=20; slots=6,8,4,2; afternoon_free=6,8' AS expected,
    'confirmed=' || (SELECT COUNT(*) FROM orders WHERE date = '2026-10-11' AND status = 'confirmed') ||
    '; slots=' || (SELECT GROUP_CONCAT(booked_units, ',') FROM (SELECT booked_units FROM delivery_slots WHERE date = '2026-10-11' ORDER BY start_time)) ||
    '; afternoon_free=' || (SELECT GROUP_CONCAT(free_units, ',') FROM (SELECT free_units FROM v_capacity_free_slots WHERE is_afternoon_slot = 1 ORDER BY start_time)) AS actual,
    CASE WHEN 
        (SELECT COUNT(*) FROM orders WHERE date = '2026-10-11' AND status = 'confirmed') = 20 AND
        (SELECT GROUP_CONCAT(booked_units, ',') FROM (SELECT booked_units FROM delivery_slots WHERE date = '2026-10-11' ORDER BY start_time)) = '6,8,4,2' AND
        (SELECT GROUP_CONCAT(free_units, ',') FROM (SELECT free_units FROM v_capacity_free_slots WHERE is_afternoon_slot = 1 ORDER BY start_time)) = '6,8'
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A2: Effective forecast units tomorrow = 25.3.
SELECT
    'A2' AS id,
    '25.3' AS expected,
    CAST((SELECT effective_units FROM v_item_requirement_tomorrow LIMIT 1) AS TEXT) AS actual,
    CASE WHEN (SELECT effective_units FROM v_item_requirement_tomorrow LIMIT 1) = 25.3
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A3: Shortfall vs tomorrow's requirement is EXACTLY {OIL-SUN-1L: 0.718 L, CONT-750: 14 pcs}; every other BOM item has stock >= requirement.
SELECT
    'A3' AS id,
    'CONT-750: 14.0, OIL-SUN-1L: 0.718' AS expected,
    (SELECT GROUP_CONCAT(item_id || ': ' || shortfall_qty, ', ') FROM (SELECT item_id, shortfall_qty FROM v_shortfall_tomorrow ORDER BY item_id)) AS actual,
    CASE WHEN (SELECT GROUP_CONCAT(item_id || ': ' || shortfall_qty, ', ') FROM (SELECT item_id, shortfall_qty FROM v_shortfall_tomorrow ORDER BY item_id)) = 'CONT-750: 14.0, OIL-SUN-1L: 0.718'
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A4: Catalogue-procured BOM items with (stock - tomorrow requirement) < reorder_point = EXACTLY {OIL, CONT, ATTA, DAL}.
SELECT
    'A4' AS id,
    'ATTA-10, CONT-750, DAL-MOONG, OIL-SUN-1L' AS expected,
    (SELECT GROUP_CONCAT(item_id, ', ') FROM (SELECT item_id FROM v_below_reorder_after_tomorrow ORDER BY item_id)) AS actual,
    CASE WHEN (SELECT GROUP_CONCAT(item_id, ', ') FROM (SELECT item_id FROM v_below_reorder_after_tomorrow ORDER BY item_id)) = 'ATTA-10, CONT-750, DAL-MOONG, OIL-SUN-1L'
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A5: No regular supplier can deliver oil before 2026-10-11 09:00; only SUP-04 can (ETA <= 45 min).
SELECT
    'A5' AS id,
    'SUP-01: 0, SUP-03: 0, SUP-04: 1' AS expected,
    (SELECT GROUP_CONCAT(supplier_id || ': ' || is_feasible_for_tomorrow, ', ') FROM (SELECT supplier_id, is_feasible_for_tomorrow FROM v_supplier_options WHERE item_id = 'OIL-SUN-1L' ORDER BY supplier_id)) AS actual,
    CASE WHEN (SELECT GROUP_CONCAT(supplier_id || ': ' || is_feasible_for_tomorrow, ', ') FROM (SELECT supplier_id, is_feasible_for_tomorrow FROM v_supplier_options WHERE item_id = 'OIL-SUN-1L' ORDER BY supplier_id)) = 'SUP-01: 0, SUP-03: 0, SUP-04: 1'
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A6: SUP-02 can deliver containers by 07:00 tomorrow when ordered before the 20:00 cutoff (as_of 19:10 is before it).
SELECT
    'A6' AS id,
    'cutoff=20:00; as_of=19:10; arrival=2026-10-11 07:00; feasible=1' AS expected,
    'cutoff=' || (SELECT cutoff_time FROM suppliers WHERE supplier_id = 'SUP-02') ||
    '; as_of=' || substr((SELECT value FROM meta WHERE key = 'as_of'), 12, 5) ||
    '; arrival=' || (SELECT earliest_arrival FROM v_supplier_options WHERE supplier_id = 'SUP-02' AND item_id = 'CONT-750') ||
    '; feasible=' || (SELECT is_feasible_for_tomorrow FROM v_supplier_options WHERE supplier_id = 'SUP-02' AND item_id = 'CONT-750') AS actual,
    CASE WHEN 
        (SELECT cutoff_time FROM suppliers WHERE supplier_id = 'SUP-02') = '20:00' AND
        substr((SELECT value FROM meta WHERE key = 'as_of'), 12, 5) <= '20:00' AND
        (SELECT earliest_arrival FROM v_supplier_options WHERE supplier_id = 'SUP-02' AND item_id = 'CONT-750') = '2026-10-11 07:00' AND
        (SELECT is_feasible_for_tomorrow FROM v_supplier_options WHERE supplier_id = 'SUP-02' AND item_id = 'CONT-750') = 1
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A7: cost(REF-ALL-FAST)=2217; cost(REF-RECOMMENDED)=1675; cost(REF-OIL-CONT-FAST)=2077, recomputed from catalogue and delivery rules.
SELECT
    'A7' AS id,
    'REF-ALL-FAST=2217; REF-OIL-CONT-FAST=2077; REF-RECOMMENDED=1675' AS expected,
    (SELECT GROUP_CONCAT(plan_id || '=' || CAST(ROUND(total_cost) AS INT), '; ') FROM (SELECT plan_id, total_cost FROM v_plan_cost ORDER BY plan_id)) AS actual,
    CASE WHEN (SELECT GROUP_CONCAT(plan_id || '=' || CAST(ROUND(total_cost) AS INT), '; ') FROM (SELECT plan_id, total_cost FROM v_plan_cost ORDER BY plan_id)) = 'REF-ALL-FAST=2217; REF-OIL-CONT-FAST=2077; REF-RECOMMENDED=1675'
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A8: Cash headroom = MIN(projected_balance) - min_cash_buffer = 6900 - 5000 = 1900.
SELECT
    'A8' AS id,
    '1900.0' AS expected,
    CAST((SELECT cash_headroom FROM v_cash_headroom) AS TEXT) AS actual,
    CASE WHEN (SELECT cash_headroom FROM v_cash_headroom) = 1900.0
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A9: Min balance after plan: RECOMMENDED = 5225 (>= buffer); ALL-FAST = 4683 (< buffer); OIL-CONT-FAST = 4823 (< buffer).
SELECT
    'A9' AS id,
    'REF-ALL-FAST: 4683 (buffer_ok=0); REF-OIL-CONT-FAST: 4823 (buffer_ok=0); REF-RECOMMENDED: 5225 (buffer_ok=1)' AS expected,
    (SELECT GROUP_CONCAT(plan_id || ': ' || CAST(ROUND(min_balance_after_plan) AS INT) || ' (buffer_ok=' || buffer_compliant || ')', '; ') FROM (SELECT plan_id, min_balance_after_plan, buffer_compliant FROM v_plan_cost ORDER BY plan_id)) AS actual,
    CASE WHEN (SELECT GROUP_CONCAT(plan_id || ': ' || CAST(ROUND(min_balance_after_plan) AS INT) || ' (buffer_ok=' || buffer_compliant || ')', '; ') FROM (SELECT plan_id, min_balance_after_plan, buffer_compliant FROM v_plan_cost ORDER BY plan_id)) = 'REF-ALL-FAST: 4683 (buffer_ok=0); REF-OIL-CONT-FAST: 4823 (buffer_ok=0); REF-RECOMMENDED: 5225 (buffer_ok=1)'
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A10: upcoming_payments Sharma dues = open balance in supplier_business_records (4200.0).
SELECT
    'A10' AS id,
    'due=4200.0; ledger_open=4200.0' AS expected,
    'due=' || (SELECT amount FROM upcoming_payments WHERE payee LIKE '%Sharma%' LIMIT 1) ||
    '; ledger_open=' || (SELECT balance_due FROM supplier_business_records WHERE supplier_id = 'SUP-01' ORDER BY date DESC, entry_id DESC LIMIT 1) AS actual,
    CASE WHEN 
        (SELECT amount FROM upcoming_payments WHERE payee LIKE '%Sharma%' LIMIT 1) = 4200.0 AND
        (SELECT balance_due FROM supplier_business_records WHERE supplier_id = 'SUP-01' ORDER BY date DESC, entry_id DESC LIMIT 1) = 4200.0
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A11: customer_metrics latest = 96 / 62 / 64.6, matching live counts in customers.
SELECT
    'A11' AS id,
    'metrics=96/62/64.6; live=96/62/64.6' AS expected,
    'metrics=' || (SELECT current_customers || '/' || recurring_customers || '/' || recurring_pct FROM customer_metrics WHERE date = '2026-10-10') ||
    '; live=' || (SELECT active_customers || '/' || active_recurring || '/' || recurring_pct FROM v_customer_snapshot) AS actual,
    CASE WHEN 
        (SELECT current_customers || '/' || recurring_customers || '/' || recurring_pct FROM customer_metrics WHERE date = '2026-10-10') = '96/62/64.6' AND
        (SELECT active_customers || '/' || active_recurring || '/' || recurring_pct FROM v_customer_snapshot) = '96/62/64.6'
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A12: Doc fixtures: clean invoice has 0 discrepancies, mismatch invoice has exactly 2 ground-truth discrepancies, excess difference = 113.92.
SELECT
    'A12' AS id,
    'clean_discrepancies=0; mismatch_discrepancies=2; excess_diff=113.92' AS expected,
    'clean_discrepancies=' || (SELECT COUNT(*) FROM doc_ground_truth WHERE doc_id = 'INV-GUPTA-0912') ||
    '; mismatch_discrepancies=' || (SELECT COUNT(*) FROM doc_ground_truth WHERE doc_id = 'INV-PKG-0245') ||
    '; excess_diff=' || CAST(ROUND((SELECT total_line_amount FROM document_lines WHERE doc_id = 'INV-PKG-0245') - (SELECT total_amount FROM purchase_orders WHERE po_id = 'PO-20261004-02'), 2) AS TEXT) AS actual,
    CASE WHEN 
        (SELECT COUNT(*) FROM doc_ground_truth WHERE doc_id = 'INV-GUPTA-0912') = 0 AND
        (SELECT COUNT(*) FROM doc_ground_truth WHERE doc_id = 'INV-PKG-0245') = 2 AND
        ROUND((SELECT total_line_amount FROM document_lines WHERE doc_id = 'INV-PKG-0245') - (SELECT total_amount FROM purchase_orders WHERE po_id = 'PO-20261004-02'), 2) = 113.92
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A13: Memory conflict present (verified 146 vs owner 135, same key).
SELECT
    'A13' AS id,
    'key=supplier.gupta.oil_price_per_l; val1=146; val2=135' AS expected,
    'key=' || (SELECT key FROM v_memory_conflicts WHERE key = 'supplier.gupta.oil_price_per_l' LIMIT 1) ||
    '; val1=' || (SELECT val_1 FROM v_memory_conflicts WHERE key = 'supplier.gupta.oil_price_per_l' LIMIT 1) ||
    '; val2=' || (SELECT val_2 FROM v_memory_conflicts WHERE key = 'supplier.gupta.oil_price_per_l' LIMIT 1) AS actual,
    CASE WHEN 
        (SELECT key FROM v_memory_conflicts WHERE key = 'supplier.gupta.oil_price_per_l' LIMIT 1) = 'supplier.gupta.oil_price_per_l' AND
        (SELECT val_1 FROM v_memory_conflicts WHERE key = 'supplier.gupta.oil_price_per_l' LIMIT 1) = '146' AND
        (SELECT val_2 FROM v_memory_conflicts WHERE key = 'supplier.gupta.oil_price_per_l' LIMIT 1) = '135'
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A14: No negative stock; every delivery_slots booked_units <= capacity_units.
SELECT
    'A14' AS id,
    'negative_stock=0; overbooked_slots=0' AS expected,
    'negative_stock=' || (SELECT COUNT(*) FROM inventory_stock WHERE stock_qty < 0) ||
    '; overbooked_slots=' || (SELECT COUNT(*) FROM delivery_slots WHERE booked_units > capacity_units) AS actual,
    CASE WHEN 
        (SELECT COUNT(*) FROM inventory_stock WHERE stock_qty < 0) = 0 AND
        (SELECT COUNT(*) FROM delivery_slots WHERE booked_units > capacity_units) = 0
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A15: sum(orders.amount) per day within 1% of daily_metrics.revenue for the last 90 days; monthly_metrics rolls up from daily for October.
SELECT
    'A15' AS id,
    'diff_days_exceeding_1pct=0; oct_rollup_match=1' AS expected,
    'diff_days_exceeding_1pct=' || (
        SELECT COUNT(*) FROM (
            SELECT 
                dm.date,
                dm.revenue,
                COALESCE(SUM(o.amount), 0.0) AS order_rev,
                ABS(COALESCE(SUM(o.amount), 0.0) - dm.revenue) / dm.revenue AS diff_ratio
            FROM daily_metrics dm
            LEFT JOIN orders o ON dm.date = o.date AND o.status IN ('delivered', 'confirmed')
            GROUP BY dm.date, dm.revenue
            HAVING diff_ratio > 0.01
        )
    ) ||
    '; oct_rollup_match=' || (
        SELECT CASE 
            WHEN mm.revenue = (SELECT SUM(revenue) FROM daily_metrics WHERE date LIKE '2026-10%')
             AND mm.units_sold = (SELECT SUM(units_sold) FROM daily_metrics WHERE date LIKE '2026-10%')
            THEN 1 ELSE 0 END
        FROM monthly_metrics mm
        WHERE mm.month = '2026-10'
    ) AS actual,
    CASE WHEN 
        (
            SELECT COUNT(*) FROM (
                SELECT 
                    dm.date,
                    dm.revenue,
                    COALESCE(SUM(o.amount), 0.0) AS order_rev,
                    ABS(COALESCE(SUM(o.amount), 0.0) - dm.revenue) / dm.revenue AS diff_ratio
                FROM daily_metrics dm
                LEFT JOIN orders o ON dm.date = o.date AND o.status IN ('delivered', 'confirmed')
                GROUP BY dm.date, dm.revenue
                HAVING diff_ratio > 0.01
            )
        ) = 0 AND
        (
            SELECT CASE 
                WHEN mm.revenue = (SELECT SUM(revenue) FROM daily_metrics WHERE date LIKE '2026-10%')
                 AND mm.units_sold = (SELECT SUM(units_sold) FROM daily_metrics WHERE date LIKE '2026-10%')
                THEN 1 ELSE 0 END
            FROM monthly_metrics mm
            WHERE mm.month = '2026-10'
        ) = 1
    THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

-- A16: Determinism assertion placeholder in SQL (build_db.py also tests bitwise dump hash).
SELECT
    'A16' AS id,
    'meta_anchor_ready=1; reference_plans_ready=3' AS expected,
    'meta_anchor_ready=' || (SELECT CASE WHEN COUNT(*) >= 5 THEN 1 ELSE 0 END FROM meta) ||
    '; reference_plans_ready=' || (SELECT COUNT(*) FROM reference_plans) AS actual,
    CASE WHEN 
        (SELECT COUNT(*) FROM meta WHERE key IN ('as_of', 'frozen_date', 'tomorrow_date')) = 3 AND
        (SELECT COUNT(*) FROM reference_plans) = 3
    THEN 'PASS' ELSE 'FAIL' END AS status;

