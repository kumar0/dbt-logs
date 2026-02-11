{{ config( materialized='view' ) }}


with order_items as (
    select * from {{ ref('stg_order_items') }}
),

orders as (
    select * from {{ ref('fact_orders') }}
),

products as (
    select * from {{ ref('dim_products') }}
    where is_current = 'Y'
),

final as (
    select
        cast(abs(hash(oi.order_item_id)) as bigint) as order_item_sk,
        o.order_sk,
        p.product_sk,
        oi.order_id,
        oi.product_id,
        oi.quantity,
        oi.unit_price,
        oi.line_total,
        oi.discount,
        oi.created_at
    from order_items oi
    left join orders o on oi.order_id = o.order_id
    left join products p on oi.product_id = p.product_id
)

select * from final