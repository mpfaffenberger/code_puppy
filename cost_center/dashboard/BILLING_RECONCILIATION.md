# Cost Data Pipeline & Billing Reconciliation Guide

## Overview

This document explains how cost data is collected, where it comes from, and how to reconcile the data with invoices for accurate budget planning.

## Data Collection Architecture

### What the Pipeline Collects (Automated)

| Data Type | Source | API Used | Notes |
|-----------|--------|----------|-------|
| **Azure Consumption** | Azure Cost Management | `queryCostBreakdown()` | MTD + 11 months historical |
| **M365 Licenses** | Microsoft Graph API | `/subscribedSkus` | SKU inventory, consumed units |
| **User Data** | Microsoft Graph API | `/users` | Sign-in activity (requires AAD Premium) |
| **Resources** | Azure Resource Manager | `Resources.list()` | All Azure resources by subscription |
| **GitHub Billing** | GitHub API | Billing endpoints | Actions minutes, storage |

### What the Pipeline Does NOT Collect

| Cost Type | Billing Source | Where to Get It |
|-----------|----------------|-----------------|
| **M365 License Costs** | CSP Invoice | Logically (HTT), SG (TLL), FTG (FN) |
| **Fabric Capacity Costs** | CSP Invoice (Logically) | Monthly invoice line items |
| **Managed Services** | CSP Invoice (Logically) | HTT only - $3,785.25/mo |
| **Azure Reserved Instances** | Direct Invoice | TLL - ~$100/mo |

## Billing Sources by Brand

### HTT Brands (anchor tenant)
- **Logically MSP** (CSP): Azure + M365 + Fabric + Managed Services
- **Microsoft Direct**: Dev/Test subscription (~$1,000/mo)

### Bishops (BCC)
- **Microsoft Direct**: Azure + M365 (~$100-150/mo)

### The Lash Lounge (TLL)
- **Sui Generis CSP**: M365 licenses (estimated ~$350/mo)
- **Microsoft Direct**: Azure RI (~$100/mo)

### Frenchies (FN)
- **FTG CSP**: M365 licenses (estimated ~$200/mo)
- **Microsoft Direct**: Azure ($0 - free tier)

## Data Reconciliation

### Monthly Process

1. **Run Validation Script**
   ```bash
   node scripts/validate-cost-data.js
   ```

2. **Compare API Data vs Invoices**
   - Invoice Reconciliation section in dashboard
   - Look for variances > 10%

3. **Update Invoice Data in `dashboard.js`**
   - `LOGICALLY_INVOICES` - HTT Azure/M365/Fabric
   - `HTT_DIRECT_INVOICES` - HTT direct billing
   - `BCC_DIRECT_INVOICES` - Bishops direct
   - `TLL_DIRECT_INVOICES` - TLL direct
   - `FN_DIRECT_INVOICES` - Frenchies direct

### Why Variances Occur

| Scenario | Explanation |
|----------|-------------|
| API > Invoice | Timing difference (usage vs billing lag) |
| API < Invoice | CSP markup, support fees, managed services |
| Large variance | Missing subscription in API, CSP-only services |
| Zero in API | No Azure consumption (M365-only tenant) |

## Sign-In Data Limitations

**Issue**: Some tenants show 0% sign-in data coverage.

**Cause**: Microsoft Graph API `signInActivity` requires Azure AD Premium P1/P2. Tenants without Premium fall back to user data without sign-in timestamps.

**Affected Tenants**:
- Frenchies (0%)
- The Lash Lounge (0%)

**Impact**: Cannot accurately identify inactive users with paid licenses for these tenants.

**Workaround**: Check Microsoft 365 Admin Center → Usage reports for sign-in activity.

## Budget Planning Recommendations

### For Accurate 2026 Budget

1. **Azure Consumption**: Use API data from `monthlyCosts` as primary source
2. **M365 Licensing**: Use Graph API license counts × MSRP pricing
3. **Fabric**: Use invoiced amounts (F64 = ~$3,152/mo)
4. **Managed Services**: Fixed $3,785.25/mo (Logically only)
5. **Growth Buffer**: Add 10-15% for organic growth

### Cost Categories

| Budget Line | Data Source | Monthly Estimate |
|-------------|-------------|------------------|
| Azure Consumption | API + Invoices | ~$8,500 |
| M365 Licensing | Graph API × MSRP | ~$1,500 |
| Fabric Capacity | CSP Invoice | ~$3,150 |
| Managed Services | Fixed | ~$3,785 |
| **Total Monthly** | Combined | ~$16,935 |

## Automation Schedule

The GitHub Actions workflow runs daily at 10:00 UTC:
- Collects data from all 4 tenants in parallel (max 2 concurrent)
- Merges reports into `latest-report.json`
- Uploads to Azure Blob Storage

To trigger manually:
```bash
gh workflow run "Multi-tenant Cost Audit"
```

## Troubleshooting

### "No cost data" for a tenant
1. Check Azure login credentials (OIDC federation)
2. Verify Cost Reader role on subscription
3. Check if subscription has any consumption

### Large API vs Invoice variance
1. Verify all subscriptions are in `tenants.json`
2. Check for CSP-only services (Fabric, M365)
3. Look for one-time credits or adjustments

### Missing sign-in data
1. Tenant needs AAD Premium P1/P2
2. Or use Microsoft 365 Admin Center reports
