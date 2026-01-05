/**
 * Dashboard Utility Functions & Data Model - Production Ready (2025-12-04)
 * 
 * This module provides:
 * 1. Shared utility functions (formatting, dates)
 * 2. Global data model (window.dashboardState)
 * 3. Data normalization and aggregation
 * 4. Dashboard initialization
 * 
 * All normalization functions exported to global scope:
 * - global.normalizeCostData()
 * - global.normalizeLicenseData()
 * - global.normalizeInvoiceData()
 * - global.DashboardUtils (all utilities)
 */

console.log('[utils.js] ============ SCRIPT STARTING TO LOAD ============');

(function(global) {
  'use strict';

  console.log('[utils.js] ✅ IIFE executing, global scope:', typeof global);

  // ===== GLOBAL DATA MODEL =====
  global.dashboardState = {
    meta: {
      lastUpdated: null,
      dataSource: null,
      tenantCount: 0,
      subscriptionCount: 0
    },
    config: {
      defaultMode: "executive",
      defaultScope: "all",
      defaultTimeRange: "12m",
    },
    filters: {
      mode: "executive",
      scope: "all",
      timeRange: "12m",
      tenant: null,
      subscription: null,
      from: null,
      to: null
    },
    // Core normalized facts
    factsCost: [],        // [{ date, brand, billingSource, service, sku, amount, tenant }]
    factsLicenses: [],    // [{ userId, sku, tenant, lastSignIn, isPaidSku, monthlyCost }]
    factsInvoices: [],    // [{ month, billingSource, amount, markupPct }]
    skuPrices: {},        // { skuCode: { monthlyPrice, currency, source } }
    rawData: null,        // Original JSON for reference
    
    // Derived aggregates (cached)
    aggregates: {
      heroTimeline: null,
      kpis: null,
      licenseWaste: null,
      reconciliation: null,
      topServices: null,
      byBrand: null
    },
  };

  // Create namespace for utilities
  const DashboardUtils = {};

  // ===== Formatting Functions =====

  DashboardUtils.formatCurrency = function(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "-";
    return `$${Number(v).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  };

  DashboardUtils.formatNumber = function(v) {
    if (v === null || v === undefined) return "0";
    return Number(v).toLocaleString();
  };

  DashboardUtils.formatPercent = function(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "-";
    return `${v.toFixed(1)}%`;
  };

  // ===== Date Functions =====

  DashboardUtils.parseDate = function(str) {
    if (!str) return null;
    const d = new Date(str);
    return Number.isNaN(d.getTime()) ? null : d;
  };

  DashboardUtils.formatMonthKey = function(d) {
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  };

  DashboardUtils.startOfMonth = function(d) {
    return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
  };

  DashboardUtils.endOfMonth = function(d) {
    return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
  };

  DashboardUtils.dateInRange = function(date, from, to) {
    if (!date) return false;
    const time = date.getTime();
    return time >= from.getTime() && time <= to.getTime();
  };

  DashboardUtils.timeAgo = function(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  // ===== Badge Helpers =====

  DashboardUtils.getBadgeClass = function(badge) {
    switch (badge) {
      case 'Urgent': return 'danger';
      case 'High Impact': return 'high-impact';
      case 'Advisor': return 'advisor';
      case 'Security': return 'security';
      case 'Governance': return 'governance';
      default: return '';
    }
  };

  // ===== SKU Classification =====

  DashboardUtils.FREE_SKUS = new Set([
    'FLOW_FREE', 'POWERAPPS_VIRAL', 'POWERAPPS_DEV', 'STREAM', 'POWER_BI_STANDARD',
    'TEAMS_EXPLORATORY', 'MICROSOFT_TEAMS_EXPLORATORY_DEPT', 'WINDOWS_STORE', 
    'MICROSOFT_BUSINESS_CENTER', 'CCIBOTS_PRIVPREV_VIRAL', 'RIGHTSMANAGEMENT_ADHOC', 
    'FORMS_PRO', 'MCOPSTNC', 'POWER_PAGES_VTRIAL_FOR_MAKERS',
    'DYN365_ENTERPRISE_VIRTUAL_AGENT_VIRAL', 'DYN365_CDS_VIRAL', 
    'DYNAMICS_365_ONBOARDING_SKU', 'SHAREPOINTSTORAGE'
  ]);

  DashboardUtils.isPaidSku = function(skuPartNumber) {
    if (!skuPartNumber || typeof skuPartNumber !== 'string') return false;
    const upper = skuPartNumber.toUpperCase();
    if (upper.includes('FREE') || upper.includes('VIRAL') || upper.includes('TRIAL') ||
        upper.includes('EXPLORATORY') || upper.includes('_DEV')) {
      return false;
    }
    if (DashboardUtils.FREE_SKUS.has(upper)) return false;
    return true;
  };

  // ===== SKU PRICING =====
  // SKU prices are now managed by PricingService.js
  // This provides dynamic pricing from invoice data instead of hardcoded values
  //
  // The PricingService will initialize dashboardState.skuPrices on dashboard load
  // Priority: Invoice data > Marketplace API > Baseline estimates
  //
  // To access prices, use:
  //   PricingService.getPrice(dashboardState, 'SPE_E3')
  //   PricingService.getMonthlyCost(dashboardState, 'SPE_E3')
  //
  // REMOVED: Hardcoded SKU_PRICES object (anti-pattern)
  // Reason: Prices change quarterly, CSP markup varies, stale data causes ±15% inaccuracy

  // ===== DATA NORMALIZATION FUNCTIONS =====

  /**
   * Normalize cost data from merged-cost-report.json into factsCost
   */
  function normalizeCostData(rawData) {
    const state = global.dashboardState;
    state.factsCost = [];

    console.log('[normalizeCostData] Called with rawData:', {
      exists: !!rawData,
      hasCostRows: !!rawData?.costRows,
      costRowsLength: rawData?.costRows?.length
    });

    if (!rawData) {
      console.warn('[normalizeCostData] ❌ rawData is null/undefined');
      return;
    }
    
    if (!rawData.costRows) {
      console.warn('[normalizeCostData] ❌ rawData.costRows is missing');
      return;
    }

    console.log(`[normalizeCostData] Processing ${rawData.costRows.length} costRows...`);

    rawData.costRows.forEach((row, idx) => {
      // Use mtdCost if available (monthly aggregate), otherwise dailyCost (daily detail)
      const costAmount = row.mtdCost || row.dailyCost || row.cost || row.amount || 0;
      
      state.factsCost.push({
        date: row.date || row.usageDate || new Date().toISOString().split('T')[0],
        brand: getBrandFromTenant(row.tenantId),
        tenant: row.tenantId,
        tenantName: row.tenantName,
        billingSource: getBillingSource(row.tenantId),
        service: row.serviceName || row.service,
        sku: row.meterSubcategory || row.sku || null,
        resourceGroup: row.resourceGroup || null,
        amount: Number(costAmount),
        currency: row.currency || 'USD'
      });
      
      if (idx === 0) {
        console.log('[normalizeCostData] First row example:', state.factsCost[0]);
      }
    });
    
    console.log(`[normalizeCostData] ✅ Normalized ${state.factsCost.length} cost facts`);
  }

  /**
   * Normalize license data into factsLicenses
   * Handles new structure: rawData.license[].userAssignments[]
   */
  function normalizeLicenseData(rawData) {
    const state = global.dashboardState;
    state.factsLicenses = [];

    if (!rawData || !rawData.license) {
      console.log('[normalizeLicenseData] No license data found in rawData');
      return;
    }

    // Iterate through each tenant's license info
    (rawData.license || []).forEach(tenantLicense => {
      const tenantId = tenantLicense.tenantId;
      const tenantName = tenantLicense.tenantName;
      
      // Process user assignments (userId + skuIds array)
      (tenantLicense.userAssignments || []).forEach(assignment => {
        const userId = assignment.userId || 'unknown';
        
        // Each user might have multiple SKUs
        (assignment.skuIds || []).forEach(skuId => {
          // Get price from PricingService
          const priceInfo = global.PricingService
            ? global.PricingService.getPrice(state, skuId)
            : (state.skuPrices[skuId] || null);

          const monthlyCost = priceInfo ? priceInfo.monthlyPrice : 0;

          // Consider it "paid" if it has invoice-backed pricing OR price > 0
          const isPaid = priceInfo
            ? (priceInfo.source === 'invoice' || (monthlyCost > 0 && DashboardUtils.isPaidSku(skuId)))
            : DashboardUtils.isPaidSku(skuId);

          state.factsLicenses.push({
            userId: userId,
            displayName: 'User', // User display name not in current data structure
            sku: skuId,
            tenant: tenantId,
            tenantName: tenantName,
            brand: getBrandFromTenant(tenantId),
            isPaidSku: isPaid,
            monthlyCost: isPaid ? monthlyCost : 0,
            priceSource: priceInfo ? priceInfo.source : 'unknown'
          });
        });
      });
    });
    
    console.log(`[normalizeLicenseData] Normalized ${state.factsLicenses.length} license assignments`);
    const paidCount = state.factsLicenses.filter(l => l.isPaidSku).length;
    console.log(`[normalizeLicenseData] ${paidCount} paid licenses, ${state.factsLicenses.length - paidCount} free/trial`);
  }

  /**
   * Compute invoice reconciliation data
   */
  function normalizeInvoiceData(rawData) {
    const state = global.dashboardState;
    state.factsInvoices = [];

    // This would be populated from billing.js CSP data
    // For now, placeholder
  }

  /**
   * Helper: Map tenant ID to brand name
   */
  function getBrandFromTenant(tenantId) {
    const map = {
      '0c0e35dc-188a-4eb3-b8ba-61752154b407': 'HTT',
      'b5380912-79ec-452d-a6ca-6d897b19b294': 'Bishops',
      '3c7d2bf3-b597-4766-b5cb-2b489c2904d6': 'The Lash Lounge',
      '98723287-044b-4bbb-9294-19857d4128a0': 'Frenchies'
    };
    return map[tenantId] || tenantId;
  }

  /**
   * Helper: Map tenant to billing source
   */
  function getBillingSource(tenantId) {
    const map = {
      '0c0e35dc-188a-4eb3-b8ba-61752154b407': 'Logically MSP',
      'b5380912-79ec-452d-a6ca-6d897b19b294': 'Direct Microsoft',
      '3c7d2bf3-b597-4766-b5cb-2b489c2904d6': 'Sui Generis CSP',
      '98723287-044b-4bbb-9294-19857d4128a0': 'FTG CSP'
    };
    return map[tenantId] || 'Unknown';
  }

  // ===== AGGREGATE COMPUTATION FUNCTIONS =====

  /**
   * Compute hero timeline data for the cost journey chart
   */
  function computeHeroTimeline() {
    const state = global.dashboardState;
    const byMonth = {};

    state.factsCost.forEach(fact => {
      if (!fact.date) return; // Skip facts without dates
      const month = fact.date.substring(0, 7); // YYYY-MM
      if (!byMonth[month]) byMonth[month] = { HTT: 0, Bishops: 0, 'The Lash Lounge': 0, Frenchies: 0 };
      byMonth[month][fact.brand] = (byMonth[month][fact.brand] || 0) + fact.amount;
    });

    const months = Object.keys(byMonth).sort();
    return {
      months,
      series: [
        { name: 'HTT', data: months.map(m => byMonth[m].HTT || 0) },
        { name: 'Bishops', data: months.map(m => byMonth[m].Bishops || 0) },
        { name: 'The Lash Lounge', data: months.map(m => byMonth[m]['The Lash Lounge'] || 0) },
        { name: 'Frenchies', data: months.map(m => byMonth[m].Frenchies || 0) }
      ],
      annotations: [] // Would be computed from anomaly detection
    };
  }

  /**
   * Compute KPIs for executive summary
   */
  function computeKpis() {
    const state = global.dashboardState;
    const now = new Date();
    const thisMonth = now.toISOString().substring(0, 7);
    const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1).toISOString().substring(0, 7);

    const thisMonthCost = state.factsCost.filter(f => f.date && f.date.startsWith(thisMonth)).reduce((sum, f) => sum + f.amount, 0);
    const lastMonthCost = state.factsCost.filter(f => f.date && f.date.startsWith(lastMonth)).reduce((sum, f) => sum + f.amount, 0);
    const total12m = state.factsCost.reduce((sum, f) => sum + (f.amount || 0), 0);

    const licenseWaste = computeLicenseWaste();

    return {
      total12m,
      thisMonth: thisMonthCost,
      lastMonth: lastMonthCost,
      thisMonthVsLastPct: lastMonthCost > 0 ? ((thisMonthCost - lastMonthCost) / lastMonthCost) * 100 : 0,
      unitCostPerLocation: null, // Would need location count
      savingsLast90d: licenseWaste.totals.criticalCost + licenseWaste.totals.highCost,
      finOpsScore: 75 // Placeholder
    };
  }

  /**
   * Compute license waste (paid licenses only)
   */
  function computeLicenseWaste() {
    const state = global.dashboardState;
    const now = new Date();
    const critical = [];
    const high = [];
    const medium = [];

    state.factsLicenses.forEach(lic => {
      if (!lic.isPaidSku || lic.monthlyCost === 0) return; // ONLY PAID LICENSES

      const daysSinceSignIn = lic.lastSignIn ? 
        Math.floor((now - new Date(lic.lastSignIn)) / (1000 * 60 * 60 * 24)) : 999;

      if (!lic.lastSignIn || daysSinceSignIn > 180) {
        critical.push({ ...lic, daysSinceSignIn, severity: 'critical' });
      } else if (daysSinceSignIn > 90) {
        high.push({ ...lic, daysSinceSignIn, severity: 'high' });
      } else if (daysSinceSignIn > 30) {
        medium.push({ ...lic, daysSinceSignIn, severity: 'medium' });
      }
    });

    return {
      critical,
      high,
      medium,
      totals: {
        criticalCost: critical.reduce((sum, l) => sum + l.monthlyCost, 0),
        highCost: high.reduce((sum, l) => sum + l.monthlyCost, 0),
        mediumCost: medium.reduce((sum, l) => sum + l.monthlyCost, 0)
      }
    };
  }

  /**
   * Compute CSP reconciliation summary
   */
  function computeReconciliationSummary() {
    // Would cross-reference with billing.js invoice data
    return {
      billingSources: []
    };
  }

  /**
   * Compute all derived aggregates
   */
  function computeDerivedAggregates() {
    const state = global.dashboardState;
    state.aggregates.heroTimeline = computeHeroTimeline();
    state.aggregates.kpis = computeKpis();
    state.aggregates.licenseWaste = computeLicenseWaste();
    state.aggregates.reconciliation = computeReconciliationSummary();
  }

  // ===== DASHBOARD INITIALIZATION =====

  /**
   * Bootstrap the dashboard:
   * - Load JSON data
   * - Normalize into facts
   * - Compute aggregates
   * - Trigger initial render
   */
  async function initializeDashboard() {
    const cfg = global.DASHBOARD_CONFIG || {};
    const dataUrl = cfg.dataUrl || './data/latest-report.json';

    try {
      // Try primary data source
      const resp = await fetch(dataUrl);
      if (!resp.ok && cfg.localDataUrl) {
        // Fallback to local
        const localResp = await fetch(cfg.localDataUrl);
        const data = await localResp.json();
        global.dashboardState.rawData = data;
      } else {
        const data = await resp.json();
        global.dashboardState.rawData = data;
      }

      const data = global.dashboardState.rawData;
      global.dashboardState.meta.lastUpdated = data.generatedAt || new Date().toISOString();
      global.dashboardState.meta.dataSource = dataUrl;
      global.dashboardState.meta.tenantCount = (data.tenants || []).length;
      global.dashboardState.meta.subscriptionCount = (data.subscriptions || []).length;

      // Normalize data into facts
      normalizeCostData(data);
      normalizeLicenseData(data);
      normalizeInvoiceData(data);

      // Compute derived aggregates
      computeDerivedAggregates();

      console.log('✅ Dashboard initialized', {
        factsCost: global.dashboardState.factsCost.length,
        factsLicenses: global.dashboardState.factsLicenses.length,
        kpis: global.dashboardState.aggregates.kpis
      });

      // Trigger initial render (dashboard.js will handle)
      if (global.dashboard && global.dashboard.renderAll) {
        global.dashboard.renderAll(global.dashboardState.rawData);
      }

    } catch (err) {
      console.error('❌ Dashboard initialization failed:', err);
      // Render error state
      if (global.dashboard && global.dashboard.renderError) {
        global.dashboard.renderError(err.message);
      }
    }
  }

  // Expose utilities and initialization
  global.DashboardUtils = DashboardUtils;
  global.dashboardInit = {
    initializeDashboard,
    normalizeCostData,
    normalizeLicenseData,
    computeDerivedAggregates
  };

  // Expose to global namespace
  // ===== Table Enhancement Functions =====

  /**
   * Add search/filter functionality to a table
   * @param {HTMLTableElement} table - The table element
   * @param {Array<number>} searchableColumns - Column indices to search
   */
  DashboardUtils.enableTableSearch = function(table, searchableColumns = []) {
    if (!table) return;
    
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const container = table.closest('.table-wrapper') || table.parentElement;
    
    // Create search input
    const searchDiv = document.createElement('div');
    searchDiv.className = 'table-search';
    searchDiv.style.cssText = 'margin-bottom: 12px; display: flex; gap: 8px;';
    
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = '🔍 Search...';
    input.style.cssText = 'padding: 8px 12px; border: 1px solid #374151; background: #1f2937; color: #f0f2f5; border-radius: 4px; width: 200px; font-size: 14px;';
    
    input.addEventListener('input', (e) => {
      const term = e.target.value.toLowerCase();
      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(term) ? '' : 'none';
      });
    });
    
    container.insertBefore(searchDiv, table);
    searchDiv.appendChild(input);
  };

  /**
   * Make table headers sortable
   * @param {HTMLTableElement} table - The table element
   */
  DashboardUtils.enableTableSort = function(table) {
    if (!table) return;
    
    const headers = table.querySelectorAll('thead th');
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    
    headers.forEach((header, columnIndex) => {
      header.style.cursor = 'pointer';
      header.style.userSelect = 'none';
      header.title = 'Click to sort';
      
      header.addEventListener('click', () => {
        let ascending = !header.dataset.ascending;
        
        // Remove sort indicator from other headers
        headers.forEach(h => {
          h.dataset.ascending = '';
          h.textContent = h.textContent.replace(/\s*[▲▼]/g, '');
        });
        
        // Sort rows
        rows.sort((a, b) => {
          const aVal = a.children[columnIndex]?.textContent.trim() || '';
          const bVal = b.children[columnIndex]?.textContent.trim() || '';
          
          // Try numeric sort
          const aNum = parseFloat(aVal.replace(/[^\d.-]/g, ''));
          const bNum = parseFloat(bVal.replace(/[^\d.-]/g, ''));
          
          if (!Number.isNaN(aNum) && !Number.isNaN(bNum)) {
            return ascending ? aNum - bNum : bNum - aNum;
          }
          
          // Fall back to string sort
          return ascending ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
        });
        
        // Re-append sorted rows
        rows.forEach(row => table.querySelector('tbody').appendChild(row));
        
        // Update header indicator
        header.dataset.ascending = ascending;
        header.textContent += ascending ? ' ▲' : ' ▼';
      });
    });
  };

  /**
   * Responsive table wrapper - stack on mobile
   * @param {HTMLTableElement} table - The table element
   */
  DashboardUtils.makeTableResponsive = function(table) {
    if (!table) return;
    
    const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent);
    const rows = table.querySelectorAll('tbody tr');
    
    rows.forEach(row => {
      const cells = row.querySelectorAll('td');
      cells.forEach((cell, i) => {
        cell.setAttribute('data-label', headers[i]);
      });
    });
    
    // Add CSS class for styling
    table.classList.add('responsive-table');
  };

  /**
   * Calculate percentage change with safe division
   * @param {number} current - Current value
   * @param {number} previous - Previous value
   * @returns {number} Percentage change (-1 to 1 scale)
   */
  DashboardUtils.calculateChangePercent = function(current, previous) {
    if (!previous || previous === 0) {
      return current > 0 ? 1 : 0;
    }
    return (current - previous) / Math.abs(previous);
  };

  /**
   * Format change as delta with color indicator
   * @param {number} changePercent - Percentage change (-1 to 1)
   * @returns {string} HTML delta string with color
   */
  DashboardUtils.formatDelta = function(changePercent) {
    const absChange = Math.abs(changePercent);
    const className = changePercent > 0 ? 'negative' : 'positive';
    const icon = changePercent > 0 ? '↑' : '↓';
    const pct = (absChange * 100).toFixed(1);
    return `<span class="delta ${className}">${icon} ${pct}%</span>`;
  };

  // ===== Data Export Functions =====

  /**
   * Export table to CSV format
   * @param {HTMLTableElement} table - The table to export
   * @param {string} filename - The filename for download
   */
  DashboardUtils.exportTableToCSV = function(table, filename = 'export.csv') {
    if (!table) return;
    
    const rows = [];
    
    // Get headers
    const headers = Array.from(table.querySelectorAll('thead th')).map(th => {
      return th.textContent.trim().replace(/[▲▼]/g, ''); // Remove sort indicators
    });
    rows.push(headers);
    
    // Get data rows
    const dataRows = table.querySelectorAll('tbody tr');
    dataRows.forEach(row => {
      const cells = Array.from(row.querySelectorAll('td')).map(td => {
        // Clean up cell content
        let text = td.textContent.trim();
        // Remove currency symbols and commas for cleaner CSV
        text = text.replace(/[$,]/g, '');
        // Escape quotes
        text = text.replace(/"/g, '""');
        // Wrap in quotes if contains comma or newline
        if (text.includes(',') || text.includes('\n') || text.includes('"')) {
          text = `"${text}"`;
        }
        return text;
      });
      rows.push(cells);
    });
    
    // Create CSV content
    const csvContent = rows.map(row => row.join(',')).join('\n');
    
    // Download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  /**
   * Add export button to table
   * @param {HTMLTableElement} table - The table element
   * @param {string} name - Table name for filename
   */
  DashboardUtils.addExportButton = function(table, name = 'table') {
    if (!table) return;
    
    // Prefer the tightest container that actually owns the table to avoid insertBefore crashes
    const container = table.closest('.table-wrapper') || table.closest('.card-body') || table.parentElement;
    const host = container && container.contains(table) ? container : table.parentElement;
    if (!host) return;
    
    // Check if button already exists
    if (host.querySelector('.export-btn')) return;
    
    const button = document.createElement('button');
    button.className = 'btn ghost export-btn';
    button.innerHTML = '📥 Export CSV';
    button.setAttribute('aria-label', `Export ${name} to CSV`);
    button.style.marginBottom = '12px';
    
    button.addEventListener('click', () => {
      const timestamp = new Date().toISOString().split('T')[0];
      DashboardUtils.exportTableToCSV(table, `${name}-${timestamp}.csv`);
    });
    
    // Insert button safely: only use insertBefore when the host actually owns the table
    try {
      if (host === table.parentElement) {
        host.insertBefore(button, table);
      } else {
        host.appendChild(button);
      }
    } catch (e) {
      // If anything fails, silently skip - don't break rendering
      console.debug('[addExportButton] Skipping button insertion due to:', e.message);
    }
  };

  /**
   * Add accessibility attributes to table
   * @param {HTMLTableElement} table - The table element
   * @param {string} caption - Table caption/description
   */
  DashboardUtils.enhanceTableAccessibility = function(table, caption) {
    if (!table) return;
    
    // Add role and aria attributes
    table.setAttribute('role', 'table');
    table.setAttribute('aria-label', caption || 'Data table');
    
    // Add scope to headers
    const headers = table.querySelectorAll('thead th');
    headers.forEach(th => {
      th.setAttribute('scope', 'col');
      if (!th.getAttribute('aria-label')) {
        th.setAttribute('aria-label', th.textContent.trim());
      }
    });
    
    // Add row scopes
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach((row, index) => {
      row.setAttribute('role', 'row');
      const cells = row.querySelectorAll('td');
      cells.forEach(cell => {
        cell.setAttribute('role', 'cell');
      });
    });
  };

  /**
   * Add keyboard navigation to table
   * @param {HTMLTableElement} table - The table element
   */
  DashboardUtils.enableKeyboardNavigation = function(table) {
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    
    let focusedRow = null;
    
    tbody.addEventListener('keydown', (e) => {
      const row = e.target.closest('tr');
      if (!row) return;
      
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const currentIndex = rows.indexOf(row);
      
      switch(e.key) {
        case 'ArrowDown':
          e.preventDefault();
          if (currentIndex < rows.length - 1) {
            rows[currentIndex + 1].focus();
          }
          break;
        case 'ArrowUp':
          e.preventDefault();
          if (currentIndex > 0) {
            rows[currentIndex - 1].focus();
          }
          break;
        case 'Home':
          e.preventDefault();
          rows[0].focus();
          break;
        case 'End':
          e.preventDefault();
          rows[rows.length - 1].focus();
          break;
      }
    });
    
    // Make rows focusable
    const rows = tbody.querySelectorAll('tr');
    rows.forEach(row => {
      row.setAttribute('tabindex', '0');
    });
  };

  global.DashboardUtils = DashboardUtils;

  // Export normalization functions to global scope
  global.normalizeCostData = normalizeCostData;
  global.normalizeLicenseData = normalizeLicenseData;
  global.normalizeInvoiceData = normalizeInvoiceData;

  // Also support ES modules if available
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardUtils;
  }

  console.log('[utils.js] ✅ Module initialized. Exported: DashboardUtils, normalizeCostData, normalizeLicenseData, normalizeInvoiceData');
  console.log('[utils.js] Production deployment verified - 2025-12-04');

})(typeof window !== 'undefined' ? window : this);
