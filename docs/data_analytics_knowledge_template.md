# Data Analytics Knowledge Base Template

This is a template for creating your own data analytics knowledge base.
Copy this file to your project directory as `data_analytics_knowledge.md`
and customize it with your domain-specific information.

---

## Overview

Describe your data domain and the primary use cases for data analysis.

**Domain:** [e.g., E-commerce, Healthcare, Finance, Retail]
**Primary Data Sources:** [e.g., BigQuery, Data Warehouse, etc.]
**Key Stakeholders:** [e.g., Marketing, Operations, Finance teams]

---

## Data Architecture

### Project Structure

| GCP Project | Purpose | Access Level |
|-------------|---------|--------------|
| `project-prod` | Production data | Read-only |
| `project-analytics` | Analytics workspace | Read/Write |
| `project-sandbox` | Development/Testing | Full access |

### Key Datasets

#### Dataset: `analytics.core_metrics`
**Description:** Central metrics and KPIs
**Update Frequency:** Daily at 2:00 AM UTC
**Retention:** 3 years

#### Dataset: `analytics.user_behavior`
**Description:** User interaction and journey data
**Update Frequency:** Real-time streaming
**Retention:** 90 days

---

## Data Dictionary

### Table: `analytics.core_metrics.daily_sales`

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `date` | DATE | Transaction date | 2024-01-15 |
| `store_id` | STRING | Store identifier | STORE_001 |
| `product_category` | STRING | Product category | Electronics |
| `total_sales` | FLOAT64 | Total sales amount (USD) | 15000.50 |
| `transaction_count` | INT64 | Number of transactions | 250 |
| `avg_basket_size` | FLOAT64 | Average transaction value | 60.00 |

### Table: `analytics.user_behavior.page_views`

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `event_timestamp` | TIMESTAMP | When the event occurred | 2024-01-15 10:30:00 |
| `user_id` | STRING | Anonymous user identifier | USR_ABC123 |
| `session_id` | STRING | Session identifier | SES_XYZ789 |
| `page_path` | STRING | URL path visited | /products/electronics |
| `device_type` | STRING | User's device type | mobile, desktop, tablet |
| `country_code` | STRING | User's country | US, UK, CA |

---

## Business Definitions

### Key Metrics

#### Gross Merchandise Value (GMV)
**Definition:** Total value of merchandise sold through the platform
**Calculation:** `SUM(item_price * quantity)` where `order_status != 'cancelled'`
**Excludes:** Shipping fees, taxes, returns

#### Customer Lifetime Value (CLV)
**Definition:** Predicted revenue from a customer over their entire relationship
**Calculation:** `AVG(annual_spend) * AVG(customer_lifespan_years)`
**Segments:** New (< 1 year), Established (1-3 years), Loyal (> 3 years)

#### Conversion Rate
**Definition:** Percentage of visitors who complete a purchase
**Calculation:** `(unique_purchasers / unique_visitors) * 100`
**Good Benchmark:** > 2.5%

### Business Rules

1. **Active Customer:** Made at least 1 purchase in the last 365 days
2. **Churned Customer:** No purchase in the last 365 days, but had previous purchases
3. **High-Value Customer:** CLV > $1000 or annual spend > $500
4. **Return Rate Threshold:** Flag products with return rate > 15%

---

## Common Query Patterns

### Daily Sales Summary

```sql
-- Get daily sales by category for the last 30 days
SELECT
  date,
  product_category,
  SUM(total_sales) AS total_revenue,
  SUM(transaction_count) AS total_transactions,
  ROUND(SUM(total_sales) / SUM(transaction_count), 2) AS avg_order_value
FROM `project.analytics.daily_sales`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY date, product_category
ORDER BY date DESC, total_revenue DESC
```

### User Funnel Analysis

```sql
-- Analyze conversion funnel by device type
WITH funnel AS (
  SELECT
    device_type,
    COUNT(DISTINCT CASE WHEN page_path LIKE '/products%' THEN session_id END) AS product_views,
    COUNT(DISTINCT CASE WHEN page_path = '/cart' THEN session_id END) AS cart_views,
    COUNT(DISTINCT CASE WHEN page_path = '/checkout' THEN session_id END) AS checkout_starts,
    COUNT(DISTINCT CASE WHEN page_path = '/order-confirmation' THEN session_id END) AS purchases
  FROM `project.analytics.page_views`
  WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY device_type
)
SELECT
  device_type,
  product_views,
  cart_views,
  ROUND(100.0 * cart_views / NULLIF(product_views, 0), 2) AS view_to_cart_rate,
  ROUND(100.0 * purchases / NULLIF(checkout_starts, 0), 2) AS checkout_conversion_rate
FROM funnel
ORDER BY product_views DESC
```

### Cohort Retention Analysis

```sql
-- Monthly cohort retention analysis
WITH first_purchase AS (
  SELECT
    user_id,
    DATE_TRUNC(MIN(order_date), MONTH) AS cohort_month
  FROM `project.analytics.orders`
  GROUP BY user_id
),
monthly_activity AS (
  SELECT
    user_id,
    DATE_TRUNC(order_date, MONTH) AS activity_month
  FROM `project.analytics.orders`
  GROUP BY user_id, DATE_TRUNC(order_date, MONTH)
)
SELECT
  fp.cohort_month,
  DATE_DIFF(ma.activity_month, fp.cohort_month, MONTH) AS months_since_first,
  COUNT(DISTINCT ma.user_id) AS active_users
FROM first_purchase fp
JOIN monthly_activity ma ON fp.user_id = ma.user_id
WHERE fp.cohort_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY cohort_month, months_since_first
ORDER BY cohort_month, months_since_first
```

---

## Data Quality Rules

### Validation Checks

| Table | Rule | Severity | Action |
|-------|------|----------|--------|
| `daily_sales` | `total_sales >= 0` | Critical | Block pipeline |
| `daily_sales` | `date <= CURRENT_DATE()` | Warning | Alert team |
| `page_views` | `user_id IS NOT NULL` | Critical | Filter records |
| `orders` | No duplicate `order_id` | Critical | Deduplicate |

### Known Data Issues

1. **Mobile App Data Gap (2024-01-01 to 2024-01-03):** Missing mobile app events due to SDK update
2. **Legacy Store IDs:** Stores with IDs starting with `OLD_` were migrated - use `new_store_id` mapping table
3. **Currency Conversion:** All amounts are in USD. For international stores, conversion happens at order time

---

## Naming Conventions

### Table Naming
- Use `snake_case` for all table and column names
- Prefix staging tables with `stg_`
- Prefix dimension tables with `dim_`
- Prefix fact tables with `fct_`

### Date Fields
- Use `_date` suffix for DATE types: `order_date`, `ship_date`
- Use `_timestamp` or `_at` suffix for TIMESTAMP types: `created_at`, `event_timestamp`

### ID Fields
- Primary keys: `<entity>_id` (e.g., `user_id`, `order_id`)
- Foreign keys: same name as the referenced primary key

---

## Access and Permissions

### Service Accounts

| Service Account | Purpose | Permissions |
|-----------------|---------|-------------|
| `analytics-reader@project.iam` | Read production data | BigQuery Data Viewer |
| `analytics-writer@project.iam` | Write to analytics | BigQuery Data Editor |

### Data Classification

| Level | Description | Examples | Access |
|-------|-------------|----------|--------|
| Public | Non-sensitive aggregates | Daily sales totals | All employees |
| Internal | Business metrics | Customer counts, revenue | Analytics team |
| Confidential | PII, sensitive data | Customer emails, addresses | Restricted |
| Restricted | Financial, legal | Contracts, settlements | Need-to-know basis |

---

## Contact Information

**Data Engineering Team:** data-eng@company.com
**Analytics Team:** analytics@company.com
**Data Steward:** Jane Doe (jane.doe@company.com)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2024-01-15 | Data Team | Initial version |
| 2024-02-01 | Analytics | Added cohort analysis patterns |
| 2024-03-01 | Data Eng | Updated table schemas |
