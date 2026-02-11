select
    order_item_id,
    order_id,
    product_id,
    quantity,
    unit_price,
    line_total,
    discount,
    created_at
from {{ source('etl_source', 'order_items') }}