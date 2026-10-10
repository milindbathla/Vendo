-- ============================================================================
-- Business Overview: Open Supplier Issues (Delays, Stockouts, Price Changes)
-- ============================================================================
SELECT 
    su.update_id,
    su.supplier_id,
    s.name AS supplier_name,
    su.date,
    su.type,
    su.message
FROM supplier_updates su
JOIN suppliers s ON su.supplier_id = s.supplier_id
WHERE su.date >= (SELECT date(value, '-14 days') FROM meta WHERE key = 'frozen_date')
  AND su.type IN ('delay', 'stockout', 'price_change')
ORDER BY su.date DESC, su.update_id DESC;

