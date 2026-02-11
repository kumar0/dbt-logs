select
    order_id,
    customer_id,
    order_date,
    order_status,
    total_amount,
    shipping_address,
    shipping_city,
    shipping_state,
    shipping_zip,
    created_at,
    updated_at
from {{ source('etl_source', 'orders') }}