-- ============================================================================
-- Business Overview: Internal Customer Feedback & Internet Reviews
-- ============================================================================
WITH internal_30d AS (
    SELECT 
        COUNT(*) AS internal_review_count,
        ROUND(AVG(rating), 2) AS internal_avg_rating,
        SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END) AS internal_low_rating_count
    FROM customer_reviews
    WHERE date >= (SELECT date(value, '-30 days') FROM meta WHERE key = 'frozen_date')
),
internet_90d AS (
    SELECT 
        COUNT(*) AS internet_review_count,
        ROUND(AVG(rating), 2) AS internet_avg_rating,
        SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END) AS internet_low_rating_count
    FROM internet_reviews
    WHERE date >= (SELECT date(value, '-90 days') FROM meta WHERE key = 'frozen_date')
),
low_rating_recent AS (
    SELECT 
        (SELECT COUNT(*) FROM customer_reviews WHERE rating <= 2 AND date >= (SELECT date(value, '-30 days') FROM meta WHERE key = 'frozen_date')) +
        (SELECT COUNT(*) FROM internet_reviews WHERE rating <= 2 AND date >= (SELECT date(value, '-30 days') FROM meta WHERE key = 'frozen_date')) AS total_low_rating_30d
)
SELECT 
    int30.internal_avg_rating,
    int30.internal_review_count,
    net90.internet_avg_rating,
    net90.internet_review_count,
    lr.total_low_rating_30d
FROM internal_30d int30
CROSS JOIN internet_90d net90
CROSS JOIN low_rating_recent lr;

