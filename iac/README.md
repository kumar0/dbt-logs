# ETL Platform - CDK Infrastructure

This CDK project creates an ETL platform with source and destination tables implementing SCD Type 2 (Slowly Changing Dimension).

## Architecture

### Source Tables (Transactional)

- **Customers**: Customer master data
- **Orders**: Order transactions
- **Products**: Product catalog
- **OrderItems**: Order line items
- **Payments**: Payment transactions

All source tables have DynamoDB Streams enabled for CDC (Change Data Capture).

### Destination Tables (Analytical)

#### Dimension Tables (SCD Type 2)

- **DimCustomers**: Customer dimension with history tracking
- **DimProducts**: Product dimension with history tracking

SCD Type 2 attributes:

- `customer_sk` / `product_sk`: Surrogate key (partition key)
- `effective_date`: Start date of the record (sort key)
- `end_date`: End date of the record (null for current)
- `is_current`: Flag indicating current record ('Y' or 'N')
- `natural_key`: Business key (e.g., customer_id, product_id)

#### Fact Tables

- **FactOrders**: Order facts with metrics
- **FactOrderItems**: Order item facts with metrics

## Deployment

### Prerequisites

```bash
cd iac
npm install
```

### Deploy Stack

```bash
npm run deploy
# or
cdk deploy --profile mondayskills.development
```

### Synthesize CloudFormation

```bash
npm run synth
# or
cdk synth --profile mondayskills.development
```

### Destroy Stack

```bash
npm run destroy
# or
cdk destroy --profile mondayskills.development
```

## Populate Source Data

After deploying the stack, populate the source tables with sample data:

```bash
cd scripts
pip install -r requirements.txt
python populate_source_data.py
```

This will create:

- 50 customers
- 30 products
- 100 orders
- ~300 order items (avg 3 per order)
- ~80 payments (for non-cancelled orders)

## SCD Type 2 Implementation

The destination dimension tables support SCD Type 2 with:

1. **Surrogate Keys**: Auto-generated unique identifiers
2. **Effective Dating**: `effective_date` and `end_date` track validity periods
3. **Current Flag**: `is_current` = 'Y' for active records
4. **GSI**: Global Secondary Index on `natural_key` + `is_current` for fast current record lookups

### Example Query Pattern

To get the current customer record:

```python
response = table.query(
    IndexName='current-records-index',
    KeyConditionExpression='natural_key = :nk AND is_current = :curr',
    ExpressionAttributeValues={
        ':nk': 'CUST-12345',
        ':curr': 'Y'
    }
)
```

## ETL Process Flow

1. **Extract**: DynamoDB Streams capture changes from source tables
2. **Transform**: Lambda functions process CDC events and apply business logic
3. **Load**:
   - For dimensions: Implement SCD Type 2 logic (expire old record, insert new)
   - For facts: Aggregate and join data from multiple sources

## Next Steps

1. Create Lambda functions to process DynamoDB Streams
2. Implement SCD Type 2 logic for dimension tables
3. Build aggregation logic for fact tables
4. Add Step Functions for orchestration
5. Implement data quality checks
6. Add monitoring and alerting
