-- ============================================================================
-- Alexa Business Autopilot: Seed Anchor SQL (Ground Truth Constants)
-- All values here are EXACT and hand-authored for the headline demo.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. SYSTEM METADATA & FROZEN CLOCK
-- ----------------------------------------------------------------------------
INSERT INTO meta (key, value) VALUES
    ('as_of', '2026-10-10T19:10:00+05:30'),
    ('frozen_date', '2026-10-10'),
    ('tomorrow_date', '2026-10-11'),
    ('business_name', 'Maa Ki Rasoi Cloud Kitchen'),
    ('single_menu_item', 'Standard Veg Tiffin'),
    ('menu_price_one_off', '90'),
    ('menu_price_subscription', '85'),
    ('currency', 'INR');

-- Business Profile
INSERT INTO business_profile (
    business_name, archetype, owner_name, locality, city, state, gstin, phone, currency, as_of, is_synthetic
) VALUES (
    'Maa Ki Rasoi Cloud Kitchen',
    'tiffin / cloud kitchen',
    'Sunita Sharma',
    'Kakadeo',
    'Kanpur',
    'Uttar Pradesh',
    '09ZZZZZ9999Z1Z5',
    '+91 XXXXXX4821',
    'INR',
    '2026-10-10T19:10:00+05:30',
    1
);

-- Business Policy (Anchor constants)
INSERT INTO business_policy (
    policy_id, min_cash_buffer, safety_stock_pct, regular_order_cutoff, cooking_start,
    packing_start, max_meals_per_day, fast_delivery_fee, stockout_cost_per_meal
) VALUES (
    1,
    5000.0,
    10.0,
    '20:00',
    '09:00',
    '11:00',
    40,
    49.0,
    90.0
);

-- ----------------------------------------------------------------------------
-- 2. SUPPLIERS
-- ----------------------------------------------------------------------------
INSERT INTO suppliers (
    supplier_id, name, category, cutoff_time, delivery_window, delivery_fee,
    free_delivery_threshold, credit_days, reliability, is_simulated, contact_phone,
    gstin, locality, is_synthetic
) VALUES
(
    'SUP-01',
    'Sharma General Traders',
    'regular grocery wholesaler',
    '20:00',
    'Next-day 10:00 delivery for orders before 20:00',
    40.0,
    500.0,
    7,
    0.91,
    0,
    '+91 XXXXXX1101',
    '09AAAAA1111A1Z1',
    'Collectorganj',
    1
),
(
    'SUP-02',
    'Kanpur Packaging Mart',
    'packaging supplier',
    '20:00',
    'Next-day 07:00 delivery for orders before 20:00',
    30.0,
    NULL,
    0,
    0.88,
    0,
    '+91 XXXXXX2202',
    '09BBBBB2222B1Z2',
    'Fazalganj Industrial Area',
    1
),
(
    'SUP-03',
    'Gupta Oil Agency',
    'edible oil distributor',
    '18:00',
    'Alternate-day route, next delivery 2026-10-12 15:00',
    0.0,
    NULL,
    15,
    0.84,
    0,
    '+91 XXXXXX3303',
    '09CCCCC3333C1Z3',
    'Transport Nagar',
    1
),
(
    'SUP-04',
    'QuickKart Now',
    'fast-delivery actuator',
    '23:59',
    'ETA 25-45 min',
    49.0,
    2500.0,
    0,
    0.95,
    1,
    '+91 XXXXXX4404',
    '09DDDDD4444D1Z4',
    'Kakadeo Dark Store',
    1
);

-- ----------------------------------------------------------------------------
-- 3. ITEMS & RECIPE BILL OF MATERIALS
-- ----------------------------------------------------------------------------
INSERT INTO items (item_id, name, unit, reorder_point, par_level, procure_mode, is_bom_item) VALUES
    ('OIL-SUN-1L',  'Refined sunflower oil',    'L',   2.0,  6.0,   'catalogue',   1),
    ('CONT-750',    'Tiffin container 750ml',   'pcs', 40.0, 200.0, 'catalogue',   1),
    ('ATTA-10',     'Wheat flour',              'kg',  10.0, 40.0,  'catalogue',   1),
    ('RICE-BAS',    'Rice',                     'kg',  4.0,  25.0,  'catalogue',   1),
    ('DAL-MOONG',   'Moong dal',                'kg',  4.0,  12.0,  'catalogue',   1),
    ('VEG-MIX',     'Seasonal vegetables',      'kg',  5.0,  12.0,  'daily_mandi', 1),
    ('SPICE-MIX',   'Spice blend',              'kg',  0.30, 1.5,   'catalogue',   1),
    ('BAG-CARRY',   'Carry bag',                'pcs', 30.0, 150.0, 'catalogue',   1),
    ('GHEE-1KG',    'Ghee (NOT in BOM)',        'kg',  1.0,  4.0,   'catalogue',   0);

-- BOM per tiffin (Standard Veg Tiffin)
INSERT INTO recipe_bom (item_id, qty_per_tiffin) VALUES
    ('OIL-SUN-1L',  0.06),
    ('CONT-750',    1.00),
    ('ATTA-10',     0.20),
    ('RICE-BAS',    0.15),
    ('DAL-MOONG',   0.08),
    ('VEG-MIX',     0.25),
    ('SPICE-MIX',   0.01),
    ('BAG-CARRY',   1.00);

-- Inventory stock as of 2026-10-10T19:10:00+05:30
INSERT INTO inventory_stock (
    item_id, stock_qty, last_restocked_date, last_restocked_qty, refresh_forecast_date, refresh_forecast_qty, as_of
) VALUES
    ('OIL-SUN-1L',  0.80, '2026-09-28', 10.0,  '2026-10-12', 6.0,   '2026-10-10T19:10:00+05:30'),
    ('CONT-750',    12.0, '2026-10-05', 100.0, '2026-10-11', 100.0, '2026-10-10T19:10:00+05:30'),
    ('ATTA-10',     14.0, '2026-10-03', 40.0,  '2026-10-13', 40.0,  '2026-10-10T19:10:00+05:30'),
    ('RICE-BAS',    9.0,  '2026-10-06', 25.0,  '2026-10-14', 25.0,  '2026-10-10T19:10:00+05:30'),
    ('DAL-MOONG',   3.5,  '2026-10-04', 10.0,  '2026-10-12', 10.0,  '2026-10-10T19:10:00+05:30'),
    ('VEG-MIX',     7.0,  '2026-10-10', 10.0,  '2026-10-11', 10.0,  '2026-10-10T19:10:00+05:30'),
    ('SPICE-MIX',   0.60, '2026-10-01', 2.0,   '2026-10-16', 2.0,   '2026-10-10T19:10:00+05:30'),
    ('BAG-CARRY',   70.0, '2026-10-02', 100.0, '2026-10-20', 100.0, '2026-10-10T19:10:00+05:30'),
    ('GHEE-1KG',    1.5,  '2026-09-20', 3.0,   '2026-10-18', 3.0,   '2026-10-10T19:10:00+05:30');

-- Supplier Inventory Info
INSERT INTO supplier_inventory_info (supplier_id, item_id, in_stock, available_qty, restock_expected_date, as_of, note) VALUES
    ('SUP-01', 'OIL-SUN-1L', 0, 0.0,   '2026-10-13', '2026-10-10T19:10:00+05:30', 'OUT OF STOCK at warehouse'),
    ('SUP-03', 'OIL-SUN-1L', 1, 50.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock, next delivery 2026-10-12 15:00'),
    ('SUP-04', 'OIL-SUN-1L', 1, 15.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock, quick delivery 25-45 min'),
    ('SUP-02', 'CONT-750',   1, 500.0, NULL,         '2026-10-10T19:10:00+05:30', 'In stock, morning delivery'),
    ('SUP-04', 'CONT-750',   1, 40.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock, quick delivery'),
    ('SUP-01', 'ATTA-10',    1, 80.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock, wholesale pack'),
    ('SUP-04', 'ATTA-10',    1, 20.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-01', 'DAL-MOONG',  1, 40.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-04', 'DAL-MOONG',  1, 25.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-01', 'RICE-BAS',   1, 50.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-04', 'RICE-BAS',   1, 30.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-01', 'SPICE-MIX',  1, 15.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-04', 'SPICE-MIX',  1, 10.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-02', 'BAG-CARRY',  1, 800.0, NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-04', 'BAG-CARRY',  1, 100.0, NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-01', 'GHEE-1KG',   1, 10.0,  NULL,         '2026-10-10T19:10:00+05:30', 'In stock'),
    ('SUP-04', 'GHEE-1KG',   0, 0.0,   '2026-10-12', '2026-10-10T19:10:00+05:30', 'OUT OF STOCK on QuickKart');

-- Catalogue Items (GST-inclusive INR)
INSERT INTO catalogue (supplier_id, item_id, pack_label, pack_qty, price_per_pack, price_per_unit, eta_minutes, in_stock, is_simulated) VALUES
    ('SUP-03', 'OIL-SUN-1L', '1L bottle',  1.0,  146.0, 146.0, 2630, 1, 0), -- Route delivery Oct 12 15:00
    ('SUP-01', 'OIL-SUN-1L', '1L pouch',   1.0,  142.0, 142.0, 890,  0, 0), -- Wholesale OOS
    ('SUP-04', 'OIL-SUN-1L', '1L bottle',  1.0,  158.0, 158.0, 30,   1, 1), -- QuickKart fast delivery
    ('SUP-02', 'CONT-750',   'Pack of 50', 50.0, 160.0, 3.20,  710,  1, 0), -- 07:00 next day
    ('SUP-04', 'CONT-750',   'Pack of 25', 25.0, 188.0, 7.52,  35,   1, 1), -- QuickKart
    ('SUP-01', 'ATTA-10',    '10kg bag',   10.0, 400.0, 40.0,  890,  1, 0), -- Sharma wholesale
    ('SUP-04', 'ATTA-10',    '10kg bag',   10.0, 460.0, 46.0,  40,   1, 1), -- QuickKart
    ('SUP-01', 'DAL-MOONG',  '1kg pack',   1.0,  112.0, 112.0, 890,  1, 0), -- Sharma wholesale
    ('SUP-04', 'DAL-MOONG',  '1kg pack',   1.0,  128.0, 128.0, 40,   1, 1), -- QuickKart
    ('SUP-01', 'RICE-BAS',   '5kg bag',    5.0,  325.0, 65.0,  890,  1, 0),
    ('SUP-04', 'RICE-BAS',   '5kg bag',    5.0,  375.0, 75.0,  35,   1, 1),
    ('SUP-01', 'SPICE-MIX',  '500g pouch', 0.5,  140.0, 280.0, 890,  1, 0),
    ('SUP-04', 'SPICE-MIX',  '500g pouch', 0.5,  165.0, 330.0, 25,   1, 1),
    ('SUP-02', 'BAG-CARRY',  'Pack of 100',100.0,120.0, 1.20,  710,  1, 0),
    ('SUP-04', 'BAG-CARRY',  'Pack of 50', 50.0, 90.0,  1.80,  30,   1, 1),
    ('SUP-01', 'GHEE-1KG',   '1kg jar',    1.0,  580.0, 580.0, 890,  1, 0),
    ('SUP-04', 'GHEE-1KG',   '1kg jar',    1.0,  640.0, 640.0, 30,   0, 1);

-- Supplier Price History (Anchor for Gupta oil price trend)
INSERT INTO supplier_price_history (supplier_id, item_id, effective_date, price_per_pack, price_per_unit, change_reason) VALUES
    ('SUP-03', 'OIL-SUN-1L', '2026-07-01', 138.0, 138.0, 'Regular quarterly tariff'),
    ('SUP-03', 'OIL-SUN-1L', '2026-08-01', 140.0, 140.0, 'Edible oil import tariff revision'),
    ('SUP-03', 'OIL-SUN-1L', '2026-09-01', 146.0, 146.0, 'Wholesale distributor price adjustment'),
    ('SUP-03', 'OIL-SUN-1L', '2026-10-01', 148.0, 148.0, 'Festival transport surcharge announcement');

-- ----------------------------------------------------------------------------
-- 4. REFERENCE PROCUREMENT PLANS (GROUND TRUTH)
-- ----------------------------------------------------------------------------
INSERT INTO reference_plans (plan_id, plan_name, strategy, description) VALUES
    ('REF-RECOMMENDED', 'Recommended Optimal Plan', 'mixed_optimal', 'Oil 2L fast (QuickKart) + Containers 100 regular (Packaging Mart) + Atta/Dal regular (Sharma)'),
    ('REF-ALL-FAST', 'All Fast Emergency Plan', 'all_fast', 'All 4 items via QuickKart Now emergency instant delivery'),
    ('REF-OIL-CONT-FAST', 'Fast Oil & Packaging Plan', 'semi_fast', 'Oil & Containers via QuickKart Now, Atta & Dal via Sharma General Traders');

-- Plan Lines
-- REF-RECOMMENDED: 316 + 49 fee + 320 + 30 fee + 400 + 560 + 0 fee = 1675
INSERT INTO reference_plan_lines (plan_line_id, plan_id, supplier_id, item_id, pack_qty_ordered, unit_qty_equivalent, price_per_pack, line_subtotal) VALUES
    ('RPL-REC-01', 'REF-RECOMMENDED', 'SUP-04', 'OIL-SUN-1L', 2, 2.0,   158.0, 316.0),
    ('RPL-REC-02', 'REF-RECOMMENDED', 'SUP-02', 'CONT-750',   2, 100.0, 160.0, 320.0),
    ('RPL-REC-03', 'REF-RECOMMENDED', 'SUP-01', 'ATTA-10',    1, 10.0,  400.0, 400.0),
    ('RPL-REC-04', 'REF-RECOMMENDED', 'SUP-01', 'DAL-MOONG',  5, 5.0,   112.0, 560.0);

-- REF-ALL-FAST: 316 + 752 + 460 + 640 + 49 fee = 2217
INSERT INTO reference_plan_lines (plan_line_id, plan_id, supplier_id, item_id, pack_qty_ordered, unit_qty_equivalent, price_per_pack, line_subtotal) VALUES
    ('RPL-FST-01', 'REF-ALL-FAST', 'SUP-04', 'OIL-SUN-1L', 2, 2.0,   158.0, 316.0),
    ('RPL-FST-02', 'REF-ALL-FAST', 'SUP-04', 'CONT-750',   4, 100.0, 188.0, 752.0),
    ('RPL-FST-03', 'REF-ALL-FAST', 'SUP-04', 'ATTA-10',    1, 10.0,  460.0, 460.0),
    ('RPL-FST-04', 'REF-ALL-FAST', 'SUP-04', 'DAL-MOONG',  5, 5.0,   128.0, 640.0);

-- REF-OIL-CONT-FAST: 316 + 752 + 49 fee + 400 + 560 + 0 fee = 2077
INSERT INTO reference_plan_lines (plan_line_id, plan_id, supplier_id, item_id, pack_qty_ordered, unit_qty_equivalent, price_per_pack, line_subtotal) VALUES
    ('RPL-OCF-01', 'REF-OIL-CONT-FAST', 'SUP-04', 'OIL-SUN-1L', 2, 2.0,   158.0, 316.0),
    ('RPL-OCF-02', 'REF-OIL-CONT-FAST', 'SUP-04', 'CONT-750',   4, 100.0, 188.0, 752.0),
    ('RPL-OCF-03', 'REF-OIL-CONT-FAST', 'SUP-01', 'ATTA-10',    1, 10.0,  400.0, 400.0),
    ('RPL-OCF-04', 'REF-OIL-CONT-FAST', 'SUP-01', 'DAL-MOONG',  5, 5.0,   112.0, 560.0);

-- ----------------------------------------------------------------------------
-- 5. DEMAND FORECAST & ANCHOR DRIVERS
-- ----------------------------------------------------------------------------
INSERT INTO demand_drivers (date, day_of_week, is_holiday, festival, weather_note, local_event, subscription_pauses) VALUES
    ('2026-10-10', 'Saturday',  0, 'Navratri (Day 1)',         'Clear, 29C', 'Market rush', 2),
    ('2026-10-11', 'Sunday',    0, 'Navratri (vrat menu)',     'Clear, 28C', 'Coaching test series Kakadeo', 3),
    ('2026-10-12', 'Monday',    0, 'Navratri (vrat menu)',     'Hazy, 27C',  'Work week starts', 2),
    ('2026-10-13', 'Tuesday',   0, 'Navratri (vrat menu)',     'Clear, 28C', 'Normal', 2),
    ('2026-10-14', 'Wednesday', 0, 'Navratri (vrat menu)',     'Clear, 29C', 'Mid-week exams', 2),
    ('2026-10-15', 'Thursday',  0, 'Navratri (vrat menu)',     'Clear, 28C', 'Normal', 2),
    ('2026-10-16', 'Friday',    0, 'Navratri (vrat menu)',     'Pleasant, 27C','Pre-weekend', 2),
    ('2026-10-17', 'Saturday',  0, 'Navratri (vrat menu)',     'Clear, 27C', 'Weekend prep', 2),
    ('2026-10-18', 'Sunday',    0, 'Navratri (vrat menu)',     'Clear, 27C', 'Maha Ashtami festivities', 3),
    ('2026-10-19', 'Monday',    0, 'Navratri (vrat menu)',     'Clear, 26C', 'Maha Navami pooja', 4),
    ('2026-10-20', 'Tuesday',   1, 'Dussehra',                 'Clear, 26C', 'Dussehra Mela Rawatpur', 8),
    ('2026-10-21', 'Wednesday', 0, NULL,                       'Clear, 27C', 'Post festival resumption', 2),
    ('2026-10-22', 'Thursday',  0, NULL,                       'Clear, 27C', 'Normal', 1),
    ('2026-10-23', 'Friday',    0, NULL,                       'Clear, 28C', 'Normal', 1),
    ('2026-10-24', 'Saturday',  0, NULL,                       'Clear, 28C', 'Weekend', 1);

INSERT INTO demand_forecast (date, units_forecast, lower, upper, confidence, method) VALUES
    ('2026-10-10', 21.0, 19.0, 23.0, 0.90, 'ensemble_exponential_smoothing'),
    ('2026-10-11', 23.0, 20.0, 26.0, 0.82, 'ensemble_exponential_smoothing'), -- 20 confirmed + 3 expected walk-ins
    ('2026-10-12', 24.0, 21.0, 27.0, 0.80, 'ensemble_exponential_smoothing'),
    ('2026-10-13', 25.0, 22.0, 28.0, 0.78, 'ensemble_exponential_smoothing'),
    ('2026-10-14', 24.0, 21.0, 27.0, 0.77, 'ensemble_exponential_smoothing'),
    ('2026-10-15', 24.0, 21.0, 27.0, 0.75, 'ensemble_exponential_smoothing'),
    ('2026-10-16', 25.0, 22.0, 28.0, 0.72, 'ensemble_exponential_smoothing'),
    ('2026-10-17', 22.0, 18.0, 26.0, 0.70, 'ensemble_exponential_smoothing'),
    ('2026-10-18', 21.0, 17.0, 25.0, 0.68, 'ensemble_exponential_smoothing'),
    ('2026-10-19', 20.0, 15.0, 25.0, 0.65, 'ensemble_exponential_smoothing'),
    ('2026-10-20', 18.0, 10.0, 28.0, 0.45, 'festival_event_heuristic'), -- Low-confidence wide band for Dussehra
    ('2026-10-21', 24.0, 20.0, 28.0, 0.60, 'ensemble_exponential_smoothing'),
    ('2026-10-22', 25.0, 21.0, 29.0, 0.58, 'ensemble_exponential_smoothing'),
    ('2026-10-23', 25.0, 21.0, 29.0, 0.55, 'ensemble_exponential_smoothing'),
    ('2026-10-24', 22.0, 18.0, 26.0, 0.50, 'ensemble_exponential_smoothing');

-- Capacity & Slots for Tomorrow (2026-10-11)
INSERT INTO capacity (date, max_meals, cook_hours) VALUES
    ('2026-10-10', 40, 6.0),
    ('2026-10-11', 40, 6.0);

INSERT INTO delivery_slots (slot_id, date, slot_label, start_time, end_time, capacity_units, booked_units) VALUES
    ('SLOT-20261011-1', '2026-10-11', '11:00-12:00', '11:00', '12:00', 10, 6), -- booked: 6, free: 4
    ('SLOT-20261011-2', '2026-10-11', '12:00-13:00', '12:00', '13:00', 10, 8), -- booked: 8, free: 2
    ('SLOT-20261011-3', '2026-10-11', '13:00-14:00', '13:00', '14:00', 10, 4), -- afternoon slot 1: free 6
    ('SLOT-20261011-4', '2026-10-11', '14:00-15:00', '14:00', '15:00', 10, 2); -- afternoon slot 2: free 8

-- ----------------------------------------------------------------------------
-- 6. CASH POSITION, UPCOMING PAYMENTS & FORECASTED BALANCE
-- ----------------------------------------------------------------------------
INSERT INTO cash_position (as_of, current_balance, min_cash_buffer) VALUES
    ('2026-10-10T19:10:00+05:30', 12000.0, 5000.0);

INSERT INTO upcoming_payments (payment_id, payee, category, amount, due_date, status) VALUES
    ('PAY-01', 'Kitchen Staff (Ramesh & Geeta)', 'salaries',        7500.0, '2026-10-11', 'pending'),
    ('PAY-02', 'Sharma General Traders',        'supplier_dues',   4200.0, '2026-10-12', 'pending'),
    ('PAY-03', 'Indane Gas Agency',             'utilities_lpg',   1950.0, '2026-10-14', 'pending'),
    ('PAY-04', 'Commercial Space Landlord',     'rent',            6000.0, '2026-10-15', 'pending'),
    ('PAY-05', 'KESCO Kanpur Electricity',     'utilities_power', 1200.0, '2026-10-20', 'pending');

-- 15 rows of forecasted balance starting 2026-10-10
-- Min projected balance over horizon MUST be 6900 on 2026-10-12
INSERT INTO forecasted_balance (date, expected_inflow, expected_outflow, projected_balance, confidence) VALUES
    ('2026-10-10', 0.0,    0.0,    12000.0, 1.00),
    ('2026-10-11', 3200.0, 7500.0, 7700.0,  0.90),
    ('2026-10-12', 3400.0, 4200.0, 6900.0,  0.88), -- Lowest point (Headroom = 6900 - 5000 = 1900)
    ('2026-10-13', 3600.0, 700.0,  9800.0,  0.85),
    ('2026-10-14', 3500.0, 2650.0, 10650.0, 0.80),
    ('2026-10-15', 3500.0, 6700.0, 7450.0,  0.75),
    ('2026-10-16', 3500.0, 700.0,  10250.0, 0.70),
    ('2026-10-17', 3300.0, 700.0,  12850.0, 0.67),
    ('2026-10-18', 3300.0, 700.0,  15450.0, 0.64),
    ('2026-10-19', 3300.0, 700.0,  18050.0, 0.61),
    ('2026-10-20', 2200.0, 1900.0, 18350.0, 0.58), -- Dussehra dip + electricity payment
    ('2026-10-21', 3300.0, 700.0,  20950.0, 0.55),
    ('2026-10-22', 3300.0, 700.0,  23550.0, 0.53),
    ('2026-10-23', 3300.0, 700.0,  26150.0, 0.51),
    ('2026-10-24', 3300.0, 700.0,  28750.0, 0.50);

-- ----------------------------------------------------------------------------
-- 7. BUSINESS DOCUMENTS & GROUND TRUTH DISCREPANCIES
-- ----------------------------------------------------------------------------
-- Purchase orders matching invoices
INSERT INTO purchase_orders (po_id, supplier_id, order_date, expected_delivery_date, status, total_taxable, total_tax, total_amount, notes) VALUES
    ('PO-20260926-01', 'SUP-03', '2026-09-26', '2026-09-28', 'received', 1460.0, 73.00, 1533.00, 'Sunflower oil 10L route delivery'),
    ('PO-20261004-02', 'SUP-02', '2026-10-04', '2026-10-05', 'received', 320.0,  57.60, 377.60,  'Tiffin container 750ml 100 pcs @3.20 + 18% GST');

INSERT INTO purchase_order_lines (line_id, po_id, item_id, ordered_qty, unit_price, tax_rate_pct, taxable_amount, tax_amount, line_total) VALUES
    ('POL-20260926-01', 'PO-20260926-01', 'OIL-SUN-1L', 10.0,  146.0, 5.0,  1460.0, 73.00, 1533.00),
    ('POL-20261004-02', 'PO-20261004-02', 'CONT-750',   100.0, 3.20,  18.0, 320.0,  57.60, 377.60);

-- Anchor Purchase History rows
INSERT INTO purchase_history (purchase_id, po_id, supplier_id, item_id, purchase_date, qty, unit_price, total_paid, payment_mode, notes) VALUES
    ('PH-ANCHOR-01', 'PO-20260926-01', 'SUP-03', 'OIL-SUN-1L', '2026-09-28', 10.0,  146.0, 1533.00, 'UPI',    '10L sunflower oil delivered and paid'),
    ('PH-ANCHOR-02', 'PO-20261004-02', 'SUP-02', 'CONT-750',   '2026-10-05', 100.0, 3.20,  377.60,  'credit', 'Goods received 100 pcs; invoice discrepancy noted');

-- Documents
INSERT INTO business_documents (doc_id, doc_type, supplier_id, po_id, doc_date, file_ref, extracted_json, extraction_confidence) VALUES
(
    'INV-GUPTA-0912',
    'invoice',
    'SUP-03',
    'PO-20260926-01',
    '2026-09-28',
    'fixtures/INV-GUPTA-0912.pdf',
    '{"invoice_number": "INV-GUPTA-0912", "date": "2026-09-28", "supplier": "Gupta Oil Agency", "lines": [{"item_id": "OIL-SUN-1L", "qty": 10.0, "unit_price": 146.0, "taxable": 1460.0, "gst_rate": 0.05, "gst": 73.0, "total": 1533.0}], "taxable_amount": 1460.0, "tax_amount": 73.0, "total_amount": 1533.0}',
    0.96
),
(
    'INV-PKG-0245',
    'invoice',
    'SUP-02',
    'PO-20261004-02',
    '2026-10-05',
    'fixtures/INV-PKG-0245.pdf',
    '{"invoice_number": "INV-PKG-0245", "date": "2026-10-05", "supplier": "Kanpur Packaging Mart", "lines": [{"item_id": "CONT-750", "qty": 120.0, "unit_price": 3.20, "taxable": 384.0, "gst_rate": 0.28, "gst": 107.52, "total": 491.52}], "taxable_amount": 384.0, "tax_amount": 107.52, "total_amount": 491.52}',
    0.93
);

-- Document Lines
INSERT INTO document_lines (doc_line_id, doc_id, item_id, billed_qty, unit_price, taxable_amount, gst_rate_pct, gst_amount, total_line_amount) VALUES
    ('DL-01', 'INV-GUPTA-0912', 'OIL-SUN-1L', 10.0,  146.0, 1460.0, 5.0,  73.00,  1533.00),
    ('DL-02', 'INV-PKG-0245',   'CONT-750',   120.0, 3.20,  384.0,  28.0, 107.52, 491.52);

-- Document Ground Truth (Exactly two discrepancies for INV-PKG-0245, none for INV-GUPTA-0912)
INSERT INTO doc_ground_truth (truth_id, doc_id, discrepancy_type, field_name, expected_value, actual_value, difference_amount, description) VALUES
(
    'TRUTH-PKG-01',
    'INV-PKG-0245',
    'quantity',
    'quantity',
    '100',
    '120',
    64.00,
    'Quantity billed (120 pcs) exceeds purchase order and goods receipt quantity (100 pcs) by +20 pcs'
),
(
    'TRUTH-PKG-02',
    'INV-PKG-0245',
    'tax_rate',
    'gst_rate_pct',
    '18%',
    '28%',
    49.92,
    'GST charged at 28% instead of standard packaging rate of 18% (excess tax difference ₹49.92; total invoice excess ₹113.92)'
);

-- ----------------------------------------------------------------------------
-- 8. BUSINESS MEMORY (GROUND TRUTH FACTS & DELIBERATE CONFLICT)
-- ----------------------------------------------------------------------------
INSERT INTO business_memory (key, value, source, timestamp, confidence) VALUES
    ('supplier.gupta.oil_price_per_l', '146', 'verified_record', '2026-09-28T14:30:00+05:30', 0.95),
    ('supplier.gupta.oil_price_per_l', '135', 'owner_statement', '2026-10-02T11:15:00+05:30', 0.40), -- Conflict
    ('owner.preferred_language', 'hinglish', 'owner_statement', '2026-09-01T10:00:00+05:30', 0.90),
    ('owner.min_cash_buffer', '5000', 'owner_statement', '2026-09-01T10:00:00+05:30', 0.95),
    ('supplier.packaging_mart.delivery_issue', 'late 2026-09-14', 'verified_record', '2026-09-14T18:00:00+05:30', 0.95);

-- ----------------------------------------------------------------------------
-- 9. SUPPLIER BUSINESS RECORDS (LEDGER FOR SHARMA DUES = 4200)
-- ----------------------------------------------------------------------------
INSERT INTO supplier_business_records (entry_id, supplier_id, date, entry_type, reference_doc, amount, balance_due, notes) VALUES
    ('SBR-01', 'SUP-01', '2026-10-03', 'invoice', 'INV-SHARMA-0881', 6200.0, 6200.0, 'Weekly grocery restocking bill'),
    ('SBR-02', 'SUP-01', '2026-10-08', 'payment', 'PAY-SHARMA-P01',  2000.0, 4200.0, 'Partial payment via UPI; open balance exactly 4200.0');

