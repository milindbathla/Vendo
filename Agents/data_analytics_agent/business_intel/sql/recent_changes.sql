-- ============================================================================
-- Recent Business Changes: Unified Multi-Source Event Stream
-- Categories: supplier, customer, procurement, document, reputation, memory, orders
-- ============================================================================
WITH all_events AS (
    -- 1. Supplier Updates
    SELECT 
        date || 'T08:00:00+05:30' AS ts,
        'supplier' AS category,
        CASE 
            WHEN type IN ('stockout', 'delay') THEN 'alert'
            WHEN type = 'price_change' THEN 'alert'
            ELSE 'notice'
        END AS severity,
        'Supplier Notice: ' || s.name AS title,
        su.message AS detail,
        'supplier_updates' AS source_table,
        su.update_id AS ref_id
    FROM supplier_updates su
    JOIN suppliers s ON su.supplier_id = s.supplier_id
    WHERE su.date >= :cutoff_date

    UNION ALL

    -- 2. Customer Updates
    SELECT 
        date || 'T10:00:00+05:30' AS ts,
        'customer' AS category,
        CASE 
            WHEN type = 'complaint' THEN 'alert'
            WHEN type = 'pause' THEN 'notice'
            ELSE 'info'
        END AS severity,
        'Customer Update: ' || c.name AS title,
        cu.message AS detail,
        'customer_updates' AS source_table,
        cu.update_id AS ref_id
    FROM customer_updates cu
    JOIN customers c ON cu.customer_id = c.customer_id
    WHERE cu.date >= :cutoff_date

    UNION ALL

    -- 3. Procurement Restocks
    SELECT 
        ph.purchase_date || 'T11:00:00+05:30' AS ts,
        'procurement' AS category,
        'info' AS severity,
        'Restock Received: ' || i.name AS title,
        'Received ' || ph.qty || ' ' || i.unit || ' via ' || s.name || ' for ₹' || CAST(ROUND(ph.total_paid) AS INT) AS detail,
        'purchase_history' AS source_table,
        ph.purchase_id AS ref_id
    FROM purchase_history ph
    JOIN items i ON ph.item_id = i.item_id
    JOIN suppliers s ON ph.supplier_id = s.supplier_id
    WHERE ph.purchase_date >= :cutoff_date

    UNION ALL

    -- 4. Business Documents Received
    SELECT 
        bd.doc_date || 'T12:00:00+05:30' AS ts,
        'document' AS category,
        CASE 
            WHEN (SELECT COUNT(*) FROM doc_ground_truth gt WHERE gt.doc_id = bd.doc_id) > 0 THEN 'alert'
            ELSE 'info'
        END AS severity,
        'Document Processed: ' || bd.doc_id AS title,
        'Received ' || bd.doc_type || ' from ' || s.name || ' (confidence ' || bd.extraction_confidence || ')' AS detail,
        'business_documents' AS source_table,
        bd.doc_id AS ref_id
    FROM business_documents bd
    JOIN suppliers s ON bd.supplier_id = s.supplier_id
    WHERE bd.doc_date >= :cutoff_date

    UNION ALL

    -- 5. Customer Reviews (Internal)
    SELECT 
        cr.date || 'T14:00:00+05:30' AS ts,
        'reputation' AS category,
        CASE WHEN cr.rating <= 2 THEN 'notice' ELSE 'info' END AS severity,
        'Internal Feedback: ' || cr.rating || '★' AS title,
        cr.review_text AS detail,
        'customer_reviews' AS source_table,
        cr.review_id AS ref_id
    FROM customer_reviews cr
    WHERE cr.date >= :cutoff_date

    UNION ALL

    -- 6. Internet Reviews
    SELECT 
        ir.date || 'T15:00:00+05:30' AS ts,
        'reputation' AS category,
        CASE WHEN ir.rating <= 2 THEN 'notice' ELSE 'info' END AS severity,
        ir.source || ' Review: ' || ir.rating || '★ by ' || ir.author_name AS title,
        ir.text AS detail,
        'internet_reviews' AS source_table,
        ir.review_id AS ref_id
    FROM internet_reviews ir
    WHERE ir.date >= :cutoff_date

    UNION ALL

    -- 7. Business Memory Writes
    SELECT 
        bm.timestamp AS ts,
        'memory' AS category,
        CASE 
            WHEN (SELECT COUNT(*) FROM business_memory m2 WHERE m2.key = bm.key AND m2.value != bm.value) > 0 THEN 'notice'
            ELSE 'info'
        END AS severity,
        'Memory Entry: ' || bm.key AS title,
        'Recorded value: "' || bm.value || '" (source: ' || bm.source || ', confidence: ' || bm.confidence || ')' AS detail,
        'business_memory' AS source_table,
        'MEM-' || bm.id AS ref_id
    FROM business_memory bm
    WHERE substr(bm.timestamp, 1, 10) >= :cutoff_date
)
SELECT 
    ts,
    category,
    severity,
    title,
    detail,
    source_table,
    ref_id
FROM all_events
ORDER BY 
    CASE severity 
        WHEN 'alert' THEN 1 
        WHEN 'notice' THEN 2 
        WHEN 'info' THEN 3 
        ELSE 4 
    END ASC,
    ts DESC;

