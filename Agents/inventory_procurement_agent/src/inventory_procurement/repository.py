"""Repository layer providing safe, parameterized database queries and writes."""

import json
from typing import Any, Dict, List, Optional, Tuple

from .db import Database
from .models import BusinessPolicy, MetaInfo, ResourceNotFoundError


class BusinessRepository:
    """Shared database repository for Demand & Capacity and Inventory & Procurement agents."""

    def __init__(self, db: Database):
        self.db = db

    # -------------------------------------------------------------------------
    # System Metadata & Policies
    # -------------------------------------------------------------------------
    def get_meta(self) -> MetaInfo:
        """Fetch system metadata and planning dates."""
        rows = self.db.fetch_all("SELECT key, value FROM meta;")
        meta_dict = {row["key"]: row["value"] for row in rows}

        def to_float(val: Optional[str]) -> Optional[float]:
            return float(val) if val is not None else None

        return MetaInfo(
            as_of=meta_dict.get("as_of", ""),
            frozen_date=meta_dict.get("frozen_date", ""),
            tomorrow_date=meta_dict.get("tomorrow_date", ""),
            business_name=meta_dict.get("business_name", ""),
            currency=meta_dict.get("currency", "INR"),
            single_menu_item=meta_dict.get("single_menu_item"),
            menu_price_one_off=to_float(meta_dict.get("menu_price_one_off")),
            menu_price_subscription=to_float(meta_dict.get("menu_price_subscription")),
        )

    def get_business_policy(self) -> BusinessPolicy:
        """Fetch business policy settings."""
        row = self.db.fetch_one("SELECT * FROM business_policy LIMIT 1;")
        if not row:
            raise ResourceNotFoundError("No business policy row found in business_policy table.")
        return BusinessPolicy(
            policy_id=row["policy_id"],
            min_cash_buffer=float(row["min_cash_buffer"]),
            safety_stock_pct=float(row["safety_stock_pct"]),
            regular_order_cutoff=str(row["regular_order_cutoff"]),
            cooking_start=str(row["cooking_start"]),
            packing_start=str(row["packing_start"]),
            max_meals_per_day=int(row["max_meals_per_day"]),
            fast_delivery_fee=float(row["fast_delivery_fee"]),
            stockout_cost_per_meal=float(row["stockout_cost_per_meal"]),
        )

    def get_business_profile(self) -> Dict[str, Any]:
        """Fetch business profile information."""
        row = self.db.fetch_one("SELECT * FROM business_profile LIMIT 1;")
        return row if row else {}

    # -------------------------------------------------------------------------
    # Demand & Capacity Queries
    # -------------------------------------------------------------------------
    def get_demand_forecast(self, date: str) -> Optional[Dict[str, Any]]:
        """Fetch demand forecast row for a single date."""
        return self.db.fetch_one(
            "SELECT * FROM demand_forecast WHERE date = ?;",
            (date,),
        )

    def get_demand_forecast_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Fetch demand forecast rows between start_date and end_date (inclusive)."""
        return self.db.fetch_all(
            "SELECT * FROM demand_forecast WHERE date >= ? AND date <= ? ORDER BY date;",
            (start_date, end_date),
        )

    def get_demand_driver(self, date: str) -> Optional[Dict[str, Any]]:
        """Fetch demand driver row for a single date."""
        return self.db.fetch_one(
            "SELECT * FROM demand_drivers WHERE date = ?;",
            (date,),
        )

    def get_demand_drivers_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Fetch demand drivers rows between start_date and end_date (inclusive)."""
        return self.db.fetch_all(
            "SELECT * FROM demand_drivers WHERE date >= ? AND date <= ? ORDER BY date;",
            (start_date, end_date),
        )

    def get_orders_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Fetch all orders for a single date."""
        return self.db.fetch_all(
            "SELECT * FROM orders WHERE date = ? ORDER BY order_id;",
            (date,),
        )

    def get_order_history(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch orders within an optional date range."""
        query = "SELECT * FROM orders WHERE 1=1"
        params: List[Any] = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date, order_id;"
        return self.db.fetch_all(query, tuple(params))

    def get_capacity_for_date(self, date: str) -> Optional[Dict[str, Any]]:
        """Fetch capacity record for a date."""
        return self.db.fetch_one(
            "SELECT * FROM capacity WHERE date = ?;",
            (date,),
        )

    def get_delivery_slots_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Fetch delivery slot records for a date ordered by start_time."""
        return self.db.fetch_all(
            "SELECT * FROM delivery_slots WHERE date = ? ORDER BY start_time;",
            (date,),
        )

    def get_capacity_declarations_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Fetch declared free capacity for a date."""
        return self.db.fetch_all(
            "SELECT * FROM capacity_declarations WHERE date = ? ORDER BY created_at;",
            (date,),
        )

    def get_customer_snapshot(self) -> Dict[str, Any]:
        """Fetch aggregate customer metrics from view v_customer_snapshot."""
        row = self.db.fetch_one("SELECT * FROM v_customer_snapshot LIMIT 1;")
        return row if row else {}

    # -------------------------------------------------------------------------
    # Inventory, BOM & Stock
    # -------------------------------------------------------------------------
    def get_items(self) -> List[Dict[str, Any]]:
        """Fetch all items from items table."""
        return self.db.fetch_all("SELECT * FROM items ORDER BY item_id;")

    def get_recipe_bom(self) -> List[Dict[str, Any]]:
        """Fetch BOM recipe quantities per tiffin."""
        return self.db.fetch_all("SELECT * FROM recipe_bom ORDER BY item_id;")

    def get_inventory_stock(self) -> List[Dict[str, Any]]:
        """Fetch current inventory stock records."""
        return self.db.fetch_all("SELECT * FROM inventory_stock ORDER BY item_id;")

    def get_v_item_requirement_tomorrow(self) -> List[Dict[str, Any]]:
        """Fetch effective item requirements from view v_item_requirement_tomorrow."""
        return self.db.fetch_all("SELECT * FROM v_item_requirement_tomorrow ORDER BY item_id;")

    def get_v_shortfall_tomorrow(self) -> List[Dict[str, Any]]:
        """Fetch current item shortfalls from view v_shortfall_tomorrow."""
        return self.db.fetch_all("SELECT * FROM v_shortfall_tomorrow ORDER BY item_id;")

    def get_v_below_reorder_after_tomorrow(self) -> List[Dict[str, Any]]:
        """Fetch items below reorder point after tomorrow."""
        return self.db.fetch_all("SELECT * FROM v_below_reorder_after_tomorrow ORDER BY item_id;")

    # -------------------------------------------------------------------------
    # Suppliers & Catalogue
    # -------------------------------------------------------------------------
    def get_suppliers(self) -> List[Dict[str, Any]]:
        """Fetch all suppliers."""
        return self.db.fetch_all("SELECT * FROM suppliers ORDER BY supplier_id;")

    def get_catalogue(self) -> List[Dict[str, Any]]:
        """Fetch all catalogue listings."""
        return self.db.fetch_all("SELECT * FROM catalogue ORDER BY supplier_id, item_id;")

    def get_supplier_inventory_info(self) -> List[Dict[str, Any]]:
        """Fetch supplier inventory availability notes."""
        return self.db.fetch_all("SELECT * FROM supplier_inventory_info ORDER BY supplier_id, item_id;")

    def get_supplier_updates(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch supplier updates/delays/stockout alerts."""
        if date:
            return self.db.fetch_all(
                "SELECT * FROM supplier_updates WHERE date = ? ORDER BY update_id;",
                (date,),
            )
        return self.db.fetch_all("SELECT * FROM supplier_updates ORDER BY date DESC, update_id;")

    def get_supplier_price_history(self, item_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch historical supplier prices."""
        if item_id:
            return self.db.fetch_all(
                "SELECT * FROM supplier_price_history WHERE item_id = ? ORDER BY effective_date DESC;",
                (item_id,),
            )
        return self.db.fetch_all("SELECT * FROM supplier_price_history ORDER BY effective_date DESC;")

    def get_v_supplier_options(self) -> List[Dict[str, Any]]:
        """Fetch pre-computed supplier feasibility options from view v_supplier_options."""
        return self.db.fetch_all("SELECT * FROM v_supplier_options ORDER BY item_id, price_per_pack;")

    def get_reference_plans(self) -> List[Dict[str, Any]]:
        """Fetch seeded reference procurement plans."""
        return self.db.fetch_all("SELECT * FROM reference_plans ORDER BY plan_id;")

    def get_reference_plan_lines(self, plan_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch reference procurement plan lines."""
        if plan_id:
            return self.db.fetch_all(
                "SELECT * FROM reference_plan_lines WHERE plan_id = ? ORDER BY plan_line_id;",
                (plan_id,),
            )
        return self.db.fetch_all("SELECT * FROM reference_plan_lines ORDER BY plan_id, plan_line_id;")

    def get_v_plan_cost(self) -> List[Dict[str, Any]]:
        """Fetch plan cost summary from view v_plan_cost."""
        return self.db.fetch_all("SELECT * FROM v_plan_cost ORDER BY total_cost;")

    # -------------------------------------------------------------------------
    # Cash & Financial Queries
    # -------------------------------------------------------------------------
    def get_cash_position(self) -> Dict[str, Any]:
        """Fetch current cash balance and minimum cash buffer."""
        row = self.db.fetch_one("SELECT * FROM cash_position ORDER BY as_of DESC LIMIT 1;")
        return row if row else {}

    def get_v_cash_headroom(self) -> Dict[str, Any]:
        """Fetch calculated cash headroom from view v_cash_headroom."""
        row = self.db.fetch_one("SELECT * FROM v_cash_headroom LIMIT 1;")
        return row if row else {}

    def get_forecasted_balance(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch projected cash balance records."""
        if date:
            return self.db.fetch_all(
                "SELECT * FROM forecasted_balance WHERE date = ?;",
                (date,),
            )
        return self.db.fetch_all("SELECT * FROM forecasted_balance ORDER BY date;")

    def get_upcoming_payments(self) -> List[Dict[str, Any]]:
        """Fetch upcoming payment obligations."""
        return self.db.fetch_all("SELECT * FROM upcoming_payments ORDER BY due_date;")

    # -------------------------------------------------------------------------
    # Procurement Planning & Execution Writes
    # -------------------------------------------------------------------------
    def insert_purchase_plan(
        self,
        plan_id: str,
        created_at: str,
        total_cost: float,
        status: str = "draft",
    ) -> None:
        """Insert a new purchase plan."""
        self.db.execute(
            """
            INSERT INTO purchase_plans (plan_id, created_at, total_cost, status)
            VALUES (?, ?, ?, ?);
            """,
            (plan_id, created_at, total_cost, status),
        )

    def insert_purchase_plan_line(
        self,
        line_id: str,
        plan_id: str,
        supplier_id: str,
        item_id: str,
        pack_qty: int,
        unit_price: float,
        line_total: float,
    ) -> None:
        """Insert a single purchase plan item line."""
        self.db.execute(
            """
            INSERT INTO purchase_plan_lines (line_id, plan_id, supplier_id, item_id, pack_qty, unit_price, line_total)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (line_id, plan_id, supplier_id, item_id, pack_qty, unit_price, line_total),
        )

    def insert_approval(
        self,
        token: str,
        plan_id: str,
        total: float,
        expires_at: str,
        used: int = 0,
    ) -> None:
        """Insert an approval token for a purchase plan."""
        self.db.execute(
            """
            INSERT INTO approvals (token, plan_id, total, expires_at, used)
            VALUES (?, ?, ?, ?, ?);
            """,
            (token, plan_id, total, expires_at, used),
        )

    def insert_audit_log(
        self,
        action: str,
        actor: str,
        payload: Optional[str],
        timestamp: str,
    ) -> int:
        """Insert an audit log entry."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_log (action, actor, payload, timestamp)
                VALUES (?, ?, ?, ?);
                """,
                (action, actor, payload, timestamp),
            )
            conn.commit()
            return cursor.lastrowid

    def get_purchase_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Fetch purchase plan by ID."""
        return self.db.fetch_one(
            "SELECT * FROM purchase_plans WHERE plan_id = ?;",
            (plan_id,),
        )

    def get_purchase_plan_lines(self, plan_id: str) -> List[Dict[str, Any]]:
        """Fetch line items for a purchase plan."""
        return self.db.fetch_all(
            "SELECT * FROM purchase_plan_lines WHERE plan_id = ? ORDER BY line_id;",
            (plan_id,),
        )

    def get_approval_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Fetch approval record by token."""
        return self.db.fetch_one(
            "SELECT * FROM approvals WHERE token = ?;",
            (token,),
        )

    def get_approval_by_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Fetch approval record by plan_id."""
        return self.db.fetch_one(
            "SELECT * FROM approvals WHERE plan_id = ? ORDER BY expires_at DESC LIMIT 1;",
            (plan_id,),
        )

    def get_simulated_orders(self) -> List[Dict[str, Any]]:
        """Fetch all simulated order entries."""
        return self.db.fetch_all("SELECT * FROM simulated_orders ORDER BY created_at DESC;")

    def execute_plan_transaction(
        self,
        plan_id: str,
        approval_token: str,
        sim_order_id: str,
        order_payload: str,
        timestamp: str,
    ) -> int:
        """Execute a purchase plan in a single atomic database transaction.

        - Marks purchase_plan status = 'executed'
        - Marks approval token used = 1
        - Inserts into simulated_orders
        - Inserts into audit_log
        """
        with self.db.transaction() as conn:
            # 1. Update purchase_plans
            conn.execute(
                "UPDATE purchase_plans SET status = 'executed' WHERE plan_id = ?;",
                (plan_id,),
            )
            # 2. Update approvals
            conn.execute(
                "UPDATE approvals SET used = 1 WHERE token = ?;",
                (approval_token,),
            )
            # 3. Insert simulated_orders
            conn.execute(
                """
                INSERT INTO simulated_orders (sim_order_id, order_payload, status, created_at)
                VALUES (?, ?, 'submitted', ?);
                """,
                (sim_order_id, order_payload, timestamp),
            )
            # 4. Insert audit_log
            audit_payload = json.dumps({
                "plan_id": plan_id,
                "token": approval_token,
                "sim_order_id": sim_order_id,
            })
            cursor = conn.execute(
                """
                INSERT INTO audit_log (action, actor, payload, timestamp)
                VALUES (?, ?, ?, ?);
                """,
                ("execute_purchase", "InventoryProcurementAgent", audit_payload, timestamp),
            )
            return cursor.lastrowid

