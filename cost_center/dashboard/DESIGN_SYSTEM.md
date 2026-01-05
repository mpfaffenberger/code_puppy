# Modular Architecture & Design System

This document covers both the modular architecture and design system for the HTT Brands Cost Center dashboard.

---

## Part 1: Modular Architecture

### Overview

The dashboard has been refactored into independent, reusable modules to improve maintainability and testability. All modules use browser-compatible UMD patterns with global namespaces.

### Module Files

| File | Namespace | Purpose | Size |
|------|-----------|---------|------|
| `utils.js` | `DashboardUtils` | Formatting, dates, SKU helpers | ~150 lines |
| `billing.js` | `DashboardBilling` | CSP/invoice data for 4 tenants | ~315 lines |
| `charts.js` | `DashboardCharts` | Chart.js visualizations | ~385 lines |
| `insights.js` | `DashboardInsights` | Optimization insights & recommendations | ~370 lines |
| `dashboard.js` | Main | Orchestration & rendering | 3,856 lines |

### Loading Order

Modules are loaded **before** `dashboard.js` in `index.html`:

```html
<script src="./utils.js?v=1"></script>
<script src="./billing.js?v=1"></script>
<script src="./charts.js?v=1"></script>
<script src="./insights.js?v=1"></script>
<script src="./dashboard.js?v=3"></script>
```

---

## DashboardUtils Module

Location: `docs/utils.js`

### Formatting Functions

```javascript
// Currency formatting
DashboardUtils.formatCurrency(1234.56)     // "$1,234.56"

// Number formatting
DashboardUtils.formatNumber(1234)          // "1,234"

// Percentage formatting
DashboardUtils.formatPercent(0.123)        // "12.3%"
```

### Date Functions

```javascript
// Parse ISO date string
DashboardUtils.parseDate("2025-03-15T10:00:00Z")

// Format date to month key
DashboardUtils.formatMonthKey(date)        // "2025-03"

// Get month boundaries
DashboardUtils.startOfMonth(date)          // First day of month
DashboardUtils.endOfMonth(date)            // Last day of month

// Check if date in range
DashboardUtils.dateInRange(date, from, to) // boolean

// Human-readable relative time
DashboardUtils.timeAgo("2025-03-15T...")   // "3d ago"
```

### SKU Classification

```javascript
// Check if SKU is paid
DashboardUtils.isPaidSku("SPE_E3")         // true
DashboardUtils.isPaidSku("M365_F1_COMM")   // false (free)

// Free SKU set reference
DashboardUtils.FREE_SKUS                   // Set of free SKU names

// Default pricing lookup
DashboardUtils.SKU_PRICES["SPE_E3"]        // 36.00 (monthly)
```

### Badge Helpers

```javascript
// Map badge type to CSS class
DashboardUtils.getBadgeClass("Urgent")     // "danger"
DashboardUtils.getBadgeClass("Advisor")    // "advisor"
```

---

## DashboardBilling Module

Location: `docs/billing.js`

### Data Objects

```javascript
// CSP Provider metadata for each tenant
DashboardBilling.CSP_BILLING_SOURCES
  → {
      "Head to Toe Brands (anchor)": {
        csp: "Logically MSP",
        type: "Azure + M365",
        billingId: "logically",
        contact: "Logically Support",
        notes: "Primary anchor tenant..."
      },
      // ... other tenants
    }

// Monthly invoices from Logically CSP (HTT)
DashboardBilling.LOGICALLY_INVOICES
  → {
      "2025-03": {
        azure: 7834.88,
        m365: 1003.60,
        fabric: 0,
        invoiceDate: "2025-04-15",
        invoiceNum: "1167103",
        // ...
      },
      // ... other months
    }

// Direct Azure invoices (by tenant)
DashboardBilling.HTT_DIRECT_INVOICES
DashboardBilling.BCC_DIRECT_INVOICES
DashboardBilling.TLL_DIRECT_INVOICES
DashboardBilling.FN_DIRECT_INVOICES

// CSP M365 invoices (by provider)
DashboardBilling.SG_CSP_INVOICES      // The Lash Lounge
DashboardBilling.FTG_CSP_INVOICES     // Frenchies
```

### Helper Functions

```javascript
// Get consolidated monthly billing
const monthly = DashboardBilling.getConsolidatedBilling();
// Returns: [
//   {
//     month: "2025-03",
//     htt: {azureCSP, m365CSP, azureDirect, credit, total},
//     bcc: {azureDirect, total},
//     tll: {azureDirect, m365CSP, total},
//     fn: {azureDirect, m365CSP, total},
//     grandTotal,
//     hasActualData
//   },
//   ...
// ]

// Get YTD summary
const summary = DashboardBilling.getInvoiceSummary();
// Returns: {ytd, latest, billing, sources}
```

---

## DashboardCharts Module

Location: `docs/charts.js`

### Trend Charts

```javascript
// Render monthly trend with optional forecast
DashboardCharts.renderMonthlyTrendChart(
  document.getElementById("trend"),
  data,
  {showForecast: true, height: 400}
)

// Render daily trend for current month
DashboardCharts.renderDailyTrendChart(
  container,
  data,
  {smooth: true}
)

// Generic trend chart
DashboardCharts.renderTrendChart(container, data, options)
```

### Domain-Specific Charts

```javascript
// Cost breakdown charts
DashboardCharts.renderCostCharts(container, data, selection)

// License utilization charts
DashboardCharts.renderLicenseCharts(container, data, selection)

// Resource inventory charts
DashboardCharts.renderResourcesCharts(container, data, selection)

// Invoice reconciliation charts
DashboardCharts.renderInvoiceCharts(container, data, selection)

// GitHub billing charts
DashboardCharts.renderGitHubBillingCharts(container, data, selection)
```

### Color Management

```javascript
// Predefined color palette
DashboardCharts.COLORS
  → {primary, secondary, success, warning, danger, cyan, pink, ...}

// Tenant-specific colors
DashboardCharts.TENANT_COLORS
  → {
      "Head to Toe Brands (anchor)": "#3b82f6",
      "Bishops": "#8b5cf6",
      "Frenchies": "#10b981",
      "The Lash Lounge": "#f59e0b"
    }

// Get/destroy chart instances
DashboardCharts.getCharts()         // Returns registry
DashboardCharts.destroyChart("name") // Cleanup before redraw
```

---

## DashboardInsights Module

Location: `docs/insights.js`

### Insight Generators

```javascript
// Generate Azure cost optimization insights
const azureInsights = DashboardInsights.generateAzureInsights(
  data,
  {tenant, subscription, period},
  helpers  // filterCostRows, calculateMonthlyCostsTotal, etc.
);
// Returns insights about: idle resources, untagged, Advisor recs, credentials, etc.

// Generate license optimization insights
const licenseInsights = DashboardInsights.generateLicenseInsights(
  data,
  {tenant, subscription, period},
  helpers
);
// Returns insights about: underutilized SKUs, inactive users, redundant assignments

// Generate top movers (MoM changes)
const movers = DashboardInsights.generateTopMovers(
  data,
  {tenant, subscription, period},
  helpers
);
// Returns: {tenants: [...], services: [...]}
```

### Rendering Functions

```javascript
// Render insight list
DashboardInsights.renderInsightsList(
  document.getElementById("azure-insights"),
  insights,
  "No insights available."
);

// Render top movers
DashboardInsights.renderTopMovers(
  document.getElementById("top-movers"),
  movers,
  "Not enough data."
);
```

### Insight Types

Each insight includes: `{title, meta, badge}`

---

## Part 3: Module Integration & Testing

### Module Load Order

All modules are loaded in `index.html` **before** `dashboard.js`:

```html
<!-- Load in order: utils → billing → charts → insights → dashboard -->
<script src="./utils.js?v=1"></script>
<script src="./billing.js?v=1"></script>
<script src="./charts.js?v=1"></script>
<script src="./insights.js?v=1"></script>

<!-- Main app (uses all modules via global namespaces) -->
<script src="./dashboard.js?v=3"></script>
```

### Namespace Availability

Each module exposes a global namespace after loading:

```javascript
// After utils.js loads:
window.DashboardUtils    → All formatting, date, SKU functions

// After billing.js loads:
window.DashboardBilling  → All billing data and helpers

// After charts.js loads:
window.DashboardCharts   → All chart rendering functions

// After insights.js loads:
window.DashboardInsights → All insight generation functions

// dashboard.js can now use all namespaces:
const fmt = DashboardUtils.formatCurrency(1234.56);
const billing = DashboardBilling.CSP_BILLING_SOURCES;
// etc.
```

### Testing Module Independence

Each module can be tested independently via the browser console:

```javascript
// Test Utils module
console.log(DashboardUtils.formatCurrency(1000));       // "$1,000.00"
console.log(DashboardUtils.isPaidSku("SPE_E3"));        // true
console.log(DashboardUtils.timeAgo("2025-12-01T..."));  // "3d ago"

// Test Billing module
console.log(DashboardBilling.CSP_BILLING_SOURCES["Head to Toe Brands (anchor)"].csp);  // "Logically MSP"
console.log(DashboardBilling.getConsolidatedBilling().length);  // 11 months

// Test Insights module
const insights = DashboardInsights.generateAzureInsights(data, selection, helpers);
console.log(insights.length > 0 ? "✅ Insights OK" : "❌ No insights");

// Test Charts module
console.log(typeof DashboardCharts.renderMonthlyTrendChart === 'function');  // true
```

### Integration Tests

#### Test 1: Module Availability

```javascript
// Verify all namespaces exist
const modules = ["DashboardUtils", "DashboardBilling", "DashboardCharts", "DashboardInsights"];
const missing = modules.filter(m => !window[m]);
console.log(missing.length === 0 ? "✅ All modules loaded" : `❌ Missing: ${missing}`);
```

#### Test 2: Function Availability

```javascript
// Verify key functions are callable
const tests = [
  ["DashboardUtils.formatCurrency", typeof DashboardUtils.formatCurrency === 'function'],
  ["DashboardUtils.isPaidSku", typeof DashboardUtils.isPaidSku === 'function'],
  ["DashboardBilling.getConsolidatedBilling", typeof DashboardBilling.getConsolidatedBilling === 'function'],
  ["DashboardCharts.renderMonthlyTrendChart", typeof DashboardCharts.renderMonthlyTrendChart === 'function'],
  ["DashboardInsights.generateAzureInsights", typeof DashboardInsights.generateAzureInsights === 'function'],
];

tests.forEach(([name, pass]) => console.log(pass ? `✅ ${name}` : `❌ ${name}`));
```

#### Test 3: Data Formatting

```javascript
// Verify formatting functions produce correct output
const tests = [
  [DashboardUtils.formatCurrency(1234.56), "$1,234.56"],
  [DashboardUtils.formatNumber(1000), "1,000"],
  [DashboardUtils.formatPercent(0.125), "12.5%"],
  [DashboardUtils.formatMonthKey(new Date("2025-03-15")), "2025-03"],
];

tests.forEach(([actual, expected]) => {
  console.log(actual === expected ? `✅ ${actual}` : `❌ Expected ${expected}, got ${actual}`);
});
```

#### Test 4: Billing Data Completeness

```javascript
// Verify billing data is complete
const consolidated = DashboardBilling.getConsolidatedBilling();
console.log(`Months: ${consolidated.length}`);  // Should be 11

// Check for required fields in each month
const hasAll = consolidated.every(m => 
  m.month && m.htt && m.bcc && m.tll && m.fn && typeof m.grandTotal === 'number'
);
console.log(hasAll ? "✅ All months have required fields" : "❌ Missing fields");
```

#### Test 5: Insight Generation

```javascript
// Verify insights can be generated
const data = window.rawData || {};  // From dashboard
const selection = {period: "mtd", tenant: null, subscription: null};
const helpers = {
  filterCostRows: f => [],
  calculateMonthlyCostsTotal: () => 0,
  getMonthlyTotals: () => [],
  filterLicenses: () => [],
  filterCostRowsAllPeriods: () => []
};

const insights = DashboardInsights.generateAzureInsights(data, selection, helpers);
console.log(Array.isArray(insights) ? `✅ Generated ${insights.length} insights` : "❌ Failed to generate insights");
```

### Fallback Handling

If a module fails to load, modules include fallback defaults:

```javascript
// Example from insights.js
function fmt() {
  return window.DashboardUtils || {
    formatCurrency: v => `$${Number(v || 0).toFixed(2)}`,
    formatPercent: v => `${(v || 0).toFixed(1)}%`,
    formatNumber: v => String(v || 0),
    // ...
  };
}
```

This ensures the app doesn't break if a module doesn't load; it will use defaults instead.

### Browser DevTools Testing

Open the browser console (F12) and test modules interactively:

```javascript
// 1. Check all modules loaded
Object.keys(window).filter(k => k.startsWith("Dashboard"))

// 2. Test a function
DashboardUtils.formatCurrency(50000)  // "$50,000.00"

// 3. Inspect a data structure
DashboardBilling.CSP_BILLING_SOURCES

// 4. Generate insights
DashboardInsights.generateAzureInsights(data, {}, helpers)

// 5. Check chart registry
DashboardCharts.getCharts()
```

---

> HTT Brands Design System for the multi-tenant Azure cost and license management dashboard.

### Overview

The dashboard uses a modern dark theme with a focus on data visualization and accessibility. Built with vanilla CSS and JavaScript, utilizing Chart.js for visualizations.

---

## 🎨 Color Palette

### Core Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#0a0c10` | Main background |
| `--bg-elevated` | `#12151a` | Elevated surfaces |
| `--sidebar-bg` | `#0d0f14` | Sidebar background |
| `--card-bg` | `#14171e` | Card backgrounds |

### Text Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--text` | `#f0f2f5` | Primary text |
| `--text-secondary` | `#9ca3af` | Secondary text |
| `--muted` | `#6b7280` | Muted/disabled text |

### Accent Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--primary` | `#3b82f6` | Primary actions, links |
| `--primary-light` | `#60a5fa` | Hover states |
| `--accent` | `#8b5cf6` | Purple accent |

### Semantic Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--success` | `#10b981` | Success states, positive values |
| `--warning` | `#f59e0b` | Warning states, caution |
| `--danger` | `#ef4444` | Error states, negative values |

### Border Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--border` | `#1f2937` | Default borders |

| `--border-light` | `#374151` | Emphasized borders |

### Gradients

```css
--gradient-1: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);  /* Blue to purple */
--gradient-2: linear-gradient(135deg, #10b981 0%, #3b82f6 100%);  /* Green to blue */
```

---

## 📝 Typography

### Font Family

```css
font-family: 'Space Grotesk', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

### Type Scale

| Size | Usage |
|------|-------|
| `2rem` | Page titles |
| `1.5rem` | Large KPI values |
| `1.25rem` | Card headers |
| `1rem` | Body text |
| `0.875rem` | Secondary text, labels |
| `0.75rem` | Small text, badges |
| `0.7rem` | Micro text |

### Font Weights

| Weight | Usage |
|--------|-------|
| `400` | Body text |
| `500` | Emphasized text |
| `600` | Section headers |
| `700` | Headings, logo |

---

## 📦 Components

### Cards

```css
.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border);
}

.card-body {
  padding: 24px;
}
```

### Buttons

#### Primary Button
```css
.btn.primary {
  background: var(--primary);
  color: white;
  border-radius: 8px;
  padding: 8px 16px;
}
```

#### Ghost Button
```css
.btn.ghost {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
```

### Badges

```css
.badge {
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge.success { background: rgba(16, 185, 129, 0.2); color: #34d399; }
.badge.warning { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
.badge.danger { background: rgba(239, 68, 68, 0.2); color: #f87171; }
.badge.info { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
```

### KPI Cards

```css
.kpi {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}

.kpi .label { color: var(--text-secondary); font-size: 0.875rem; }
.kpi .value { font-size: 1.5rem; font-weight: 600; }
.kpi .delta { font-size: 0.875rem; }
```

### Tables

```css
table {
  width: 100%;
  border-collapse: collapse;
}

th {
  text-align: left;
  color: var(--text-secondary);
  font-weight: 500;
  font-size: 0.75rem;
  text-transform: uppercase;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

tr:hover {
  background: rgba(59, 130, 246, 0.05);
}

.num { text-align: right; font-variant-numeric: tabular-nums; }
```

### Pagination

```css
.pagination {
  display: flex;
  justify-content: space-between;
  padding: 16px 0;
  border-top: 1px solid var(--border);
}
```

### Status Badges

```css
.status-badge {
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 0.75rem;
}
```

### Utilization Bar

```css
.utilization-bar {
  height: 8px;
  background: var(--bg);
  border-radius: 4px;
  overflow: hidden;
}

.utilization-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}
```

---

## 🔗 Navigation

### Sidebar

- Fixed position, 260px width
- Collapses on mobile (<1024px)
- Sections: Overview, Azure Hierarchy, Cost Analysis, Licensing, Identity Governance, GitHub

### Nav Items

```css
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-radius: 8px;
  transition: all 0.2s;
}

.nav-item:hover { background: rgba(59, 130, 246, 0.1); }
.nav-item.active { 
  background: rgba(59, 130, 246, 0.15); 
  color: var(--primary-light); 
}
```

---

## 📊 Charts

Using Chart.js 4.4.2 with dark theme configuration:

```javascript
// Common chart options
{
  plugins: {
    legend: { 
      labels: { color: "#9ca3af" } 
    }
  },
  scales: {
    x: { 
      grid: { color: "#1f2937" }, 
      ticks: { color: "#9ca3af" } 
    },
    y: { 
      grid: { color: "#1f2937" }, 
      ticks: { color: "#9ca3af" } 
    }
  }
}
```

### Chart Color Palette

| Color | Hex | Usage |
|-------|-----|-------|
| Blue | `#3b82f6` | Primary data series |
| Purple | `#8b5cf6` | Secondary series |
| Green | `#10b981` | Positive values |
| Red | `#ef4444` | Negative values |
| Amber | `#f59e0b` | Warning/attention |

---

## ♿ Accessibility

### Focus Indicators

```css
:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
```

### Skip Link

```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  background: var(--primary);
  color: white;
  padding: 8px 16px;
  z-index: 1000;
}

.skip-link:focus { top: 0; }
```

### Screen Reader Only

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### High Contrast Mode

```css
@media (prefers-contrast: high) {
  :root {
    --border: #4b5563;
    --text-secondary: #d1d5db;
  }
}
```

---

## 📱 Responsive Breakpoints

| Breakpoint | Width | Target |
|------------|-------|--------|
| Desktop XL | `≥1440px` | Large monitors |
| Desktop | `≥1024px` | Standard desktop |
| Tablet | `≥640px` | Tablets, small laptops |
| Mobile | `≥480px` | Phones landscape |
| Mobile SM | `<480px` | Phones portrait |

### Mobile Considerations

- Sidebar transforms to overlay menu
- KPI cards stack vertically
- Tables get horizontal scroll
- Filters stack vertically

---

## 🎭 Loading States

### Skeleton Loader

```css
.skeleton {
  background: linear-gradient(
    90deg,
    var(--bg-elevated) 25%,
    var(--border) 50%,
    var(--bg-elevated) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
}
```

### Spinner

```css
.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
```

---

## 🔔 Toast Notifications

```css
.toast {
  padding: 12px 20px;
  border-radius: 8px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  animation: slide-in 0.3s ease;
}

.toast.success { border-left: 3px solid var(--success); }
.toast.warning { border-left: 3px solid var(--warning); }
.toast.error { border-left: 3px solid var(--danger); }
.toast.info { border-left: 3px solid var(--primary); }
```

---

## 📂 File Structure

```
docs/
├── index.html          # Main dashboard HTML
├── dashboard.js        # Dashboard logic (3700+ lines)
├── styles.css          # All styles (1300+ lines)
├── config.js           # Runtime configuration
├── DESIGN_SYSTEM.md    # This file
└── data/
    ├── latest-report.json   # Live data from Azure
    ├── sample-report.json   # Fallback sample data
    └── sku-pricing.json     # License pricing reference
```

---

## 🔧 Configuration

The dashboard is configured via `config.js`:

```javascript
window.DASHBOARD_CONFIG = {
  dataUrl: "https://..../latest-report.json",
  refreshWorkflowUrl: "https://github.com/.../actions/workflows/...",
  budgetMonthly: null  // Optional budget threshold
};
```

URL query parameters can override:
- `?dataUrl=...` — Custom data source
- `?budget=5000` — Monthly budget threshold

---

## 🚀 Phase 3: Enhancement Features (NEW)

### 1. Predictive Analytics (ML Forecasting)

**Purpose**: Forecast future costs using machine learning algorithms to enable proactive budget planning.

**Configuration** (`config.js`):
```javascript
forecasting: {
  enabled: true,
  method: 'linear-regression', // or 'exponential-smoothing', 'moving-average'
  horizon: 3, // months to forecast
  confidence: 0.95,
  minHistoricalMonths: 3
}
```

**Features**:
- Three forecasting algorithms: Linear Regression, Exponential Smoothing, Moving Average
- 95% confidence intervals with upper/lower bounds
- Interactive Chart.js visualization with historical vs predicted
- Forecast KPIs: Next month prediction, 3-month projection, trend direction

**Usage**:
```javascript
const forecast = generateForecast(data, 'linear-regression', 3);
renderForecastChart(forecast);
renderForecastKpis(forecast);
```

**UI Components**:
- `#forecast-chart`: Canvas for visualization
- `#forecast-kpis`: Grid of forecast metrics

---

### 2. Automated Recommendations

**Purpose**: Automatically execute cost optimization actions with approval workflows.

**Configuration** (`config.js`):
```javascript
automation: {
  enabled: true,
  autoTag: false,
  autoDisableInactive: false,
  autoCleanup: false,
  approvalRequired: true
}
```

**Available Actions**:
1. Auto-tag untagged resources
2. Disable inactive users (90+ days no sign-in)
3. Resource cleanup (orphaned disks, idle VMs)

**Workflow**: Review → Approve → Execute → Audit Log

**UI Components**:
- `#automated-actions-list`: Container for action cards
- CSS: `.action-item`, `.action-header`, `.action-meta`

---

### 3. Custom Report Builder

**Purpose**: Generate reports in PDF, Excel, CSV, HTML, or JSON with selected data sections.

**Features**:
- Report types: Executive Summary, Detailed Analysis, License Audit, Cost Optimization, Tenant Comparison
- Sections: KPIs, Charts, Tables, Recommendations, Budget Tracking, Forecasts
- Export formats: PDF, Excel, CSV, HTML, JSON
- Save templates for reuse
- Live preview before generation

**Usage**:
```javascript
showReportBuilder();    // Open modal
generateReport();       // Create report from form
saveReportTemplate();   // Save config for reuse
```

**UI Components**:
- `#report-builder-modal`: Modal container (`.modal-wide`)
- `#report-builder-form`: Form with options
- `#saved-reports-list`: Generated reports list

---

### 4. Ticketing Integration

**Purpose**: Create tickets in Jira, Azure DevOps, or GitHub Issues from recommendations.

**Configuration** (`config.js`):
```javascript
integrations: {
  jira: {
    enabled: false,
    url: 'https://your-domain.atlassian.net',
    projectKey: 'COST',
    apiToken: '' // use env var
  },
  azureDevOps: {
    enabled: false,
    organization: 'your-org',
    project: 'CostManagement',
    pat: '' // use env var
  },
  github: {
    enabled: false,
    owner: 'HTT-BRANDS',
    repo: 'cost-tracking',
    token: '' // use env var
  }
}
```

**Workflow**:
1. Click "Create Ticket" from recommendation
2. Select system (Jira/AzDO/GitHub)
3. Fill form (title, description, priority, assignee)
4. System creates ticket via REST API

**Usage**:
```javascript
showCreateTicketModal(recommendation);  // Open with pre-filled data
createTicket();                          // Submit to API
```

**UI Components**:
- `#create-ticket-modal`: Modal container
- `#create-ticket-form`: Ticket details form
- CSS: `.ticket-system-options`

---

### 5. Public API

**Purpose**: Expose dashboard data via RESTful API for external integrations.

**Configuration** (`config.js`):
```javascript
api: {
  enabled: true,
  baseUrl: '/api',
  version: 'v1',
  rateLimitPerMinute: 60
}
```

**Endpoints**:

**GET /api/v1/costs**
```javascript
await DashboardAPI.getCosts({ tenant: 'htt', from: '2025-01-01', to: '2025-01-31' });
// Returns: { success: true, data: { monthly: [...], total: 12500 } }
```

**GET /api/v1/recommendations**
```javascript
await DashboardAPI.getRecommendations();
// Returns: { success: true, data: { recommendations: [...], count: 12, totalSavings: 2500 } }
```

**GET /api/v1/forecast**
```javascript
await DashboardAPI.getForecast('linear-regression', 3);
// Returns: { success: true, data: { method: 'linear-regression', predictions: [...], horizon: 3 } }
```

**POST /api/v1/reports**
```javascript
await DashboardAPI.generateReport({ name: 'Q1 Report', type: 'executive', format: 'pdf' });
// Returns: { success: true, data: { reportId: 'report-123', url: '/reports/...' } }
```

**Security**:
- Rate limiting: 60 req/min
- API key authentication (future)
- CORS whitelist
- Read-only endpoints

---

## Testing Phase 3 Features

### Enable in config.js
```javascript
window.DASHBOARD_CONFIG = {
  forecasting: { enabled: true, method: 'linear-regression', horizon: 3 },
  automation: { enabled: true, approvalRequired: true },
  integrations: { /* configure if testing ticketing */ },
  api: { enabled: true }
};
```

### Test Forecasting
1. Load dashboard with 3+ months of data
2. Verify forecast chart renders with confidence bounds
3. Check forecast KPIs show next month and 3-month projections

### Test Automated Actions
1. Enable `automation.enabled: true`
2. Review actions list in dashboard
3. Click "Review & Execute" (demo mode - safe)

### Test Report Builder
1. Click "🛠️ Open Report Builder"
2. Fill form: name, type, sections, format
3. Click "Generate" → See demo confirmation
4. Verify saved report appears in list

### Test Ticketing
1. Configure integration in config.js (demo mode works without)
2. Click "Create Ticket" from recommendation
3. Select system, fill form
4. Click "Create Ticket" → See demo confirmation

### Test API
```javascript
const costs = await DashboardAPI.getCosts();
const recs = await DashboardAPI.getRecommendations();
const forecast = await DashboardAPI.getForecast();
console.log('API tests passed');
```

---

## Production Deployment Checklist

### Phase 3 Pre-Flight
- [ ] Configure forecasting method in config.js
- [ ] Set automation approval requirements
- [ ] Add API tokens for ticketing (environment variables, not in code)
- [ ] Test forecasting accuracy with historical data
- [ ] Verify report generation for all formats
- [ ] Configure API rate limiting
- [ ] Add server-side API implementation (Azure Functions recommended)
- [ ] Set up email delivery for reports (SendGrid/Azure Communication Services)
- [ ] Add monitoring and logging for automated actions
- [ ] Document API endpoints for external consumers

### Security
- [ ] No API tokens in client-side code
- [ ] CORS configured for API
- [ ] Rate limiting enabled
- [ ] Approval workflow enforced
- [ ] Audit logging for actions
- [ ] Input validation on forms
- [ ] XSS protection

---

## 🚀 Future Improvements

1. **Advanced ML**: Anomaly detection, clustering, pattern recognition
2. **Collaboration**: Team comments, shared insights, approvals
3. **Mobile App**: Native iOS/Android apps
4. **Real-time**: WebSocket updates, live cost tracking
5. **AI Copilot**: Natural language queries, automated insights

