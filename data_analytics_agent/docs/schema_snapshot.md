# Database Schema Snapshot: demo_data/demo.db

This document records the exact introspected schema (`PRAGMA table_info`, `PRAGMA foreign_key_list`) from `demo_data/demo.db` as required by the Business Intel Agent specification.

**Total Tables:** 45  
**Total Views:** 9  

---

## Tables

### `approvals` (0 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `token` | TEXT | False | NULL | True |
| 1 | `plan_id` | TEXT | False | NULL | False |
| 2 | `total` | REAL | True | NULL | False |
| 3 | `expires_at` | TEXT | True | NULL | False |
| 4 | `used` | INTEGER | True | 0 | False |

**Foreign Keys:**
- `plan_id` -> `purchase_plans(plan_id)`

### `audit_log` (0 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `log_id` | INTEGER | False | NULL | True |
| 1 | `action` | TEXT | True | NULL | False |
| 2 | `actor` | TEXT | True | NULL | False |
| 3 | `payload` | TEXT | False | NULL | False |
| 4 | `timestamp` | TEXT | True | NULL | False |

### `business_documents` (2 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `doc_id` | TEXT | False | NULL | True |
| 1 | `doc_type` | TEXT | True | NULL | False |
| 2 | `supplier_id` | TEXT | True | NULL | False |
| 3 | `po_id` | TEXT | False | NULL | False |
| 4 | `doc_date` | TEXT | True | NULL | False |
| 5 | `file_ref` | TEXT | True | NULL | False |
| 6 | `extracted_json` | TEXT | True | NULL | False |
| 7 | `extraction_confidence` | REAL | True | NULL | False |

**Foreign Keys:**
- `po_id` -> `purchase_orders(po_id)`
- `supplier_id` -> `suppliers(supplier_id)`

### `business_memory` (5 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `id` | INTEGER | False | NULL | True |
| 1 | `key` | TEXT | True | NULL | False |
| 2 | `value` | TEXT | True | NULL | False |
| 3 | `source` | TEXT | True | NULL | False |
| 4 | `timestamp` | TEXT | True | NULL | False |
| 5 | `confidence` | REAL | True | NULL | False |

### `business_policy` (1 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `policy_id` | INTEGER | False | NULL | True |
| 1 | `min_cash_buffer` | REAL | True | NULL | False |
| 2 | `safety_stock_pct` | REAL | True | NULL | False |
| 3 | `regular_order_cutoff` | TEXT | True | NULL | False |
| 4 | `cooking_start` | TEXT | True | NULL | False |
| 5 | `packing_start` | TEXT | True | NULL | False |
| 6 | `max_meals_per_day` | INTEGER | True | NULL | False |
| 7 | `fast_delivery_fee` | REAL | True | NULL | False |
| 8 | `stockout_cost_per_meal` | REAL | True | NULL | False |

### `business_profile` (1 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `business_name` | TEXT | False | NULL | True |
| 1 | `archetype` | TEXT | True | NULL | False |
| 2 | `owner_name` | TEXT | True | NULL | False |
| 3 | `locality` | TEXT | True | NULL | False |
| 4 | `city` | TEXT | True | NULL | False |
| 5 | `state` | TEXT | True | NULL | False |
| 6 | `gstin` | TEXT | True | NULL | False |
| 7 | `phone` | TEXT | True | NULL | False |
| 8 | `currency` | TEXT | True | 'INR' | False |
| 9 | `as_of` | TEXT | True | NULL | False |
| 10 | `is_synthetic` | INTEGER | True | 1 | False |

### `capacity` (105 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `date` | TEXT | False | NULL | True |
| 1 | `max_meals` | INTEGER | True | NULL | False |
| 2 | `cook_hours` | REAL | True | NULL | False |

### `capacity_declarations` (0 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `declaration_id` | TEXT | False | NULL | True |
| 1 | `date` | TEXT | True | NULL | False |
| 2 | `slot_id` | TEXT | False | NULL | False |
| 3 | `declared_free_capacity` | INTEGER | True | NULL | False |
| 4 | `notes` | TEXT | False | NULL | False |
| 5 | `created_at` | TEXT | True | NULL | False |

**Foreign Keys:**
- `slot_id` -> `delivery_slots(slot_id)`

### `cash_position` (1 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `as_of` | TEXT | False | NULL | True |
| 1 | `current_balance` | REAL | True | NULL | False |
| 2 | `min_cash_buffer` | REAL | True | NULL | False |

### `catalogue` (17 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `supplier_id` | TEXT | True | NULL | True |
| 1 | `item_id` | TEXT | True | NULL | True |
| 2 | `pack_label` | TEXT | True | NULL | False |
| 3 | `pack_qty` | REAL | True | NULL | False |
| 4 | `price_per_pack` | REAL | True | NULL | False |
| 5 | `price_per_unit` | REAL | True | NULL | False |
| 6 | `eta_minutes` | INTEGER | True | NULL | False |
| 7 | `in_stock` | INTEGER | True | NULL | False |
| 8 | `is_simulated` | INTEGER | True | 0 | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`
- `supplier_id` -> `suppliers(supplier_id)`

### `customer_business_records` (77 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `entry_id` | TEXT | False | NULL | True |
| 1 | `customer_id` | TEXT | True | NULL | False |
| 2 | `date` | TEXT | True | NULL | False |
| 3 | `entry_type` | TEXT | True | NULL | False |
| 4 | `payment_mode` | TEXT | False | NULL | False |
| 5 | `amount` | REAL | True | NULL | False |
| 6 | `balance_due` | REAL | True | NULL | False |
| 7 | `notes` | TEXT | False | NULL | False |

**Foreign Keys:**
- `customer_id` -> `customers(customer_id)`

### `customer_metrics` (91 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `date` | TEXT | False | NULL | True |
| 1 | `current_customers` | INTEGER | True | NULL | False |
| 2 | `recurring_customers` | INTEGER | True | NULL | False |
| 3 | `recurring_pct` | REAL | True | NULL | False |
| 4 | `new` | INTEGER | True | 0 | False |
| 5 | `churned` | INTEGER | True | 0 | False |

### `customer_reviews` (150 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `review_id` | TEXT | False | NULL | True |
| 1 | `customer_id` | TEXT | False | NULL | False |
| 2 | `order_id` | TEXT | False | NULL | False |
| 3 | `date` | TEXT | True | NULL | False |
| 4 | `rating` | INTEGER | True | NULL | False |
| 5 | `review_text` | TEXT | True | NULL | False |
| 6 | `channel` | TEXT | True | 'post_delivery_sms' | False |
| 7 | `sentiment` | TEXT | True | NULL | False |

**Foreign Keys:**
- `order_id` -> `orders(order_id)`
- `customer_id` -> `customers(customer_id)`

### `customer_updates` (120 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `update_id` | TEXT | False | NULL | True |
| 1 | `customer_id` | TEXT | True | NULL | False |
| 2 | `date` | TEXT | True | NULL | False |
| 3 | `type` | TEXT | True | NULL | False |
| 4 | `message` | TEXT | True | NULL | False |

**Foreign Keys:**
- `customer_id` -> `customers(customer_id)`

### `customers` (136 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `customer_id` | TEXT | False | NULL | True |
| 1 | `name` | TEXT | True | NULL | False |
| 2 | `segment` | TEXT | True | NULL | False |
| 3 | `locality` | TEXT | True | NULL | False |
| 4 | `phone` | TEXT | True | NULL | False |
| 5 | `joined_date` | TEXT | True | NULL | False |
| 6 | `is_recurring` | INTEGER | True | NULL | False |
| 7 | `status` | TEXT | True | NULL | False |
| 8 | `is_synthetic` | INTEGER | True | 1 | False |

### `daily_metrics` (91 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `date` | TEXT | False | NULL | True |
| 1 | `units_sold` | INTEGER | True | NULL | False |
| 2 | `revenue` | REAL | True | NULL | False |
| 3 | `cogs` | REAL | True | NULL | False |
| 4 | `opex` | REAL | True | NULL | False |
| 5 | `net_profit` | REAL | True | NULL | False |
| 6 | `cash_inflow` | REAL | True | NULL | False |
| 7 | `cash_outflow` | REAL | True | NULL | False |

### `delivery_slots` (420 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `slot_id` | TEXT | False | NULL | True |
| 1 | `date` | TEXT | True | NULL | False |
| 2 | `slot_label` | TEXT | True | NULL | False |
| 3 | `start_time` | TEXT | True | NULL | False |
| 4 | `end_time` | TEXT | True | NULL | False |
| 5 | `capacity_units` | INTEGER | True | NULL | False |
| 6 | `booked_units` | INTEGER | True | NULL | False |

### `demand_drivers` (105 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `date` | TEXT | False | NULL | True |
| 1 | `day_of_week` | TEXT | True | NULL | False |
| 2 | `is_holiday` | INTEGER | True | 0 | False |
| 3 | `festival` | TEXT | False | NULL | False |
| 4 | `weather_note` | TEXT | False | NULL | False |
| 5 | `local_event` | TEXT | False | NULL | False |
| 6 | `subscription_pauses` | INTEGER | True | 0 | False |

### `demand_forecast` (105 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `date` | TEXT | False | NULL | True |
| 1 | `units_forecast` | REAL | True | NULL | False |
| 2 | `lower` | REAL | True | NULL | False |
| 3 | `upper` | REAL | True | NULL | False |
| 4 | `confidence` | REAL | True | NULL | False |
| 5 | `method` | TEXT | True | NULL | False |

**Foreign Keys:**
- `date` -> `demand_drivers(date)`

### `doc_ground_truth` (2 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `truth_id` | TEXT | False | NULL | True |
| 1 | `doc_id` | TEXT | True | NULL | False |
| 2 | `discrepancy_type` | TEXT | True | NULL | False |
| 3 | `field_name` | TEXT | True | NULL | False |
| 4 | `expected_value` | TEXT | True | NULL | False |
| 5 | `actual_value` | TEXT | True | NULL | False |
| 6 | `difference_amount` | REAL | True | 0 | False |
| 7 | `description` | TEXT | True | NULL | False |

**Foreign Keys:**
- `doc_id` -> `business_documents(doc_id)`

### `document_lines` (2 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `doc_line_id` | TEXT | False | NULL | True |
| 1 | `doc_id` | TEXT | True | NULL | False |
| 2 | `item_id` | TEXT | True | NULL | False |
| 3 | `billed_qty` | REAL | True | NULL | False |
| 4 | `unit_price` | REAL | True | NULL | False |
| 5 | `taxable_amount` | REAL | True | NULL | False |
| 6 | `gst_rate_pct` | REAL | True | NULL | False |
| 7 | `gst_amount` | REAL | True | NULL | False |
| 8 | `total_line_amount` | REAL | True | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`
- `doc_id` -> `business_documents(doc_id)`

### `forecasted_balance` (15 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `date` | TEXT | False | NULL | True |
| 1 | `expected_inflow` | REAL | True | NULL | False |
| 2 | `expected_outflow` | REAL | True | NULL | False |
| 3 | `projected_balance` | REAL | True | NULL | False |
| 4 | `confidence` | REAL | True | NULL | False |

### `internet_reviews` (40 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `review_id` | TEXT | False | NULL | True |
| 1 | `source` | TEXT | True | NULL | False |
| 2 | `author_name` | TEXT | True | NULL | False |
| 3 | `date` | TEXT | True | NULL | False |
| 4 | `rating` | INTEGER | True | NULL | False |
| 5 | `text` | TEXT | True | NULL | False |
| 6 | `sentiment` | TEXT | True | NULL | False |

### `inventory_stock` (9 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `item_id` | TEXT | False | NULL | True |
| 1 | `stock_qty` | REAL | True | NULL | False |
| 2 | `last_restocked_date` | TEXT | False | NULL | False |
| 3 | `last_restocked_qty` | REAL | False | NULL | False |
| 4 | `refresh_forecast_date` | TEXT | False | NULL | False |
| 5 | `refresh_forecast_qty` | REAL | False | NULL | False |
| 6 | `as_of` | TEXT | True | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`

### `items` (9 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `item_id` | TEXT | False | NULL | True |
| 1 | `name` | TEXT | True | NULL | False |
| 2 | `unit` | TEXT | True | NULL | False |
| 3 | `reorder_point` | REAL | True | NULL | False |
| 4 | `par_level` | REAL | True | NULL | False |
| 5 | `procure_mode` | TEXT | True | 'catalogue' | False |
| 6 | `is_bom_item` | INTEGER | True | 1 | False |

### `meta` (8 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `key` | TEXT | False | NULL | True |
| 1 | `value` | TEXT | True | NULL | False |

### `monthly_metrics` (13 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `month` | TEXT | False | NULL | True |
| 1 | `units_sold` | INTEGER | True | NULL | False |
| 2 | `revenue` | REAL | True | NULL | False |
| 3 | `cogs` | REAL | True | NULL | False |
| 4 | `opex` | REAL | True | NULL | False |
| 5 | `net_profit` | REAL | True | NULL | False |
| 6 | `mrr` | REAL | True | NULL | False |
| 7 | `arr` | REAL | True | NULL | False |

### `orders` (2231 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `order_id` | TEXT | False | NULL | True |
| 1 | `customer_id` | TEXT | True | NULL | False |
| 2 | `date` | TEXT | True | NULL | False |
| 3 | `delivery_slot_id` | TEXT | False | NULL | False |
| 4 | `type` | TEXT | True | NULL | False |
| 5 | `status` | TEXT | True | NULL | False |
| 6 | `units` | INTEGER | True | NULL | False |
| 7 | `unit_price` | REAL | True | NULL | False |
| 8 | `amount` | REAL | True | NULL | False |
| 9 | `created_at` | TEXT | True | NULL | False |

**Foreign Keys:**
- `delivery_slot_id` -> `delivery_slots(slot_id)`
- `customer_id` -> `customers(customer_id)`

### `potential_customer_segments` (12 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `locality` | TEXT | True | NULL | True |
| 1 | `segment` | TEXT | True | NULL | True |
| 2 | `est_households` | INTEGER | True | NULL | False |
| 3 | `budget_per_meal` | REAL | True | NULL | False |
| 4 | `meal_time_pref` | TEXT | True | NULL | False |
| 5 | `interest_score` | REAL | True | NULL | False |
| 6 | `distance_km` | REAL | True | NULL | False |
| 7 | `competitor_density` | TEXT | True | NULL | False |

### `purchase_history` (113 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `purchase_id` | TEXT | False | NULL | True |
| 1 | `po_id` | TEXT | False | NULL | False |
| 2 | `supplier_id` | TEXT | True | NULL | False |
| 3 | `item_id` | TEXT | True | NULL | False |
| 4 | `purchase_date` | TEXT | True | NULL | False |
| 5 | `qty` | REAL | True | NULL | False |
| 6 | `unit_price` | REAL | True | NULL | False |
| 7 | `total_paid` | REAL | True | NULL | False |
| 8 | `payment_mode` | TEXT | True | NULL | False |
| 9 | `notes` | TEXT | False | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`
- `supplier_id` -> `suppliers(supplier_id)`
- `po_id` -> `purchase_orders(po_id)`

### `purchase_order_lines` (23 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `line_id` | TEXT | False | NULL | True |
| 1 | `po_id` | TEXT | True | NULL | False |
| 2 | `item_id` | TEXT | True | NULL | False |
| 3 | `ordered_qty` | REAL | True | NULL | False |
| 4 | `unit_price` | REAL | True | NULL | False |
| 5 | `tax_rate_pct` | REAL | True | NULL | False |
| 6 | `taxable_amount` | REAL | True | NULL | False |
| 7 | `tax_amount` | REAL | True | NULL | False |
| 8 | `line_total` | REAL | True | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`
- `po_id` -> `purchase_orders(po_id)`

### `purchase_orders` (23 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `po_id` | TEXT | False | NULL | True |
| 1 | `supplier_id` | TEXT | True | NULL | False |
| 2 | `order_date` | TEXT | True | NULL | False |
| 3 | `expected_delivery_date` | TEXT | False | NULL | False |
| 4 | `status` | TEXT | True | NULL | False |
| 5 | `total_taxable` | REAL | True | NULL | False |
| 6 | `total_tax` | REAL | True | NULL | False |
| 7 | `total_amount` | REAL | True | NULL | False |
| 8 | `notes` | TEXT | False | NULL | False |

**Foreign Keys:**
- `supplier_id` -> `suppliers(supplier_id)`

### `purchase_plan_lines` (0 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `line_id` | TEXT | False | NULL | True |
| 1 | `plan_id` | TEXT | True | NULL | False |
| 2 | `supplier_id` | TEXT | True | NULL | False |
| 3 | `item_id` | TEXT | True | NULL | False |
| 4 | `pack_qty` | INTEGER | True | NULL | False |
| 5 | `unit_price` | REAL | True | NULL | False |
| 6 | `line_total` | REAL | True | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`
- `supplier_id` -> `suppliers(supplier_id)`
- `plan_id` -> `purchase_plans(plan_id)`

### `purchase_plans` (0 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `plan_id` | TEXT | False | NULL | True |
| 1 | `created_at` | TEXT | True | NULL | False |
| 2 | `total_cost` | REAL | True | NULL | False |
| 3 | `status` | TEXT | True | 'draft' | False |

### `recipe_bom` (8 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `item_id` | TEXT | False | NULL | True |
| 1 | `qty_per_tiffin` | REAL | True | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`

### `reference_plan_lines` (12 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `plan_line_id` | TEXT | False | NULL | True |
| 1 | `plan_id` | TEXT | True | NULL | False |
| 2 | `supplier_id` | TEXT | True | NULL | False |
| 3 | `item_id` | TEXT | True | NULL | False |
| 4 | `pack_qty_ordered` | INTEGER | True | NULL | False |
| 5 | `unit_qty_equivalent` | REAL | True | NULL | False |
| 6 | `price_per_pack` | REAL | True | NULL | False |
| 7 | `line_subtotal` | REAL | True | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`
- `supplier_id` -> `suppliers(supplier_id)`
- `plan_id` -> `reference_plans(plan_id)`

### `reference_plans` (3 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `plan_id` | TEXT | False | NULL | True |
| 1 | `plan_name` | TEXT | True | NULL | False |
| 2 | `strategy` | TEXT | True | NULL | False |
| 3 | `description` | TEXT | True | NULL | False |

### `simulated_orders` (0 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `sim_order_id` | TEXT | False | NULL | True |
| 1 | `order_payload` | TEXT | True | NULL | False |
| 2 | `status` | TEXT | True | 'submitted' | False |
| 3 | `created_at` | TEXT | True | NULL | False |

### `social_media_engagement` (39 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `engagement_id` | TEXT | False | NULL | True |
| 1 | `platform` | TEXT | True | NULL | False |
| 2 | `week_start` | TEXT | True | NULL | False |
| 3 | `followers` | INTEGER | True | NULL | False |
| 4 | `reach` | INTEGER | True | NULL | False |
| 5 | `impressions` | INTEGER | True | NULL | False |
| 6 | `likes` | INTEGER | True | NULL | False |
| 7 | `comments` | INTEGER | True | NULL | False |
| 8 | `shares` | INTEGER | True | NULL | False |
| 9 | `enquiries` | INTEGER | True | NULL | False |

### `supplier_business_records` (6 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `entry_id` | TEXT | False | NULL | True |
| 1 | `supplier_id` | TEXT | True | NULL | False |
| 2 | `date` | TEXT | True | NULL | False |
| 3 | `entry_type` | TEXT | True | NULL | False |
| 4 | `reference_doc` | TEXT | False | NULL | False |
| 5 | `amount` | REAL | True | NULL | False |
| 6 | `balance_due` | REAL | True | NULL | False |
| 7 | `notes` | TEXT | False | NULL | False |

**Foreign Keys:**
- `supplier_id` -> `suppliers(supplier_id)`

### `supplier_inventory_info` (17 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `supplier_id` | TEXT | True | NULL | True |
| 1 | `item_id` | TEXT | True | NULL | True |
| 2 | `in_stock` | INTEGER | True | NULL | False |
| 3 | `available_qty` | REAL | False | NULL | False |
| 4 | `restock_expected_date` | TEXT | False | NULL | False |
| 5 | `as_of` | TEXT | True | NULL | False |
| 6 | `note` | TEXT | False | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`
- `supplier_id` -> `suppliers(supplier_id)`

### `supplier_price_history` (148 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `id` | INTEGER | False | NULL | True |
| 1 | `supplier_id` | TEXT | True | NULL | False |
| 2 | `item_id` | TEXT | True | NULL | False |
| 3 | `effective_date` | TEXT | True | NULL | False |
| 4 | `price_per_pack` | REAL | True | NULL | False |
| 5 | `price_per_unit` | REAL | True | NULL | False |
| 6 | `change_reason` | TEXT | False | NULL | False |

**Foreign Keys:**
- `item_id` -> `items(item_id)`
- `supplier_id` -> `suppliers(supplier_id)`

### `supplier_updates` (25 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `update_id` | TEXT | False | NULL | True |
| 1 | `supplier_id` | TEXT | True | NULL | False |
| 2 | `date` | TEXT | True | NULL | False |
| 3 | `type` | TEXT | True | NULL | False |
| 4 | `message` | TEXT | True | NULL | False |

**Foreign Keys:**
- `supplier_id` -> `suppliers(supplier_id)`

### `suppliers` (4 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `supplier_id` | TEXT | False | NULL | True |
| 1 | `name` | TEXT | True | NULL | False |
| 2 | `category` | TEXT | True | NULL | False |
| 3 | `cutoff_time` | TEXT | False | NULL | False |
| 4 | `delivery_window` | TEXT | True | NULL | False |
| 5 | `delivery_fee` | REAL | True | 0 | False |
| 6 | `free_delivery_threshold` | REAL | False | NULL | False |
| 7 | `credit_days` | INTEGER | True | 0 | False |
| 8 | `reliability` | REAL | True | NULL | False |
| 9 | `is_simulated` | INTEGER | True | 0 | False |
| 10 | `contact_phone` | TEXT | False | NULL | False |
| 11 | `gstin` | TEXT | False | NULL | False |
| 12 | `locality` | TEXT | False | NULL | False |
| 13 | `is_synthetic` | INTEGER | True | 1 | False |

### `upcoming_payments` (5 rows)

| # | Column | Type | NotNull | Default | PK |
|---|---|---|---|---|---|
| 0 | `payment_id` | TEXT | False | NULL | True |
| 1 | `payee` | TEXT | True | NULL | False |
| 2 | `category` | TEXT | True | NULL | False |
| 3 | `amount` | REAL | True | NULL | False |
| 4 | `due_date` | TEXT | True | NULL | False |
| 5 | `status` | TEXT | True | 'pending' | False |

---

## Views

### `v_below_reorder_after_tomorrow`
```sql
CREATE VIEW v_below_reorder_after_tomorrow AS
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
  AND (current_stock - effective_requirement) < reorder_point
```

### `v_capacity_free_slots`
```sql
CREATE VIEW v_capacity_free_slots AS
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
ORDER BY ds.start_time
```

### `v_cash_headroom`
```sql
CREATE VIEW v_cash_headroom AS
SELECT
    (SELECT current_balance FROM cash_position WHERE as_of = (SELECT value FROM meta WHERE key = 'as_of')) AS current_balance,
    bp.min_cash_buffer,
    MIN(fb.projected_balance) AS min_projected_balance,
    MIN(fb.projected_balance) - bp.min_cash_buffer AS cash_headroom,
    (SELECT date FROM forecasted_balance WHERE projected_balance = (SELECT MIN(projected_balance) FROM forecasted_balance) LIMIT 1) AS lowest_balance_date
FROM forecasted_balance fb
CROSS JOIN business_policy bp
```

### `v_customer_snapshot`
```sql
CREATE VIEW v_customer_snapshot AS
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
FROM customers
```

### `v_item_requirement_tomorrow`
```sql
CREATE VIEW v_item_requirement_tomorrow AS
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
JOIN inventory_stock s ON i.item_id = s.item_id
```

### `v_memory_conflicts`
```sql
CREATE VIEW v_memory_conflicts AS
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
WHERE m1.value != m2.value
```

### `v_plan_cost`
```sql
CREATE VIEW v_plan_cost AS
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
FROM plan_totals pt
```

### `v_shortfall_tomorrow`
```sql
CREATE VIEW v_shortfall_tomorrow AS
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
WHERE effective_requirement > current_stock
```

### `v_supplier_options`
```sql
CREATE VIEW v_supplier_options AS
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
JOIN items i ON c.item_id = i.item_id
```
