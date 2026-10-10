-- ============================================================================
-- Business Overview: Memory Conflicts
-- ============================================================================
SELECT 
    m1.key,
    m1.value AS verified_value,
    m1.confidence AS verified_confidence,
    m2.value AS owner_value,
    m2.confidence AS owner_confidence,
    m2.timestamp AS owner_timestamp
FROM business_memory m1
JOIN business_memory m2 ON m1.key = m2.key AND m1.id != m2.id
WHERE m1.source = 'verified_record' 
  AND m2.source = 'owner_statement'
  AND m1.value != m2.value;

