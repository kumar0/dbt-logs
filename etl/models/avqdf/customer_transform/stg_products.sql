{{ config(materialized='view') }}

select
    product_id,
    name,
    category,
    price,
    cost,
    stock_quantity,
    supplier,
    status,
    created_at,
    updated_at
from {{ source('etl_source', 'products') }}