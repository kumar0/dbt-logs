
{{
    config(
        materialized='incremental',
        unique_key=['customer_sk'],
        incremental_strategy='insert_overwrite',
        file_format='iceberg',
        iceberg_expire_snapshots='False',
        partition_by=['is_current']
    )
}}

{% if is_incremental() %}


with source_data as (
    select * from {{ ref('stg_customers') }}
),

existing_records as (
    select * from {{ this }}
    where is_current = 'Y'
),

changed_records as (
    select
        s.customer_id,
        s.first_name,
        s.last_name,
        s.email,
        s.phone,
        s.address,
        s.city,
        s.state,
        s.zip_code,
        s.status,
        s.created_at,
        s.updated_at
    from source_data s
    inner join existing_records e on s.customer_id = e.customer_id
    where s.updated_at > e.updated_at
        or s.first_name != e.first_name
        or s.last_name != e.last_name
        or s.email != e.email
        or s.phone != e.phone
        or s.address != e.address
        or s.city != e.city
        or s.state != e.state
        or s.zip_code != e.zip_code
        or s.status != e.status
),

expired_records as (
    select
        e.customer_sk,
        e.customer_id,
        e.first_name,
        e.last_name,
        e.email,
        e.phone,
        e.address,
        e.city,
        e.state,
        e.zip_code,
        e.status,
        e.effective_date,
        current_date as end_date,
        'N' as is_current,
        e.created_at,
        e.updated_at
    from existing_records e
    inner join changed_records c on e.customer_id = c.customer_id
),

new_records as (
    select
        cast(abs(hash(customer_id, cast(updated_at as string))) as bigint) as customer_sk,
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        address,
        city,
        state,
        zip_code,
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
        cast(abs(hash(customer_id, cast(updated_at as string))) as bigint) as customer_sk,
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        address,
        city,
        state,
        zip_code,
        status,
        current_date as effective_date,
        cast(null as date) as end_date,
        'Y' as is_current,
        created_at,
        updated_at
    from source_data s
    where not exists (
        select 1 from existing_records e where e.customer_id = s.customer_id
    )
)


select * from expired_records
union all
select * from new_records
union all
select * from unchanged_new_records

{% else %}


select
    cast(abs(hash(customer_id, cast(updated_at as string))) as bigint) as customer_sk,
    customer_id,
    first_name,
    last_name,
    email,
    phone,
    address,
    city,
    state,
    zip_code,
    status,
    current_date as effective_date,
    cast(null as date) as end_date,
    'Y' as is_current,
    created_at,
    updated_at
from {{ ref('stg_customers') }}

{% endif %}