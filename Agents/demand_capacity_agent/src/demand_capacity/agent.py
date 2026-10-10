"""Demand & Capacity specialist agent."""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from .db import Database
from .engine import calculate_effective_units, calculate_item_requirement
from .models import (
    AdditionalDemandSimulationResponse,
    CapacityStatusResponse,
    DeliverySlotStatus,
    DemandDriverInfo,
    DemandForecastResponse,
    DemandPatternAnalysis,
    ForecastDayResult,
    ItemRequirementSim,
    ValidationError,
)
from .repository import BusinessRepository


class DemandCapacityAgent:
    """Specialist agent for demand forecasting, historical patterns, and capacity constraints."""

    def __init__(self, repository: BusinessRepository):
        self.repo = repository

    @classmethod
    def from_db_path(cls, db_path: str) -> "DemandCapacityAgent":
        """Instantiate agent from an SQLite database path."""
        db = Database(db_path)
        repo = BusinessRepository(db)
        return cls(repo)

    # -------------------------------------------------------------------------
    # 1. forecast_demand
    # -------------------------------------------------------------------------
    def forecast_demand(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        scenario: Optional[str] = None,
    ) -> DemandForecastResponse:
        """Fetch demand forecasts joined with demand drivers and order commitments.

        Defaults to the tomorrow planning date from meta when dates are omitted.
        Distinguishes confirmed/tentative historical orders from forecast values.
        """
        meta = self.repo.get_meta()
        planning_date = meta.tomorrow_date

        if start_date is None and end_date is None:
            start_date = planning_date
            end_date = planning_date
        elif start_date is not None and end_date is None:
            end_date = start_date
        elif start_date is None and end_date is not None:
            start_date = end_date

        if start_date > end_date:
            raise ValidationError(f"start_date '{start_date}' cannot be after end_date '{end_date}'.")

        forecast_rows = self.repo.get_demand_forecast_range(start_date, end_date)
        forecast_by_date = {r["date"]: r for r in forecast_rows}

        drivers_rows = self.repo.get_demand_drivers_range(start_date, end_date)
        drivers_by_date = {r["date"]: r for r in drivers_rows}

        all_orders = self.repo.get_order_history(start_date, end_date)
        orders_by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for order in all_orders:
            orders_by_date[order["date"]].append(order)

        date_set = set(forecast_by_date.keys()) | set(drivers_by_date.keys()) | {start_date, end_date}
        sorted_dates = sorted([d for d in date_set if start_date <= d <= end_date])

        day_results: List[ForecastDayResult] = []
        total_forecast = 0.0
        total_confirmed = 0
        total_tentative = 0

        for d in sorted_dates:
            fc_row = forecast_by_date.get(d)
            drv_row = drivers_by_date.get(d)
            orders = orders_by_date.get(d, [])

            driver_info = None
            if drv_row:
                driver_info = DemandDriverInfo(
                    date=drv_row["date"],
                    weekday=drv_row.get("day_of_week") or drv_row.get("weekday", ""),
                    is_holiday=int(drv_row.get("is_holiday", 0)),
                    festival=drv_row.get("festival"),
                    weather=drv_row.get("weather_note") or drv_row.get("weather"),
                    local_event=drv_row.get("local_event"),
                    subscription_pauses=int(drv_row.get("subscription_pauses", 0)),
                )

            confirmed_orders = [o for o in orders if o["status"] == "confirmed"]
            confirmed_units = sum(int(o["units"]) for o in confirmed_orders)
            confirmed_count = len(confirmed_orders)

            tentative_orders = [o for o in orders if o["status"] == "tentative"]
            tentative_units = sum(int(o["units"]) for o in tentative_orders)

            total_confirmed += confirmed_units
            total_tentative += tentative_units

            if fc_row:
                u_fc = float(fc_row["units_forecast"])
                total_forecast += u_fc
                day_results.append(
                    ForecastDayResult(
                        date=d,
                        status="available",
                        forecast_units=u_fc,
                        lower_bound=float(fc_row["lower"]) if fc_row.get("lower") is not None else (float(fc_row["units_lower"]) if fc_row.get("units_lower") is not None else None),
                        upper_bound=float(fc_row["upper"]) if fc_row.get("upper") is not None else (float(fc_row["units_upper"]) if fc_row.get("units_upper") is not None else None),
                        confidence=float(fc_row["confidence"]) if fc_row.get("confidence") is not None else None,
                        method=fc_row.get("method"),
                        demand_driver=driver_info,
                        confirmed_orders_count=confirmed_count,
                        confirmed_units=confirmed_units,
                        tentative_units=tentative_units,
                        note="Forecast retrieved from database.",
                    )
                )
            else:
                day_results.append(
                    ForecastDayResult(
                        date=d,
                        status="unavailable",
                        demand_driver=driver_info,
                        confirmed_orders_count=confirmed_count,
                        confirmed_units=confirmed_units,
                        tentative_units=tentative_units,
                        note=f"No forecast record exists in demand_forecast for {d}.",
                    )
                )

        notes = [
            f"Planning date in meta is {planning_date}.",
            f"Query range: {start_date} to {end_date}.",
        ]
        if scenario:
            notes.append(f"Scenario requested: {scenario} (baseline model returned).")

        return DemandForecastResponse(
            planning_date=planning_date,
            start_date=start_date,
            end_date=end_date,
            scenario=scenario,
            days=day_results,
            total_forecast_units=total_forecast,
            total_confirmed_units=total_confirmed,
            total_tentative_units=total_tentative,
            notes=notes,
        )

    # -------------------------------------------------------------------------
    # 2. analyze_demand_patterns
    # -------------------------------------------------------------------------
    def analyze_demand_patterns(
        self,
        date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> DemandPatternAnalysis:
        """Analyze order history by weekday, order type, status, and driver correlation."""
        if date and not start_date and not end_date:
            start_date = date
            end_date = date

        orders = self.repo.get_order_history(start_date, end_date)
        if not orders:
            raise ValidationError(
                f"No order records found for the requested timeframe ({start_date or 'all'} to {end_date or 'all'})."
            )

        sample_size = len(orders)
        min_date = min(o["date"] for o in orders)
        max_date = max(o["date"] for o in orders)

        driver_rows = self.repo.get_demand_drivers_range(min_date, max_date)
        weekday_map = {d["date"]: (d.get("day_of_week") or d.get("weekday", "Unknown")) for d in driver_rows}

        weekday_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"order_count": 0, "total_units": 0, "dates": set()}
        )
        type_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"order_count": 0, "total_units": 0}
        )
        status_stats: Dict[str, int] = defaultdict(int)

        for o in orders:
            w_day = weekday_map.get(o["date"], "Unknown")
            units = int(o["units"])
            o_type = o.get("type", "unknown")
            o_status = o.get("status", "unknown")

            weekday_stats[w_day]["order_count"] += 1
            weekday_stats[w_day]["total_units"] += units
            weekday_stats[w_day]["dates"].add(o["date"])

            type_stats[o_type]["order_count"] += 1
            type_stats[o_type]["total_units"] += units

            status_stats[o_status] += 1

        weekday_distribution: Dict[str, Dict[str, Any]] = {}
        for w_day, s in weekday_stats.items():
            num_days = max(1, len(s["dates"]))
            weekday_distribution[w_day] = {
                "order_count": s["order_count"],
                "total_units": s["total_units"],
                "active_days": num_days,
                "avg_units_per_day": round(s["total_units"] / num_days, 2),
            }

        total_units_all = sum(s["total_units"] for s in type_stats.values())
        order_type_distribution: Dict[str, Dict[str, Any]] = {}
        for o_type, s in type_stats.items():
            share_pct = round((s["total_units"] / total_units_all) * 100.0, 1) if total_units_all > 0 else 0.0
            order_type_distribution[o_type] = {
                "order_count": s["order_count"],
                "total_units": s["total_units"],
                "volume_share_pct": share_pct,
            }

        customer_snapshot = self.repo.get_customer_snapshot()

        trend_observations = [
            f"Analyzed {sample_size} orders spanning {min_date} to {max_date}.",
            (
                f"Subscription orders account for {order_type_distribution.get('subscription', {}).get('volume_share_pct', 0)}% "
                f"of total meal volume, demonstrating high demand stability."
            ),
            (
                f"Recurring active customers represent {customer_snapshot.get('recurring_pct', 'N/A')}% "
                f"of the active customer base."
            ),
        ]

        uncertainty_limitations = [
            "Data is sourced from a synthetic single-kitchen operational database (Maa Ki Rasoi).",
            "Observed event and weather patterns reflect local correlation; no causal relationship is asserted.",
            "Historical trends do not account for external competitor entry or unforeseen supply shocks.",
        ]

        return DemandPatternAnalysis(
            sample_size=sample_size,
            date_range={"min_date": min_date, "max_date": max_date},
            weekday_distribution=weekday_distribution,
            order_type_distribution=order_type_distribution,
            order_status_distribution=dict(status_stats),
            recurring_customer_snapshot=customer_snapshot,
            trend_observations=trend_observations,
            uncertainty_limitations=uncertainty_limitations,
        )

    # -------------------------------------------------------------------------
    # 3. get_capacity_status
    # -------------------------------------------------------------------------
    def get_capacity_status(self, date: Optional[str] = None) -> CapacityStatusResponse:
        """Inspect kitchen production capacity and delivery slot availability for a date."""
        if not date:
            date = self.repo.get_meta().tomorrow_date

        policy = self.repo.get_business_policy()
        capacity_row = self.repo.get_capacity_for_date(date)

        if capacity_row:
            max_meals = int(capacity_row["max_meals"])
            cook_hours = float(capacity_row["cook_hours"])
        else:
            max_meals = policy.max_meals_per_day
            cook_hours = 6.0

        orders = self.repo.get_orders_for_date(date)
        committed_orders = [o for o in orders if o["status"] not in ("cancelled", "refunded")]
        committed_units = sum(int(o["units"]) for o in committed_orders)

        remaining_production = max(0, max_meals - committed_units)
        utilization_pct = round((committed_units / max_meals) * 100.0, 1) if max_meals > 0 else 0.0

        slot_rows = self.repo.get_delivery_slots_for_date(date)
        delivery_slots: List[DeliverySlotStatus] = []
        total_slot_cap = 0
        total_slot_booked = 0
        total_slot_free = 0
        saturated_slots = []

        for s in slot_rows:
            cap = int(s["capacity_units"])
            booked = int(s["booked_units"])
            free = max(0, cap - booked)
            total_slot_cap += cap
            total_slot_booked += booked
            total_slot_free += free
            if free == 0:
                saturated_slots.append(s["slot_id"])

            delivery_slots.append(
                DeliverySlotStatus(
                    slot_id=s["slot_id"],
                    date=s["date"],
                    slot_label=s["slot_label"],
                    start_time=s["start_time"],
                    end_time=s["end_time"],
                    capacity_units=cap,
                    booked_units=booked,
                    free_units=free,
                )
            )

        decl_rows = self.repo.get_capacity_declarations_for_date(date)
        declared_capacity = decl_rows[0] if decl_rows else None

        bottlenecks = []
        capacity_shortfall = 0
        if committed_units > max_meals:
            capacity_shortfall = committed_units - max_meals
            bottlenecks.append(
                f"Production capacity exceeded by {capacity_shortfall} units ({committed_units}/{max_meals})."
            )

        if saturated_slots:
            bottlenecks.append(f"Delivery slots saturated: {', '.join(saturated_slots)}.")

        tightest_constraint = "none"
        if remaining_production == 0:
            tightest_constraint = "production_capacity"
        elif total_slot_free == 0:
            tightest_constraint = "delivery_slots"
        elif remaining_production < total_slot_free:
            tightest_constraint = "production_capacity"
        elif total_slot_free < remaining_production:
            tightest_constraint = "delivery_slots"

        return CapacityStatusResponse(
            date=date,
            max_production_meals=max_meals,
            cook_hours=cook_hours,
            committed_units=committed_units,
            remaining_production_capacity=remaining_production,
            production_utilization_pct=utilization_pct,
            delivery_slots=delivery_slots,
            total_slot_capacity=total_slot_cap,
            total_slot_booked=total_slot_booked,
            total_slot_free=total_slot_free,
            declared_capacity=declared_capacity,
            tightest_constraint=tightest_constraint,
            capacity_shortfall=capacity_shortfall,
            bottlenecks=bottlenecks,
        )

    # -------------------------------------------------------------------------
    # 4. simulate_additional_demand
    # -------------------------------------------------------------------------
    def simulate_additional_demand(
        self,
        additional_units: int,
        date: Optional[str] = None,
        delivery_slot_id: Optional[str] = None,
        slot_allocation_preference: Optional[str] = None,
    ) -> AdditionalDemandSimulationResponse:
        """Simulate whether kitchen can accept proposed additional units on a specific date.

        Read-only feasibility check evaluating:
        - Production capacity limit
        - Delivery slot capacity
        - Recipe BOM stock requirements vs current inventory stock
        - Restock constraints & financial headroom
        """
        if additional_units <= 0:
            raise ValidationError("additional_units must be a strictly positive integer.")

        if not date:
            date = self.repo.get_meta().tomorrow_date

        policy = self.repo.get_business_policy()
        capacity_status = self.get_capacity_status(date)

        fc_row = self.repo.get_demand_forecast(date)
        forecast_units = float(fc_row["units_forecast"]) if fc_row else 0.0
        committed_units = capacity_status.committed_units

        max_meals = capacity_status.max_production_meals
        simulated_production_demand = committed_units + additional_units
        prod_shortfall = max(0, simulated_production_demand - max_meals)
        prod_exceeded = simulated_production_demand > max_meals

        production_impact = {
            "max_meals": max_meals,
            "baseline_committed": committed_units,
            "additional_requested": additional_units,
            "simulated_total_committed": simulated_production_demand,
            "remaining_production_after": max_meals - simulated_production_demand,
            "is_exceeded": prod_exceeded,
            "shortfall": prod_shortfall,
        }

        slots = capacity_status.delivery_slots
        slot_map = {s.slot_id: s for s in slots}
        slot_exceeded = False
        slot_shortfall = 0
        selected_slot_info = None

        if delivery_slot_id:
            if delivery_slot_id not in slot_map:
                raise ValidationError(f"delivery_slot_id '{delivery_slot_id}' is invalid for date {date}.")
            target_slot = slot_map[delivery_slot_id]
            slot_free = target_slot.free_units
            if additional_units > slot_free:
                slot_exceeded = True
                slot_shortfall = additional_units - slot_free
            selected_slot_info = {
                "slot_id": target_slot.slot_id,
                "label": target_slot.slot_label,
                "free_units": slot_free,
                "remaining_after": slot_free - additional_units,
            }
        else:
            total_free = capacity_status.total_slot_free
            if additional_units > total_free:
                slot_exceeded = True
                slot_shortfall = additional_units - total_free

        slot_impact = {
            "selected_slot": selected_slot_info,
            "total_slots_free": capacity_status.total_slot_free,
            "is_exceeded": slot_exceeded,
            "shortfall": slot_shortfall,
            "slot_allocation_preference": slot_allocation_preference or "any_free_slot",
        }

        bom_rows = self.repo.get_recipe_bom()
        items_rows = self.repo.get_items()
        stock_rows = self.repo.get_inventory_stock()

        items_map = {i["item_id"]: i for i in items_rows}
        stock_map = {s["item_id"]: float(s["stock_qty"]) for s in stock_rows}

        effective_sim_units = calculate_effective_units(simulated_production_demand, policy.safety_stock_pct)

        item_reqs: List[ItemRequirementSim] = []
        stock_shortfalls: List[ItemRequirementSim] = []

        for bom in bom_rows:
            item_id = bom["item_id"]
            item_meta = items_map.get(item_id, {})
            unit = item_meta.get("unit", "kg")
            bom_qty = float(bom["qty_per_tiffin"])
            curr_stock = stock_map.get(item_id, 0.0)

            required_qty = calculate_item_requirement(effective_sim_units, bom_qty, unit)
            shortfall = max(0.0, round(required_qty - curr_stock, 3))
            is_sf = shortfall > 0

            req_sim = ItemRequirementSim(
                item_id=item_id,
                name=item_meta.get("name", item_id),
                unit=unit,
                bom_qty=bom_qty,
                required_qty=required_qty,
                current_stock=curr_stock,
                shortfall_qty=shortfall,
                is_shortfall=is_sf,
            )
            item_reqs.append(req_sim)
            if is_sf:
                stock_shortfalls.append(req_sim)

        cash_headroom_row = self.repo.get_v_cash_headroom()
        cash_headroom = float(cash_headroom_row.get("cash_headroom", 0.0))
        meta = self.repo.get_meta()
        menu_price = meta.menu_price_one_off or 90.0
        est_revenue = round(additional_units * menu_price, 2)

        financial_summary = {
            "current_balance": float(cash_headroom_row.get("current_balance", 0.0)),
            "min_cash_buffer": float(cash_headroom_row.get("min_cash_buffer", policy.min_cash_buffer)),
            "min_projected_balance": float(cash_headroom_row.get("min_projected_balance", 0.0)),
            "cash_headroom": cash_headroom,
            "estimated_incremental_revenue": est_revenue,
        }

        blockers: List[str] = []
        warnings: List[str] = []
        assumptions: List[str] = [
            f"Safety stock policy buffer: {policy.safety_stock_pct}% applied.",
            f"Menu item unit price assumption: Rs {menu_price}.",
        ]

        if prod_exceeded:
            blockers.append(
                f"Production limit exceeded: Kitchen capacity is {max_meals} meals/day; "
                f"requested total is {simulated_production_demand} meals (shortfall of {prod_shortfall} meals)."
            )

        if slot_exceeded:
            if delivery_slot_id:
                blockers.append(
                    f"Selected delivery slot {delivery_slot_id} only has {selected_slot_info['free_units']} free units "
                    f"(requested {additional_units})."
                )
            else:
                blockers.append(
                    f"Total delivery slot capacity across all slots is {capacity_status.total_slot_free} free units "
                    f"(requested {additional_units})."
                )

        restock_implications = []
        if stock_shortfalls:
            sf_names = [f"{s.name} ({s.shortfall_qty} {s.unit})" for s in stock_shortfalls]
            blockers.append(
                f"Inventory stock shortfall: {', '.join(sf_names)} are insufficient for tomorrow's production."
            )
            for sf in stock_shortfalls:
                restock_implications.append(
                    f"Requires procurement of at least {sf.shortfall_qty} {sf.unit} of {sf.name}."
                )

        binding_constraint = None
        feasible = len(blockers) == 0

        if not feasible:
            if prod_exceeded:
                binding_constraint = "production_capacity"
            elif slot_exceeded:
                binding_constraint = "delivery_slot_capacity"
            elif stock_shortfalls:
                binding_constraint = "inventory_stockout"
            else:
                binding_constraint = "operational_constraint"
            recommended_next_action = (
                f"Reject or reduce additional demand. Binding constraint: {binding_constraint}. "
                f"Review blockers before accepting."
            )
        else:
            recommended_next_action = (
                f"Accept additional demand of {additional_units} meals. Production and delivery slots available. "
                f"Stock levels are sufficient."
            )

        return AdditionalDemandSimulationResponse(
            feasible=feasible,
            binding_constraint=binding_constraint,
            date=date,
            additional_units=additional_units,
            baseline_demand={
                "forecast_units": forecast_units,
                "confirmed_units": committed_units,
            },
            production_capacity_impact=production_impact,
            delivery_slot_impact=slot_impact,
            item_requirements=item_reqs,
            stock_shortfalls=stock_shortfalls,
            restock_implications=restock_implications,
            financial_constraint_summary=financial_summary,
            blockers=blockers,
            warnings=warnings,
            assumptions=assumptions,
            recommended_next_action=recommended_next_action,
        )

