"""
Deterministic Bulk Data Generator for Alexa Business Autopilot Demo Database.
Uses seeded RNG (seed=42) to produce demo_data/seed_bulk.sql.
Ensures zero conflict with seed_anchor.sql and strictly satisfies invariants A1-A16.
"""

from __future__ import annotations

import datetime
import random
from typing import List, Dict, Tuple, Any

SEED = 42
rng = random.Random(SEED)

FROZEN_AS_OF = "2026-10-10T19:10:00+05:30"
FROZEN_DATE = datetime.date(2026, 10, 10)
TOMORROW_DATE = datetime.date(2026, 10, 11)
HISTORY_DAYS = 90
START_DATE = FROZEN_DATE - datetime.timedelta(days=HISTORY_DAYS) # 2026-07-12
FUTURE_DAYS = 14 # 2026-10-11 to 2026-10-24

KANPUR_LOCALITIES = [
    "Kakadeo",
    "Swaroop Nagar",
    "Civil Lines",
    "Kidwai Nagar",
    "Arya Nagar",
    "Govind Nagar",
    "Kalyanpur"
]

FIRST_NAMES = [
    "Aarav", "Amit", "Ananya", "Deepak", "Divya", "Gaurav", "Kavita", "Manish",
    "Neha", "Nikhil", "Pooja", "Prateek", "Priya", "Rahul", "Rakesh", "Ritu",
    "Rohit", "Sachin", "Sanjay", "Shikha", "Shivani", "Sneha", "Sourabh", "Sunil",
    "Tarun", "Vandana", "Varun", "Vikas", "Vishal", "Yash", "Alok", "Anil",
    "Ankit", "Arun", "Ashok", "Bhavna", "Chhavi", "Devendra", "Garima", "Hemant",
    "Ishita", "Jitendra", "Kamal", "Lalit", "Megha", "Mohit", "Naveen", "Nisha",
    "Pankaj", "Pradeep", "Preeti", "Rajeev", "Rashmi", "Richa", "Sandeep", "Seema"
]

LAST_NAMES = [
    "Agarwal", "Bansal", "Chauhan", "Dixit", "Dubey", "Gupta", "Jaiswal", "Kapoor",
    "Katiyar", "Mishra", "Pandey", "Pathak", "Rathore", "Saxena", "Sharma", "Shukla",
    "Singh", "Srivastava", "Tiwari", "Tripathi", "Upadhyay", "Varma", "Yadav"
]

CUSTOMER_SEGMENTS = ["student", "pg_hostel", "office_worker", "household", "iitk_staff"]


def sql_str(val: Any) -> str:
    """Escape values for standard SQL."""
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    # text
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


def generate_customers() -> Tuple[List[Dict[str, Any]], str]:
    """
    Generate exactly 96 active customers (62 recurring, 34 one-off) + 40 inactive customers (15 paused, 25 churned).
    Total = 136 customers.
    """
    customers: List[Dict[str, Any]] = []
    cust_idx = 1
    
    # 62 active recurring
    for i in range(62):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        name = f"{fn} {ln}"
        seg = rng.choice(CUSTOMER_SEGMENTS)
        loc = rng.choice(KANPUR_LOCALITIES)
        phone = f"+91 XXXXXX{4000 + cust_idx:04d}"
        join_offset = rng.randint(20, 180)
        joined_date = (FROZEN_DATE - datetime.timedelta(days=join_offset)).isoformat()
        customers.append({
            "customer_id": f"CUST-{cust_idx:03d}",
            "name": name,
            "segment": seg,
            "locality": loc,
            "phone": phone,
            "joined_date": joined_date,
            "is_recurring": 1,
            "status": "active"
        })
        cust_idx += 1

    # 34 active non-recurring (one-off)
    for i in range(34):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        name = f"{fn} {ln}"
        seg = rng.choice(CUSTOMER_SEGMENTS)
        loc = rng.choice(KANPUR_LOCALITIES)
        phone = f"+91 XXXXXX{4000 + cust_idx:04d}"
        join_offset = rng.randint(5, 90)
        joined_date = (FROZEN_DATE - datetime.timedelta(days=join_offset)).isoformat()
        customers.append({
            "customer_id": f"CUST-{cust_idx:03d}",
            "name": name,
            "segment": seg,
            "locality": loc,
            "phone": phone,
            "joined_date": joined_date,
            "is_recurring": 0,
            "status": "active"
        })
        cust_idx += 1

    # 15 paused
    for i in range(15):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        name = f"{fn} {ln}"
        seg = rng.choice(CUSTOMER_SEGMENTS)
        loc = rng.choice(KANPUR_LOCALITIES)
        phone = f"+91 XXXXXX{4000 + cust_idx:04d}"
        join_offset = rng.randint(40, 150)
        joined_date = (FROZEN_DATE - datetime.timedelta(days=join_offset)).isoformat()
        customers.append({
            "customer_id": f"CUST-{cust_idx:03d}",
            "name": name,
            "segment": seg,
            "locality": loc,
            "phone": phone,
            "joined_date": joined_date,
            "is_recurring": 1,
            "status": "paused"
        })
        cust_idx += 1

    # 25 churned
    for i in range(25):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        name = f"{fn} {ln}"
        seg = rng.choice(CUSTOMER_SEGMENTS)
        loc = rng.choice(KANPUR_LOCALITIES)
        phone = f"+91 XXXXXX{4000 + cust_idx:04d}"
        join_offset = rng.randint(70, 220)
        joined_date = (FROZEN_DATE - datetime.timedelta(days=join_offset)).isoformat()
        customers.append({
            "customer_id": f"CUST-{cust_idx:03d}",
            "name": name,
            "segment": seg,
            "locality": loc,
            "phone": phone,
            "joined_date": joined_date,
            "is_recurring": rng.choice([0, 1]),
            "status": "churned"
        })
        cust_idx += 1

    lines = ["-- ----------------------------------------------------------------------------",
             "-- CUSTOMERS (96 active: 62 recurring + 34 one-off; 40 inactive: 15 paused + 25 churned)",
             "-- ----------------------------------------------------------------------------",
             "INSERT INTO customers (customer_id, name, segment, locality, phone, joined_date, is_recurring, status, is_synthetic) VALUES"]
    row_strs = []
    for c in customers:
        row_strs.append(
            f"    ({sql_str(c['customer_id'])}, {sql_str(c['name'])}, {sql_str(c['segment'])}, {sql_str(c['locality'])}, "
            f"{sql_str(c['phone'])}, {sql_str(c['joined_date'])}, {c['is_recurring']}, {sql_str(c['status'])}, 1)"
        )
    lines.append(",\n".join(row_strs) + ";\n")
    return customers, "\n".join(lines)


def generate_customer_metrics() -> str:
    """Generate customer metrics history for 90 days ending in 96 current, 62 recurring, 64.6%."""
    lines = ["-- ----------------------------------------------------------------------------",
             "-- CUSTOMER METRICS (90-day trajectory ending at exactly 96 / 62 / 64.6%)",
             "-- ----------------------------------------------------------------------------",
             "INSERT INTO customer_metrics (date, current_customers, recurring_customers, recurring_pct, new, churned) VALUES"]
    
    rows = []
    cur_total = 78
    cur_rec = 48
    
    for day_idx in range(HISTORY_DAYS + 1):
        dt = START_DATE + datetime.timedelta(days=day_idx)
        dt_str = dt.isoformat()
        
        if dt == FROZEN_DATE:
            cur_total = 96
            cur_rec = 62
            pct = 64.6
            new_c = 1
            churn_c = 0
        else:
            # step gradually towards 96 and 62
            target_tot = 78 + int((96 - 78) * (day_idx / HISTORY_DAYS))
            target_rec = 48 + int((62 - 48) * (day_idx / HISTORY_DAYS))
            new_c = 1 if rng.random() < 0.25 else 0
            churn_c = 1 if rng.random() < 0.10 else 0
            cur_total = target_tot
            cur_rec = target_rec
            pct = round((cur_rec / cur_total) * 100.0, 1)
            
        rows.append(f"    ({sql_str(dt_str)}, {cur_total}, {cur_rec}, {pct}, {new_c}, {churn_c})")
        
    lines.append(",\n".join(rows) + ";\n")
    return "\n".join(lines)


def generate_capacity_and_slots() -> Tuple[List[Dict[str, Any]], str]:
    """
    Generate capacity and delivery slots for history and future.
    Skip 2026-10-10 and 2026-10-11 which are already in anchor data!
    """
    slots: List[Dict[str, Any]] = []
    cap_lines = ["-- ----------------------------------------------------------------------------",
                 "-- CAPACITY (Historical 90 days and Future 14 days; excluding anchor 10-10 & 10-11)",
                 "-- ----------------------------------------------------------------------------",
                 "INSERT INTO capacity (date, max_meals, cook_hours) VALUES"]
    
    cap_rows = []
    slot_lines = ["-- ----------------------------------------------------------------------------",
                  "-- DELIVERY SLOTS (Historical & Future slots; excluding anchor 10-11)",
                  "-- ----------------------------------------------------------------------------",
                  "INSERT INTO delivery_slots (slot_id, date, slot_label, start_time, end_time, capacity_units, booked_units) VALUES"]
    slot_rows = []

    total_days = HISTORY_DAYS + 1 + FUTURE_DAYS
    for d_idx in range(total_days):
        dt = START_DATE + datetime.timedelta(days=d_idx)
        dt_str = dt.isoformat()
        
        # 2026-10-10 and 2026-10-11 capacity are in anchor
        if dt_str not in ("2026-10-10", "2026-10-11"):
            cap_rows.append(f"    ({sql_str(dt_str)}, 40, 6.0)")

        # 2026-10-11 slots are in anchor
        if dt_str == "2026-10-11":
            continue
            
        slot_defs = [
            ("1", "11:00-12:00", "11:00", "12:00"),
            ("2", "12:00-13:00", "12:00", "13:00"),
            ("3", "13:00-14:00", "13:00", "14:00"),
            ("4", "14:00-15:00", "14:00", "15:00")
        ]
        
        for s_num, s_lbl, s_start, s_end in slot_defs:
            s_id = f"SLOT-{dt.strftime('%Y%m%d')}-{s_num}"
            # Booked units will be updated/matched with orders
            cap = 10
            slots.append({
                "slot_id": s_id,
                "date": dt_str,
                "slot_label": s_lbl,
                "start_time": s_start,
                "end_time": s_end,
                "capacity_units": cap,
                "booked_units": 0 # filled later
            })

    cap_lines.append(",\n".join(cap_rows) + ";\n")
    return slots, "\n".join(cap_lines)


def generate_demand_and_metrics_and_orders(
    customers: List[Dict[str, Any]], slots: List[Dict[str, Any]]
) -> Tuple[str, str, str, str]:
    """
    Generate daily metrics, monthly metrics, demand drivers/forecast, and orders.
    STRICT INVARIANT:
      sum(orders.amount) per day within 1% of daily_metrics.revenue for the last 90 days!
      monthly_metrics rolls up from daily for the current month!
      On 2026-10-11: exactly 20 confirmed units (14 sub, 6 one-off), split 6/8/4/2 across slots.
    """
    daily_rows = []
    order_rows = []
    demand_driver_rows = []
    demand_forecast_rows = []

    active_recurring = [c["customer_id"] for c in customers if c["status"] == "active" and c["is_recurring"] == 1]
    active_one_off = [c["customer_id"] for c in customers if c["status"] == "active" and c["is_recurring"] == 0]

    # Map slot_id to slot dict for easy lookup
    slot_map = {s["slot_id"]: s for s in slots}

    # Track October metrics for MTD rollup
    oct_units = 0
    oct_rev = 0.0
    oct_cogs = 0.0
    oct_opex = 0.0
    oct_net = 0.0

    order_seq = 1

    # 1. Historical 90 days (2026-07-12 to 2026-10-10)
    for day_idx in range(HISTORY_DAYS + 1):
        dt = START_DATE + datetime.timedelta(days=day_idx)
        dt_str = dt.isoformat()
        weekday = dt.strftime("%A")
        is_weekend = weekday in ("Saturday", "Sunday")
        
        # Target daily volume: weekday ~22-25, weekend ~15-18
        if is_weekend:
            target_units = rng.randint(15, 18)
        else:
            target_units = rng.randint(22, 25)

        # Mix: ~65-70% subscription (@85), remainder one-off (@90)
        sub_units = int(round(target_units * rng.uniform(0.65, 0.72)))
        one_off_units = target_units - sub_units
        day_revenue = (sub_units * 85.0) + (one_off_units * 90.0)

        # COGS ~48%, OPEX ~640
        day_cogs = round(day_revenue * rng.uniform(0.47, 0.49), 2)
        day_opex = round(rng.uniform(620.0, 660.0), 2)
        day_net = round(day_revenue - day_cogs - day_opex, 2)
        inflow = round(day_revenue * rng.uniform(0.95, 1.05), 2)
        outflow = round((day_cogs + day_opex) * rng.uniform(0.95, 1.05), 2)

        daily_rows.append(
            f"    ({sql_str(dt_str)}, {target_units}, {day_revenue:.2f}, {day_cogs:.2f}, "
            f"{day_opex:.2f}, {day_net:.2f}, {inflow:.2f}, {outflow:.2f})"
        )

        if dt_str.startswith("2026-10"):
            oct_units += target_units
            oct_rev += day_revenue
            oct_cogs += day_cogs
            oct_opex += day_opex
            oct_net += day_net

        # Create orders for this day matching target_units and revenue EXACTLY
        # Distribute units across the 4 delivery slots for this day
        day_slots = [s for s in slots if s["date"] == dt_str]
        slot_caps = [target_units // 4] * 4
        rem = target_units % 4
        for r_i in range(rem):
            slot_caps[r_i] += 1

        units_assigned_sub = 0
        units_assigned_one = 0

        # Create subscription orders
        chosen_subs = rng.sample(active_recurring, min(sub_units, len(active_recurring)))
        sub_cust_pool = chosen_subs[:]
        while units_assigned_sub < sub_units:
            cust = sub_cust_pool[units_assigned_sub % len(sub_cust_pool)]
            s_idx = units_assigned_sub % 4
            s_id = day_slots[s_idx]["slot_id"]
            order_rows.append(
                f"    ('ORD-{order_seq:06d}', {sql_str(cust)}, {sql_str(dt_str)}, {sql_str(s_id)}, "
                f"'subscription', 'delivered', 1, 85.0, 85.0, {sql_str(dt_str + 'T08:30:00+05:30')})"
            )
            order_seq += 1
            units_assigned_sub += 1
            slot_map[s_id]["booked_units"] += 1

        # Create one-off orders
        chosen_ones = rng.sample(active_one_off, min(one_off_units, len(active_one_off)))
        one_cust_pool = chosen_ones[:]
        while units_assigned_one < one_off_units:
            cust = one_cust_pool[units_assigned_one % len(one_cust_pool)]
            s_idx = (units_assigned_sub + units_assigned_one) % 4
            s_id = day_slots[s_idx]["slot_id"]
            order_rows.append(
                f"    ('ORD-{order_seq:06d}', {sql_str(cust)}, {sql_str(dt_str)}, {sql_str(s_id)}, "
                f"'one_off', 'delivered', 1, 90.0, 90.0, {sql_str(dt_str + 'T10:15:00+05:30')})"
            )
            order_seq += 1
            units_assigned_one += 1
            slot_map[s_id]["booked_units"] += 1

        # Historical demand drivers & forecast (skip 2026-10-10 as in anchor)
        if dt_str != "2026-10-10":
            demand_driver_rows.append(
                f"    ({sql_str(dt_str)}, {sql_str(weekday)}, {1 if is_weekend and rng.random() < 0.1 else 0}, "
                f"NULL, 'Pleasant weather', 'Routine service', {rng.randint(0, 3)})"
            )
            forecast_units = round(target_units * rng.uniform(0.95, 1.05), 1)
            demand_forecast_rows.append(
                f"    ({sql_str(dt_str)}, {forecast_units}, {forecast_units - 3.0}, {forecast_units + 3.0}, "
                f"{round(rng.uniform(0.80, 0.92), 2)}, 'ensemble_exponential_smoothing')"
            )

    # 2. Tomorrow: 2026-10-11 (Sunday)
    # EXACTLY 20 confirmed units across 4 slots: 6, 8, 4, 2 (14 sub @85, 6 one-off @90)
    tomorrow_str = "2026-10-11"
    # Slot 1: 6 units (4 sub, 2 one-off)
    # Slot 2: 8 units (6 sub, 2 one-off)
    # Slot 3: 4 units (3 sub, 1 one-off)
    # Slot 4: 2 units (1 sub, 1 one-off)
    tomorrow_slot_plan = [
        ("SLOT-20261011-1", 4, 2), # 6
        ("SLOT-20261011-2", 6, 2), # 8
        ("SLOT-20261011-3", 3, 1), # 4
        ("SLOT-20261011-4", 1, 1), # 2
    ]
    sub_pick_idx = 0
    one_pick_idx = 0
    for s_id, s_sub_cnt, s_one_cnt in tomorrow_slot_plan:
        for _ in range(s_sub_cnt):
            cust = active_recurring[sub_pick_idx % len(active_recurring)]
            sub_pick_idx += 1
            order_rows.append(
                f"    ('ORD-{order_seq:06d}', {sql_str(cust)}, '{tomorrow_str}', '{s_id}', "
                f"'subscription', 'confirmed', 1, 85.0, 85.0, '{tomorrow_str}T08:00:00+05:30')"
            )
            order_seq += 1
        for _ in range(s_one_cnt):
            cust = active_one_off[one_pick_idx % len(active_one_off)]
            one_pick_idx += 1
            order_rows.append(
                f"    ('ORD-{order_seq:06d}', {sql_str(cust)}, '{tomorrow_str}', '{s_id}', "
                f"'one_off', 'confirmed', 1, 90.0, 90.0, '{tomorrow_str}T10:00:00+05:30')"
            )
            order_seq += 1

    # 3. Future days (2026-10-12 to 2026-10-24)
    # Add confirmed and tentative orders for future slots
    for fut_idx in range(2, FUTURE_DAYS + 1):
        f_dt = FROZEN_DATE + datetime.timedelta(days=fut_idx)
        f_dt_str = f_dt.isoformat()
        fut_slots = [s for s in slots if s["date"] == f_dt_str]
        
        # 16-22 planned orders
        fut_cnt = rng.randint(16, 22)
        for i in range(fut_cnt):
            s_target = fut_slots[i % len(fut_slots)]
            c_target = active_recurring[i % len(active_recurring)]
            st = "confirmed" if i < 14 else "tentative"
            order_rows.append(
                f"    ('ORD-{order_seq:06d}', {sql_str(c_target)}, {sql_str(f_dt_str)}, {sql_str(s_target['slot_id'])}, "
                f"'subscription', '{st}', 1, 85.0, 85.0, {sql_str(f_dt_str + 'T08:00:00+05:30')})"
            )
            order_seq += 1
            s_target["booked_units"] += 1

    # 4. Generate monthly metrics: Oct 2025 -> Sep 2026 + Oct 2026 MTD
    monthly_rows = []
    # 12 prior months
    m_units = 520
    m_rev = 45000.0
    months = [
        "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
        "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"
    ]
    for m in months:
        m_cogs = round(m_rev * 0.48, 2)
        m_opex = round(640.0 * 30, 2)
        m_net = round(m_rev - m_cogs - m_opex, 2)
        mrr = round(m_rev * 0.70, 2)
        arr = round(mrr * 12.0, 2)
        monthly_rows.append(
            f"    ('{m}', {m_units}, {m_rev:.2f}, {m_cogs:.2f}, {m_opex:.2f}, {m_net:.2f}, {mrr:.2f}, {arr:.2f})"
        )
        m_rev = round(m_rev * 1.025, 2) # 2.5% monthly growth
        m_units = int(round(m_units * 1.025))

    # Oct 2026 MTD: strict rollup from daily_metrics
    oct_mrr = round(62 * 85.0 * 30, 2) # normalized recurring run rate
    oct_arr = round(oct_mrr * 12.0, 2)
    monthly_rows.append(
        f"    ('2026-10', {oct_units}, {oct_rev:.2f}, {oct_cogs:.2f}, {oct_opex:.2f}, {oct_net:.2f}, {oct_mrr:.2f}, {oct_arr:.2f})"
    )

    daily_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- DAILY METRICS (90-day history 2026-07-12 -> 2026-10-10)\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO daily_metrics (date, units_sold, revenue, cogs, opex, net_profit, cash_inflow, cash_outflow) VALUES\n"
        + ",\n".join(daily_rows) + ";\n"
    )

    monthly_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- MONTHLY METRICS (Oct 2025 -> Sep 2026 plus October 2026 MTD Rollup)\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO monthly_metrics (month, units_sold, revenue, cogs, opex, net_profit, mrr, arr) VALUES\n"
        + ",\n".join(monthly_rows) + ";\n"
    )

    orders_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- ORDERS (Historical delivered + Tomorrow's 20 confirmed + Future tentative)\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO orders (order_id, customer_id, date, delivery_slot_id, type, status, units, unit_price, amount, created_at) VALUES\n"
        + ",\n".join(order_rows) + ";\n"
    )

    demand_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- HISTORICAL DEMAND DRIVERS & FORECAST\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO demand_drivers (date, day_of_week, is_holiday, festival, weather_note, local_event, subscription_pauses) VALUES\n"
        + ",\n".join(demand_driver_rows) + ";\n\n"
        "INSERT INTO demand_forecast (date, units_forecast, lower, upper, confidence, method) VALUES\n"
        + ",\n".join(demand_forecast_rows) + ";\n"
    )

    return daily_sql, monthly_sql, orders_sql, demand_sql


def generate_purchases_and_ledgers() -> Tuple[str, str, str, str]:
    """
    Generate purchase orders, purchase order lines, purchase history (~150 rows),
    supplier price history (~150 rows), and business records (ledgers).
    Strictly preserve anchor restock dates and Sharma open balance (4200.0).
    """
    po_rows = []
    pol_rows = []
    ph_rows = []
    sph_rows = []
    sbr_rows = []
    cbr_rows = []

    # Supplier list
    # SUP-01: groceries (Atta, Dal, Rice, Spice)
    # SUP-02: packaging (Containers, Bags)
    # SUP-03: oil
    po_seq = 3 # 1 and 2 in anchor
    pol_seq = 3
    ph_seq = 3

    # Items to regularly purchase
    # Anchor restocks:
    # OIL-SUN-1L: 2026-09-28 / 10L (already in anchor!)
    # CONT-750: 2026-10-05 / 100 pcs (already in anchor!)
    # ATTA-10: 2026-10-03 / 40 kg
    # RICE-BAS: 2026-10-06 / 25 kg
    # DAL-MOONG: 2026-10-04 / 10 kg
    # VEG-MIX: daily mandi
    # SPICE-MIX: 2026-10-01 / 2 kg
    # BAG-CARRY: 2026-10-02 / 100 pcs
    # GHEE-1KG: 2026-09-20 / 3 kg

    # 1. Exact anchor restocks that must appear in purchase history
    anchor_purchases = [
        ("SUP-01", "ATTA-10", "2026-10-03", 40.0, 40.0, 1600.0, "credit", 0.0),
        ("SUP-01", "DAL-MOONG", "2026-10-04", 10.0, 112.0, 1120.0, "credit", 0.0),
        ("SUP-01", "RICE-BAS", "2026-10-06", 25.0, 65.0, 1625.0, "UPI", 0.0),
        ("SUP-01", "SPICE-MIX", "2026-10-01", 2.0, 280.0, 560.0, "cash", 0.0),
        ("SUP-02", "BAG-CARRY", "2026-10-02", 100.0, 1.20, 120.0, "credit", 18.0),
        ("SUP-01", "GHEE-1KG", "2026-09-20", 3.0, 580.0, 1740.0, "UPI", 5.0)
    ]

    for supp, item, p_date, qty, u_price, tot, p_mode, tax_pct in anchor_purchases:
        po_id = f"PO-{p_date.replace('-', '')}-{po_seq:02d}"
        pol_id = f"POL-{pol_seq:04d}"
        ph_id = f"PH-{ph_seq:04d}"
        taxable = tot / (1.0 + tax_pct / 100.0)
        tax = tot - taxable
        po_rows.append(
            f"    ('{po_id}', '{supp}', '{p_date}', '{p_date}', 'received', {taxable:.2f}, {tax:.2f}, {tot:.2f}, 'Routine restock')"
        )
        pol_rows.append(
            f"    ('{pol_id}', '{po_id}', '{item}', {qty}, {u_price:.2f}, {tax_pct:.1f}, {taxable:.2f}, {tax:.2f}, {tot:.2f})"
        )
        ph_rows.append(
            f"    ('{ph_id}', '{po_id}', '{supp}', '{item}', '{p_date}', {qty}, {u_price:.2f}, {tot:.2f}, '{p_mode}', 'Restock received')"
        )
        po_seq += 1
        pol_seq += 1
        ph_seq += 1

    # 2. Daily Mandi Veg purchases over 90 days (cash)
    for day_idx in range(HISTORY_DAYS):
        dt = START_DATE + datetime.timedelta(days=day_idx)
        dt_str = dt.isoformat()
        veg_qty = round(rng.uniform(6.0, 8.5), 1)
        veg_price = round(rng.uniform(32.0, 38.0), 2)
        veg_tot = round(veg_qty * veg_price, 2)
        ph_id = f"PH-{ph_seq:04d}"
        ph_rows.append(
            f"    ('{ph_id}', NULL, 'SUP-01', 'VEG-MIX', '{dt_str}', {veg_qty}, {veg_price:.2f}, {veg_tot:.2f}, 'cash', 'Daily mandi fresh purchase')"
        )
        ph_seq += 1

    # 3. Bi-weekly wholesale grocery & packaging purchases to reach ~150 total purchases
    curr_d = START_DATE
    while curr_d < FROZEN_DATE - datetime.timedelta(days=12):
        d_str = curr_d.isoformat()
        # Atta / Rice / Dal from SUP-01
        p_item = rng.choice(["ATTA-10", "RICE-BAS", "DAL-MOONG"])
        p_qty = 20.0 if p_item == "ATTA-10" else (15.0 if p_item == "RICE-BAS" else 8.0)
        p_uprice = 40.0 if p_item == "ATTA-10" else (65.0 if p_item == "RICE-BAS" else 112.0)
        p_tot = p_qty * p_uprice
        po_id = f"PO-{d_str.replace('-', '')}-{po_seq:02d}"
        pol_id = f"POL-{pol_seq:04d}"
        ph_id = f"PH-{ph_seq:04d}"
        po_rows.append(
            f"    ('{po_id}', 'SUP-01', '{d_str}', '{d_str}', 'received', {p_tot:.2f}, 0.0, {p_tot:.2f}, 'Wholesale grocery cycle')"
        )
        pol_rows.append(
            f"    ('{pol_id}', '{po_id}', '{p_item}', {p_qty}, {p_uprice:.2f}, 0.0, {p_tot:.2f}, 0.0, {p_tot:.2f})"
        )
        ph_rows.append(
            f"    ('{ph_id}', '{po_id}', 'SUP-01', '{p_item}', '{d_str}', {p_qty}, {p_uprice:.2f}, {p_tot:.2f}, 'UPI', 'Wholesale grocery delivery')"
        )
        po_seq += 1
        pol_seq += 1
        ph_seq += 1

        # Packaging from SUP-02 every 2-3 weeks
        if rng.random() < 0.6:
            pkg_tot = 320.0
            po_id_pkg = f"PO-{d_str.replace('-', '')}-{po_seq:02d}"
            pol_id_pkg = f"POL-{pol_seq:04d}"
            ph_id_pkg = f"PH-{ph_seq:04d}"
            po_rows.append(
                f"    ('{po_id_pkg}', 'SUP-02', '{d_str}', '{d_str}', 'received', 320.0, 57.60, 377.60, 'Containers restock batch')"
            )
            pol_rows.append(
                f"    ('{pol_id_pkg}', '{po_id_pkg}', 'CONT-750', 100.0, 3.20, 18.0, 320.0, 57.60, 377.60)"
            )
            ph_rows.append(
                f"    ('{ph_id_pkg}', '{po_id_pkg}', 'SUP-02', 'CONT-750', '{d_str}', 100.0, 3.20, 377.60, 'UPI', '100 pcs containers delivered')"
            )
            po_seq += 1
            pol_seq += 1
            ph_seq += 1

        curr_d += datetime.timedelta(days=rng.randint(6, 10))

    # 4. Supplier price history (~150 rows over 120 days)
    sph_seq = 5 # 1-4 in anchor
    hist_items = [
        ("SUP-01", "ATTA-10", 400.0, 40.0),
        ("SUP-01", "DAL-MOONG", 112.0, 112.0),
        ("SUP-01", "RICE-BAS", 325.0, 65.0),
        ("SUP-01", "SPICE-MIX", 140.0, 280.0),
        ("SUP-01", "GHEE-1KG", 580.0, 580.0),
        ("SUP-02", "CONT-750", 160.0, 3.20),
        ("SUP-02", "BAG-CARRY", 120.0, 1.20),
        ("SUP-03", "OIL-SUN-1L", 146.0, 146.0),
        ("SUP-04", "OIL-SUN-1L", 158.0, 158.0),
        ("SUP-04", "CONT-750", 188.0, 7.52),
        ("SUP-04", "ATTA-10", 460.0, 46.0),
        ("SUP-04", "DAL-MOONG", 128.0, 128.0)
    ]
    for step in range(12):
        h_date = (FROZEN_DATE - datetime.timedelta(days=120 - step * 10)).isoformat()
        for supp_id, it_id, p_pack, p_unit in hist_items:
            # small jitter
            factor = 1.0 + (step - 6) * 0.005
            p_p = round(p_pack * factor, 2)
            p_u = round(p_unit * factor, 2)
            sph_rows.append(
                f"    ('{supp_id}', '{it_id}', '{h_date}', {p_p:.2f}, {p_u:.2f}, 'Periodic supplier rate update')"
            )

    # 5. Customer business records (ledger entries)
    # Extra test edge case: one customer with outstanding balance (CUST-015 balance_due = 170.0)
    for c_id_int in range(1, 40):
        c_str = f"CUST-{c_id_int:03d}"
        if c_str == "CUST-015":
            cbr_rows.append(
                f"    ('CBR-{c_id_int:03d}-1', '{c_str}', '2026-10-08', 'order', 'credit', 170.0, 170.0, '2 tiffins on credit')"
            )
        else:
            cbr_rows.append(
                f"    ('CBR-{c_id_int:03d}-1', '{c_str}', '2026-10-01', 'order', 'UPI', 2550.0, 2550.0, 'Monthly subscription bill')"
            )
            cbr_rows.append(
                f"    ('CBR-{c_id_int:03d}-2', '{c_str}', '2026-10-01', 'payment', 'UPI', 2550.0, 0.0, 'UPI payment received in full')"
            )

    # 6. Historical supplier business records (older transactions for SUP-01, SUP-02, SUP-03)
    # Must NOT disturb SUP-01 open balance of 4200 (which has SBR-01 and SBR-02 in anchor)!
    sbr_rows.append(
        "    ('SBR-HIST-01', 'SUP-02', '2026-09-15', 'invoice', 'INV-PKG-0199', 1600.0, 1600.0, 'Bulk container batch')"
    )
    sbr_rows.append(
        "    ('SBR-HIST-02', 'SUP-02', '2026-09-16', 'payment', 'PAY-PKG-0199', 1600.0, 0.0, 'Paid in full via bank transfer')"
    )
    sbr_rows.append(
        "    ('SBR-HIST-03', 'SUP-03', '2026-09-28', 'invoice', 'INV-GUPTA-0912', 1533.0, 1533.0, 'Oil delivery invoice')"
    )
    sbr_rows.append(
        "    ('SBR-HIST-04', 'SUP-03', '2026-09-28', 'payment', 'PAY-GUPTA-0912', 1533.0, 0.0, 'Paid immediately via UPI')"
    )

    po_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- PURCHASE ORDERS & LINES\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO purchase_orders (po_id, supplier_id, order_date, expected_delivery_date, status, total_taxable, total_tax, total_amount, notes) VALUES\n"
        + ",\n".join(po_rows) + ";\n\n"
        "INSERT INTO purchase_order_lines (line_id, po_id, item_id, ordered_qty, unit_price, tax_rate_pct, taxable_amount, tax_amount, line_total) VALUES\n"
        + ",\n".join(pol_rows) + ";\n"
    )

    ph_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- PURCHASE HISTORY (~150 rows over 90 days)\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO purchase_history (purchase_id, po_id, supplier_id, item_id, purchase_date, qty, unit_price, total_paid, payment_mode, notes) VALUES\n"
        + ",\n".join(ph_rows) + ";\n"
    )

    sph_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- SUPPLIER PRICE HISTORY (~150 historical observations)\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO supplier_price_history (supplier_id, item_id, effective_date, price_per_pack, price_per_unit, change_reason) VALUES\n"
        + ",\n".join(sph_rows) + ";\n"
    )

    ledgers_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- SUPPLIER & CUSTOMER BUSINESS RECORDS (LEDGERS)\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO supplier_business_records (entry_id, supplier_id, date, entry_type, reference_doc, amount, balance_due, notes) VALUES\n"
        + ",\n".join(sbr_rows) + ";\n\n"
        "INSERT INTO customer_business_records (entry_id, customer_id, date, entry_type, payment_mode, amount, balance_due, notes) VALUES\n"
        + ",\n".join(cbr_rows) + ";\n"
    )

    return po_sql, ph_sql, sph_sql, ledgers_sql


def generate_reviews_and_social_and_segments(customers: List[Dict[str, Any]]) -> str:
    """
    Generate customer reviews (~150), internet reviews (~40), social media engagement (13 weeks x 3),
    potential customer segments (~12), supplier updates (~25), customer updates (~120).
    """
    lines = []

    # 1. Potential customer segments (~12 rows across Kanpur localities)
    segments_data = [
        ("Kakadeo", "coaching_students", 4500, 90.0, "afternoon_lunch", 0.94, 0.8, "high"),
        ("Kakadeo", "pg_residents",      2800, 85.0, "both_lunch_dinner",0.91, 1.2, "medium"),
        ("Kakadeo", "faculty_staff",      650, 95.0, "afternoon_lunch", 0.82, 1.5, "low"),
        ("Swaroop Nagar", "office_workers", 1800, 110.0,"afternoon_lunch", 0.88, 3.2, "high"),
        ("Swaroop Nagar", "households",    3200, 100.0,"dinner",          0.72, 3.5, "low"),
        ("Civil Lines", "bank_corporate", 2400, 120.0,"afternoon_lunch", 0.89, 4.8, "medium"),
        ("Civil Lines", "lawyers_chambers", 950, 115.0,"afternoon_lunch", 0.84, 5.0, "low"),
        ("Kidwai Nagar", "coaching_hub",  1600, 85.0, "afternoon_lunch", 0.85, 6.2, "medium"),
        ("Kidwai Nagar", "households",    4100, 90.0, "both_lunch_dinner",0.68, 6.5, "high"),
        ("Arya Nagar", "traders_business",1900, 100.0,"afternoon_lunch", 0.79, 4.0, "medium"),
        ("Govind Nagar", "small_industry", 1500, 85.0, "afternoon_lunch", 0.75, 5.5, "medium"),
        ("Kalyanpur", "iitk_staff_pg",    2200, 95.0, "both_lunch_dinner",0.87, 7.2, "low")
    ]
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("-- POTENTIAL CUSTOMER SEGMENTS (Kakadeo & corporate highest for afternoon)")
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("INSERT INTO potential_customer_segments (locality, segment, est_households, budget_per_meal, meal_time_pref, interest_score, distance_km, competitor_density) VALUES")
    s_rows = []
    for loc, seg, hh, bud, pref, sc, dist, comp in segments_data:
        s_rows.append(f"    ('{loc}', '{seg}', {hh}, {bud:.1f}, '{pref}', {sc:.2f}, {dist:.1f}, '{comp}')")
    lines.append(",\n".join(s_rows) + ";\n")

    # 2. Customer Reviews (~150 rows)
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("-- CUSTOMER REVIEWS (~150 post-delivery internal reviews)")
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("INSERT INTO customer_reviews (review_id, customer_id, order_id, date, rating, review_text, channel, sentiment) VALUES")
    review_templates = [
        (5, "Khana bilkul ghar jaisa tha, roti bahut soft thi!", "positive"),
        (5, "Best tiffin in Kakadeo. Time par deliver ho gaya.", "positive"),
        (4, "Dal fry and sabzi were tasty, portion size is very satisfying.", "positive"),
        (4, "Good home style meal, not too oily. Keep it up Sunita ji.", "positive"),
        (3, "Taste is okay, but delivery was 15 mins late today.", "neutral"),
        (2, "Packaging leak ho gayi thi, bag me dal gir gayi thi.", "negative"),
        (2, "Container ka dhakkan theek se band nahi tha, dal leak hui.", "negative"),
        (5, "Sunday special halwa was delicious!", "positive"),
        (4, "Simple and nutritious daily food, highly recommended for students.", "positive"),
        (1, "Food arrived completely cold and container was broken.", "negative"),
        (5, "Very hygienic packaging and authentic North Indian taste.", "positive")
    ]
    cr_rows = []
    for r_i in range(150):
        c = customers[r_i % len(customers)]
        r_dt = (FROZEN_DATE - datetime.timedelta(days=rng.randint(1, 88))).isoformat()
        rat, txt, sent = rng.choice(review_templates)
        cr_rows.append(
            f"    ('CREV-{r_i + 1:04d}', '{c['customer_id']}', NULL, '{r_dt}', {rat}, {sql_str(txt)}, 'post_delivery_sms', '{sent}')"
        )
    lines.append(",\n".join(cr_rows) + ";\n")

    # 3. Internet Reviews (~40 rows; avg ~4.2, a few 2-star container leaks, one oil smell)
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("-- INTERNET REVIEWS (~40 public reviews on Google/Zomato/Swiggy)")
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("INSERT INTO internet_reviews (review_id, source, author_name, date, rating, text, sentiment) VALUES")
    inet_reviews_data = [
        ("Google", "Abhishek Tiwari", "2026-08-15", 5, "Maa Ki Rasoi has been a lifesaver during my NEET prep at Kakadeo. Proper home cooked feel.", "positive"),
        ("Zomato", "Neha Verma", "2026-08-20", 4, "Reliable subscription service. Very clean food.", "positive"),
        ("Swiggy", "Kunal Bansal", "2026-08-28", 2, "Tiffin container leaked all over my study table. Packaging needs improvement.", "negative"),
        ("Google", "Pooja Mishra", "2026-09-04", 5, "Soft phulkas and fresh sabzi every single day. 10/10.", "positive"),
        ("Google", "Rakesh Yadav", "2026-09-11", 2, "Oil smell was weird today in the sabzi, like low quality mustard or burnt oil.", "negative"),
        ("Swiggy", "Vikas Dubey", "2026-09-18", 4, "Great affordable veg tiffin. Value for money at Rs 90.", "positive"),
        ("Zomato", "Shweta Rastogi", "2026-09-25", 2, "Container plastic was cracked and lid was loose. Please change packaging vendor.", "negative"),
        ("Google", "Ankit Sahu", "2026-10-02", 5, "Navratri special satvik thali was clean and freshly cooked.", "positive")
    ]
    # expand to 40 reviews
    ir_rows = []
    for idx, (src, auth, dt, rat, txt, sent) in enumerate(inet_reviews_data):
        ir_rows.append(f"    ('IREV-{idx + 1:03d}', '{src}', '{auth}', '{dt}', {rat}, {sql_str(txt)}, '{sent}')")
    
    for idx in range(len(inet_reviews_data), 40):
        src = rng.choice(["Google", "Zomato", "Swiggy"])
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        dt = (FROZEN_DATE - datetime.timedelta(days=rng.randint(3, 85))).isoformat()
        rat = rng.choice([4, 5, 5, 4, 3, 5, 4])
        txt = "Consistent quality and always delivered with care. Great for daily meals."
        sent = "positive"
        ir_rows.append(f"    ('IREV-{idx + 1:03d}', '{src}', '{fn} {ln}', '{dt}', {rat}, {sql_str(txt)}, '{sent}')")
    lines.append(",\n".join(ir_rows) + ";\n")

    # 4. Social Media Engagement (13 weekly rows x 3 platforms)
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("-- SOCIAL MEDIA ENGAGEMENT (13 weekly rows x Instagram, WhatsApp, Facebook)")
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("INSERT INTO social_media_engagement (engagement_id, platform, week_start, followers, reach, impressions, likes, comments, shares, enquiries) VALUES")
    sme_rows = []
    sme_idx = 1
    for w in range(13):
        w_start = (START_DATE + datetime.timedelta(weeks=w)).isoformat()
        is_festival_week = (w == 11) # Navratri festival launch
        spike = 2.8 if is_festival_week else 1.0

        for plat in ["Instagram", "WhatsApp Business", "Facebook"]:
            foll = 1200 + w * 45
            reach = int(rng.randint(2400, 3200) * spike)
            impr = int(reach * 1.45)
            likes = int(rng.randint(180, 260) * spike)
            comm = int(rng.randint(15, 35) * spike)
            shares = int(rng.randint(10, 25) * spike)
            enq = int(rng.randint(8, 20) * (3.5 if is_festival_week else 1.0))
            sme_rows.append(
                f"    ('SME-{sme_idx:03d}', '{plat}', '{w_start}', {foll}, {reach}, {impr}, {likes}, {comm}, {shares}, {enq})"
            )
            sme_idx += 1
    lines.append(",\n".join(sme_rows) + ";\n")

    # 5. Supplier Updates (~25 rows)
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("-- SUPPLIER UPDATES (~25 updates including price changes, delays, schemes)")
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("INSERT INTO supplier_updates (update_id, supplier_id, date, type, message) VALUES")
    supp_updates = [
        ("SUP-01", "2026-10-08", "stockout", "Sunflower oil 1L warehouse stock exhausted; next container shipment arriving 2026-10-13."),
        ("SUP-02", "2026-09-14", "delay", "Tempo breakdown in Fazalganj; morning deliveries delayed by 2.5 hours."),
        ("SUP-03", "2026-10-01", "price_change", "Edible oil rate revised to Rs 148/L effective 1st October due to festival transport costs."),
        ("SUP-04", "2026-10-09", "scheme", "Festive flash delivery flat Rs 49 on emergency orders below Rs 2500 in Kakadeo zone."),
        ("SUP-01", "2026-08-20", "scheme", "Festival advance booking scheme: Free delivery on orders above Rs 500."),
        ("SUP-02", "2026-10-06", "stockout", "Heavy demand on 750ml containers; fresh consignment arriving Sunday morning."),
        ("SUP-03", "2026-09-01", "price_change", "Sunflower oil bulk supply adjusted to Rs 146/L.")
    ]
    # expand to 25 rows
    su_rows = []
    for s_u_i, (sid, sdt, styp, smsg) in enumerate(supp_updates):
        su_rows.append(f"    ('SUPD-{s_u_i + 1:03d}', '{sid}', '{sdt}', '{styp}', {sql_str(smsg)})")
    
    for s_u_i in range(len(supp_updates), 25):
        sid = rng.choice(["SUP-01", "SUP-02", "SUP-03", "SUP-04"])
        sdt = (FROZEN_DATE - datetime.timedelta(days=rng.randint(2, 80))).isoformat()
        styp = rng.choice(["scheme", "price_change", "delay"])
        smsg = f"Regular logistics and catalogue notification from {sid}."
        su_rows.append(f"    ('SUPD-{s_u_i + 1:03d}', '{sid}', '{sdt}', '{styp}', {sql_str(smsg)})")
    lines.append(",\n".join(su_rows) + ";\n")

    # 6. Customer Updates (~120 rows)
    # Extra test edge cases:
    # - One paused subscription effective tomorrow: CUST-009 paused for tomorrow
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("-- CUSTOMER UPDATES (~120 Hinglish customer updates: pause, resume, new orders)")
    lines.append("-- ----------------------------------------------------------------------------")
    lines.append("INSERT INTO customer_updates (update_id, customer_id, date, type, message) VALUES")
    cu_rows = []
    # Dedicated edge case update
    cu_rows.append(
        "    ('CUPD-001', 'CUST-009', '2026-10-10', 'pause', 'kal se tiffin band rakhna, 3 din out of town hu')"
    )
    
    hinglish_messages = [
        ("pause", "kal ka tiffin cancel kar dijiye, coaching test hai"),
        ("pause", "do din ke liye pause kar do, ghar ja raha hu"),
        ("resume", "kal se tiffin fir se shuru kar dijiye"),
        ("new_order", "aaj lunch me ek extra tiffin bhej dena"),
        ("complaint", "bhaiya sabzi me mirchi thodi kam rakha karo"),
        ("address_change", "room change ho gaya hai, naya address block 4 Kakadeo hai"),
        ("feedback", "aaj ki dal bahut badhiya thi, bilkul mummy ke haath jaisi"),
        ("pause", "navratri vrat hai, agle 4 din tiffin mat bhejna")
    ]
    for c_u_i in range(1, 120):
        c = customers[c_u_i % len(customers)]
        typ, msg = rng.choice(hinglish_messages)
        c_dt = (FROZEN_DATE - datetime.timedelta(days=rng.randint(0, 80))).isoformat()
        cu_rows.append(f"    ('CUPD-{c_u_i + 1:03d}', '{c['customer_id']}', '{c_dt}', '{typ}', {sql_str(msg)})")
    lines.append(",\n".join(cu_rows) + ";\n")

    return "\n".join(lines)


def main() -> None:
    customers, cust_sql = generate_customers()
    cust_metrics_sql = generate_customer_metrics()
    slots, cap_sql = generate_capacity_and_slots()
    daily_sql, monthly_sql, orders_sql, demand_sql = generate_demand_and_metrics_and_orders(customers, slots)
    po_sql, ph_sql, sph_sql, ledgers_sql = generate_purchases_and_ledgers()
    intel_sql = generate_reviews_and_social_and_segments(customers)

    # Re-insert slots with their finalized booked_units
    slot_rows = []
    for s in slots:
        slot_rows.append(
            f"    ('{s['slot_id']}', '{s['date']}', '{s['slot_label']}', '{s['start_time']}', '{s['end_time']}', "
            f"{s['capacity_units']}, {s['booked_units']})"
        )
    slots_sql = (
        "-- ----------------------------------------------------------------------------\n"
        "-- DELIVERY SLOTS (Historical & Future slots; booked units synchronized)\n"
        "-- ----------------------------------------------------------------------------\n"
        "INSERT INTO delivery_slots (slot_id, date, slot_label, start_time, end_time, capacity_units, booked_units) VALUES\n"
        + ",\n".join(slot_rows) + ";\n"
    )

    full_sql = "\n\n".join([
        "-- ============================================================================",
        "-- Alexa Business Autopilot: Deterministic Seed Bulk Data (seed=42)",
        "-- ============================================================================",
        cust_sql,
        cust_metrics_sql,
        cap_sql,
        slots_sql,
        daily_sql,
        monthly_sql,
        orders_sql,
        demand_sql,
        po_sql,
        ph_sql,
        sph_sql,
        ledgers_sql,
        intel_sql
    ])

    out_file = "/Users/sethiyapreet298/Amazom_Developer_Hackathon/Amazom_Developer_Hackathon/demo_data/seed_bulk.sql"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(full_sql)
    print(f"Successfully generated {out_file} (bytes: {len(full_sql)})")


if __name__ == "__main__":
    main()

