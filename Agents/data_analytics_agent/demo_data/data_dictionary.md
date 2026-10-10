# Alexa Business Autopilot: Comprehensive Data Dictionary

This document provides the definitive data dictionary for the synthetic test dataset developed for **Alexa Business Autopilot**, a voice-first business agent tailored for Indian owner-operated small businesses. The reference archetype is **Maa Ki Rasoi Cloud Kitchen**, a cloud kitchen / tiffin service operating in Kakadeo, Kanpur, Uttar Pradesh.

---

## 1. Mapping of Handwritten Field Notes to Schema

The table below maps every single item from the business owner's handwritten specification (found in the hackathon brief, page 8) directly to its relational database table and column(s):

| Handwritten Field | Table.Column(s) | Description & Role in Decision Loop |
|---|---|---|
| **Demand_variables** | `demand_drivers.date`, `demand_drivers.day_of_week`, `demand_drivers.is_holiday`, `demand_drivers.festival`, `demand_drivers.weather_note`, `demand_drivers.local_event`, `demand_drivers.subscription_pauses`, `demand_forecast.units_forecast`, `demand_forecast.lower`, `demand_forecast.upper`, `demand_forecast.confidence`, `demand_forecast.method` | Exogenous demand drivers, calendar events (e.g. Navratri, Dussehra), weather, coaching schedules in Kakadeo, and statistical demand forecasts with upper/lower uncertainty bounds. |
| **Inventory stock (qty)** | `inventory_stock.stock_qty` | Instantaneous physical stock quantity on-hand as of the frozen clock (`2026-10-10T19:10:00+05:30`). |
| **Inventory last restocked (date, qty)** | `inventory_stock.last_restocked_date`, `inventory_stock.last_restocked_qty` | Date and batch quantity of the most recent physical inventory delivery for each ingredient/packaging SKU. |
| **Inventory refresh forecast / bulk order schedule (date, qty)** | `inventory_stock.refresh_forecast_date`, `inventory_stock.refresh_forecast_qty` | Scheduled bulk order replenishment date and expected quantity. Used by the agent to prevent redundant ordering if a regular delivery is already planned. |
| **Any info on supplier inventory** | `supplier_inventory_info.supplier_id`, `supplier_inventory_info.item_id`, `supplier_inventory_info.in_stock`, `supplier_inventory_info.available_qty`, `supplier_inventory_info.restock_expected_date`, `supplier_inventory_info.as_of`, `supplier_inventory_info.note` | Real-time visibility into supplier stock levels, warehouse stockouts (e.g. SUP-01 oil outage), and next expected availability dates. |
| **Current balance (cash)** | `cash_position.as_of`, `cash_position.current_balance`, `cash_position.min_cash_buffer` | Liquid bank and cash balance as of the frozen timestamp, alongside the business's policy minimum safety liquidity buffer (₹5,000). |
| **Purchase history (cash)** | `purchase_history.purchase_id`, `purchase_history.po_id`, `purchase_history.supplier_id`, `purchase_history.item_id`, `purchase_history.purchase_date`, `purchase_history.qty`, `purchase_history.unit_price`, `purchase_history.total_paid`, `purchase_history.payment_mode`, `purchase_orders.*`, `purchase_order_lines.*` | Detailed chronological procurement history over 90 days, payment channels (cash, UPI, credit), and line-level item pricing. |
| **Forecasted balance (cash)** | `forecasted_balance.date`, `forecasted_balance.expected_inflow`, `forecasted_balance.expected_outflow`, `forecasted_balance.projected_balance`, `forecasted_balance.confidence` | Forward-looking 15-day rolling cash flow projection from 2026-10-10 to 2026-10-24, modeling daily inflows, payroll, supplier dues, rent, and utilities. |
| **Item-price mappings / catalogue** | `items.item_id`, `items.name`, `items.unit`, `items.reorder_point`, `items.par_level`, `items.procure_mode`, `catalogue.supplier_id`, `catalogue.item_id`, `catalogue.pack_label`, `catalogue.pack_qty`, `catalogue.price_per_pack`, `catalogue.price_per_unit`, `catalogue.eta_minutes`, `catalogue.in_stock`, `catalogue.is_simulated`, `supplier_price_history.*` | Supplier price books, pack sizes, delivery ETAs, unit prices (GST-inclusive), and price trend tracking over time. |
| **Supplier updates** | `supplier_updates.update_id`, `supplier_updates.supplier_id`, `supplier_updates.date`, `supplier_updates.type`, `supplier_updates.message` | Real-time supplier announcements: price hikes (Gupta oil), delivery delays (Packaging Mart breakdown), stockouts (Sharma oil), and promotional schemes (QuickKart). |
| **Customer updates** | `customer_updates.update_id`, `customer_updates.customer_id`, `customer_updates.date`, `customer_updates.type`, `customer_updates.message` | Natural language WhatsApp/phone requests from tiffin customers in Hinglish (subscription pauses, address updates, taste preferences, feedback). |
| **Daily/weekly/monthly appointments** | `orders.order_id`, `orders.customer_id`, `orders.date`, `orders.delivery_slot_id`, `orders.type`, `orders.status`, `orders.units`, `orders.amount`, `delivery_slots.*`, `capacity.*` | Customer meal delivery bookings, slot time windows (11:00-15:00), kitchen meal capacity limits (40 meals/day), and unbooked slot capacity. |
| **ARR + P&L + units sold + cash flow (date)** | `daily_metrics.date`, `daily_metrics.units_sold`, `daily_metrics.revenue`, `daily_metrics.cogs`, `daily_metrics.opex`, `daily_metrics.net_profit`, `daily_metrics.cash_inflow`, `daily_metrics.cash_outflow`, `monthly_metrics.month`, `monthly_metrics.mrr`, `monthly_metrics.arr` | Comprehensive daily and monthly financial performance metrics: revenue, COGS, operating expenses, net margins, MRR, and ARR run-rates. |
| **Business documents** | `business_documents.doc_id`, `business_documents.doc_type`, `business_documents.supplier_id`, `business_documents.po_id`, `business_documents.doc_date`, `business_documents.file_ref`, `business_documents.extracted_json`, `business_documents.extraction_confidence`, `document_lines.*`, `doc_ground_truth.*` | Multimodal invoice and receipt uploads, OCR/extraction payloads, line items, and ground-truth discrepancy reconciliation records. |
| **Current customers (numbers), % recurring** | `customer_metrics.date`, `customer_metrics.current_customers`, `customer_metrics.recurring_customers`, `customer_metrics.recurring_pct`, `customer_metrics.new`, `customer_metrics.churned`, `customers.*` | Customer base tracking: live active customers (96), recurring subscription holders (62), recurring customer percentage (64.6%), and cohort status. |
| **Potential customer demography** | `potential_customer_segments.locality`, `potential_customer_segments.segment`, `potential_customer_segments.est_households`, `potential_customer_segments.budget_per_meal`, `potential_customer_segments.meal_time_pref`, `potential_customer_segments.interest_score`, `potential_customer_segments.distance_km`, `potential_customer_segments.competitor_density` | Demographic data for local customer acquisition and capacity matching in Kanpur (Kakadeo coaching students, Civil Lines bankers, Swaroop Nagar corporate). |
| **Customer reviews / Internet reviews** | `customer_reviews.review_id`, `customer_reviews.rating`, `customer_reviews.review_text`, `customer_reviews.sentiment`, `internet_reviews.source`, `internet_reviews.author_name`, `internet_reviews.rating`, `internet_reviews.text`, `internet_reviews.sentiment` | Internal feedback via SMS/WhatsApp alongside external public platform reviews (Google, Zomato, Swiggy) covering taste, delivery timing, and leaky packaging. |
| **Social media engagement** | `social_media_engagement.engagement_id`, `social_media_engagement.platform`, `social_media_engagement.week_start`, `social_media_engagement.followers`, `social_media_engagement.reach`, `social_media_engagement.impressions`, `social_media_engagement.likes`, `social_media_engagement.comments`, `social_media_engagement.shares`, `social_media_engagement.enquiries` | Weekly social media performance across Instagram, WhatsApp Business, and Facebook, highlighting seasonal festival engagement spikes. |
| **Supplier-business & customer-business records** | `supplier_business_records.entry_id`, `supplier_business_records.supplier_id`, `supplier_business_records.entry_type`, `supplier_business_records.amount`, `supplier_business_records.balance_due`, `customer_business_records.*` | Dual ledgers tracking invoices, partial payments, credit notes, customer credit balances, and open supplier dues (e.g. Sharma dues of ₹4,200). |

---

## 2. Table-by-Table Schema Specification

### 2.1 System Metadata & Configuration

#### `meta`
- **Purpose**: System-wide key-value storage for the frozen evaluation environment. Ensures deterministic replay without accessing the host operating system clock.
- **Columns**:
  - `key` (TEXT, PK): Unique metadata identifier (`as_of`, `frozen_date`, `tomorrow_date`, `single_menu_item`, etc.).
  - `value` (TEXT): Stored value (e.g. `'2026-10-10T19:10:00+05:30'`).

#### `business_profile`
- **Purpose**: High-level legal, geographic, and tax profile of the enterprise.
- **Columns**:
  - `business_name` (TEXT, PK): "Maa Ki Rasoi Cloud Kitchen".
  - `archetype` (TEXT): "tiffin / cloud kitchen".
  - `owner_name` (TEXT): "Sunita Sharma".
  - `locality`, `city`, `state` (TEXT): "Kakadeo", "Kanpur", "Uttar Pradesh".
  - `gstin` (TEXT): "09ZZZZZ9999Z1Z5" (synthetic).
  - `phone` (TEXT): "+91 XXXXXX4821" (masked).
  - `currency` (TEXT): 'INR'.
  - `as_of` (TEXT): ISO-8601 timestamp.
  - `is_synthetic` (INTEGER): 1.

#### `business_policy`
- **Purpose**: Operating policy guardrails governing kitchen production and liquidity.
- **Columns**:
  - `policy_id` (INTEGER, PK): Primary key (1).
  - `min_cash_buffer` (REAL): Mandatory liquidity buffer (₹5,000.0).
  - `safety_stock_pct` (REAL): Buffer percentage over demand forecast (10.0%).
  - `regular_order_cutoff` (TEXT): Wholesaler daily order deadline ('20:00').
  - `cooking_start` (TEXT): Kitchen morning cooking start time ('09:00').
  - `packing_start` (TEXT): Meal packaging start time ('11:00').
  - `max_meals_per_day` (INTEGER): Daily kitchen capacity (40 meals).
  - `fast_delivery_fee` (REAL): Expedited logistics fee (₹49.0 on carts < ₹2,500).
  - `stockout_cost_per_meal` (REAL): Opportunity and penalty cost per missed meal (₹90.0).

---

### 2.2 Suppliers, Inventory & Catalogue

#### `suppliers`
- **Purpose**: Commercial registry of wholesale, packaging, and quick-commerce vendors.
- **Columns**:
  - `supplier_id` (TEXT, PK): Unique supplier code (`SUP-01` to `SUP-04`).
  - `name` (TEXT): Commercial name.
  - `category` (TEXT): Wholesaler, packaging vendor, distributor, or quick-commerce actuator.
  - `cutoff_time` (TEXT): Order cutoff time for next-day dispatch.
  - `delivery_window` (TEXT): Expected dispatch window or SLA.
  - `delivery_fee` (REAL): Baseline delivery fee.
  - `free_delivery_threshold` (REAL): Minimum order value for free delivery.
  - `credit_days` (INTEGER): Credit period allowed (e.g. 7 days, 15 days).
  - `reliability` (REAL): Historical reliability score between 0.0 and 1.0.
  - `is_simulated` (INTEGER): 1 for simulated quick-commerce actuators (`SUP-04`), 0 for physical vendors.

#### `items`
- **Purpose**: Master inventory catalogue of ingredients and packaging SKUs.
- **Columns**:
  - `item_id` (TEXT, PK): SKU identifier (`OIL-SUN-1L`, `CONT-750`, `ATTA-10`, etc.).
  - `name` (TEXT): Item description.
  - `unit` (TEXT): Measurement unit ('L', 'kg', 'pcs').
  - `reorder_point` (REAL): Minimum inventory threshold triggering replenishment.
  - `par_level` (REAL): Target full-stock level.
  - `procure_mode` (TEXT): 'catalogue', 'daily_mandi', or 'specialty'.
  - `is_bom_item` (INTEGER): 1 if included in standard veg tiffin recipe, 0 otherwise (e.g. Ghee).

#### `recipe_bom`
- **Purpose**: Bill of Materials specifying exact ingredient/packaging consumption per Standard Veg Tiffin.
- **Columns**:
  - `item_id` (TEXT, PK, FK -> `items.item_id`): Component SKU.
  - `qty_per_tiffin` (REAL): Quantity consumed per single tiffin meal.

#### `inventory_stock`
- **Purpose**: Current on-hand stock and replenishment schedule as of the frozen clock.
- **Columns**:
  - `item_id` (TEXT, PK, FK -> `items.item_id`): Component SKU.
  - `stock_qty` (REAL): Physical quantity on-hand.
  - `last_restocked_date` (TEXT): Date of most recent arrival.
  - `last_restocked_qty` (REAL): Batch quantity arrived.
  - `refresh_forecast_date` (TEXT): Next scheduled regular bulk order date.
  - `refresh_forecast_qty` (REAL): Next scheduled regular bulk order quantity.
  - `as_of` (TEXT): Frozen timestamp.

#### `supplier_inventory_info`
- **Purpose**: Real-time supplier warehouse availability notes and expected restock dates.
- **Columns**:
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `item_id` (TEXT, FK -> `items.item_id`)
  - `in_stock` (INTEGER): 1 if available, 0 if out of stock.
  - `available_qty` (REAL): Quantity available in supplier warehouse.
  - `restock_expected_date` (TEXT): Expected date of warehouse replenishment.
  - `note` (TEXT): Supplier status note.

#### `catalogue`
- **Purpose**: Active vendor pricing, pack configurations, and instant delivery ETAs.
- **Columns**:
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `item_id` (TEXT, FK -> `items.item_id`)
  - `pack_label` (TEXT): Commercial packaging unit ('1L bottle', 'Pack of 50', '10kg bag').
  - `pack_qty` (REAL): Quantity contained in pack.
  - `price_per_pack` (REAL): GST-inclusive pack price.
  - `price_per_unit` (REAL): Effective price per unit (L, kg, pc).
  - `eta_minutes` (INTEGER): Delivery lead time in minutes.
  - `in_stock` (INTEGER): Stock availability flag.
  - `is_simulated` (INTEGER): Simulated commerce flag.

#### `supplier_price_history`
- **Purpose**: Historical price observations tracking inflation and seasonal supplier revisions.
- **Columns**:
  - `id` (INTEGER, PK): Auto-increment row ID.
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `item_id` (TEXT, FK -> `items.item_id`)
  - `effective_date` (TEXT): Effective date of tariff.
  - `price_per_pack`, `price_per_unit` (REAL): Historical prices.
  - `change_reason` (TEXT): Explanation of price shift.

---

### 2.3 Demand, Capacity & Orders

#### `demand_drivers`
- **Purpose**: Contextual demand variables influencing daily meal orders.
- **Columns**:
  - `date` (TEXT, PK): Observation date.
  - `day_of_week` (TEXT): Monday through Sunday.
  - `is_holiday` (INTEGER): 1 if public/festival holiday, 0 otherwise.
  - `festival` (TEXT): Festival or ritual note (e.g. 'Navratri (vrat menu)', 'Dussehra').
  - `weather_note` (TEXT): Local weather conditions.
  - `local_event` (TEXT): Local exam series or events in Kakadeo.
  - `subscription_pauses` (INTEGER): Count of customer-requested meal pauses.

#### `demand_forecast`
- **Purpose**: Daily meal forecasts with statistical uncertainty bands.
- **Columns**:
  - `date` (TEXT, PK, FK -> `demand_drivers.date`)
  - `units_forecast` (REAL): Point estimate (e.g. 23.0 for tomorrow).
  - `lower`, `upper` (REAL): Confidence interval bounds.
  - `confidence` (REAL): Forecast confidence score (0.0 to 1.0).
  - `method` (TEXT): Modeling technique.

#### `capacity`
- **Purpose**: Kitchen production limits and cooking staff hours.
- **Columns**:
  - `date` (TEXT, PK): Production date.
  - `max_meals` (INTEGER): Maximum meals kitchen can prepare (40).
  - `cook_hours` (REAL): Daily scheduled kitchen shift hours (6.0).

#### `delivery_slots`
- **Purpose**: Discrete meal delivery time windows and capacity bookings.
- **Columns**:
  - `slot_id` (TEXT, PK): Unique slot code (`SLOT-20261011-1` to `4`).
  - `date` (TEXT): Service date.
  - `slot_label` (TEXT): Time range ('11:00-12:00', '12:00-13:00', etc.).
  - `start_time`, `end_time` (TEXT): 'HH:MM'.
  - `capacity_units` (INTEGER): Meal slot capacity (10).
  - `booked_units` (INTEGER): Confirmed meals assigned to slot.

#### `customers`
- **Purpose**: Registered customer directory with status and subscription flags.
- **Columns**:
  - `customer_id` (TEXT, PK): Customer identifier (`CUST-001` to `CUST-136`).
  - `name` (TEXT): Customer name.
  - `segment` (TEXT): 'student', 'pg_hostel', 'office_worker', 'household', 'iitk_staff'.
  - `locality` (TEXT): Kanpur neighborhood.
  - `phone` (TEXT): Masked phone number (`+91 XXXXXX4821`).
  - `joined_date` (TEXT): Onboarding date.
  - `is_recurring` (INTEGER): 1 if recurring subscription, 0 for ad-hoc.
  - `status` (TEXT): 'active' (96), 'paused' (15), 'churned' (25).
  - `is_synthetic` (INTEGER): 1.

#### `customer_metrics`
- **Purpose**: Daily customer base snapshot and subscription health indicators.
- **Columns**:
  - `date` (TEXT, PK): Date.
  - `current_customers` (INTEGER): Active customer count (96 on 2026-10-10).
  - `recurring_customers` (INTEGER): Active recurring subscribers (62).
  - `recurring_pct` (REAL): Recurring ratio (64.6%).
  - `new`, `churned` (INTEGER): Daily customer movements.

#### `orders`
- **Purpose**: Individual customer order transactions.
- **Columns**:
  - `order_id` (TEXT, PK): Order identifier (`ORD-000001`...).
  - `customer_id` (TEXT, FK -> `customers.customer_id`)
  - `date` (TEXT): Order date.
  - `delivery_slot_id` (TEXT, FK -> `delivery_slots.slot_id`)
  - `type` (TEXT): 'subscription' (₹85) or 'one_off' (₹90).
  - `status` (TEXT): 'delivered', 'confirmed', 'tentative', 'cancelled', 'refunded'.
  - `units` (INTEGER): Meal units (1).
  - `unit_price`, `amount` (REAL): Pricing in INR.
  - `created_at` (TEXT): Timestamp.

---

### 2.4 Financials & Cash Projections

#### `cash_position`
- **Purpose**: Liquid bank balance as of frozen time.
- **Columns**:
  - `as_of` (TEXT, PK): Frozen timestamp.
  - `current_balance` (REAL): Available cash (₹12,000.0).
  - `min_cash_buffer` (REAL): Policy minimum liquidity floor (₹5,000.0).

#### `forecasted_balance`
- **Purpose**: Forward 15-day rolling cash flow projection (2026-10-10 to 2026-10-24).
- **Columns**:
  - `date` (TEXT, PK): Projection date.
  - `expected_inflow` (REAL): Forecasted cash collected from tiffin sales.
  - `expected_outflow` (REAL): Scheduled disbursements (salaries, supplier dues, rent, utilities).
  - `projected_balance` (REAL): Projected bank balance (reaches minimum ₹6,900 on 2026-10-12).
  - `confidence` (REAL): Decaying projection confidence (1.00 down to 0.50).

#### `upcoming_payments`
- **Purpose**: Scheduled liabilities, payroll, rent, and utility disbursements.
- **Columns**:
  - `payment_id` (TEXT, PK): Payment identifier (`PAY-01` to `PAY-05`).
  - `payee` (TEXT): Payee name.
  - `category` (TEXT): 'salaries', 'supplier_dues', 'utilities_lpg', 'rent', 'utilities_power'.
  - `amount` (REAL): Amount due.
  - `due_date` (TEXT): Due date.
  - `status` (TEXT): 'pending', 'scheduled', 'paid'.

#### `daily_metrics` & `monthly_metrics`
- **Purpose**: Historical operational and P&L performance.
- **Columns (`daily_metrics`)**:
  - `date` (TEXT, PK): Date.
  - `units_sold` (INTEGER): Meals served.
  - `revenue` (REAL): Daily gross revenue (reconciled within 1% of orders).
  - `cogs` (REAL): Cost of goods sold (~48%).
  - `opex` (REAL): Operating expenses (~₹640/day).
  - `net_profit` (REAL): Operating profit.
  - `cash_inflow`, `cash_outflow` (REAL): Daily cash movements.
- **Columns (`monthly_metrics`)**:
  - `month` (TEXT, PK): 'YYYY-MM'.
  - `units_sold`, `revenue`, `cogs`, `opex`, `net_profit` (REAL): Monthly totals.
  - `mrr` (REAL): Monthly recurring revenue.
  - `arr` (REAL): Annual recurring revenue run-rate (`mrr * 12`).

---

### 2.5 Procurement, Documents & Reconciliation

#### `purchase_orders` & `purchase_order_lines`
- **Purpose**: Internal purchase orders issued to suppliers before delivery.
- **Columns (`purchase_orders`)**:
  - `po_id` (TEXT, PK): Purchase order code (`PO-20260926-01`, `PO-20261004-02`, etc.).
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `order_date`, `expected_delivery_date` (TEXT): Dates.
  - `status` (TEXT): 'placed', 'received', 'cancelled'.
  - `total_taxable`, `total_tax`, `total_amount` (REAL): PO financial totals.
  - `notes` (TEXT): Description.
- **Columns (`purchase_order_lines`)**:
  - `line_id` (TEXT, PK): Line ID.
  - `po_id` (TEXT, FK -> `purchase_orders.po_id`)
  - `item_id` (TEXT, FK -> `items.item_id`)
  - `ordered_qty`, `unit_price`, `tax_rate_pct`, `taxable_amount`, `tax_amount`, `line_total` (REAL): Line details.

#### `purchase_history`
- **Purpose**: Physical purchase fulfillment ledger recording received goods and payment mode.
- **Columns**:
  - `purchase_id` (TEXT, PK): Fulfillment record ID.
  - `po_id` (TEXT, FK -> `purchase_orders.po_id`)
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `item_id` (TEXT, FK -> `items.item_id`)
  - `purchase_date` (TEXT): Delivery date.
  - `qty`, `unit_price`, `total_paid` (REAL): Received quantities and paid amounts.
  - `payment_mode` (TEXT): 'cash', 'UPI', 'credit', 'bank_transfer'.
  - `notes` (TEXT): Receipt notes.

#### `business_documents` & `document_lines`
- **Purpose**: Digital document ingestion repository storing OCR/extraction metadata from vendor invoices.
- **Columns (`business_documents`)**:
  - `doc_id` (TEXT, PK): Document code (`INV-GUPTA-0912`, `INV-PKG-0245`).
  - `doc_type` (TEXT): 'invoice', 'receipt', 'purchase_order', 'delivery_challan'.
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `po_id` (TEXT, FK -> `purchase_orders.po_id`)
  - `doc_date` (TEXT): Invoice date.
  - `file_ref` (TEXT): Relative path to PDF file fixture.
  - `extracted_json` (TEXT): Raw structured JSON extracted by OCR/Textract engine.
  - `extraction_confidence` (REAL): Model extraction confidence (0.96 for Gupta, 0.93 for Packaging Mart).
- **Columns (`document_lines`)**:
  - `doc_line_id` (TEXT, PK): Line ID.
  - `doc_id` (TEXT, FK -> `business_documents.doc_id`)
  - `item_id` (TEXT, FK -> `items.item_id`)
  - `billed_qty`, `unit_price`, `taxable_amount`, `gst_rate_pct`, `gst_amount`, `total_line_amount` (REAL): Line values billed by vendor.

#### `doc_ground_truth`
- **Purpose**: Ground-truth reconciliation audit table defining verified document discrepancies.
- **Columns**:
  - `truth_id` (TEXT, PK): Discrepancy identifier (`TRUTH-PKG-01`, `TRUTH-PKG-02`).
  - `doc_id` (TEXT, FK -> `business_documents.doc_id`)
  - `discrepancy_type` (TEXT): 'quantity', 'tax_rate', 'price', 'duplicate', 'none'.
  - `field_name` (TEXT): Erroneous field ('quantity', 'gst_rate_pct').
  - `expected_value`, `actual_value` (TEXT): PO baseline vs vendor bill.
  - `difference_amount` (REAL): Excess financial difference.
  - `description` (TEXT): Human-readable explanation.

#### `supplier_business_records` & `customer_business_records`
- **Purpose**: Commercial accounts ledgers tracking receivables and payables.
- **Columns (`supplier_business_records`)**:
  - `entry_id` (TEXT, PK): Entry ID.
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `date` (TEXT): Date.
  - `entry_type` (TEXT): 'invoice', 'payment', 'credit_note'.
  - `reference_doc` (TEXT): Reference invoice or payment receipt ID.
  - `amount`, `balance_due` (REAL): Transaction amount and running balance due.
- **Columns (`customer_business_records`)**:
  - `entry_id` (TEXT, PK): Entry ID.
  - `customer_id` (TEXT, FK -> `customers.customer_id`)
  - `date` (TEXT): Date.
  - `entry_type` (TEXT): 'order', 'payment', 'credit_note'.
  - `payment_mode` (TEXT): 'UPI', 'cash', 'card', 'credit'.
  - `amount`, `balance_due` (REAL): Customer balance due.

---

### 2.6 Customer Intelligence, Feedback & Social Media

#### `potential_customer_segments`
- **Purpose**: Market demographic profiles for capacity-to-customer matching.
- **Columns**:
  - `locality`, `segment` (TEXT, Composite PK): Target zone and cohort (e.g. Kakadeo coaching students).
  - `est_households` (INTEGER): Estimated reachable cohort size.
  - `budget_per_meal` (REAL): Willingness to pay.
  - `meal_time_pref` (TEXT): 'afternoon_lunch', 'dinner', 'both_lunch_dinner'.
  - `interest_score` (REAL): Affinity score between 0.0 and 1.0.
  - `distance_km` (REAL): Travel distance from Kakadeo kitchen.
  - `competitor_density` (TEXT): 'low', 'medium', 'high'.

#### `customer_reviews` & `internet_reviews`
- **Purpose**: Internal post-delivery SMS feedback and external platform reviews.
- **Columns (`customer_reviews`)**:
  - `review_id` (TEXT, PK): Review ID.
  - `customer_id` (TEXT, FK -> `customers.customer_id`)
  - `order_id` (TEXT, FK -> `orders.order_id`)
  - `date` (TEXT): Date.
  - `rating` (INTEGER): Rating (1 to 5).
  - `review_text` (TEXT): English/Hinglish feedback text.
  - `channel` (TEXT): 'post_delivery_sms'.
  - `sentiment` (TEXT): 'positive', 'neutral', 'negative'.
- **Columns (`internet_reviews`)**:
  - `review_id` (TEXT, PK): Review ID.
  - `source` (TEXT): 'Google', 'Zomato', 'Swiggy'.
  - `author_name` (TEXT): Public reviewer name.
  - `date` (TEXT): Date.
  - `rating` (INTEGER): Rating (1 to 5).
  - `text` (TEXT): Public review text.
  - `sentiment` (TEXT): 'positive', 'neutral', 'negative'.

#### `social_media_engagement`
- **Purpose**: Weekly organic and campaign reach metrics.
- **Columns**:
  - `engagement_id` (TEXT, PK): Engagement record ID.
  - `platform` (TEXT): 'Instagram', 'WhatsApp Business', 'Facebook'.
  - `week_start` (TEXT): Monday week starting date.
  - `followers`, `reach`, `impressions`, `likes`, `comments`, `shares`, `enquiries` (INTEGER): Engagement metrics.

#### `supplier_updates` & `customer_updates`
- **Purpose**: Real-time notifications and conversational updates from suppliers and customers.
- **Columns (`supplier_updates`)**:
  - `update_id` (TEXT, PK): Update ID.
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `date` (TEXT): Date.
  - `type` (TEXT): 'price_change', 'delay', 'stockout', 'scheme'.
  - `message` (TEXT): Notification message.
- **Columns (`customer_updates`)**:
  - `update_id` (TEXT, PK): Update ID.
  - `customer_id` (TEXT, FK -> `customers.customer_id`)
  - `date` (TEXT): Date.
  - `type` (TEXT): 'pause', 'resume', 'new_order', 'complaint', 'address_change', 'feedback'.
  - `message` (TEXT): Natural Hinglish WhatsApp message.

---

### 2.7 Business Memory & Procurement Benchmarks

#### `business_memory`
- **Purpose**: Structured long-term knowledge facts distinguishing verified transactional records from informal owner verbal statements.
- **Columns**:
  - `id` (INTEGER, PK): Auto-increment row ID.
  - `key` (TEXT): Knowledge key (e.g. `supplier.gupta.oil_price_per_l`).
  - `value` (TEXT): Stored knowledge value.
  - `source` (TEXT): 'verified_record' or 'owner_statement'.
  - `timestamp` (TEXT): Observation timestamp.
  - `confidence` (REAL): Confidence level (0.0 to 1.0).

#### `reference_plans` & `reference_plan_lines`
- **Purpose**: Ground-truth benchmark procurement plans used to evaluate agent optimization performance.
- **Columns (`reference_plans`)**:
  - `plan_id` (TEXT, PK): Plan code (`REF-RECOMMENDED`, `REF-ALL-FAST`, `REF-OIL-CONT-FAST`).
  - `plan_name` (TEXT): Plan title.
  - `strategy` (TEXT): 'mixed_optimal', 'all_fast', 'semi_fast'.
  - `description` (TEXT): Procurement strategy explanation.
- **Columns (`reference_plan_lines`)**:
  - `plan_line_id` (TEXT, PK): Line ID.
  - `plan_id` (TEXT, FK -> `reference_plans.plan_id`)
  - `supplier_id` (TEXT, FK -> `suppliers.supplier_id`)
  - `item_id` (TEXT, FK -> `items.item_id`)
  - `pack_qty_ordered` (INTEGER): Pack count.
  - `unit_qty_equivalent` (REAL): Equivalent unit quantity (L, kg, pcs).
  - `price_per_pack`, `line_subtotal` (REAL): Pack price and line total.

---

### 2.8 Working Tables for Write-Paths (Empty State)

- **`purchase_plans`**: Staging table for agent-generated purchase plans prior to owner approval.
- **`purchase_plan_lines`**: Itemized lines of agent purchase plans.
- **`approvals`**: Cryptographic voice approval tokens issued by Alexa+ (`token`, `plan_id`, `total`, `expires_at`, `used`).
- **`capacity_declarations`**: Agent declarations of free capacity submitted to local discovery channels.
- **`simulated_orders`**: Payload records dispatched to simulated quick-commerce APIs (`SUP-04`).
- **`audit_log`**: Comprehensive immutable event trail for all agent actions and voice approvals.

