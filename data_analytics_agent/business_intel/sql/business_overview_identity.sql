-- ============================================================================
-- Business Overview: Identity, Profile and Policy
-- ============================================================================
SELECT 
    bp.business_name,
    bp.archetype,
    bp.owner_name,
    bp.city,
    bp.locality,
    bp.state,
    bp.currency,
    m_menu.value AS menu_item,
    CAST(m_one.value AS REAL) AS price_one_off,
    CAST(m_sub.value AS REAL) AS price_subscription
FROM business_profile bp
LEFT JOIN meta m_menu ON m_menu.key = 'single_menu_item'
LEFT JOIN meta m_one ON m_one.key = 'menu_price_one_off'
LEFT JOIN meta m_sub ON m_sub.key = 'menu_price_subscription';

