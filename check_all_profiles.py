from src.simulator import BusinessSimulator, load_business_profiles

profiles = load_business_profiles()

for key, profile in profiles.items():
    sim = BusinessSimulator(profile=profile, days=90, seed=42)
    res = sim.run()
    s = res.to_summary_dict()

    print(
        f"{key}: "
        f"Rev=Rs.{s['total_revenue']:,.0f} "
        f"Cost=Rs.{s['total_cost']:,.0f} "
        f"Profit=Rs.{s['net_profit']:,.0f} "
        f"OCF=Rs.{s['operating_cash_flow']:,.0f} "
        f"EndCash=Rs.{s['ending_cash']:,.0f} "
        f"FulRate={s['fulfillment_rate_pct']}% "
        f"Stockouts={s['total_stockout_days']} "
        f"Customers={s['total_customers_acquired']} "
        f"TotalCust={s['total_customer_base']} "
        f"Wastage={s['total_wastage_units']:,.1f}"
    )
