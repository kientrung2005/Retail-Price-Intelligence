{{ config(materialized='table') }}

SELECT
    MD5(CONCAT(s.site_product_id, '_', COALESCE(s.location_code, 'HN'), '_', TO_CHAR(s.crawl_time, 'YYYYMMDD_HH24MISS'))) AS fact_key,
    dps.product_site_key,
    dp.product_key,
    MD5(COALESCE(s.location_code, 'HN')) AS location_key,
    dd.date_key,
    s.current_price,
    s.original_price,
    s.discount_percent,
    s.availability,
    s.rating,
    s.review_count,
    s.promotions,
    s.crawl_time
FROM {{ ref('stg_products') }} s
JOIN {{ ref('dim_product_site') }} dps ON s.site_product_id = dps.site_product_id
JOIN {{ ref('dim_product') }} dp ON dps.canonical_key = dp.canonical_key
JOIN {{ ref('dim_date') }} dd ON TO_CHAR(s.crawl_time, 'YYYYMMDD')::INT = dd.date_key
