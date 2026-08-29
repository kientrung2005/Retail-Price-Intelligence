{{ config(materialized='table') }}

SELECT
    TO_CHAR(d::date, 'YYYYMMDD')::INT AS date_key,
    d::date AS full_date,
    EXTRACT(YEAR FROM d)::SMALLINT AS year,
    EXTRACT(MONTH FROM d)::SMALLINT AS month,
    EXTRACT(DAY FROM d)::SMALLINT AS day,
    TO_CHAR(d, 'Day') AS weekday
FROM generate_series(CURRENT_DATE - INTERVAL '2 years', CURRENT_DATE + INTERVAL '1 year', INTERVAL '1 day') d
