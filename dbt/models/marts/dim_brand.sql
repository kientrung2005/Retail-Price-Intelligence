{{ config(materialized='incremental', unique_key='brand') }}

SELECT 
    MD5(brand) AS brand_key,
    brand
FROM (
    SELECT DISTINCT brand
    FROM {{ ref('stg_products') }}
    WHERE brand IS NOT NULL
) b
{% if is_incremental() %}
WHERE brand NOT IN (SELECT brand FROM {{ this }})
{% endif %}
