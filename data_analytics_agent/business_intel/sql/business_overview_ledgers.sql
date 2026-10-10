-- ============================================================================
-- Business Overview: Supplier Dues & Customer Outstanding Balances
-- ============================================================================
WITH latest_supplier_dues AS (
    SELECT 
        supplier_id,
        balance_due,
        ROW_NUMBER() OVER (PARTITION BY supplier_id ORDER BY date DESC, entry_id DESC) AS rn
    FROM supplier_business_records
),
latest_customer_dues AS (
    SELECT 
        customer_id,
        balance_due,
        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY date DESC, entry_id DESC) AS rn
    FROM customer_business_records
)
SELECT 
    (SELECT COALESCE(SUM(balance_due), 0.0) FROM latest_supplier_dues WHERE rn = 1) AS total_supplier_dues,
    (SELECT COALESCE(SUM(balance_due), 0.0) FROM latest_customer_dues WHERE rn = 1) AS total_customer_outstanding,
    (SELECT COUNT(*) FROM latest_customer_dues WHERE rn = 1 AND balance_due > 0) AS customers_with_balance;

