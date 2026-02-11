
{{
    config(
        materialized='incremental',
        unique_key=['product_sk'],
        incremental_strategy='insert_overwrite',
        file_format='iceberg',
        iceberg_expire_snapshots='False',
        partition_by=['is_current']
    )
}}

{% if is_incremental() %}


with source_data as (
    select * from {{ ref('stg_products') }}
),

existing_records as (
    select * from {{ this }}
    where is_current = 'Y'
),

changed_records as (
    select
        s.product_id,
        s.name,
        s.category,
        s.price,
        s.cost,
        s.supplier,
        s.status,
        s.created_at,
        s.updated_at
    from source_data s
    inner join existing_records e on s.product_id = e.product_id
    where s.updated_at > e.updated_at
        or s.name != e.name
        or s.category != e.category
        or s.price != e.price
        or s.cost != e.cost
        or s.supplier != e.supplier
        or s.status != e.status
),

expired_records as (
    select
        e.product_sk,
        e.product_id,
        e.name,
        e.category,
        e.price,
        e.cost,
        e.supplier,
        e.status,
        e.effective_date,
        current_date as end_date,
        'N' as is_current,
        e.created_at,
        e.updated_at
    from existing_records e
    inner join changed_records c on e.product_id = c.product_id
),

new_records as (
    select
        cast(abs(hash(product_id, cast(updated_at as string))) as bigint) as product_sk,
        product_id,
        name,
        category,
        price,
        cost,
        supplier,
        status,
        current_date as effective_date,
        cast(null as date) as end_date,
        'Y' as is_current,
        created_at,
        updated_at
    from changed_records
),

unchanged_new_records as (
    select
        cast(abs(hash(product_id, cast(updated_at as string))) as bigint) as product_sk,
        product_id,
        name,
        category,
        price,
        cost,
        supplier,
        status,
        current_date as effective_date,
        cast(null as date) as end_date,
        'Y' as is_current,
        created_at,
        updated_at
    from source_data s
    where not exists (
        select 1 from existing_records e where e.product_id = s.product_id
    )
)


select * from expired_records
union all
select * from new_records
union all
select * from unchanged_new_records

{% else %}


select
    cast(abs(hash(product_id, cast(updated_at as string))) as bigint) as product_sk,
    product_id,
    name,
    category,
    price,
    cost,
    supplier,
    status,
    current_date as effective_date,
    cast(null as date) as end_date,
    'Y' as is_current,
    created_at,
    updated_at
from {{ ref('stg_products') }}

{% endif %}