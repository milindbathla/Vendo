-- ============================================================================
-- Business Memory: Retrieval and Candidate History
-- ============================================================================
SELECT 
    id,
    key,
    value,
    source,
    timestamp,
    confidence
FROM business_memory
WHERE (:key IS NULL OR key = :key)
  AND (:prefix IS NULL OR key LIKE :prefix || '%')
ORDER BY key ASC, 
         CASE source WHEN 'verified_record' THEN 1 ELSE 2 END ASC,
         confidence DESC,
         timestamp DESC;

