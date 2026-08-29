{{ config(materialized='incremental', unique_key='category') }}

SELECT 
    MD5(category) AS category_key,
    category
FROM (
    SELECT DISTINCT category
    FROM {{ ref('stg_products') }}
    WHERE category IS NOT NULL
) c
{% if is_incremental() %}
WHERE category NOT IN (SELECT category FROM {{ this }})
{% endif %}
