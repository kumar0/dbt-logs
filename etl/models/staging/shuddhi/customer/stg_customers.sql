select
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
    created_at,
    updated_at
from {{ source('etl_source', 'customers') }}