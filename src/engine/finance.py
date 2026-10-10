"""
Finance and Working Capital Engine
Separates accounting profitability from real cash-flow liquidity.
Models receivables delay (credit terms), procurement outflows, and cash runway.
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

@dataclass
class PendingReceivable:
    amount: float
    days_until_received: int

class FinanceEngine:
    def __init__(
        self,
        starting_cash: float,
        daily_fixed_cost: float,
        platform_commission_rate: float,
        receivables_delay_days: int = 0,
    ):
        self.cash_balance = starting_cash
        self.daily_fixed_cost = daily_fixed_cost
        self.platform_commission_rate = platform_commission_rate
        self.receivables_delay_days = receivables_delay_days
        self.receivables_queue: List[PendingReceivable] = []

    def process_daily_finance(
        self,
        fulfilled_orders: int,
        selling_price: float,
        unit_material_cost: float,
        variable_operating_cost: float,
        delivery_cost: float,
        marketing_spend: float,
        procurement_cash_outflow: float,
        actual_cogs: Optional[float] = None,
    ) -> Tuple[float, float, float, float, float, float, float, float, float, float]:
        """
        Executes daily financial accounting and cash movement.
        Returns:
          (revenue, cogs, platform_commission, fixed_overhead, total_cost,
           daily_profit, starting_cash, ending_cash, cash_inflow, cash_outflow)
        """
        starting_cash = self.cash_balance

        # 1. Accounting Revenue
        revenue = fulfilled_orders * selling_price

        # 2. Accounting Costs (Actual lot COGS if provided, else standard unit cost)
        cogs = actual_cogs if actual_cogs is not None else (fulfilled_orders * unit_material_cost)
        platform_commission = revenue * self.platform_commission_rate
        fixed_overhead = self.daily_fixed_cost
        total_cost = (
            cogs
            + variable_operating_cost
            + delivery_cost
            + platform_commission
            + marketing_spend
            + fixed_overhead
        )

        # 3. Accounting Profit
        daily_profit = revenue - total_cost

        # 4. Cash Inflow Processing (Receivables Pipeline)
        net_cash_earned_from_sales = revenue - platform_commission

        # Collect matured receivables from previous days first
        collected_receivables = 0.0
        remaining_queue = []
        for rec in self.receivables_queue:
            rec.days_until_received -= 1
            if rec.days_until_received <= 0:
                collected_receivables += rec.amount
            else:
                remaining_queue.append(rec)
        self.receivables_queue = remaining_queue

        # Enqueue today's credit sales or collect immediately
        if self.receivables_delay_days <= 0:
            immediate_cash_inflow = net_cash_earned_from_sales
        else:
            self.receivables_queue.append(
                PendingReceivable(
                    amount=net_cash_earned_from_sales,
                    days_until_received=self.receivables_delay_days,
                )
            )
            immediate_cash_inflow = 0.0

        total_cash_inflow = immediate_cash_inflow + collected_receivables

        # 5. Cash Outflow Processing
        # Daily operational expenses must be paid immediately in cash
        daily_opex_outflow = (
            variable_operating_cost
            + delivery_cost
            + marketing_spend
            + fixed_overhead
        )
        total_cash_outflow = procurement_cash_outflow + daily_opex_outflow

        # 6. Cash Balance Update
        self.cash_balance = starting_cash + total_cash_inflow - total_cash_outflow
        ending_cash = self.cash_balance

        return (
            revenue,
            cogs,
            platform_commission,
            fixed_overhead,
            total_cost,
            daily_profit,
            starting_cash,
            ending_cash,
            total_cash_inflow,
            total_cash_outflow,
        )
