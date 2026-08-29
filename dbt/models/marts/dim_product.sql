{{ config(materialized='incremental', unique_key='canonical_key') }}

WITH mapped AS (
    SELECT
        s.match_key_raw,
        COALESCE(m.canonical_key, s.match_key_raw) AS canonical_key,
        s.product_name,
        s.brand,
        s.category,
        s.crawl_time
    FROM {{ ref('stg_products') }} s
    LEFT JOIN {{ ref('product_mapping') }} m ON s.site_product_id = m.site_product_id
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY canonical_key ORDER BY crawl_time DESC) AS rn
    FROM mapped
)
SELECT
    MD5(canonical_key) AS product_key,
    canonical_key,
    product_name AS display_name,
    MD5(brand) AS brand_key,
    MD5(category) AS category_key
FROM ranked
WHERE rn = 1
{% if is_incremental() %}
AND canonical_key NOT IN (SELECT canonical_key FROM {{ this }})
{% endif %}
