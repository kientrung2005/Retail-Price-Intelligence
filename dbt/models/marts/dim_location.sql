{{ config(materialized='table') }}

SELECT
    MD5(location_code) AS location_key,
    location_code,
    province_name,
    short_name,
    region,
    province_type,
    merged_provinces,
    'Việt Nam' AS country
FROM {{ ref('dim_locations') }}
