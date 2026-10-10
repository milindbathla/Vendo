-- ============================================================================
-- Alexa Business Autopilot: Deterministic Synthetic Database Schema
-- Archetype: Cloud Kitchen / Tiffin Service ("Maa Ki Rasoi Cloud Kitchen", Kanpur)
-- Target: SQLite 3.35+ (PostgreSQL portable standard SQL: INTEGER, REAL, TEXT)
-- PRAGMA foreign_keys = ON;
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. SYSTEM METADATA & FROZEN CLOCK
-- ----------------------------------------------------------------------------
-- Handwritten mapping: Core system configuration & frozen time anchor.
-- Store as_of = 2026-10-10T19:10:00+05:30. Never use system clock.
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Business profile overview
CREATE TABLE IF NOT EXISTS business_profile (
    business_name TEXT PRIMARY KEY,
    archetype TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    locality TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    gstin TEXT NOT NULL,
    phone TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    as_of TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic IN (0, 1))
);

-- Core business policy parameters
CREATE TABLE IF NOT EXISTS business_policy (
    policy_id INTEGER PRIMARY KEY,
    min_cash_buffer REAL NOT NULL CHECK (min_cash_buffer >= 0),
    safety_stock_pct REAL NOT NULL CHECK (safety_stock_pct >= 0),
    regular_order_cutoff TEXT NOT NULL, -- 'HH:MM'
    cooking_start TEXT NOT NULL,        -- 'HH:MM'
    packing_start TEXT NOT NULL,        -- 'HH:MM'
    max_meals_per_day INTEGER NOT NULL CHECK (max_meals_per_day > 0),
    fast_delivery_fee REAL NOT NULL CHECK (fast_delivery_fee >= 0),
    stockout_cost_per_meal REAL NOT NULL CHECK (stockout_cost_per_meal >= 0)
);

-- ----------------------------------------------------------------------------
-- 2. SUPPLIERS & CATALOGUE
-- ----------------------------------------------------------------------------
-- Handwritten mapping: Item-price mappings / catalogue & Any info on supplier inventory
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    cutoff_time TEXT,                      -- e.g. '20:00'
    delivery_window TEXT NOT NULL,          -- e.g. 'Next-day 10:00'
    delivery_fee REAL NOT NULL DEFAULT 0 CHECK (delivery_fee >= 0),
    free_delivery_threshold REAL CHECK (free_delivery_threshold IS NULL OR free_delivery_threshold >= 0),
    credit_days INTEGER NOT NULL DEFAULT 0 CHECK (credit_days >= 0),
    reliability REAL NOT NULL CHECK (reliability BETWEEN 0.0 AND 1.0),
    is_simulated INTEGER NOT NULL DEFAULT 0 CHECK (is_simulated IN (0, 1)),
    contact_phone TEXT,
    gstin TEXT,
    locality TEXT,
    is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic IN (0, 1))
);

-- Handwritten mapping: Item-price mappings / catalogue
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,                    -- 'L', 'kg', 'pcs'
    reorder_point REAL NOT NULL CHECK (reorder_point >= 0),
    par_level REAL NOT NULL CHECK (par_level >= 0),
    procure_mode TEXT NOT NULL DEFAULT 'catalogue' CHECK (procure_mode IN ('catalogue', 'daily_mandi', 'specialty')),
    is_bom_item INTEGER NOT NULL DEFAULT 1 CHECK (is_bom_item IN (0, 1))
);

-- Bill of Materials per standard veg tiffin meal
CREATE TABLE IF NOT EXISTS recipe_bom (
    item_id TEXT PRIMARY KEY REFERENCES items(item_id),
    qty_per_tiffin REAL NOT NULL CHECK (qty_per_tiffin >= 0)
);

-- Handwritten mapping: Inventory stock (qty), Inventory last restocked, Inventory refresh forecast
CREATE TABLE IF NOT EXISTS inventory_stock (
    item_id TEXT PRIMARY KEY REFERENCES items(item_id),
    stock_qty REAL NOT NULL CHECK (stock_qty >= 0),
    last_restocked_date TEXT,
    last_restocked_qty REAL CHECK (last_restocked_qty IS NULL OR last_restocked_qty >= 0),
    refresh_forecast_date TEXT,
    refresh_forecast_qty REAL CHECK (refresh_forecast_qty IS NULL OR refresh_forecast_qty >= 0),
    as_of TEXT NOT NULL
);

-- Handwritten mapping: Any info on supplier inventory
CREATE TABLE IF NOT EXISTS supplier_inventory_info (
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    in_stock INTEGER NOT NULL CHECK (in_stock IN (0, 1)),
    available_qty REAL CHECK (available_qty IS NULL OR available_qty >= 0),
    restock_expected_date TEXT,
    as_of TEXT NOT NULL,
    note TEXT,
    PRIMARY KEY (supplier_id, item_id)
);

-- Handwritten mapping: Item-price mappings / catalogue
CREATE TABLE IF NOT EXISTS catalogue (
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    pack_label TEXT NOT NULL,
    pack_qty REAL NOT NULL CHECK (pack_qty > 0),
    price_per_pack REAL NOT NULL CHECK (price_per_pack >= 0),
    price_per_unit REAL NOT NULL CHECK (price_per_unit >= 0),
    eta_minutes INTEGER NOT NULL CHECK (eta_minutes >= 0),
    in_stock INTEGER NOT NULL CHECK (in_stock IN (0, 1)),
    is_simulated INTEGER NOT NULL DEFAULT 0 CHECK (is_simulated IN (0, 1)),
    PRIMARY KEY (supplier_id, item_id)
);

-- Handwritten mapping: Item-price mappings / catalogue
CREATE TABLE IF NOT EXISTS supplier_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    effective_date TEXT NOT NULL,
    price_per_pack REAL NOT NULL CHECK (price_per_pack >= 0),
    price_per_unit REAL NOT NULL CHECK (price_per_unit >= 0),
    change_reason TEXT
);

-- ----------------------------------------------------------------------------
-- 3. DEMAND & CAPACITY
-- ----------------------------------------------------------------------------
-- Handwritten mapping: Demand_variables
CREATE TABLE IF NOT EXISTS demand_drivers (
    date TEXT PRIMARY KEY,
    day_of_week TEXT NOT NULL,
    is_holiday INTEGER NOT NULL DEFAULT 0 CHECK (is_holiday IN (0, 1)),
    festival TEXT,
    weather_note TEXT,
    local_event TEXT,
    subscription_pauses INTEGER NOT NULL DEFAULT 0 CHECK (subscription_pauses >= 0)
);

-- Handwritten mapping: Demand_variables
CREATE TABLE IF NOT EXISTS demand_forecast (
    date TEXT PRIMARY KEY REFERENCES demand_drivers(date),
    units_forecast REAL NOT NULL CHECK (units_forecast >= 0),
    lower REAL NOT NULL CHECK (lower >= 0),
    upper REAL NOT NULL CHECK (upper >= lower),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    method TEXT NOT NULL
);

-- Handwritten mapping: Daily/weekly/monthly appointments (Capacity & Slots)
CREATE TABLE IF NOT EXISTS capacity (
    date TEXT PRIMARY KEY,
    max_meals INTEGER NOT NULL CHECK (max_meals > 0),
    cook_hours REAL NOT NULL CHECK (cook_hours > 0)
);

-- Handwritten mapping: Daily/weekly/monthly appointments (Delivery slots)
CREATE TABLE IF NOT EXISTS delivery_slots (
    slot_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    slot_label TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    capacity_units INTEGER NOT NULL CHECK (capacity_units >= 0),
    booked_units INTEGER NOT NULL CHECK (booked_units >= 0),
    CHECK (booked_units <= capacity_units)
);

-- ----------------------------------------------------------------------------
-- 4. CASH POSITION & PROJECTIONS
-- ----------------------------------------------------------------------------
-- Handwritten mapping: Current balance (cash)
CREATE TABLE IF NOT EXISTS cash_position (
    as_of TEXT PRIMARY KEY,
    current_balance REAL NOT NULL CHECK (current_balance >= 0),
    min_cash_buffer REAL NOT NULL CHECK (min_cash_buffer >= 0)
);

-- Handwritten mapping: Forecasted balance (cash)
CREATE TABLE IF NOT EXISTS forecasted_balance (
    date TEXT PRIMARY KEY,
    expected_inflow REAL NOT NULL CHECK (expected_inflow >= 0),
    expected_outflow REAL NOT NULL CHECK (expected_outflow >= 0),
    projected_balance REAL NOT NULL CHECK (projected_balance >= 0),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0)
);

-- Upcoming payments / payables
CREATE TABLE IF NOT EXISTS upcoming_payments (
    payment_id TEXT PRIMARY KEY,
    payee TEXT NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'scheduled', 'paid'))
);

-- ----------------------------------------------------------------------------
-- 5. CUSTOMERS & APPOINTMENTS / ORDERS
-- ----------------------------------------------------------------------------
-- Handwritten mapping: Current customers (numbers), % recurring
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    segment TEXT NOT NULL,
    locality TEXT NOT NULL,
    phone TEXT NOT NULL,
    joined_date TEXT NOT NULL,
    is_recurring INTEGER NOT NULL CHECK (is_recurring IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('active', 'paused', 'churned')),
    is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic IN (0, 1))
);

-- Handwritten mapping: Current customers (numbers), % recurring
CREATE TABLE IF NOT EXISTS customer_metrics (
    date TEXT PRIMARY KEY,
    current_customers INTEGER NOT NULL CHECK (current_customers >= 0),
    recurring_customers INTEGER NOT NULL CHECK (recurring_customers >= 0),
    recurring_pct REAL NOT NULL CHECK (recurring_pct BETWEEN 0.0 AND 100.0),
    new INTEGER NOT NULL DEFAULT 0 CHECK (new >= 0),
    churned INTEGER NOT NULL DEFAULT 0 CHECK (churned >= 0)
);

-- Handwritten mapping: Daily/weekly/monthly appointments
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    date TEXT NOT NULL,
    delivery_slot_id TEXT REFERENCES delivery_slots(slot_id),
    type TEXT NOT NULL CHECK (type IN ('subscription', 'one_off')),
    status TEXT NOT NULL CHECK (status IN ('confirmed', 'tentative', 'delivered', 'cancelled', 'refunded')),
    units INTEGER NOT NULL CHECK (units > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    amount REAL NOT NULL CHECK (amount >= 0),
    created_at TEXT NOT NULL
);

-- ----------------------------------------------------------------------------
-- 6. PROCUREMENT, LEDGERS & BUSINESS DOCUMENTS
-- ----------------------------------------------------------------------------
-- Handwritten mapping: Purchase history (cash)
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    order_date TEXT NOT NULL,
    expected_delivery_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('placed', 'received', 'cancelled')),
    total_taxable REAL NOT NULL CHECK (total_taxable >= 0),
    total_tax REAL NOT NULL CHECK (total_tax >= 0),
    total_amount REAL NOT NULL CHECK (total_amount >= 0),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
    line_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL REFERENCES purchase_orders(po_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    ordered_qty REAL NOT NULL CHECK (ordered_qty > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    tax_rate_pct REAL NOT NULL CHECK (tax_rate_pct >= 0),
    taxable_amount REAL NOT NULL CHECK (taxable_amount >= 0),
    tax_amount REAL NOT NULL CHECK (tax_amount >= 0),
    line_total REAL NOT NULL CHECK (line_total >= 0)
);

-- Handwritten mapping: Purchase history (cash)
CREATE TABLE IF NOT EXISTS purchase_history (
    purchase_id TEXT PRIMARY KEY,
    po_id TEXT REFERENCES purchase_orders(po_id),
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    purchase_date TEXT NOT NULL,
    qty REAL NOT NULL CHECK (qty > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    total_paid REAL NOT NULL CHECK (total_paid >= 0),
    payment_mode TEXT NOT NULL CHECK (payment_mode IN ('cash', 'UPI', 'credit', 'bank_transfer')),
    notes TEXT
);

-- Handwritten mapping: Business documents
CREATE TABLE IF NOT EXISTS business_documents (
    doc_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL CHECK (doc_type IN ('invoice', 'receipt', 'purchase_order', 'delivery_challan')),
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    po_id TEXT REFERENCES purchase_orders(po_id),
    doc_date TEXT NOT NULL,
    file_ref TEXT NOT NULL,
    extracted_json TEXT NOT NULL,
    extraction_confidence REAL NOT NULL CHECK (extraction_confidence BETWEEN 0.0 AND 1.0)
);

-- Handwritten mapping: Business documents (document lines)
CREATE TABLE IF NOT EXISTS document_lines (
    doc_line_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES business_documents(doc_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    billed_qty REAL NOT NULL CHECK (billed_qty > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    taxable_amount REAL NOT NULL CHECK (taxable_amount >= 0),
    gst_rate_pct REAL NOT NULL CHECK (gst_rate_pct >= 0),
    gst_amount REAL NOT NULL CHECK (gst_amount >= 0),
    total_line_amount REAL NOT NULL CHECK (total_line_amount >= 0)
);

-- Handwritten mapping: Business documents (reconciliation ground truth)
CREATE TABLE IF NOT EXISTS doc_ground_truth (
    truth_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES business_documents(doc_id),
    discrepancy_type TEXT NOT NULL CHECK (discrepancy_type IN ('quantity', 'tax_rate', 'price', 'duplicate', 'none')),
    field_name TEXT NOT NULL,
    expected_value TEXT NOT NULL,
    actual_value TEXT NOT NULL,
    difference_amount REAL NOT NULL DEFAULT 0,
    description TEXT NOT NULL
);

-- Handwritten mapping: Supplier-business & customer-business records
CREATE TABLE IF NOT EXISTS supplier_business_records (
    entry_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    date TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('invoice', 'payment', 'credit_note')),
    reference_doc TEXT,
    amount REAL NOT NULL CHECK (amount >= 0),
    balance_due REAL NOT NULL CHECK (balance_due >= 0),
    notes TEXT
);

-- Handwritten mapping: Supplier-business & customer-business records
CREATE TABLE IF NOT EXISTS customer_business_records (
    entry_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    date TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('order', 'payment', 'credit_note')),
    payment_mode TEXT CHECK (payment_mode IN ('UPI', 'cash', 'card', 'credit')),
    amount REAL NOT NULL CHECK (amount >= 0),
    balance_due REAL NOT NULL CHECK (balance_due >= 0),
    notes TEXT
);

-- ----------------------------------------------------------------------------
-- 7. METRICS & FINANCIALS
-- ----------------------------------------------------------------------------
-- Handwritten mapping: ARR + P&L + units sold + cash flow (date)
CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    units_sold INTEGER NOT NULL CHECK (units_sold >= 0),
    revenue REAL NOT NULL CHECK (revenue >= 0),
    cogs REAL NOT NULL CHECK (cogs >= 0),
    opex REAL NOT NULL CHECK (opex >= 0),
    net_profit REAL NOT NULL,
    cash_inflow REAL NOT NULL CHECK (cash_inflow >= 0),
    cash_outflow REAL NOT NULL CHECK (cash_outflow >= 0)
);

-- Handwritten mapping: ARR + P&L + units sold + cash flow (date)
CREATE TABLE IF NOT EXISTS monthly_metrics (
    month TEXT PRIMARY KEY, -- 'YYYY-MM'
    units_sold INTEGER NOT NULL CHECK (units_sold >= 0),
    revenue REAL NOT NULL CHECK (revenue >= 0),
    cogs REAL NOT NULL CHECK (cogs >= 0),
    opex REAL NOT NULL CHECK (opex >= 0),
    net_profit REAL NOT NULL,
    mrr REAL NOT NULL CHECK (mrr >= 0),
    arr REAL NOT NULL CHECK (arr >= 0)
);

-- ----------------------------------------------------------------------------
-- 8. CUSTOMER & SUPPLIER INTELLIGENCE, REVIEWS & SOCIAL
-- ----------------------------------------------------------------------------
-- Handwritten mapping: Potential customer demography
CREATE TABLE IF NOT EXISTS potential_customer_segments (
    locality TEXT NOT NULL,
    segment TEXT NOT NULL,
    est_households INTEGER NOT NULL CHECK (est_households > 0),
    budget_per_meal REAL NOT NULL CHECK (budget_per_meal > 0),
    meal_time_pref TEXT NOT NULL,
    interest_score REAL NOT NULL CHECK (interest_score BETWEEN 0.0 AND 1.0),
    distance_km REAL NOT NULL CHECK (distance_km >= 0),
    competitor_density TEXT NOT NULL,
    PRIMARY KEY (locality, segment)
);

-- Handwritten mapping: Customer reviews / Internet reviews
CREATE TABLE IF NOT EXISTS customer_reviews (
    review_id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES customers(customer_id),
    order_id TEXT REFERENCES orders(order_id),
    date TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'post_delivery_sms',
    sentiment TEXT NOT NULL CHECK (sentiment IN ('positive', 'neutral', 'negative'))
);

-- Handwritten mapping: Customer reviews / Internet reviews
CREATE TABLE IF NOT EXISTS internet_reviews (
    review_id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('Google', 'Zomato', 'Swiggy')),
    author_name TEXT NOT NULL,
    date TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text TEXT NOT NULL,
    sentiment TEXT NOT NULL CHECK (sentiment IN ('positive', 'neutral', 'negative'))
);

-- Handwritten mapping: Social media engagement
CREATE TABLE IF NOT EXISTS social_media_engagement (
    engagement_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('Instagram', 'WhatsApp Business', 'Facebook')),
    week_start TEXT NOT NULL,
    followers INTEGER NOT NULL CHECK (followers >= 0),
    reach INTEGER NOT NULL CHECK (reach >= 0),
    impressions INTEGER NOT NULL CHECK (impressions >= 0),
    likes INTEGER NOT NULL CHECK (likes >= 0),
    comments INTEGER NOT NULL CHECK (comments >= 0),
    shares INTEGER NOT NULL CHECK (shares >= 0),
    enquiries INTEGER NOT NULL CHECK (enquiries >= 0)
);

-- Handwritten mapping: Supplier updates
CREATE TABLE IF NOT EXISTS supplier_updates (
    update_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    date TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('price_change', 'delay', 'stockout', 'scheme')),
    message TEXT NOT NULL
);

-- Handwritten mapping: Customer updates
CREATE TABLE IF NOT EXISTS customer_updates (
    update_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    date TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('pause', 'resume', 'new_order', 'complaint', 'address_change', 'feedback')),
    message TEXT NOT NULL
);

-- ----------------------------------------------------------------------------
-- 9. BUSINESS MEMORY LAYER
-- ----------------------------------------------------------------------------
-- Ground-truth memory facts distinguishing verified records from owner statements
CREATE TABLE IF NOT EXISTS business_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('verified_record', 'owner_statement')),
    timestamp TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0)
);

-- ----------------------------------------------------------------------------
-- 10. REFERENCE PROCUREMENT PLANS (GROUND TRUTH BENCHMARKS)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_plans (
    plan_id TEXT PRIMARY KEY,
    plan_name TEXT NOT NULL,
    strategy TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_plan_lines (
    plan_line_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES reference_plans(plan_id),
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    pack_qty_ordered INTEGER NOT NULL CHECK (pack_qty_ordered > 0),
    unit_qty_equivalent REAL NOT NULL CHECK (unit_qty_equivalent > 0),
    price_per_pack REAL NOT NULL CHECK (price_per_pack >= 0),
    line_subtotal REAL NOT NULL CHECK (line_subtotal >= 0)
);

-- ----------------------------------------------------------------------------
-- 11. EMPTY WORKING TABLES (WRITE PATHS FOR ORCHESTRATOR & SIMULATOR)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS purchase_plans (
    plan_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    total_cost REAL NOT NULL CHECK (total_cost >= 0),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'executed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS purchase_plan_lines (
    line_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES purchase_plans(plan_id),
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    item_id TEXT NOT NULL REFERENCES items(item_id),
    pack_qty INTEGER NOT NULL CHECK (pack_qty > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    line_total REAL NOT NULL CHECK (line_total >= 0)
);

CREATE TABLE IF NOT EXISTS approvals (
    token TEXT PRIMARY KEY,
    plan_id TEXT REFERENCES purchase_plans(plan_id),
    total REAL NOT NULL CHECK (total >= 0),
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0 CHECK (used IN (0, 1))
);

CREATE TABLE IF NOT EXISTS capacity_declarations (
    declaration_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    slot_id TEXT REFERENCES delivery_slots(slot_id),
    declared_free_capacity INTEGER NOT NULL CHECK (declared_free_capacity >= 0),
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulated_orders (
    sim_order_id TEXT PRIMARY KEY,
    order_payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted', 'confirmed', 'failed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload TEXT,
    timestamp TEXT NOT NULL
);

-- ----------------------------------------------------------------------------
-- 12. PERFORMANCE INDEXES
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(date);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_slot ON orders(delivery_slot_id);
CREATE INDEX IF NOT EXISTS idx_delivery_slots_date ON delivery_slots(date);
CREATE INDEX IF NOT EXISTS idx_purchase_history_date ON purchase_history(purchase_date);
CREATE INDEX IF NOT EXISTS idx_purchase_history_item ON purchase_history(item_id);
CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(date);
CREATE INDEX IF NOT EXISTS idx_catalogue_supplier_item ON catalogue(supplier_id, item_id);
CREATE INDEX IF NOT EXISTS idx_doc_ground_truth_doc ON doc_ground_truth(doc_id);
CREATE INDEX IF NOT EXISTS idx_business_memory_key ON business_memory(key);
CREATE INDEX IF NOT EXISTS idx_supplier_business_records_supp ON supplier_business_records(supplier_id, date);
CREATE INDEX IF NOT EXISTS idx_customer_business_records_cust ON customer_business_records(customer_id, date);

