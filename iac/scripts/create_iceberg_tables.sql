-- Create Source Tables as Iceberg

CREATE TABLE IF NOT EXISTS etl_source_db.customers (
    customer_id string,
    first_name string,
    last_name string,
    email string,
    phone string,
    address string,
    city string,
    state string,
    zip_code string,
    status string,
    created_at timestamp,
    updated_at timestamp
) LOCATION 's3://etl-datalake-777334699019-us-east-1/source/customers/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);

CREATE TABLE IF NOT EXISTS etl_source_db.products (
    product_id string,
    name string,
    category string,
    price decimal(10, 2),
    cost decimal(10, 2),
    stock_quantity int,
    supplier string,
    status string,
    created_at timestamp,
    updated_at timestamp
) LOCATION 's3://etl-datalake-777334699019-us-east-1/source/products/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);

CREATE TABLE IF NOT EXISTS etl_source_db.orders (
    order_id string,
    customer_id string,
    order_date timestamp,
    order_status string,
    total_amount decimal(10, 2),
    shipping_address string,
    shipping_city string,
    shipping_state string,
    shipping_zip string,
    created_at timestamp,
    updated_at timestamp
) LOCATION 's3://etl-datalake-777334699019-us-east-1/source/orders/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);

CREATE TABLE IF NOT EXISTS etl_source_db.order_items (
    order_item_id string,
    order_id string,
    product_id string,
    quantity int,
    unit_price decimal(10, 2),
    line_total decimal(10, 2),
    discount decimal(10, 2),
    created_at timestamp
) LOCATION 's3://etl-datalake-777334699019-us-east-1/source/order_items/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);

CREATE TABLE IF NOT EXISTS etl_source_db.payments (
    payment_id string,
    order_id string,
    payment_method string,
    payment_status string,
    amount decimal(10, 2),
    payment_date timestamp,
    transaction_id string,
    created_at timestamp
) LOCATION 's3://etl-datalake-777334699019-us-east-1/source/payments/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);

-- Create Destination Tables as Iceberg with SCD Type 2

CREATE TABLE IF NOT EXISTS etl_dest_db.dim_customers (
    customer_sk string,
    customer_id string,
    first_name string,
    last_name string,
    email string,
    phone string,
    address string,
    city string,
    state string,
    zip_code string,
    status string,
    effective_date timestamp,
    end_date timestamp,
    is_current string,
    created_at timestamp,
    updated_at timestamp
) PARTITIONED BY (is_current) LOCATION 's3://etl-datalake-777334699019-us-east-1/destination/dim_customers/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);

CREATE TABLE IF NOT EXISTS etl_dest_db.dim_products (
    product_sk string,
    product_id string,
    name string,
    category string,
    price decimal(10, 2),
    cost decimal(10, 2),
    supplier string,
    status string,
    effective_date timestamp,
    end_date timestamp,
    is_current string,
    created_at timestamp,
    updated_at timestamp
) PARTITIONED BY (is_current) LOCATION 's3://etl-datalake-777334699019-us-east-1/destination/dim_products/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);

CREATE TABLE IF NOT EXISTS etl_dest_db.fact_orders (
    order_sk string,
    order_id string,
    customer_sk string,
    order_date timestamp,
    order_status string,
    total_amount decimal(10, 2),
    total_items int,
    shipping_city string,
    shipping_state string,
    created_at timestamp
) LOCATION 's3://etl-datalake-777334699019-us-east-1/destination/fact_orders/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);

CREATE TABLE IF NOT EXISTS etl_dest_db.fact_order_items (
    order_item_sk string,
    order_sk string,
    product_sk string,
    order_id string,
    product_id string,
    quantity int,
    unit_price decimal(10, 2),
    line_total decimal(10, 2),
    discount decimal(10, 2),
    created_at timestamp
) LOCATION 's3://etl-datalake-777334699019-us-east-1/destination/fact_order_items/' TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);