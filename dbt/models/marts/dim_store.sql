{{ config(materialized='incremental', unique_key='store_name') }}

SELECT 
    MD5(store_name) AS store_key,
    store_name
FROM (
    SELECT DISTINCT store_name
    FROM {{ ref('stg_products') }}
    WHERE store_name IS NOT NULL
) s
{% if is_incremental() %}
WHERE store_name NOT IN (SELECT store_name FROM {{ this }})
{% endif %}
