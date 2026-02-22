{{ config( materialized='view' ) }}


with orders as (
    select * from {{ ref('stg_orders') }}
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

customers as (
    select * from {{ ref('dim_customers') }}
    where is_current = 'Y'
),

order_aggregates as (
    select
        order_id,
        count(*) as total_items
    from order_items
    group by order_id
),

final as (
    select
        cast(abs(hash(o.order_id)) as bigint) as order_sk,
        o.order_id,
        c.customer_sk,
        o.order_date,
        o.order_status,
        o.total_amount,
        coalesce(oa.total_items, 0) as total_items,
        o.shipping_city,
        o.shipping_state,
        o.created_at
    from orders o
    left join customers c on o.customer_id = c.customer_id
    left join order_aggregates oa on o.order_id = oa.order_id
)

select * from final