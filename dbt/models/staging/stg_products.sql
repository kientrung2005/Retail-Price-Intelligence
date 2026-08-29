{{ config(materialized='view') }}

WITH deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY product_id, location_code, crawl_time
            ORDER BY crawl_time DESC
        ) AS rn
    FROM {{ source('raw', 'raw_products') }}
)

SELECT
    product_id                                                                AS site_product_id,
    product_name,
    UPPER(TRIM(brand))                                                        AS brand,
    LOWER(TRIM(category))                                                     AS category,
    NULLIF(REGEXP_REPLACE(current_price, '[^0-9]', '', 'g'), '')::BIGINT     AS current_price,
    NULLIF(REGEXP_REPLACE(original_price, '[^0-9]', '', 'g'), '')::BIGINT    AS original_price,
    COALESCE(NULLIF(REGEXP_REPLACE(discount_percent, '[^0-9]', '', 'g'), '')::INTEGER, 0) AS discount_percent,
    availability,
    INITCAP(TRIM(store_name))                                                 AS store_name,
    COALESCE(location_code, 'HN')                                             AS location_code,
    COALESCE(province_name, 'Thành phố Hà Nội')                               AS province_name,
    COALESCE(region, 'Miền Bắc')                                              AS region,
    promotions,
    product_url,
    image_url,
    rating,
    review_count,
    crawl_time,
    REGEXP_REPLACE(
        LOWER(TRIM(product_name)),
        '(chính hãng|vn/a|likenew|new 100%|đen|trắng|xanh|hồng|titan|xám)', '', 'g'
    ) AS match_key_raw
FROM deduped
WHERE rn = 1
