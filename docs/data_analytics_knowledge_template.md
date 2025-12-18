# Data Analytics Knowledge Base Template

This is a template for creating your own data analytics knowledge base.
Copy this file to your project directory as `data_analytics_knowledge.md`
and customize it with your domain-specific information.

---

## Overview

**Domain:** Sam's Club - Retail Membership Warehouse
**Primary Data Sources:** BigQuery (prod-sams-cdp)
**Key Stakeholders:** Marketing, Operations, Membership, Finance teams

---

## Data Architecture

### Project Structure

| GCP Project | Purpose | Access Level |
|-------------|---------|--------------|
| `prod-sams-cdp` | Sam's Club CDP Production Data | Read-only |

### Key Datasets

#### Dataset: `prod-sams-cdp.US_SAMS_CORE_CDP_VM`
**Description:** Sam's Club Core CDP Virtual Mart - Contains club and member information
**Update Frequency:** Daily
**Retention:** As per data governance policy

---

## Data Dictionary

### Table: `prod-sams-cdp.US_SAMS_CORE_CDP_VM.CLUB_INFO`

This table contains information about Sam's Club warehouse locations.

**Fully Qualified Name:** `prod-sams-cdp.US_SAMS_CORE_CDP_VM.CLUB_INFO`

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `CLUB_NBR` | INT64 | Unique club/warehouse number | 6365 |
| `CLUB_NM` | STRING | Club name | Sam's Club |
| `ADDR_LINE_1` | STRING | Street address | 1234 Main St |
| `CITY_NM` | STRING | City name | Bentonville |
| `STATE_CD` | STRING | State code | AR |
| `POSTAL_CD` | STRING | ZIP/Postal code | 72712 |
| `CNTRY_CD` | STRING | Country code | US |
| `CLUB_OPEN_DT` | DATE | Date club opened | 1990-05-15 |
| `CLUB_CLOSE_DT` | DATE | Date club closed (if applicable) | NULL |
| `CLUB_STATUS` | STRING | Current status (OPEN/CLOSED) | OPEN |
| `REGION_CD` | STRING | Regional code | SOUTH |
| `DISTRICT_CD` | STRING | District code | D001 |
| `MARKET_CD` | STRING | Market code | M001 |
| `TIMEZONE` | STRING | Club timezone | America/Chicago |

**Note:** Always verify schema by running a sample query first. Column names and types may vary.

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

### Schema Discovery (ALWAYS DO THIS FIRST!)

```sql
-- ALWAYS pull 10 records first to understand schema and data types
SELECT *
FROM `prod-sams-cdp.US_SAMS_CORE_CDP_VM.CLUB_INFO`
LIMIT 10
```

### List All Clubs by State

```sql
-- Get all clubs grouped by state
SELECT
  STATE_CD,
  COUNT(*) AS club_count,
  STRING_AGG(CAST(CLUB_NBR AS STRING), ', ' ORDER BY CLUB_NBR) AS club_numbers
FROM `prod-sams-cdp.US_SAMS_CORE_CDP_VM.CLUB_INFO`
WHERE CLUB_STATUS = 'OPEN'
GROUP BY STATE_CD
ORDER BY club_count DESC
```

### Find Clubs in a Specific Region

```sql
-- Find all clubs in a specific region
SELECT
  CLUB_NBR,
  CLUB_NM,
  CITY_NM,
  STATE_CD,
  REGION_CD,
  DISTRICT_CD
FROM `prod-sams-cdp.US_SAMS_CORE_CDP_VM.CLUB_INFO`
WHERE REGION_CD = 'SOUTH'
  AND CLUB_STATUS = 'OPEN'
ORDER BY STATE_CD, CITY_NM
```

### Club Opening Timeline Analysis

```sql
-- Analyze club openings by year
SELECT
  EXTRACT(YEAR FROM CLUB_OPEN_DT) AS open_year,
  COUNT(*) AS clubs_opened,
  STRING_AGG(CAST(CLUB_NBR AS STRING), ', ' ORDER BY CLUB_OPEN_DT LIMIT 5) AS sample_clubs
FROM `prod-sams-cdp.US_SAMS_CORE_CDP_VM.CLUB_INFO`
WHERE CLUB_OPEN_DT IS NOT NULL
GROUP BY open_year
ORDER BY open_year DESC
LIMIT 20
```

### Geographic Distribution

```sql
-- Club distribution by state with city breakdown
SELECT
  STATE_CD,
  CITY_NM,
  COUNT(*) AS club_count
FROM `prod-sams-cdp.US_SAMS_CORE_CDP_VM.CLUB_INFO`
WHERE CLUB_STATUS = 'OPEN'
GROUP BY STATE_CD, CITY_NM
HAVING COUNT(*) > 1
ORDER BY STATE_CD, club_count DESC
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
