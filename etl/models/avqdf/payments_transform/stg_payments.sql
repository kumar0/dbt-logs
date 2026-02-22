{{ config(materialized='view') }}

select
    payment_id,
    order_id,
    payment_method,
    payment_status,
    amount,
    payment_date,
    transaction_id,
    created_at
from {{ source('etl_source', 'payments') }}