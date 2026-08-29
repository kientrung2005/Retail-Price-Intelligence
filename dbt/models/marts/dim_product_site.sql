{{ config(materialized='incremental', unique_key='site_product_id') }}

WITH ranked AS (
    SELECT
        s.site_product_id,
        s.product_name,
        s.store_name,
        s.product_url,
        s.image_url,
        s.crawl_time,
        COALESCE(m.canonical_key, s.match_key_raw) AS canonical_key,
        ROW_NUMBER() OVER (PARTITION BY s.site_product_id ORDER BY s.crawl_time DESC) AS rn
    FROM {{ ref('stg_products') }} s
    LEFT JOIN {{ ref('product_mapping') }} m ON s.site_product_id = m.site_product_id
)
SELECT 
    MD5(site_product_id) AS product_site_key,
    site_product_id,
    canonical_key,
    product_name,
    MD5(store_name) AS store_key,
    product_url,
    image_url,
    crawl_time
FROM ranked
WHERE rn = 1
{% if is_incremental() %}
AND site_product_id IN (
    SELECT site_product_id FROM {{ ref('stg_products') }}
    WHERE crawl_time > (SELECT COALESCE(MAX(crawl_time), '1900-01-01') FROM {{ this }})
)
{% endif %}
