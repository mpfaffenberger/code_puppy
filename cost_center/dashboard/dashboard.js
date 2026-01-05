(() => {
  // ===== Configuration =====
  const defaultConfig = {
    dataUrl: "./data/latest-report.json",
    refreshWorkflowUrl: "",
    budgetMonthly: null,
  };

  const cfg = { ...defaultConfig, ...(window.DASHBOARD_CONFIG || {}) };

  const qs = new URLSearchParams(window.location.search);
  if (qs.get("dataUrl")) {
    cfg.dataUrl = qs.get("dataUrl");
  }
  if (qs.get("budget")) {
    const b = Number(qs.get("budget"));
    if (!Number.isNaN(b)) cfg.budgetMonthly = b;
  }

  // ===== DOM Elements =====
  const dom = {
    // Sidebar
    sidebar: document.getElementById("sidebar"),
    sidebarToggle: document.getElementById("sidebar-toggle"),
    navItems: document.querySelectorAll(".nav-item"),
    
    // Counts in sidebar
    tenantCount: document.getElementById("tenant-count"),
    mgCount: document.getElementById("mg-count"),
    subCount: document.getElementById("sub-count"),
    rgCount: document.getElementById("rg-count"),
    resourceCount: document.getElementById("resource-count"),
    licenseCount: document.getElementById("license-count"),
    userCount: document.getElementById("user-count"),
    spCount: document.getElementById("sp-count"),
    appCount: document.getElementById("app-count"),
    capCount: document.getElementById("cap-count"),
    // Sidebar CTA badges
    costAlertsCount: document.getElementById("cost-alerts-count"),
    licenseWasteCount: document.getElementById("license-waste-count"),
    identityTotalCount: document.getElementById("identity-total-count"),
    
    // Header
    pageTitle: document.getElementById("page-title"),
    pageSubtitle: document.getElementById("page-subtitle"),
    datasetMeta: document.getElementById("dataset-meta"),
    dataFreshness: document.getElementById("data-freshness"),
    refreshBtn: document.getElementById("refresh-btn"),
    triggerBtn: document.getElementById("trigger-btn"),
    
    // Filters
    period: document.getElementById("period-select"),
    from: document.getElementById("from-date"),
    to: document.getElementById("to-date"),
    tenant: document.getElementById("tenant-select"),
    subscription: document.getElementById("subscription-select"),
    
    // Content sections
    sections: document.querySelectorAll(".content-section"),
    
    // Tables
    tenantsTable: document.querySelector("#tenants-table tbody"),
    subsTable: document.querySelector("#subscriptions-table-section tbody"),
    rgTable: document.querySelector("#rg-table-section tbody"),
    resourcesTable: document.querySelector("#resources-table-core tbody"),
    costBreakdownTable: document.querySelector("#cost-breakdown-table-section tbody"),
    licenseSummaryTable: document.querySelector("#license-summary-table-optimization tbody"),
    licensesTable: document.querySelector("#licenses-table-details tbody"),
    userLicensesTable: document.querySelector("#user-licenses-table-optimization tbody"),
    identityUsersTable: document.querySelector("#identity-users-table-core tbody"),
    identityAppsTable: document.querySelector("#identity-apps-table-core tbody"),
    identityAppregsTable: document.querySelector("#identity-appregs-table-core tbody"),
    identityCapTable: document.querySelector("#identity-cap-table-core tbody"),
    githubBillingTable: document.querySelector("#github-billing-table-core tbody"),
    invoiceReconTable: document.querySelector("#invoice-recon-table-section tbody"),
    licenseCostTable: document.querySelector("#license-cost-table-optimization tbody"),
    
    // Task-centric: Cost Management
    costMgmtKpis: document.getElementById("cost-mgmt-kpis"),
    costBudgetAlert: document.getElementById("cost-budget-alert"),
    costBudgetMessage: document.querySelector("#section-cost-management #budget-alert-message"),
    costByBrandChart: document.getElementById("cost-by-brand-chart"),
    costTrendChart: document.getElementById("cost-trend-chart"),
    costForecastSummary: document.getElementById("cost-forecast-summary"),
    costWasteList: document.getElementById("cost-waste-list"),

    // Task-centric: License Optimization
    licenseOptKpis: document.getElementById("license-opt-kpis"),
    licenseWasteAlert: document.getElementById("license-waste-alert"),
    licenseWasteMessage: document.getElementById("license-waste-message"),
    criticalWasteList: document.getElementById("critical-waste-list"),
    highWasteList: document.getElementById("high-waste-list"),
    mediumWasteList: document.getElementById("medium-waste-list"),
    fixWasteBtn: document.getElementById("fix-waste-btn"),
    
    // Task-centric: Brand sections
    brandHTTSummary: document.getElementById("brand-htt-summary"),
    brandHTTKpis: document.getElementById("brand-htt-kpis"),
    brandHTTCostChart: document.getElementById("brand-htt-costs-chart"),
    brandHTTLicenses: document.getElementById("brand-htt-licenses"),
    brandBishopsSummary: document.getElementById("brand-bishops-summary"),
    brandBishopsKpis: document.getElementById("brand-bishops-kpis"),
    brandBishopsCostChart: document.getElementById("brand-bishops-costs-chart"),
    brandBishopsLicenses: document.getElementById("brand-bishops-licenses"),
    brandLashSummary: document.getElementById("brand-lash-summary"),
    brandLashKpis: document.getElementById("brand-lash-kpis"),
    brandLashCostChart: document.getElementById("brand-lash-costs-chart"),
    brandLashLicenses: document.getElementById("brand-lash-licenses"),
    brandFrenchiesSummary: document.getElementById("brand-frenchies-summary"),
    brandFrenchiesKpis: document.getElementById("brand-frenchies-kpis"),
    brandFrenchiesCostChart: document.getElementById("brand-frenchies-costs-chart"),
    brandFrenchiesLicenses: document.getElementById("brand-frenchies-licenses"),
    
    // Other containers
    kpiCards: document.getElementById("kpi-cards"),
    tenantSummary: document.getElementById("tenant-summary"),
    mgTree: document.getElementById("mg-tree"),
    licenseKpis: document.getElementById("license-kpis"),
    invoiceReconKpis: document.getElementById("invoice-recon-kpis"),
    resourcesKpis: document.getElementById("resources-kpis"),
    identityUsersKpis: document.getElementById("identity-users-kpis"),
    identityAppsKpis: document.getElementById("identity-apps-kpis"),
    identityAppregsKpis: document.getElementById("identity-appregs-kpis"),
    identityCapKpis: document.getElementById("identity-cap-kpis"),
    githubBillingKpis: document.getElementById("github-billing-kpis"),
    momComparison: document.getElementById("mom-comparison"),
    forecastCard: document.getElementById("forecast-card"),
    dataHealth: document.getElementById("data-health"),
    azureInsights: document.getElementById("azure-insights"),
    licenseInsights: document.getElementById("license-insights"),
    topMoversTenants: document.getElementById("top-movers-tenants"),
    topMoversServices: document.getElementById("top-movers-services"),

    // Mobile badges
    mobileCostBadge: document.getElementById("mobile-cost-badge"),
    mobileLicenseBadge: document.getElementById("mobile-license-badge"),
  };

  // ===== State =====
  let rawData = null;
  let skuPricing = null;
  const defaultSkuPrices = (window.DashboardUtils && window.DashboardUtils.SKU_PRICES) || {};
  let charts = {};
  const paginationState = {};
  const PAGINATION_THRESHOLD = 100;
  const validSections = new Set(Array.from(dom.sections || []).map(section => section.id.replace(/^section-/, "")));
  // Ensure sections expose data-section="section-..." for tests and selectors
  if (dom.sections && dom.sections.forEach) {
    dom.sections.forEach(section => {
      if (!section.dataset.section) {
        section.dataset.section = section.id;
      }
    });
  }
  
  // Phase 2: Saved views and role-based state
  let currentRole = localStorage.getItem('dashboard-role') || 'admin';
  let savedViews = JSON.parse(localStorage.getItem('dashboard-saved-views') || '[]');
  let budgetAlerts = {
    warning: false,
    critical: false
  };

  // ===== Loading State Helpers =====
  function showLoadingState() {
    // Show loading spinner in KPI cards
    if (dom.kpiCards) {
      dom.kpiCards.innerHTML = `
        <div class="kpi loading" style="grid-column: 1 / -1">
          <div class="label">Loading</div>
          <div class="value" style="display: flex; align-items: center; gap: 12px;">
            <span class="loading-spinner"></span>
            <span>Fetching data...</span>
          </div>
        </div>
      `;
    }
    
    // Show loading state in tables
    const tables = [
      dom.tenantsTable, dom.subsTable, dom.rgTable, dom.resourcesTable,
      dom.costBreakdownTable, dom.licenseSummaryTable, dom.licensesTable,
      dom.userLicensesTable, dom.identityUsersTable, dom.identityAppsTable,
      dom.identityAppregsTable, dom.identityCapTable, dom.githubBillingTable,
      dom.invoiceReconTable, dom.licenseCostTable
    ];
    
    tables.forEach(table => {
      if (table) {
        const colCount = table.closest('table')?.querySelector('thead tr')?.children.length || 6;
        table.innerHTML = `
          <tr>
            <td colspan="${colCount}" class="table-loading">
              <span class="loading-spinner"></span>
              <span>Loading data...</span>
            </td>
          </tr>
        `;
      }
    });
  }

  function showErrorState(message) {
    if (dom.kpiCards) {
      dom.kpiCards.innerHTML = `
        <div class="kpi" style="grid-column: 1 / -1">
          <div class="label" style="color: var(--danger);">Error</div>
          <div class="value" style="color: var(--danger)">Failed to load data</div>
          <div class="delta">${message}${message?.includes("Failed to fetch") ? " · If loading from a blob URL, enable CORS for this origin." : ""}</div>
        </div>
      `;
    }
  }

  // ===== SKU Pricing Helpers =====
  async function loadSkuPricing() {
    try {
      const response = await fetch('./data/sku-pricing.json');
      if (response.ok) {
        skuPricing = await response.json();
        console.log('Loaded SKU pricing data');
      }
    } catch (err) {
      console.warn('SKU pricing data not available, using defaults');
    }
  }

  function getSkuPrice(skuPartNumber) {
    if (!skuPartNumber) return null;
    if (skuPricing?.skus?.[skuPartNumber]) {
      return skuPricing.skus[skuPartNumber].monthlyPrice;
    }
    // Fallback to hardcoded defaults
    return defaultSkuPrices[skuPartNumber] || null;
  }

  function getSkuDisplayName(skuPartNumber) {
    if (!skuPartNumber) return skuPartNumber;
    if (skuPricing?.skus?.[skuPartNumber]) {
      return skuPricing.skus[skuPartNumber].displayName;
    }
    return skuPartNumber;
  }

  // ===== Utility Functions =====
  function formatCurrency(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "-";
    return `$${Number(v).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  // ===== Pagination Helpers =====
  function ensurePaginationControls(tableKey, tableElement) {
    const wrapper = tableElement?.closest(".card-body") || tableElement?.parentElement;
    if (!wrapper) return null;
    const existing = wrapper.querySelector(`.pagination[data-table="${tableKey}"]`);
    if (existing) return existing;

    const div = document.createElement("div");
    div.className = "pagination";
    div.dataset.table = tableKey;
    div.innerHTML = `
      <div class="pagination-left">
        <input type="search" class="pagination-filter" placeholder="Filter..." aria-label="Filter rows" />
      </div>
      <div class="pagination-right">
        <button class="btn ghost btn-prev">Prev</button>
        <span class="page-info"></span>
        <button class="btn ghost btn-next">Next</button>
      </div>
    `;
    wrapper.appendChild(div);
    return div;
  }

  function renderPaginatedTable(tableKey, rows, tableElement, columns) {
    if (!tableElement) return;

    if (!paginationState[tableKey]) {
      paginationState[tableKey] = { page: 1, pageSize: 50, filter: "" };
    }
    const state = paginationState[tableKey];
    const controls = ensurePaginationControls(tableKey, tableElement);
    const filterInput = controls?.querySelector(".pagination-filter");
    const btnPrev = controls?.querySelector(".btn-prev");
    const btnNext = controls?.querySelector(".btn-next");
    const pageInfo = controls?.querySelector(".page-info");

    // Bind events once
    if (filterInput && !filterInput.dataset.bound) {
      filterInput.dataset.bound = "true";
      filterInput.addEventListener("input", () => {
        state.filter = filterInput.value.toLowerCase();
        state.page = 1;
        renderPaginatedTable(tableKey, rows, tableElement, columns);
      });
    }
    if (btnPrev && !btnPrev.dataset.bound) {
      btnPrev.dataset.bound = "true";
      btnPrev.addEventListener("click", () => {
        if (state.page > 1) {
          state.page -= 1;
          renderPaginatedTable(tableKey, rows, tableElement, columns);
        }
      });
    }
    if (btnNext && !btnNext.dataset.bound) {
      btnNext.dataset.bound = "true";
      btnNext.addEventListener("click", () => {
        const maxPage = Math.max(1, Math.ceil(rows.length / state.pageSize));
        if (state.page < maxPage) {
          state.page += 1;
          renderPaginatedTable(tableKey, rows, tableElement, columns);
        }
      });
    }

    const filtered = state.filter
      ? rows.filter(r => r.toLowerCase().includes(state.filter))
      : rows;

    const maxPage = Math.max(1, Math.ceil(filtered.length / state.pageSize));
    if (state.page > maxPage) state.page = maxPage;
    const start = (state.page - 1) * state.pageSize;
    const pageRows = filtered.slice(start, start + state.pageSize);

    tableElement.innerHTML = pageRows.length ? pageRows.join("") : `
      <tr><td colspan="${columns}" class="empty-state">No rows match this filter.</td></tr>
    `;

    // Update button states
    if (btnPrev) {
      btnPrev.disabled = state.page <= 1;
    }
    if (btnNext) {
      btnNext.disabled = state.page >= maxPage;
    }

    if (pageInfo) {
      pageInfo.textContent = `${pageRows.length ? start + 1 : 0}-${Math.min(start + pageRows.length, filtered.length)} of ${filtered.length}`;
    }
  }

  function formatNumber(v) {
    if (v === null || v === undefined) return "0";
    return Number(v).toLocaleString();
  }

  function formatPercent(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "-";
    return `${v.toFixed(1)}%`;
  }

  function parseDate(str) {
    if (!str) return null;
    const d = new Date(str);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function formatMonthKey(d) {
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  }

  function startOfMonth(d) {
    return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
  }

  function endOfMonth(d) {
    return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
  }

  function dateInRange(date, from, to) {
    if (!date) return false;
    const time = date.getTime();
    return time >= from.getTime() && time <= to.getTime();
  }

  function timeAgo(dateStr) {
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
  }

  // ===== Navigation =====
  function initNavigation() {
    const resolveSectionId = (candidate) => {
      const sanitized = (candidate || "").replace(/^#/, "").trim();
      if (validSections.has(sanitized)) return sanitized;
      return "overview";
    };

    const syncToHash = () => {
      const target = resolveSectionId(window.location.hash);
      navigateToSection(target, { updateHistory: false });
    };

    dom.navItems.forEach(item => {
      item.addEventListener("click", (e) => {
        e.preventDefault();
        const section = item.dataset.section;
        navigateToSection(section);
      });
      
      // Keyboard navigation support
      item.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          const section = item.dataset.section;
          navigateToSection(section);
        }
      });
      
      // Ensure nav items are focusable
      if (!item.hasAttribute("tabindex")) {
        item.setAttribute("tabindex", "0");
      }
    });

    dom.sidebarToggle?.addEventListener("click", () => {
      const isOpen = dom.sidebar.classList.toggle("open");
      dom.sidebar.classList.toggle("visible", isOpen);
      dom.sidebarToggle.setAttribute("aria-expanded", isOpen);
    });
    
    // Keyboard support for sidebar toggle
    dom.sidebarToggle?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        const isOpen = dom.sidebar.classList.toggle("open");
        dom.sidebar.classList.toggle("visible", isOpen);
        dom.sidebarToggle.setAttribute("aria-expanded", isOpen);
      }
    });
    
    // Close sidebar on Escape key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && dom.sidebar.classList.contains("open")) {
        dom.sidebar.classList.remove("open");
        dom.sidebar.classList.remove("visible");
        dom.sidebarToggle?.setAttribute("aria-expanded", "false");
        dom.sidebarToggle?.focus();
      }
    });

    // Handle hash navigation
    if (window.location.hash) {
      syncToHash();
    } else {
      navigateToSection("overview", { updateHistory: false });
    }

    window.addEventListener("hashchange", syncToHash);
    window.addEventListener("popstate", syncToHash);
    
    // Mobile navigation
    const mobileNavItems = document.querySelectorAll('.mobile-nav-item[data-section]');
    mobileNavItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const section = item.dataset.section;
        navigateToSection(section);
        
        // Update mobile nav active state
        mobileNavItems.forEach(navItem => navItem.classList.remove('active'));
        item.classList.add('active');
      });
    });
    
    // Mobile menu toggle
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    if (mobileMenuToggle) {
      mobileMenuToggle.addEventListener('click', () => {
        dom.sidebar.classList.toggle('open');
      });
    }
  }

  function navigateToSection(sectionId, options = {}) {
    const { updateHistory = true } = options;
    const targetSection = validSections.has(sectionId) ? sectionId : "overview";

    // Update nav items
    dom.navItems.forEach(item => {
      item.classList.toggle("active", item.dataset.section === targetSection);
    });

    // Update sections
    dom.sections.forEach(section => {
      section.classList.toggle("active", section.id === `section-${targetSection}`);
    });

    // Update header - TASK-CENTRIC TITLES
    const titles = {
      // Core Dashboards
      overview: ["Executive Summary", "High-level KPIs, trends, and critical alerts across all brands"],
      "cost-management": ["Cost Management", "Spending analysis, waste detection, and budget tracking"],
      "license-optimization": ["License Optimization", "Paid license waste, utilization, and compliance"],
      
      // Brand Operations
      "brand-htt": ["HTT (Head to Toe)", "Complete cost, license, and resource view for HTT"],
      "brand-bishops": ["Bishops", "Complete cost, license, and resource view for Bishops"],
      "brand-lash": ["The Lash Lounge", "Complete cost, license, and resource view for The Lash Lounge"],
      "brand-frenchies": ["Frenchies", "Complete cost, license, and resource view for Frenchies"],
      
      // IT Operations
      "it-resources": ["Resource Inventory", "All Azure resources with costs, purpose, and ownership"],
      "it-identity": ["Identity & Access", "Users, apps, service principals, and conditional access"],
      topology: ["Cloud Architecture", "Multi-brand Azure + M365 topology diagram"],
      
      // Advanced
      "data-explorer": ["Data Explorer", "Raw data tables and advanced filtering"],
      
      // Legacy sections (kept for backward compatibility)
      recommendations: ["Recommendations", "Actionable insights to optimize costs and reduce waste"],
      tenants: ["Brands", "All managed Entra ID tenants (Brands)"],
      "management-groups": ["Management Groups", "Azure management group hierarchy"],
      subscriptions: ["Subscriptions", "Azure subscriptions across all brands"],
      "resource-groups": ["Resource Groups", "Logical containers for Azure resources"],
      resources: ["Resources", "Complete Azure resource inventory with YTD spend"],
      costs: ["Cost Breakdown", "Detailed cost analysis by service and resource"],
      trends: ["Trends", "Historical spend analysis and forecasting"],
      "invoice-recon": ["Invoice Reconciliation", "Compare MSP invoices against Microsoft direct costs"],
      licenses: ["License Overview", "License utilization and waste detection"],
      "license-details": ["SKU Details", "Complete license SKU inventory"],
      "user-licenses": ["User Assignments", "Per-user license allocation with waste detection"],
      "identity-users": ["Users", "Entra ID user directory by brand"],
      "identity-apps": ["Enterprise Apps", "Service principals and enterprise applications"],
      "identity-appregs": ["App Registrations", "Application registrations"],
      "identity-cap": ["Conditional Access", "Conditional Access policies"],
      "github-billing": ["GitHub Billing", "GitHub usage and costs"],
    };

    const [title, subtitle] = titles[targetSection] || ["Dashboard", ""];
    dom.pageTitle.textContent = title;
    dom.pageSubtitle.textContent = subtitle;

    // Control filter bar visibility - only show on pages that use date filters
    const filterBar = document.querySelector(".filter-bar");
    const periodFilter = filterBar?.querySelector(".filter-group:first-child");
    
    // Pages that should NOT show period/date filters (they show current state or YTD data)
    const noDateFilterPages = [
      "licenses", "license-details", "user-licenses",    // License data is current snapshot
      "invoice-recon",                                    // YTD reconciliation data
      "identity-users", "identity-apps", "identity-appregs", "identity-cap",  // Identity data is current
      "tenants", "management-groups", "subscriptions", "resource-groups",     // Hierarchy is current
      "github-billing",                                   // GitHub is current
      "topology"                                          // Topology is architectural view
    ];
    
    if (periodFilter) {
      periodFilter.style.display = noDateFilterPages.includes(targetSection) ? "none" : "flex";
    }

    // Update URL hash when explicitly navigating via UI
    if (updateHistory && window.location.hash !== `#${targetSection}`) {
      history.pushState(null, "", `#${targetSection}`);
    }

    // Close mobile sidebar
    dom.sidebar.classList.remove("open");
    dom.sidebar.classList.remove("visible");
  }

  // ===== Data Fetching =====
  async function fetchData() {
    const configuredUrl = cfg.dataUrl;
    const isLocalhost = /^https?:\/\/(localhost|127\.0\.0\.1)(:\\d+)?$/i.test(window.location.origin);
    const localLatest = "./data/latest-report.json";
    const localSample = "./data/sample-report.json";

    const queue = [];
    const seen = new Set();
    const enqueue = url => {
      if (!url || seen.has(url)) return;
      seen.add(url);
      queue.push(url);
    };

    if (isLocalhost) {
      enqueue(localLatest);
      enqueue(localSample);
    }

    if (configuredUrl) {
      enqueue(configuredUrl);
      if (configuredUrl.includes("latest-report")) {
        enqueue(configuredUrl.replace("latest-report.json", "sample-report.json"));
      }
    }

    // Always keep repo data as a final fallback for offline builds or CORS errors
    enqueue(localLatest);
    enqueue(localSample);

    let lastError = null;

    for (const url of queue) {
      try {
        const response = await fetch(url, { 
          cache: "no-store",
          mode: "cors",
          credentials: "omit"
        });
        if (!response.ok) {
          lastError = new Error(`HTTP ${response.status} ${response.statusText} (${url})`);
          continue;
        }
        if (url !== configuredUrl) {
          console.warn(`Dashboard data loaded from fallback source: ${url}`);
        }
        return await response.json();
      } catch (err) {
        lastError = err;
        console.warn(`Dashboard data fetch failed for ${url}:`, err);
      }
    }

    throw new Error(lastError?.message || "Failed to load data");
  }

  // ===== Filter Helpers =====
  function getSelection() {
    return {
      period: dom.period.value,
      tenant: dom.tenant.value,
      subscription: dom.subscription.value,
    };
  }

  function computeFilterRange(period) {
    const today = new Date();
    const utcToday = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));

    switch (period) {
      case "mtd": {
        const from = startOfMonth(utcToday);
        return { from, to: utcToday };
      }
      case "prev-month":
      case "last-month": {
        const prev = new Date(Date.UTC(utcToday.getUTCFullYear(), utcToday.getUTCMonth() - 1, 15));
        return { from: startOfMonth(prev), to: endOfMonth(prev) };
      }
      case "6m":
      case "last-6-months": {
        const from = new Date(Date.UTC(utcToday.getUTCFullYear(), utcToday.getUTCMonth() - 5, 1));
        return { from, to: utcToday };
      }
      case "12m":
      case "last-12-months": {
        const from = new Date(Date.UTC(utcToday.getUTCFullYear() - 1, utcToday.getUTCMonth(), 1));
        return { from, to: utcToday };
      }
      case "custom": {
        const fromVal = dom.from.value ? parseDate(dom.from.value) : null;
        const toVal = dom.to.value ? parseDate(dom.to.value) : null;
        if (fromVal && toVal) return { from: fromVal, to: toVal };
        return null;
      }
      default:
        return { from: utcToday, to: utcToday };
    }
  }

  function filterCostRows(data, selection) {
    const range = computeFilterRange(selection.period);
    if (!range) return [];

    return (data.costRows || []).filter(row => {
      if (selection.tenant && row.tenantId !== selection.tenant) return false;
      if (selection.subscription && row.subscriptionId !== selection.subscription) return false;

      // If row has a date, filter by date range
      if (row.date) {
        const d = parseDate(row.date);
        return d ? dateInRange(d, range.from, range.to) : false;
      }

      // For rows with mtdCost (no date), include if the filter includes current month
      if (row.mtdCost !== undefined) {
        const now = new Date();
        const currentMonthStart = startOfMonth(now);
        const currentMonthEnd = endOfMonth(now);
        return range.from <= currentMonthEnd && range.to >= currentMonthStart;
      }

      return false;
    });
  }

  // Cost rows filtered only by tenant/subscription (ignore date)
  function filterCostRowsAllPeriods(data, selection) {
    return (data.costRows || []).filter(row => {
      if (selection.tenant && row.tenantId !== selection.tenant) return false;
      if (selection.subscription && row.subscriptionId !== selection.subscription) return false;
      return true;
    });
  }

  // Calculate total spend from monthlyCosts for a date range
  function calculateMonthlyCostsTotal(data, selection) {
    const range = computeFilterRange(selection.period);
    if (!range) return 0;

    const monthlyCosts = data.monthlyCosts || {};
    let total = 0;

    // Convert range to month strings for comparison
    const fromMonth = `${range.from.getUTCFullYear()}-${String(range.from.getUTCMonth() + 1).padStart(2, '0')}`;
    const toMonth = `${range.to.getUTCFullYear()}-${String(range.to.getUTCMonth() + 1).padStart(2, '0')}`;

    Object.entries(monthlyCosts).forEach(([subscriptionId, subData]) => {
      // Filter by subscription if selected
      if (selection.subscription && subscriptionId !== selection.subscription) return;
      
      // Filter by tenant if selected (need to look up tenant from subscription)
      if (selection.tenant) {
        const tenant = (data.tenants || []).find(t => 
          (t.subscriptions || []).some(s => s.subscriptionId === subscriptionId)
        );
        if (!tenant || tenant.tenantId !== selection.tenant) return;
      }

      (subData.months || []).forEach(monthData => {
        const month = monthData.month;
        if (month >= fromMonth && month <= toMonth) {
          total += monthData.total || 0;
        }
      });
    });

    return total;
  }

  // Get monthly breakdown for charts
  function getMonthlyCostsBreakdown(data, selection) {
    const range = computeFilterRange(selection.period);
    if (!range) return [];

    const monthlyCosts = data.monthlyCosts || {};
    const monthlyTotals = {};

    // Convert range to month strings for comparison
    const fromMonth = `${range.from.getUTCFullYear()}-${String(range.from.getUTCMonth() + 1).padStart(2, '0')}`;
    const toMonth = `${range.to.getUTCFullYear()}-${String(range.to.getUTCMonth() + 1).padStart(2, '0')}`;

    Object.entries(monthlyCosts).forEach(([subscriptionId, subData]) => {
      // Filter by subscription if selected
      if (selection.subscription && subscriptionId !== selection.subscription) return;
      
      // Filter by tenant if selected
      if (selection.tenant) {
        const tenant = (data.tenants || []).find(t => 
          (t.subscriptions || []).some(s => s.subscriptionId === subscriptionId)
        );
        if (!tenant || tenant.tenantId !== selection.tenant) return;
      }

      (subData.months || []).forEach(monthData => {
        const month = monthData.month;
        if (month >= fromMonth && month <= toMonth) {
          monthlyTotals[month] = (monthlyTotals[month] || 0) + (monthData.total || 0);
        }
      });
    });

    return Object.entries(monthlyTotals)
      .map(([month, total]) => ({ month, total }))
      .sort((a, b) => a.month.localeCompare(b.month));
  }

  // Aggregate monthly totals (with tenant/subscription filtering)
  function getMonthlyTotals(data, selection, { limitToRange = false } = {}) {
    const monthlyCosts = data.monthlyCosts || {};
    const tenants = data.tenants || [];
    const subToTenant = new Map();
    tenants.forEach(t => {
      (t.subscriptions || []).forEach(s => {
        subToTenant.set(s.subscriptionId, t.tenantId);
      });
    });

    const range = limitToRange ? computeFilterRange(selection.period) : null;
    const totals = new Map();

    Object.entries(monthlyCosts).forEach(([subId, subData]) => {
      const tenantId = subToTenant.get(subId);
      if (selection.tenant && tenantId !== selection.tenant) return;
      if (selection.subscription && subId !== selection.subscription) return;

      (subData.months || []).forEach(m => {
        const monthKey = m.month;
        if (range) {
          const monthDate = new Date(monthKey + "-01");
          if (monthDate < range.from || monthDate > range.to) return;
        }
        totals.set(monthKey, (totals.get(monthKey) || 0) + (m.total || 0));
      });
    });

    return Array.from(totals.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }

  // Aggregate monthly totals by tenant for MoM/top-mover views
  function getTenantMonthlyTotals(data, selection) {
    const monthlyCosts = data.monthlyCosts || {};
    const tenants = data.tenants || [];
    const subToTenant = new Map();
    tenants.forEach(t => {
      (t.subscriptions || []).forEach(s => {
        subToTenant.set(s.subscriptionId, t.tenantId);
      });
    });

    const byTenant = new Map();
    Object.entries(monthlyCosts).forEach(([subId, subData]) => {
      const tenantId = subToTenant.get(subId);
      if (!tenantId) return;
      if (selection.tenant && tenantId !== selection.tenant) return;
      if (selection.subscription && subId !== selection.subscription) return;

      if (!byTenant.has(tenantId)) byTenant.set(tenantId, new Map());
      const monthMap = byTenant.get(tenantId);
      (subData.months || []).forEach(m => {
        monthMap.set(m.month, (monthMap.get(m.month) || 0) + (m.total || 0));
      });
    });

    return byTenant;
  }

  // Aggregate monthly totals by service (prefers data.serviceMonthlyCosts if available; otherwise derive from dated costRows)
  function getServiceMonthlyTotals(data, selection) {
    const serviceMonthly = data.serviceMonthlyCosts || {};
    const byService = new Map();

    // If serviceMonthlyCosts is present, use it
    if (Object.keys(serviceMonthly).length > 0) {
      Object.entries(serviceMonthly).forEach(([serviceName, entries]) => {
        entries.forEach(m => {
          // Apply filters if metadata is present on entries
          if (selection.tenant && m.tenantId && m.tenantId !== selection.tenant) return;
          if (selection.subscription && m.subscriptionId && m.subscriptionId !== selection.subscription) return;

          if (!byService.has(serviceName)) byService.set(serviceName, new Map());
          const map = byService.get(serviceName);
          map.set(m.month, (map.get(m.month) || 0) + (m.total || 0));
        });
      });
      return byService;
    }

    // Derive from costRows with dates
    const costs = filterCostRowsAllPeriods(data, selection);
    costs.forEach(c => {
      if (!c.date) return;
      const monthKey = c.date.slice(0, 7);
      const service = c.serviceName || c.meterCategory || "Other";
      if (!byService.has(service)) byService.set(service, new Map());
      const map = byService.get(service);
      const val = c.dailyCost ?? c.mtdCost ?? 0;
      map.set(monthKey, (map.get(monthKey) || 0) + val);
    });
    return byService;
  }

  // Find the latest month that has daily cost rows for the current selection
  function getLatestDailyMonthContext(costRows, selection) {
    const filtered = (costRows || []).filter(r => {
      if (!r.date || r.dailyCost === undefined) return false;
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });
    if (!filtered.length) return null;

    const latestDate = filtered
      .map(r => new Date(r.date))
      .filter(d => !Number.isNaN(d.getTime()))
      .sort((a, b) => b - a)[0];
    if (!latestDate) return null;

    const monthKey = `${latestDate.getUTCFullYear()}-${String(latestDate.getUTCMonth() + 1).padStart(2, "0")}`;
    const monthRows = filtered.filter(r => r.date && r.date.startsWith(monthKey));
    const mtdTotal = monthRows.reduce((sum, r) => sum + (r.dailyCost ?? 0), 0);
    const daysElapsed = latestDate.getUTCDate();
    const daysInMonth = endOfMonth(latestDate).getUTCDate();

    return { monthKey, mtdTotal, daysElapsed, daysInMonth };
  }

  function filterLicenses(data, selection) {
    return (data.license || []).filter(lic => {
      if (selection.tenant && lic.tenantId !== selection.tenant) return false;
      return true;
    });
  }

  // ===== Build Dropdowns =====
  function buildSelections(data) {
    // Tenant dropdown
    const tenantOptions = [{ value: "", label: "All tenants" }];
    (data.tenants || []).forEach(t => {
      tenantOptions.push({ value: t.tenantId, label: t.tenantName });
    });
    dom.tenant.innerHTML = tenantOptions.map(t => 
      `<option value="${t.value}">${t.label}</option>`
    ).join("");

    // Subscription dropdown - cascades based on tenant selection
    updateSubscriptionDropdown(data, "");
  }

  // Update subscription dropdown based on selected tenant (cascade filter)
  function updateSubscriptionDropdown(data, selectedTenant) {
    const subscriptionOptions = [{ value: "", label: "All subscriptions" }];
    const seen = new Set();
    (data.tenants || []).forEach(t => {
      // If tenant is selected, only show subscriptions for that tenant
      if (selectedTenant && t.tenantId !== selectedTenant) return;
      (t.subscriptions || []).forEach(sub => {
        if (!seen.has(sub.subscriptionId)) {
          seen.add(sub.subscriptionId);
          subscriptionOptions.push({
            value: sub.subscriptionId,
            label: sub.displayName || sub.subscriptionId,
            tenantId: t.tenantId,
          });
        }
      });
    });
    dom.subscription.innerHTML = subscriptionOptions.map(s =>
      `<option value="${s.value}">${s.label}</option>`
    ).join("");
  }

  // ===== Update Sidebar Counts =====
  function updateSidebarCounts(data) {
    const selection = getSelection();
    const tenants = data.tenants || [];
    const subscriptions = tenants.flatMap(t => t.subscriptions || []);
    const resourceGroups = (data.resourceGroups || []);
    const resources = (data.resources || []);
    const mgGroups = (data.managementGroups || []);
    const licenses = (data.license || []);
    
    const totalLicenseUsers = licenses.reduce((sum, l) => 
      sum + (l.userAssignments?.length || 0), 0);

    // Count identity objects across all tenants
    const users = data.users || {};
    const servicePrincipals = data.servicePrincipals || {};
    const applications = data.applications || {};
    const conditionalAccess = data.conditionalAccess || {};

    const totalUsers = Object.values(users).reduce((sum, arr) => sum + arr.length, 0);
    const totalSPs = Object.values(servicePrincipals).reduce((sum, arr) => sum + arr.length, 0);
    const totalApps = Object.values(applications).reduce((sum, arr) => sum + arr.length, 0);
    const totalCAP = Object.values(conditionalAccess).reduce((sum, arr) => sum + arr.length, 0);

    // Defensive null checks for all DOM elements
    if (dom.tenantCount) dom.tenantCount.textContent = tenants.length;
    if (dom.mgCount) dom.mgCount.textContent = mgGroups.length;
    if (dom.subCount) dom.subCount.textContent = subscriptions.length;
    if (dom.rgCount) dom.rgCount.textContent = resourceGroups.length || "-";
    if (dom.resourceCount) dom.resourceCount.textContent = resources.length || "-";
    if (dom.licenseCount) dom.licenseCount.textContent = totalLicenseUsers;
    if (dom.userCount) dom.userCount.textContent = totalUsers || "0";
    if (dom.spCount) dom.spCount.textContent = totalSPs || "0";
    if (dom.appCount) dom.appCount.textContent = totalApps || "0";
    if (dom.capCount) dom.capCount.textContent = totalCAP || "0";

    // Identity total badge (aggregate)
    const identityTotal = (totalUsers || 0) + (totalSPs || 0) + (totalApps || 0) + (totalCAP || 0);
    if (dom.identityTotalCount) dom.identityTotalCount.textContent = identityTotal;

    // Cost alerts badge: number of recommendations for current selection
    try {
      const recs = generateRecommendations(data, selection) || [];
      const recCount = recs.length;
      if (dom.costAlertsCount) dom.costAlertsCount.textContent = String(recCount);
      if (dom.mobileCostBadge) dom.mobileCostBadge.textContent = String(recCount);
    } catch (e) {
      // leave defaults
    }

    // License waste badge: number of inactive paid license cases
    try {
      const wasteCases = collectLicenseWasteCases(data, selection) || [];
      const wasteCount = wasteCases.length;
      if (dom.licenseWasteCount) dom.licenseWasteCount.textContent = String(wasteCount);
      if (dom.mobileLicenseBadge) dom.mobileLicenseBadge.textContent = String(wasteCount);
    } catch (e) {
      // leave defaults
    }
  }

  // ===== Phase 2: Saved Views & Role Management =====
  
  function initRoleSelector() {
    const roleSelector = document.getElementById('role-selector');
    if (!roleSelector) return;
    
    roleSelector.value = currentRole;
    roleSelector.addEventListener('change', (e) => {
      currentRole = e.target.value;
      localStorage.setItem('dashboard-role', currentRole);
      applyRoleView(currentRole);
      render();
    });
    
    // Apply role on load
    applyRoleView(currentRole);
  }
  
  function applyRoleView(role) {
    const roleConfig = cfg.roleDefaults?.[role];
    if (!roleConfig) return;
    
    // Filter navigation items based on role using data-role attribute
    dom.navItems.forEach(item => {
      const section = item.dataset.section;
      const allowedRoles = (item.dataset.role || 'all').split(',');
      
      // Show item if:
      // 1. Role is admin (sees all)
      // 2. Item explicitly allows this role
      // 3. Item allows 'all' roles
      const isVisible = role === 'admin' || 
                       allowedRoles.includes(role) || 
                       allowedRoles.includes('all');
      
      item.style.display = isVisible ? '' : 'none';
    });
    
    // Navigate to default view if not already there
    const currentSection = window.location.hash.replace('#', '') || 'overview';
    if (roleConfig.defaultView && currentSection === 'overview') {
      navigateToSection(roleConfig.defaultView, { updateHistory: true });
    }
  }
  
  function saveCurrentView() {
    const viewName = prompt('Enter a name for this view:');
    if (!viewName) return;
    
    const currentView = {
      id: Date.now().toString(),
      name: viewName,
      section: window.location.hash.replace('#', '') || 'overview',
      filters: {
        period: dom.period.value,
        tenant: dom.tenant.value,
        subscription: dom.subscription.value
      },
      role: currentRole,
      created: new Date().toISOString()
    };
    
    savedViews.push(currentView);
    localStorage.setItem('dashboard-saved-views', JSON.stringify(savedViews));
    
    alert(`View \"${viewName}\" saved successfully!`);
  }
  
  function loadSavedView(viewId) {
    const view = savedViews.find(v => v.id === viewId);
    if (!view) return;
    
    // Apply filters
    if (view.filters.period) dom.period.value = view.filters.period;
    if (view.filters.tenant) dom.tenant.value = view.filters.tenant;
    if (view.filters.subscription) dom.subscription.value = view.filters.subscription;
    
    // Navigate to section
    navigateToSection(view.section, { updateHistory: true });
    
    // Re-render with new filters
    render();
    
    // Close modal
    closeViewsModal();
  }
  
  function deleteSavedView(viewId) {
    if (!confirm('Are you sure you want to delete this view?')) return;
    
    savedViews = savedViews.filter(v => v.id !== viewId);
    localStorage.setItem('dashboard-saved-views', JSON.stringify(savedViews));
    renderViewsModal();
  }
  
  function showViewsModal() {
    const modal = document.getElementById('views-modal');
    if (!modal) return;
    
    modal.classList.remove('hidden');
    renderViewsModal();
  }
  
  function closeViewsModal() {
    const modal = document.getElementById('views-modal');
    if (modal) modal.classList.add('hidden');
  }
  
  function renderViewsModal() {
    const viewsList = document.getElementById('views-list');
    if (!viewsList) return;
    
    // Merge config views with user-saved views
    const configViews = cfg.savedViews || [];
    const allViews = [...configViews, ...savedViews];
    
    if (allViews.length === 0) {
      viewsList.innerHTML = '<p class=\"muted\" style=\"text-align: center; padding: 40px;\">No saved views yet. Click \"Save View\" to bookmark your current view.</p>';
      return;
    }
    
    viewsList.innerHTML = allViews.map(view => `
      <div class=\"saved-view-item\" data-view-id=\"${view.id}\">
        <div class=\"saved-view-info\">
          <div class=\"saved-view-name\">${view.name}</div>
          <div class=\"saved-view-meta\">
            ${view.section} • ${view.filters?.period || 'mtd'} • ${view.role || 'admin'}
            ${view.created ? ' • ' + new Date(view.created).toLocaleDateString() : ''}
          </div>
        </div>
        <div class=\"saved-view-actions\">
          <button class=\"btn primary\" onclick=\"(${loadSavedView.toString()})('${view.id}')\">Load</button>
          ${!configViews.find(v => v.id === view.id) ? `<button class=\"btn ghost\" onclick=\"(${deleteSavedView.toString()})('${view.id}')\">Delete</button>` : ''}
        </div>
      </div>
    `).join('');
  }
  
  // ===== Phase 2: Budget Tracking & Alerts =====
  
  function renderHeroBanner(totalCost, aggregates) {
    const budgetMonthly = cfg.budgetMonthly || 15000;
    const budgetAlert = cfg.budgetAlert || 0.8;
    const budgetCritical = cfg.budgetCritical || 0.95;
    
    const utilization = totalCost / budgetMonthly;
    const remaining = Math.max(0, budgetMonthly - totalCost);
    
    // Calculate YTD (assuming monthly budget * current month)
    const currentMonth = new Date().getMonth() + 1; // 1-12
    const ytdBudget = budgetMonthly * currentMonth;
    const ytdSpend = aggregates?.ytdTotal || totalCost * currentMonth; // Rough estimate
    const ytdChange = ytdBudget > 0 ? ((ytdSpend / ytdBudget - 1) * 100) : 0;
    
    // Simple projection (current spend * days remaining ratio)
    const now = new Date();
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const daysPassed = now.getDate();
    const daysRemaining = daysInMonth - daysPassed;
    const dailyBurn = daysPassed > 0 ? totalCost / daysPassed : 0;
    const projected = totalCost + (dailyBurn * daysRemaining);
    const projectionChange = budgetMonthly > 0 ? ((projected / budgetMonthly - 1) * 100) : 0;
    
    // Update hero elements
    const heroTitle = document.getElementById('budget-hero-title');
    const heroBadge = document.getElementById('budget-hero-badge');
    const heroSubtitle = document.getElementById('budget-hero-subtitle');
    const heroBudget = document.getElementById('hero-budget');
    const heroYtdSpend = document.getElementById('hero-ytd-spend');
    const heroYtdChange = document.getElementById('hero-ytd-change');
    const heroRemaining = document.getElementById('hero-remaining');
    const heroProjected = document.getElementById('hero-projected');
    const heroProjectionChange = document.getElementById('hero-projection-change');
    const progressFill = document.getElementById('budget-progress-fill');
    const progressText = document.getElementById('budget-progress-text');
    const budgetDaysText = document.getElementById('budget-days-text');
    
    if (!heroBadge) return; // Hero not in DOM
    
    // Set badge status
    heroBadge.classList.remove('warning', 'critical');
    if (utilization >= budgetCritical) {
      heroBadge.textContent = 'Critical';
      heroBadge.classList.add('critical');
    } else if (utilization >= budgetAlert) {
      heroBadge.textContent = 'Warning';
      heroBadge.classList.add('warning');
    } else {
      heroBadge.textContent = 'Healthy';
      heroBadge.className = 'hero-badge'; // Reset to default (green)
    }
    
    // Update metrics
    if (heroBudget) heroBudget.textContent = formatCurrency(budgetMonthly);
    if (heroYtdSpend) heroYtdSpend.textContent = formatCurrency(ytdSpend);
    if (heroYtdChange) {
      heroYtdChange.textContent = `${ytdChange >= 0 ? '+' : ''}${ytdChange.toFixed(1)}%`;
      heroYtdChange.classList.toggle('positive', ytdChange > 0);
      heroYtdChange.classList.toggle('negative', ytdChange < 0);
    }
    if (heroRemaining) heroRemaining.textContent = formatCurrency(remaining);
    if (heroProjected) heroProjected.textContent = formatCurrency(projected);
    if (heroProjectionChange) {
      heroProjectionChange.textContent = `${projectionChange >= 0 ? '+' : ''}${projectionChange.toFixed(1)}%`;
      heroProjectionChange.classList.toggle('positive', projectionChange > 0);
      heroProjectionChange.classList.toggle('negative', projectionChange < 0);
    }
    
    // Update progress bar
    if (progressFill) {
      const progressPercent = Math.min(100, utilization * 100);
      progressFill.style.width = `${progressPercent}%`;
      progressFill.classList.remove('warning', 'critical');
      if (utilization >= budgetCritical) {
        progressFill.classList.add('critical');
      } else if (utilization >= budgetAlert) {
        progressFill.classList.add('warning');
      }
    }
    
    if (progressText) {
      progressText.textContent = `${(utilization * 100).toFixed(1)}% utilized`;
    }
    
    if (budgetDaysText) {
      budgetDaysText.textContent = `${daysRemaining} days left in period`;
    }
  }
  
  function checkBudgetAlerts(totalCost) {
    const budgetMonthly = cfg.budgetMonthly || 15000;
    const budgetAlert = cfg.budgetAlert || 0.8;
    const budgetCritical = cfg.budgetCritical || 0.95;
    
    const utilization = totalCost / budgetMonthly;
    const budgetAlertBanner = document.getElementById('budget-alert');
    const budgetAlertTitle = document.getElementById('budget-alert-title');
    const budgetAlertMessage = document.getElementById('budget-alert-message');
    
    if (!budgetAlertBanner) return;
    
    if (utilization >= budgetCritical) {
      budgetAlertBanner.classList.remove('hidden', 'budget-warning');
      budgetAlertBanner.classList.add('budget-critical');
      if (budgetAlertTitle) budgetAlertTitle.textContent = '🚨 Critical Budget Alert';
      if (budgetAlertMessage) {
        budgetAlertMessage.textContent = `You have exceeded ${(utilization * 100).toFixed(1)}% of your monthly budget (${formatCurrency(totalCost)} of ${formatCurrency(budgetMonthly)}). Immediate action required!`;
      }
      
      if (!budgetAlerts.critical) {
        budgetAlerts.critical = true;
        // Could trigger email/notification here
        console.warn('CRITICAL BUDGET ALERT:', { utilization, totalCost, budgetMonthly });
      }
    } else if (utilization >= budgetAlert) {
      budgetAlertBanner.classList.remove('hidden', 'budget-critical');
      budgetAlertBanner.classList.add('budget-warning');
      if (budgetAlertTitle) budgetAlertTitle.textContent = '⚠️ Budget Warning';
      if (budgetAlertMessage) {
        budgetAlertMessage.textContent = `You have used ${(utilization * 100).toFixed(1)}% of your monthly budget (${formatCurrency(totalCost)} of ${formatCurrency(budgetMonthly)}). Consider reviewing costs.`;
      }
      
      if (!budgetAlerts.warning) {
        budgetAlerts.warning = true;
        console.warn('Budget warning triggered:', { utilization, totalCost, budgetMonthly });
      }
    } else {
      budgetAlertBanner.classList.add('hidden');
      budgetAlerts.warning = false;
      budgetAlerts.critical = false;
    }
  }
  
  // ===== Phase 2: Interactive Charts =====
  
  function makeChartInteractive(chartInstance, chartType) {
    if (!chartInstance || !chartInstance.canvas) return;
    
    chartInstance.options.onClick = (event, activeElements) => {
      if (activeElements.length === 0) return;
      
      const element = activeElements[0];
      const datasetIndex = element.datasetIndex;
      const index = element.index;
      const dataset = chartInstance.data.datasets[datasetIndex];
      const label = chartInstance.data.labels[index];
      
      // Determine what to filter based on chart type
      if (chartType === 'services') {
        // Filter by service name - navigate to cost breakdown
        const serviceName = label;
        console.log('Filtering by service:', serviceName);
        navigateToSection('costs', { updateHistory: true });
        
      } else if (chartType === 'tenant' || chartType === 'brand') {
        // Filter by tenant
        const tenantName = dataset.label || label;
        const tenant = rawData.tenants?.find(t => t.tenantName === tenantName);
        if (tenant && dom.tenant) {
          dom.tenant.value = tenant.tenantId;
          render();
        }
        
      } else if (chartType === 'monthly' || chartType === 'trend') {
        // Click on month - set custom date range for that month
        const monthLabel = label;
        console.log('Clicked month:', monthLabel);
        // Could implement month filtering here
      }
    };
    
    // Add cursor pointer on hover
    chartInstance.options.onHover = (event, activeElements) => {
      event.native.target.style.cursor = activeElements.length > 0 ? 'pointer' : 'default';
    };
    
    chartInstance.update();
  }
  
  // ===== Phase 2: Email Digest =====
  
  function generateEmailDigest(data, selection) {
    const recommendations = generateRecommendations(data, selection);
    const costs = filterCostRows(data, selection);
    const totalCost = costs.reduce((sum, r) => sum + (r.dailyCost ?? r.mtdCost ?? 0), 0);
    const budgetMonthly = cfg.budgetMonthly || 15000;
    const budgetUtilization = (totalCost / budgetMonthly) * 100;
    
    const prefs = JSON.parse(localStorage.getItem('email-digest-prefs') || '{}');
    
    let digest = `
<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }
    .container { max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; }
    .header { background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: white; padding: 30px 20px; text-align: center; }
    .content { padding: 30px 20px; }
    .kpi { display: inline-block; width: 48%; padding: 15px; background: #f9fafb; border-radius: 8px; margin-bottom: 10px; }
    .kpi-label { font-size: 12px; color: #6b7280; text-transform: uppercase; }
    .kpi-value { font-size: 24px; font-weight: bold; color: #1f2937; }
    .section { margin-bottom: 30px; }
    .section h2 { font-size: 18px; margin-bottom: 15px; color: #1f2937; }
    .recommendation { background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin-bottom: 10px; border-radius: 4px; }
    .recommendation-title { font-weight: bold; margin-bottom: 5px; }
    .footer { background: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #6b7280; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>💰 HTT Brands Cost Center Digest</h1>
      <p>Weekly summary for ${new Date().toLocaleDateString()}</p>
    </div>
    <div class="content">
`;
    
    if (prefs.budget !== false) {
      digest += `
      <div class="section">
        <h2>📊 Budget Status</h2>
        <div class="kpi">
          <div class="kpi-label">MTD Spend</div>
          <div class="kpi-value">${formatCurrency(totalCost)}</div>
        </div>
        <div class="kpi" style="float: right;">
          <div class="kpi-label">Budget Utilization</div>
          <div class="kpi-value" style="color: ${budgetUtilization > 90 ? '#ef4444' : budgetUtilization > 80 ? '#f59e0b' : '#10b981'}">${budgetUtilization.toFixed(1)}%</div>
        </div>
        <div style="clear: both;"></div>
      </div>
`;
    }
    
    if (prefs.recommendations !== false) {
      const topRecommendations = recommendations.slice(0, 5);
      if (topRecommendations.length > 0) {
        digest += `
      <div class="section">
        <h2>💡 Top Recommendations</h2>
`;
        topRecommendations.forEach(rec => {
          digest += `
        <div class="recommendation">
          <div class="recommendation-title">${rec.icon} ${rec.title}</div>
          <div>${rec.description}</div>
          <div style="margin-top: 8px; font-size: 12px; color: #6b7280;">
            💰 ${rec.savings > 0 ? formatCurrency(rec.savings) + '/mo' : 'TBD'} • 
            ⚡ ${rec.effort} effort • 
            📈 ${rec.impact} impact
          </div>
        </div>
`;
        });
        digest += `
      </div>
`;
      }
    }
    
    if (prefs.costs !== false) {
      const tenants = (data.tenants || []).filter(t => 
        !selection.tenant || t.tenantId === selection.tenant
      );
      digest += `
      <div class="section">
        <h2>💸 Cost Summary</h2>
        <ul>
          <li><strong>${tenants.length}</strong> tenant(s) managed</li>
          <li><strong>${formatCurrency(totalCost)}</strong> total MTD spend</li>
          <li><strong>${formatCurrency(budgetMonthly - totalCost)}</strong> remaining budget</li>
        </ul>
      </div>
`;
    }
    
    digest += `
    </div>
    <div class="footer">
      <p>This is an automated digest from HTT Brands Azure Cost Center Dashboard</p>
      <p><a href="https://azure.httbrands.com">View Full Dashboard</a></p>
    </div>
  </div>
</body>
</html>
`;
    
    return digest;
  }
  
  function showEmailDigestModal() {
    const modal = document.getElementById('email-modal');
    if (!modal) return;
    
    modal.classList.remove('hidden');
    
    // Load saved preferences
    const prefs = JSON.parse(localStorage.getItem('email-digest-prefs') || '{}');
    const emailInput = document.getElementById('email-address');
    const frequencySelect = document.getElementById('email-frequency');
    
    if (emailInput && prefs.email) emailInput.value = prefs.email;
    if (frequencySelect && prefs.frequency) frequencySelect.value = prefs.frequency;
    
    ['budget', 'recommendations', 'costs', 'licenses', 'trends'].forEach(key => {
      const checkbox = document.getElementById(`digest-${key}`);
      if (checkbox && prefs[key] !== undefined) checkbox.checked = prefs[key];
    });
  }
  
  function closeEmailDigestModal() {
    const modal = document.getElementById('email-modal');
    if (modal) modal.classList.add('hidden');
  }
  
  function saveEmailPreferences(e) {
    e.preventDefault();
    
    const email = document.getElementById('email-address')?.value;
    const frequency = document.getElementById('email-frequency')?.value;
    
    const prefs = {
      email,
      frequency,
      budget: document.getElementById('digest-budget')?.checked ?? true,
      recommendations: document.getElementById('digest-recommendations')?.checked ?? true,
      costs: document.getElementById('digest-costs')?.checked ?? true,
      licenses: document.getElementById('digest-licenses')?.checked ?? true,
      trends: document.getElementById('digest-trends')?.checked ?? false,
    };
    
    localStorage.setItem('email-digest-prefs', JSON.stringify(prefs));
    alert(`Email digest preferences saved! You'll receive ${frequency} digests at ${email}.\\n\\nNote: This is a demo. Actual email delivery requires backend integration.`);
    closeEmailDigestModal();
  }
  
  function previewEmailDigest() {
    if (!rawData) {
      alert('No data loaded yet. Please wait for the dashboard to load.');
      return;
    }
    
    const selection = getSelection();
    const digest = generateEmailDigest(rawData, selection);
    
    // Open preview in new window
    const previewWindow = window.open('', 'Email Digest Preview', 'width=700,height=800');
    if (previewWindow) {
      previewWindow.document.write(digest);
      previewWindow.document.close();
    }
  }

  // ===== Render Functions =====

  // Assess data quality and return warnings
  function assessDataQuality(data) {
    const warnings = [];
    const issues = [];
    
    // Check report age
    if (data.generatedAt) {
      const ageHours = Math.floor((Date.now() - new Date(data.generatedAt).getTime()) / (1000 * 60 * 60));
      if (ageHours > 48) {
        warnings.push(`Data is ${ageHours} hours old`);
      }
    }
    
    // Check tenant coverage
    const tenantCount = (data.tenants || []).length;
    if (tenantCount < 4) {
      warnings.push(`Only ${tenantCount}/4 brands loaded`);
    }
    
    // Check user sign-in data coverage
    const users = data.users || {};
    let usersWithNoSignIn = 0;
    let totalUsers = 0;
    Object.values(users).forEach(userList => {
      totalUsers += userList.length;
      usersWithNoSignIn += userList.filter(u => !u.lastSignInDateTime).length;
    });
    if (totalUsers > 0 && usersWithNoSignIn / totalUsers > 0.5) {
      warnings.push(`${Math.round((usersWithNoSignIn / totalUsers) * 100)}% users missing sign-in data`);
    }
    
    // Check monthlyCosts coverage
    const monthlyCosts = data.monthlyCosts || {};
    const subsWithData = Object.values(monthlyCosts).filter(s => (s.months || []).length > 3).length;
    if (Object.keys(monthlyCosts).length > 0 && subsWithData < 2) {
      warnings.push('Limited historical cost data');
    }
    
    return { warnings, issues };
  }

  function renderMeta(data) {
    const generated = data.generatedAt ? new Date(data.generatedAt).toLocaleString() : "Unknown";
    const { warnings } = assessDataQuality(data);
    
    // Build warning badge HTML
    const warningBadge = warnings.length > 0 
      ? `<span class="data-quality-badge warning" title="${warnings.join('\n')}">⚠ ${warnings.length} issue${warnings.length > 1 ? 's' : ''}</span>`
      : `<span class="data-quality-badge success">✓ Data OK</span>`;
    
    dom.datasetMeta.innerHTML = `
      <div><strong>Generated:</strong> ${generated}</div>
      <div><strong>Granularity:</strong> ${data.costGranularity || "N/A"}</div>
      <div style="margin-top: 4px;">${warningBadge}</div>
    `;
    
    const freshnessText = dom.dataFreshness.querySelector(".freshness-text");
    if (freshnessText) {
      freshnessText.textContent = data.generatedAt ? timeAgo(data.generatedAt) : "Unknown";
    }
  }

  function renderKpis(data, selection) {
    // Prefer monthly aggregates for historical ranges to avoid under-reporting when daily rows only cover current month
    const useMonthlyTotals = selection.period !== "mtd" && data.monthlyCosts && Object.keys(data.monthlyCosts).length > 0;

    // First try to get daily cost rows (for current period/MTD)
    const costs = filterCostRows(data, selection);
    let totalCost = costs.reduce((sum, r) => sum + (r.dailyCost ?? r.mtdCost ?? 0), 0);

    // For non-MTD periods, rely on monthly aggregates to show the full period total
    if (useMonthlyTotals) {
      const monthlyTotal = calculateMonthlyCostsTotal(data, selection);
      if (monthlyTotal > 0 || totalCost === 0) {
        totalCost = monthlyTotal;
      }
    }

    // Determine the period label
    const periodLabels = {
      "mtd": "Total Spend (MTD)",
      "prev-month": "Total Spend (Prev Month)",
      "6m": "Total Spend (6 Months)",
      "12m": "Total Spend (12 Months)",
      "custom": "Total Spend (Custom)"
    };
    const periodLabel = periodLabels[selection.period] || "Total Spend";

    const tenants = (data.tenants || []).filter(t => 
      !selection.tenant || t.tenantId === selection.tenant
    );
    const subscriptions = tenants.flatMap(t => t.subscriptions || []);
    
    const licenses = filterLicenses(data, selection);
    const totalLicenseUsers = licenses.reduce((sum, l) => 
      sum + (l.userAssignments?.length || 0), 0);

    // Get top service - aggregate by serviceName across all filtered rows
    const serviceTotals = new Map();
    costs.forEach(row => {
      const key = row.serviceName || row.meterCategory || "Other Services";
      const val = row.dailyCost ?? row.mtdCost ?? 0;
      serviceTotals.set(key, (serviceTotals.get(key) || 0) + val);
    });
    
    let topService = null;
    if (serviceTotals.size > 0) {
      const topEntry = [...serviceTotals.entries()].sort((a, b) => b[1] - a[1])[0];
      topService = { 
        serviceName: topEntry[0], 
        meterCategory: topEntry[0], 
        mtdCost: topEntry[1], 
        dailyCost: topEntry[1] 
      };
    }

    // Calculate cost optimization opportunities
    const resources = (data.resources || []).filter(r => {
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });
    const costResourceIds = new Set(costs.filter(c => c.resourceId).map(c => c.resourceId.toLowerCase()));
    const idleResources = resources.filter(r => !costResourceIds.has((r.id || "").toLowerCase())).length;
    
    // Calculate unused licenses (heuristic: more prepaid than consumed)
    let underutilizedSkus = 0;
    licenses.forEach(l => {
      (l.subscribedSkus || l.skuAssignments || []).forEach(sku => {
        const utilization = (sku.consumedUnits || 0) / (sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 1) || 0;
        if (utilization < 0.5 && (sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 0) > 0) {
          underutilizedSkus++;
        }
      });
    });

    // Calculate YoY comparison (compare current month to same month last year)
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const lastYearMonth = `${now.getFullYear() - 1}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    
    const currentMonthCost = data.monthlyCosts?.[currentMonth] || 0;
    const lastYearCost = data.monthlyCosts?.[lastYearMonth] || 0;
    const yoyChange = lastYearCost > 0 ? ((currentMonthCost - lastYearCost) / lastYearCost) * 100 : null;
    const yoyDelta = currentMonthCost - lastYearCost;

    // Budget tracking (from config or default)
    const monthlyBudget = cfg.budgetMonthly || 15000; // Default $15k/month budget
    const budgetUtilization = (totalCost / monthlyBudget) * 100;
    const budgetRemaining = monthlyBudget - totalCost;

    dom.kpiCards.innerHTML = `
      <div class="kpi">
        <div class="label">${periodLabel}</div>
        <div class="value ${budgetUtilization > 100 ? 'danger' : budgetUtilization > 80 ? 'warning' : ''}">${formatCurrency(totalCost)}</div>
        <div class="delta muted">Across ${tenants.length} tenant(s)</div>
        <div class="context">
          <div class="context-item">
            <span class="context-label">Budget (MTD)</span>
            <span class="context-value ${budgetUtilization > 100 ? 'negative' : 'positive'}">${formatCurrency(monthlyBudget)}</span>
          </div>
          <div class="context-item">
            <span class="context-label">Remaining</span>
            <span class="context-value ${budgetRemaining < 0 ? 'negative' : 'positive'}">${formatCurrency(budgetRemaining)}</span>
          </div>
          <div class="budget-bar">
            <div class="budget-progress ${budgetUtilization > 100 ? 'over-budget' : ''}" style="width: ${Math.min(budgetUtilization, 100)}%"></div>
          </div>
        </div>
      </div>
      <div class="kpi">
        <div class="label">Tenants</div>
        <div class="value">${tenants.length}</div>
        <div class="delta muted">${subscriptions.length} subscription(s)</div>
        <div class="context">
          <div class="context-item">
            <span class="context-label">YoY Change</span>
            <span class="context-value ${yoyChange !== null ? (yoyChange > 0 ? 'negative' : 'positive') : ''}">${yoyChange !== null ? (yoyChange > 0 ? '+' : '') + yoyChange.toFixed(1) + '%' : 'N/A'}</span>
          </div>
          ${yoyChange !== null ? `<div class="context-item">
            <span class="context-label">vs ${lastYearMonth}</span>
            <span class="context-value">${formatCurrency(Math.abs(yoyDelta))} ${yoyDelta > 0 ? 'higher' : 'lower'}</span>
          </div>` : ''}
        </div>
      </div>
      <div class="kpi">
        <div class="label">License Users</div>
        <div class="value">${formatNumber(totalLicenseUsers)}</div>
        <div class="delta muted">Across all SKUs</div>
        <div class="context">
          <div class="context-item">
            <span class="context-label">Licenses</span>
            <span class="context-value">${licenses.reduce((sum, l) => sum + (l.subscribedSkus || l.skuAssignments || []).length, 0)} SKUs</span>
          </div>
        </div>
      </div>
      <div class="kpi">
        <div class="label">Top Service</div>
        <div class="value">${topService?.serviceName || topService?.meterCategory || "Multiple"}</div>
        <div class="delta muted">${topService ? formatCurrency(topService.dailyCost ?? topService.mtdCost ?? 0) : "View Cost Analysis"}</div>
        <div class="context">
          <div class="context-item">
            <span class="context-label">% of Total</span>
            <span class="context-value">${topService && totalCost > 0 ? ((topService.dailyCost ?? topService.mtdCost ?? 0) / totalCost * 100).toFixed(1) + '%' : 'N/A'}</span>
          </div>
        </div>
      </div>
      <div class="kpi">
        <div class="label">Optimization Opportunities</div>
        <div class="value ${idleResources + underutilizedSkus > 0 ? "warning" : "success"}">${idleResources + underutilizedSkus}</div>
        <div class="delta muted">${idleResources} idle · ${underutilizedSkus} low-util</div>
        <div class="context">
          <div class="context-item">
            <span class="context-label">Action Required</span>
            <span class="context-value ${idleResources + underutilizedSkus > 0 ? 'negative' : 'positive'}">${idleResources + underutilizedSkus > 0 ? 'Yes' : 'No'}</span>
          </div>
        </div>
      </div>
    `;
    
    // Phase 2: Check budget alerts
    checkBudgetAlerts(totalCost);
    
    // Render hero banner
    renderHeroBanner(totalCost, data);
  }

  function renderDataHealth(data, selection) {
    if (!dom.dataHealth) return;

    const costRows = filterCostRowsAllPeriods(data, selection);
    const monthlyTotals = getMonthlyTotals(data, selection, { limitToRange: false });
    const months = monthlyTotals.map(([m]) => m);
    const firstMonth = months[0];
    const lastMonth = months[months.length - 1];

    const licenses = filterLicenses(data, selection);
    const licenseUsers = licenses.reduce((sum, l) => sum + (l.userAssignments?.length || 0), 0);

    const resources = (data.resources || []).filter(r => {
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });

    // Check user sign-in coverage
    const users = data.users || {};
    let usersWithSignIn = 0;
    let totalUsers = 0;
    Object.values(users).forEach(userList => {
      totalUsers += userList.length;
      usersWithSignIn += userList.filter(u => u.lastSignInDateTime).length;
    });
    const signInCoverage = totalUsers > 0 ? Math.round((usersWithSignIn / totalUsers) * 100) : 0;

    // Check data source breakdown
    const tenantCount = (data.tenants || []).length;
    const subCount = Object.keys(data.monthlyCosts || {}).length;

    const warnings = [];
    if (!costRows.length) warnings.push("No cost rows");
    if (!months.length) warnings.push("No monthly coverage");
    if (!resources.length) warnings.push("No resources found");
    if (signInCoverage < 50) warnings.push("Low sign-in data coverage");

    const generatedAt = data.generatedAt ? timeAgo(data.generatedAt) : "n/a";

    dom.dataHealth.innerHTML = `
      <div class="health-item">
        <div class="health-label">Data Source</div>
        <div class="health-value">${data.environment || "unknown"}</div>
        <div class="muted">${generatedAt}</div>
      </div>
      <div class="health-item">
        <div class="health-label">API Coverage</div>
        <div class="health-value">${tenantCount} brands · ${subCount} subs</div>
        <div class="muted">Azure Cost Management</div>
      </div>
      <div class="health-item">
        <div class="health-label">Historical Data</div>
        <div class="health-value ${months.length >= 6 ? "" : "health-warn"}">${months.length} months</div>
        <div class="muted">${months.length ? `${firstMonth || "?"} → ${lastMonth || "?"}` : "No monthlyCosts"}</div>
      </div>
      <div class="health-item">
        <div class="health-label">Sign-In Audit</div>
        <div class="health-value ${signInCoverage >= 70 ? "" : "health-warn"}">${signInCoverage}%</div>
        <div class="muted">${formatNumber(usersWithSignIn)}/${formatNumber(totalUsers)} users</div>
      </div>
      <div class="health-item">
        <div class="health-label">Status</div>
        <div class="health-value ${warnings.length ? "health-warn" : ""}">${warnings.length ? warnings.length + " warning(s)" : "✓ OK"}</div>
        <div class="muted">${warnings.length ? warnings.slice(0, 2).join(" · ") : "All checks passed"}</div>
      </div>
    `;
  }

  function renderTenantSummary(data, selection) {
    const tenants = (data.tenants || []).filter(t =>
      !selection.tenant || t.tenantId === selection.tenant
    );
    const licenses = data.license || [];

    if (tenants.length === 0) {
      dom.tenantSummary.innerHTML = `<div class="empty-state"><p>No tenants found</p></div>`;
      return;
    }

    dom.tenantSummary.innerHTML = tenants.map(t => {
      const subCount = t.subscriptions?.length || 0;
      const licenseData = licenses.find(l => l.tenantId === t.tenantId);
      const licenseUsers = licenseData?.userAssignments?.length || 0;
      const skuCount = licenseData?.subscribedSkus?.length || 0;

      return `
        <div class="tenant-card">
          <div class="tenant-card-header">
            <div class="tenant-icon">🏢</div>
            <div>
              <div class="tenant-name">${t.tenantName}</div>
              <div class="tenant-domain">${t.defaultDomain || t.tenantId.substring(0, 8)}</div>
            </div>
          </div>
          <div class="tenant-stats">
            <div class="tenant-stat">
              <div class="tenant-stat-value">${subCount}</div>
              <div class="tenant-stat-label">Subs</div>
            </div>
            <div class="tenant-stat">
              <div class="tenant-stat-value">${skuCount}</div>
              <div class="tenant-stat-label">SKUs</div>
            </div>
            <div class="tenant-stat">
              <div class="tenant-stat-value">${licenseUsers}</div>
              <div class="tenant-stat-label">Users</div>
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderTenantsTable(data) {
    const tenants = data.tenants || [];
    const licenses = data.license || [];

    if (tenants.length === 0) {
      dom.tenantsTable.innerHTML = `<tr><td colspan="6" class="empty-state">No tenants found</td></tr>`;
      return;
    }

    dom.tenantsTable.innerHTML = tenants.map(t => {
      const licenseData = licenses.find(l => l.tenantId === t.tenantId);
      const licenseUsers = licenseData?.userAssignments?.length || 0;

      return `
        <tr>
          <td><strong>${t.tenantName}</strong></td>
          <td>${t.organizationDisplayName || "-"}</td>
          <td>${t.defaultDomain || "-"}</td>
          <td><code style="font-size: 11px; color: var(--muted)">${t.tenantId}</code></td>
          <td class="num">${t.subscriptions?.length || 0}</td>
          <td class="num">${formatNumber(licenseUsers)}</td>
        </tr>
      `;
    }).join("");

    // Apply table enhancements
    const table = dom.tenantsTable.closest('table');
    if (table) {
      window.DashboardUtils.enableTableSearch(table, ['tenantName', 'organizationDisplayName']);
      window.DashboardUtils.enableTableSort(table);
      window.DashboardUtils.makeTableResponsive(table);
      window.DashboardUtils.addExportButton(table, 'tenants');
      window.DashboardUtils.enhanceTableAccessibility(table, 'Tenants overview table');
      window.DashboardUtils.enableKeyboardNavigation(table);
    }
  }

  function renderManagementGroupsTree(data) {
    const mgGroups = data.managementGroups || [];
    const tenants = data.tenants || [];
    
    if (mgGroups.length === 0) {
      dom.mgTree.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">📁</span>
          <p>No management groups found or data not yet collected.</p>
          <p class="muted">Management group collection requires additional permissions.</p>
        </div>
      `;
      return;
    }

    // Group by tenant
    const byTenant = new Map();
    mgGroups.forEach(mg => {
      const tenantId = mg.tenantId;
      if (!byTenant.has(tenantId)) {
        byTenant.set(tenantId, []);
      }
      byTenant.get(tenantId).push(mg);
    });

    // Build tree HTML
    let html = '<div class="mg-tree-container">';
    
    byTenant.forEach((groups, tenantId) => {
      const tenant = tenants.find(t => t.tenantId === tenantId);
      const tenantName = tenant?.tenantName || tenantId.substring(0, 8) + '...';
      
      html += `
        <div class="mg-tenant-group">
          <div class="mg-tenant-header">
            <span class="mg-tenant-icon">🏢</span>
            <span class="mg-tenant-name">${tenantName}</span>
            <span class="mg-count-badge">${groups.length} group(s)</span>
          </div>
          <div class="mg-groups-list">
      `;
      
      // Sort groups - root groups first
      const sortedGroups = groups.sort((a, b) => {
        if (a.displayName === 'Tenant Root Group') return -1;
        if (b.displayName === 'Tenant Root Group') return 1;
        return (a.displayName || '').localeCompare(b.displayName || '');
      });
      
      sortedGroups.forEach(mg => {
        const isRoot = mg.displayName === 'Tenant Root Group';
        const icon = isRoot ? '🌳' : '📂';
        html += `
          <div class="mg-item ${isRoot ? 'root' : ''}">
            <span class="mg-icon">${icon}</span>
            <div class="mg-details">
              <span class="mg-name">${mg.displayName || mg.name}</span>
              <span class="mg-id muted">${mg.name}</span>
            </div>
          </div>
        `;
      });
      
      html += `
          </div>
        </div>
      `;
    });
    
    html += '</div>';
    dom.mgTree.innerHTML = html;
  }

  function renderSubscriptionsTable(data, selection) {
    const tenants = (data.tenants || []).filter(t =>
      !selection.tenant || t.tenantId === selection.tenant
    );
    const costs = filterCostRows(data, selection);

    const rows = [];
    tenants.forEach(t => {
      (t.subscriptions || []).forEach(sub => {
        if (selection.subscription && sub.subscriptionId !== selection.subscription) return;
        
        const subCosts = costs.filter(c => c.subscriptionId === sub.subscriptionId);
        const totalCost = subCosts.reduce((sum, c) => sum + (c.dailyCost ?? c.mtdCost ?? 0), 0);

        rows.push({
          tenantName: t.tenantName,
          subscriptionName: sub.displayName || sub.subscriptionId,
          subscriptionId: sub.subscriptionId,
          state: sub.state || "Unknown",
          owners: sub.owners || [],
          cost: totalCost,
        });
      });
    });

    if (rows.length === 0) {
      dom.subsTable.innerHTML = `<tr><td colspan="6" class="empty-state">No subscriptions found</td></tr>`;
      return;
    }

    dom.subsTable.innerHTML = rows.map(r => `
      <tr>
        <td>${r.tenantName}</td>
        <td><strong>${r.subscriptionName}</strong></td>
        <td><code style="font-size: 11px; color: var(--muted)">${r.subscriptionId}</code></td>
        <td><span class="status-badge ${r.state === 'Enabled' ? 'enabled' : 'warning'}">${r.state}</span></td>
        <td>${r.owners.slice(0, 2).map(o => `<span class="chip">${o.principalType || 'User'}</span>`).join("")}${r.owners.length > 2 ? `<span class="chip">+${r.owners.length - 2}</span>` : ''}</td>
        <td class="num">${formatCurrency(r.cost)}</td>
      </tr>
    `).join("");

    // Apply table enhancements
    const subsTableEl = dom.subsTable.closest('table');
    if (subsTableEl) {
      window.DashboardUtils.enableTableSearch(subsTableEl, ['subscriptionName', 'state']);
      window.DashboardUtils.enableTableSort(subsTableEl);
      window.DashboardUtils.makeTableResponsive(subsTableEl);
      window.DashboardUtils.addExportButton(subsTableEl, 'subscriptions');
      window.DashboardUtils.enhanceTableAccessibility(subsTableEl, 'Azure subscriptions table');
      window.DashboardUtils.enableKeyboardNavigation(subsTableEl);
    }
  }

  function renderResourceGroupsTable(data, selection) {
    const resourceGroups = data.resourceGroups || [];
    const costs = filterCostRows(data, selection);

    // Group costs by resource group
    const rgCosts = new Map();
    costs.forEach(c => {
      if (!c.resourceGroup) return;
      const key = `${c.tenantId}|${c.subscriptionId}|${c.resourceGroup}`;
      const current = rgCosts.get(key) || { cost: 0, count: 0 };
      current.cost += c.dailyCost ?? c.mtdCost ?? 0;
      current.count++;
      rgCosts.set(key, current);
    });

    // If we have resourceGroups in data, show them
    if (resourceGroups.length > 0) {
      dom.rgTable.innerHTML = resourceGroups.map(rg => {
        const key = `${rg.tenantId}|${rg.subscriptionId}|${rg.name}`;
        const costData = rgCosts.get(key) || { cost: 0, count: 0 };
        return `
          <tr>
            <td>${rg.tenantName || "-"}</td>
            <td>${rg.subscriptionName || "-"}</td>
            <td><strong>${rg.name}</strong></td>
            <td>${rg.location || "-"}</td>
            <td class="num">${costData.count || "-"}</td>
            <td class="num">${formatCurrency(costData.cost)}</td>
          </tr>
        `;
      }).join("");
    } else if (rgCosts.size > 0) {
      // Extract RGs from cost data
      const rows = Array.from(rgCosts.entries()).map(([key, data]) => {
        const [tenantId, subscriptionId, resourceGroup] = key.split("|");
        const tenant = (rawData.tenants || []).find(t => t.tenantId === tenantId);
        const sub = tenant?.subscriptions?.find(s => s.subscriptionId === subscriptionId);
        return {
          tenantName: tenant?.tenantName || tenantId.substring(0, 8),
          subscriptionName: sub?.displayName || subscriptionId.substring(0, 8),
          resourceGroup,
          cost: data.cost,
          count: data.count,
        };
      });

      dom.rgTable.innerHTML = rows.map(r => `
        <tr>
          <td>${r.tenantName}</td>
          <td>${r.subscriptionName}</td>
          <td><strong>${r.resourceGroup}</strong></td>
          <td>-</td>
          <td class="num">${r.count}</td>
          <td class="num">${formatCurrency(r.cost)}</td>
        </tr>
      `).join("");
    } else {
      dom.rgTable.innerHTML = `
        <tr><td colspan="6" class="empty-state">
          No resource groups found. Resource data will appear when Azure resources are deployed.
        </td></tr>
      `;
    }
  }

  // ===== Resource Descriptions Reference Data =====
  // Loaded from data/reference/resources-descriptions.csv
  const RESOURCE_DESCRIPTIONS = {
    "sql-import-vm_osdisk_1_4707c35ce03c4cf89607044c035e0387": { purpose: "OS disk for SQL Import VM used in data migration and ETL processes", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "htt-bi-dev-vnet": { purpose: "Isolated network for BI development workloads and data pipelines", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "sql-import-nic": { purpose: "Network interface for SQL Import VM connectivity", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "sql-import-nsg": { purpose: "Security rules controlling SQL Import VM network access", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "sql-import-udr": { purpose: "Custom routing for SQL Import VM traffic through firewall", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "sql-import-vm-data-disk": { purpose: "Data disk for SQL Server databases and staging data", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "htt-bi-adf-dev": { purpose: "Development Azure Data Factory for building and testing ETL pipelines", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "httadsldevstaging": { purpose: "Staging storage for ADF dev pipeline data landing zone", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "httdevbackup": { purpose: "Backup storage for development environment data and configs", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "httdevintegration": { purpose: "Integration storage for cross-system data exchange in dev", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "httdevkv": { purpose: "Key Vault for BI dev secrets, connection strings, and certificates", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "htt-bi-prod-vnet": { purpose: "Production network for BI workloads and Fabric connectivity", initiative: "BI Platform Production", function: "Data Engineering", owner: "BI Team" },
    "htt-bi-adf-prod": { purpose: "Production Azure Data Factory for enterprise ETL pipelines", initiative: "BI Platform Production", function: "Data Engineering", owner: "BI Team" },
    "httfabricmain": { purpose: "Secondary Fabric capacity for development and overflow workloads", initiative: "BI Platform Production", function: "Analytics & Reporting", owner: "BI Team" },
    "httfabric": { purpose: "Primary Microsoft Fabric capacity for enterprise BI workloads", initiative: "BI Platform Production", function: "Analytics & Reporting", owner: "BI Team" },
    "sql-import-vm": { purpose: "SQL Server VM for data import, migration, and ETL processing", initiative: "BI Platform Development", function: "Data Engineering", owner: "BI Team" },
    "syntex": { purpose: "SharePoint Syntex document processor for AI content processing", initiative: "Content Services", function: "Document Management", owner: "IT Operations" },
    "htt-core-fw": { purpose: "Central Azure Firewall for hub-spoke network security", initiative: "Core Infrastructure", function: "Network Security", owner: "IT Operations" },
    "htt-core-vpngw": { purpose: "VPN Gateway for secure site-to-site connectivity", initiative: "Core Infrastructure", function: "Network Connectivity", owner: "IT Operations" },
    "htt-core-vnet": { purpose: "Hub virtual network for centralized connectivity", initiative: "Core Infrastructure", function: "Networking", owner: "IT Operations" },
    "httnetlogs": { purpose: "Storage for network flow logs and diagnostic data", initiative: "Core Infrastructure", function: "Monitoring", owner: "IT Operations" },
    "htt-cost-dashboard": { purpose: "Static Web App hosting cost center dashboard", initiative: "FinOps", function: "Cost Management", owner: "Finance/IT" },
    "httcostcenter": { purpose: "Storage for cost reports and financial data", initiative: "FinOps", function: "Cost Management", owner: "Finance/IT" },
    "tll-web-func-prod": { purpose: "Production Azure Function for TLL web integrations", initiative: "TLL Digital", function: "Web Integrations", owner: "TLL Dev Team" },
    "tll-web-pg-prod": { purpose: "Production PostgreSQL for TLL web application", initiative: "TLL Digital", function: "Web Integrations", owner: "TLL Dev Team" },
    "tll-kv-prod": { purpose: "Production Key Vault for TLL secrets", initiative: "TLL Digital", function: "Web Integrations", owner: "TLL Dev Team" },
  };

  function getResourceDescription(resourceName) {
    const key = resourceName?.toLowerCase?.() || "";
    return RESOURCE_DESCRIPTIONS[key] || { purpose: "", initiative: "", function: "", owner: "" };
  }

  function renderResourcesTable(data, selection) {
    const resources = data.resources || [];
    const costRows = data.costRows || [];
    const period = selection.period;

    // Calculate cost based on period selection
    const costs = filterCostRows(data, selection);
    
    // Build a cost lookup by resourceId
    const costByResourceId = new Map();
    
    // For historical periods, we need to use monthlyCosts since costRows only has recent data
    const useMonthly = (period === "6m" || period === "12m" || period === "prev-month");
    
    if (useMonthly) {
      // Use monthlyCosts for historical periods
      // Since monthlyCosts is by subscription, not by resource, we'll show subscription-level costs
      // and note that resource-level breakdown is only available for current period
    }
    
    // Build cost map from filtered cost rows
    costs.forEach(c => {
      if (c.resourceId) {
        const key = c.resourceId.toLowerCase();
        const existing = costByResourceId.get(key) || 0;
        costByResourceId.set(key, existing + (c.dailyCost ?? c.mtdCost ?? 0));
      }
    });

    // Also aggregate unfiltered costRows to get MTD costs for current period
    if (!useMonthly) {
      costRows.forEach(c => {
        if (c.resourceId && c.mtdCost) {
          const key = c.resourceId.toLowerCase();
          // Use mtdCost if we don't have daily aggregation
          if (!costByResourceId.has(key)) {
            costByResourceId.set(key, c.mtdCost);
          }
        }
      });
    }

    if (resources.length > 0) {
      const rows = resources.filter(r => {
        if (selection.tenant && r.tenantId !== selection.tenant) return false;
        if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
        return true;
      }).map(r => {
        const resourceCost = costByResourceId.get(r.id?.toLowerCase()) || 0;
        const desc = getResourceDescription(r.name);
        const tenantShort = (r.tenantName || "")
          .replace("Head to Toe Brands (anchor)", "HTT Brands")
          .replace("The Lash Lounge", "TLL")
          .replace("Frenchies", "FN")
          .replace("Bishops", "BCC");
        return { 
          ...r, 
          cost: resourceCost,
          tenantShort,
          purpose: desc.purpose,
          initiative: desc.initiative,
          businessFunction: desc.function,
          owner: desc.owner
        };
      });

      // Sort by cost descending so resources with costs show first
      rows.sort((a, b) => b.cost - a.cost);

      const periodLabel = period === "mtd" ? "MTD" : 
                          period === "prev-month" ? "Prev Month" :
                          period === "6m" ? "6 Months" : 
                          period === "12m" ? "12 Months" : "Period";

      dom.resourcesTable.innerHTML = rows.map(r => {
        const typeShort = r.type?.split("/").pop() || "-";
        const purposeDisplay = r.purpose || r.initiative || "-";
        const functionDisplay = r.businessFunction || "-";
        
        return `
          <tr>
            <td><strong>${r.tenantShort}</strong></td>
            <td>${r.name || r.id?.split("/").pop() || "-"}</td>
            <td><span class="chip">${typeShort}</span></td>
            <td>${purposeDisplay}</td>
            <td>${functionDisplay}</td>
            <td class="num">${formatCurrency(r.cost)}</td>
          </tr>
        `;
      }).join("");

      // Apply table enhancements with pagination and better filtering
      const resourceTableEl = dom.resourcesTable.closest('table');
      if (resourceTableEl) {
        // Create unified filter header before table (idempotent)
        const filterContainer = window.dashboard.utils.insertTableFilterHeader(resourceTableEl, {
          searchPlaceholder: 'Search resources by name, type, or purpose...',
          columnSelect: ['Name', 'Type', 'Purpose', 'Function', 'Tenant'],
          showBrandTabs: true,
          brands: ['All Brands', 'HTT Brands', 'TLL', 'FN', 'BCC']
        });

        // Apply pagination (idempotent)
        window.dashboard.utils.applyTablePagination(resourceTableEl, 20);

        // Apply brand filtering
        filterContainer.querySelectorAll('.brand-tab').forEach(tab => {
          tab.addEventListener('click', () => {
            filterContainer.querySelectorAll('.brand-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            window.dashboard.utils.applyBrandFiltering(resourceTableEl.closest('.table-wrapper') || resourceTableEl, tab.dataset.brand);
          });
        });

        // Apply unified search
        const searchInput = filterContainer.querySelector('.table-search-unified');
        if (searchInput) {
          searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            const tbody = resourceTableEl.querySelector('tbody');
            let visibleCount = 0;
            
            tbody.querySelectorAll('tr').forEach(row => {
              const text = row.textContent.toLowerCase();
              const matches = text.includes(term);
              row.style.display = matches ? '' : 'none';
              if (matches) visibleCount++;
            });

            const resultsSpan = filterContainer.querySelector('.filter-results');
            if (resultsSpan) {
              resultsSpan.textContent = `${visibleCount} of ${tbody.querySelectorAll('tr').length} items`;
            }
          });
        }

        // Keep original utilities for sorting and export
        window.DashboardUtils.enableTableSort(resourceTableEl);
        window.DashboardUtils.addExportButton(resourceTableEl, 'resources');
        window.DashboardUtils.enhanceTableAccessibility(resourceTableEl, 'Azure resources table');
        window.DashboardUtils.enableKeyboardNavigation(resourceTableEl);
      }
    } else {
      dom.resourcesTable.innerHTML = `
        <tr><td colspan="6" class="empty-state">
          No resources found. Resource inventory will appear when Azure resources are deployed.
        </td></tr>
      `;
    }

    // Render resource KPIs and charts
    renderResourcesKpis(data, selection);
    renderResourcesCharts(data, selection);
  }

  function renderResourcesKpis(data, selection) {
    if (!dom.resourcesKpis) return;
    
    const resources = data.resources || [];
    const costs = filterCostRows(data, selection);
    const period = selection.period;
    
    // Filter resources by selection
    const filteredResources = resources.filter(r => {
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });
    
    // Calculate total cost for the period
    let totalCost = 0;
    const costByResourceId = new Map();
    costs.forEach(c => {
      if (c.resourceId) {
        const key = c.resourceId.toLowerCase();
        const val = c.dailyCost ?? c.mtdCost ?? 0;
        costByResourceId.set(key, (costByResourceId.get(key) || 0) + val);
        totalCost += val;
      }
    });
    
    // For historical periods, use monthlyCosts
    const useMonthly = (period === "6m" || period === "12m" || period === "prev-month");
    if (useMonthly) {
      totalCost = calculateMonthlyCostsTotal(data, selection);
    }
    
    // Count resources with costs
    const resourcesWithCost = filteredResources.filter(r => 
      costByResourceId.has(r.id?.toLowerCase())
    ).length;
    
    // Unique resource types
    const resourceTypes = new Set(filteredResources.map(r => r.type?.split("/").pop() || "Unknown"));
    
    // Unique subscriptions
    const subscriptions = new Set(filteredResources.map(r => r.subscriptionId));
    
    const periodLabel = period === "mtd" ? "MTD" : 
                        period === "prev-month" ? "Previous Month" :
                        period === "6m" ? "Last 6 Months" : 
                        period === "12m" ? "Last 12 Months" : "Period";
    
    dom.resourcesKpis.innerHTML = `
      <div class="kpi">
        <div class="label">Total Resources</div>
        <div class="value">${formatNumber(filteredResources.length)}</div>
        <div class="delta muted">Across ${subscriptions.size} subscription(s)</div>
      </div>
      <div class="kpi">
        <div class="label">Resource Types</div>
        <div class="value">${formatNumber(resourceTypes.size)}</div>
        <div class="delta muted">Unique Azure resource types</div>
      </div>
      <div class="kpi">
        <div class="label">Resources with Cost</div>
        <div class="value">${formatNumber(resourcesWithCost)}</div>
        <div class="delta muted">${formatPercent((resourcesWithCost / filteredResources.length) * 100 || 0)} of inventory</div>
      </div>
      <div class="kpi">
        <div class="label">${periodLabel} Spend</div>
        <div class="value">${formatCurrency(totalCost)}</div>
        <div class="delta muted">Azure consumption costs</div>
      </div>
    `;
  }

  function renderResourcesCharts(data, selection) {
    const resources = data.resources || [];
    const costs = filterCostRows(data, selection);
    const period = selection.period;
    
    // For historical periods, use monthlyCosts
    const useMonthly = (period === "6m" || period === "12m" || period === "prev-month");
    
    // Build cost lookup
    const costByResourceId = new Map();
    costs.forEach(c => {
      if (c.resourceId) {
        const key = c.resourceId.toLowerCase();
        costByResourceId.set(key, (costByResourceId.get(key) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
      }
    });
    
    // Chart 1: Cost by Brand
    const ctxBrand = document.getElementById("resource-brand-chart");
    if (ctxBrand) {
      const byBrand = new Map();
      
      if (useMonthly) {
        // Use monthlyCosts for brand breakdown
        const monthlyCosts = data.monthlyCosts || {};
        const tenants = data.tenants || [];
        const range = computeFilterRange(selection.period);
        const fromMonth = range ? `${range.from.getUTCFullYear()}-${String(range.from.getUTCMonth() + 1).padStart(2, '0')}` : "";
        const toMonth = range ? `${range.to.getUTCFullYear()}-${String(range.to.getUTCMonth() + 1).padStart(2, '0')}` : "";
        
        // Map subscriptions to tenants
        const subToTenant = new Map();
        tenants.forEach(t => {
          (t.subscriptions || []).forEach(s => {
            subToTenant.set(s.subscriptionId, t.name || t.tenantId);
          });
        });
        
        Object.entries(monthlyCosts).forEach(([subId, subData]) => {
          const tenantName = subToTenant.get(subId) || "Unknown";
          const shortName = tenantName
            .replace("Head to Toe Brands (anchor)", "HTT Brands")
            .replace("The Lash Lounge", "TLL")
            .replace("Frenchies", "FN")
            .replace("Bishops", "BCC");
          
          (subData.months || []).forEach(m => {
            if ((!fromMonth || m.month >= fromMonth) && (!toMonth || m.month <= toMonth)) {
              byBrand.set(shortName, (byBrand.get(shortName) || 0) + (m.total || 0));
            }
          });
        });
      } else {
        // Use resources with costs
        resources.forEach(r => {
          const cost = costByResourceId.get(r.id?.toLowerCase()) || 0;
          if (cost > 0) {
            const shortName = (r.tenantName || "Unknown")
              .replace("Head to Toe Brands (anchor)", "HTT Brands")
              .replace("The Lash Lounge", "TLL")
              .replace("Frenchies", "FN")
              .replace("Bishops", "BCC");
            byBrand.set(shortName, (byBrand.get(shortName) || 0) + cost);
          }
        });
      }
      
      const brandData = Array.from(byBrand.entries()).sort((a, b) => b[1] - a[1]);
      
      if (charts.resourceBrand) charts.resourceBrand.destroy();
      charts.resourceBrand = new Chart(ctxBrand, {
        type: "doughnut",
        data: {
          labels: brandData.map(b => b[0]),
          datasets: [{
            data: brandData.map(b => b[1]),
            backgroundColor: ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6"],
            borderColor: "#111827",
            borderWidth: 2,
          }],
        },
        options: {
          plugins: { 
            legend: { position: "right", labels: { color: "#9ca3af" } },
          },
        },
      });
    }
    
    // Chart 2: Cost by Business Function
    const ctxFunction = document.getElementById("resource-function-chart");
    if (ctxFunction) {
      const byFunction = new Map();
      
      resources.forEach(r => {
        const cost = costByResourceId.get(r.id?.toLowerCase()) || 0;
        if (cost > 0) {
          const desc = getResourceDescription(r.name);
          const func = desc.function || desc.initiative || "Unclassified";
          byFunction.set(func, (byFunction.get(func) || 0) + cost);
        }
      });
      
      const funcData = Array.from(byFunction.entries()).sort((a, b) => b[1] - a[1]).slice(0, 8);
      
      if (charts.resourceFunction) charts.resourceFunction.destroy();
      charts.resourceFunction = new Chart(ctxFunction, {
        type: "bar",
        data: {
          labels: funcData.map(f => f[0]),
          datasets: [{
            data: funcData.map(f => f[1]),
            backgroundColor: "#8b5cf6",
          }],
        },
        options: {
          indexAxis: "y",
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: "#1f2937" }, ticks: { color: "#9ca3af" } },
            y: { grid: { display: false }, ticks: { color: "#9ca3af" } },
          },
        },
      });
    }
    
    // Chart 3: YTD Monthly Trend by Brand (stacked bar)
    const ctxYtd = document.getElementById("resource-ytd-chart");
    if (ctxYtd && data.monthlyCosts) {
      const monthlyCosts = data.monthlyCosts || {};
      const tenants = data.tenants || [];
      
      // Map subscriptions to tenants
      const subToTenant = new Map();
      tenants.forEach(t => {
        (t.subscriptions || []).forEach(s => {
          const shortName = (t.tenantName || t.name || "Unknown")
            .replace("Head to Toe Brands (anchor)", "HTT Brands")
            .replace("The Lash Lounge", "TLL")
            .replace("Frenchies", "FN")
            .replace("Bishops", "BCC");
          subToTenant.set(s.subscriptionId, shortName);
        });
      });
      
      // Build monthly data by brand
      const allMonths = new Set();
      const brandMonths = new Map(); // brand -> month -> cost
      
      Object.entries(monthlyCosts).forEach(([subId, subData]) => {
        const brand = subToTenant.get(subId) || "Unknown";
        
        // Apply tenant filter if set
        if (selection.tenant) {
          const tenant = tenants.find(t => 
            (t.subscriptions || []).some(s => s.subscriptionId === subId)
          );
          if (tenant && tenant.tenantId !== selection.tenant) return;
        }
        
        if (!brandMonths.has(brand)) brandMonths.set(brand, new Map());
        const bm = brandMonths.get(brand);
        
        (subData.months || []).forEach(m => {
          allMonths.add(m.month);
          bm.set(m.month, (bm.get(m.month) || 0) + (m.total || 0));
        });
      });
      
      // Sort months and get last 12 for YTD view
      const sortedMonths = Array.from(allMonths).sort().slice(-12);
      
      // Brand colors
      const brandColors = {
        "HTT Brands": "#3b82f6",
        "BCC": "#8b5cf6",
        "TLL": "#f59e0b",
        "FN": "#10b981",
        "Unknown": "#6b7280"
      };
      
      // Build datasets per brand
      const datasets = Array.from(brandMonths.entries()).map(([brand, monthMap]) => ({
        label: brand,
        data: sortedMonths.map(m => monthMap.get(m) || 0),
        backgroundColor: brandColors[brand] || "#6b7280",
        stack: "brands",
      }));
      
      // Add cumulative line
      const monthlyTotals = sortedMonths.map(m => {
        let sum = 0;
        brandMonths.forEach(bm => { sum += bm.get(m) || 0; });
        return sum;
      });
      let cumulative = 0;
      const cumulativeData = monthlyTotals.map(v => cumulative += v);
      
      datasets.push({
        label: "YTD Cumulative",
        data: cumulativeData,
        borderColor: "#ef4444",
        backgroundColor: "transparent",
        borderDash: [5, 5],
        borderWidth: 2,
        type: "line",
        tension: 0.4,
        yAxisID: "y1",
      });
      
      if (charts.resourceYtd) charts.resourceYtd.destroy();
      charts.resourceYtd = new Chart(ctxYtd, {
        type: "bar",
        data: {
          labels: sortedMonths.map(m => {
            const d = new Date(m + "-01");
            return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
          }),
          datasets,
        },
        options: {
          plugins: { 
            legend: { position: "top", labels: { color: "#9ca3af" } },
            title: { 
              display: true, 
              text: selection.tenant ? "Filtered by selected tenant" : "All Brands - YTD Monthly Spend",
              color: "#9ca3af"
            }
          },
          scales: {
            y: { 
              stacked: true,
              grid: { color: "#1f2937" }, 
              ticks: { 
                color: "#9ca3af",
                callback: v => "$" + v.toLocaleString()
              }
            },
            y1: {
              position: "right",
              grid: { display: false },
              ticks: { 
                color: "#ef4444",
                callback: v => "$" + v.toLocaleString()
              },
            },
            x: { 
              stacked: true,
              grid: { display: false }, 
              ticks: { color: "#9ca3af" } 
            },
          },
        },
      });
    }
  }

  function renderCostBreakdown(data, selection) {
    const costs = filterCostRows(data, selection);

    if (costs.length === 0) {
      dom.costBreakdownTable.innerHTML = `
        <tr><td colspan="7" class="empty-state">
          No cost data for the selected period. Try a different time range.
        </td></tr>
      `;
      return;
    }

    // Aggregate by tenant/subscription/rg/service
    const grouped = new Map();
    costs.forEach(c => {
      const key = `${c.tenantId}|${c.subscriptionId}|${c.resourceGroup || ""}|${c.serviceName || ""}`;
      const current = grouped.get(key) || {
        tenantName: c.tenantName,
        subscriptionName: c.subscriptionName,
        resourceGroup: c.resourceGroup,
        serviceName: c.serviceName,
        meterCategory: c.meterCategory,
        dailyCost: 0,
        mtdCost: 0,
      };
      if (c.dailyCost) current.dailyCost += c.dailyCost;
      if (c.mtdCost) current.mtdCost += c.mtdCost;
      grouped.set(key, current);
    });

    const rows = Array.from(grouped.values()).sort((a, b) => 
      (b.dailyCost + b.mtdCost) - (a.dailyCost + a.mtdCost)
    );

    dom.costBreakdownTable.innerHTML = rows.slice(0, 50).map(r => `
      <tr>
        <td>${r.tenantName || "-"}</td>
        <td>${r.subscriptionName || "-"}</td>
        <td>${r.resourceGroup || "-"}</td>
        <td>${r.serviceName || "-"}</td>
        <td>${r.meterCategory || "-"}</td>
        <td class="num">${formatCurrency(r.dailyCost)}</td>
        <td class="num">${formatCurrency(r.mtdCost)}</td>
      </tr>
    `).join("");

    // Apply table enhancements
    const costTableEl = dom.costBreakdownTable.closest('table');
    if (costTableEl) {
      window.DashboardUtils.enableTableSearch(costTableEl, ['serviceName', 'resourceGroup', 'meterCategory']);
      window.DashboardUtils.enableTableSort(costTableEl);
      window.DashboardUtils.makeTableResponsive(costTableEl);
      window.DashboardUtils.addExportButton(costTableEl, 'cost-breakdown');
      window.DashboardUtils.enhanceTableAccessibility(costTableEl, 'Cost breakdown by service table');
      window.DashboardUtils.enableKeyboardNavigation(costTableEl);
    }
  }

  function renderAzureInsights(data, selection) {
    if (!dom.azureInsights) return;
    const insights = [];
    const costs = filterCostRows(data, selection);
    const totalCost = costs.reduce((sum, r) => sum + (r.dailyCost ?? r.mtdCost ?? 0), 0) || calculateMonthlyCostsTotal(data, selection);

    // Idle/zero-cost resources in the selected period
    const resources = (data.resources || []).filter(r => {
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });
    const costResourceIds = new Set(costs.filter(c => c.resourceId && (c.dailyCost || c.mtdCost)).map(c => c.resourceId.toLowerCase()));
    const idleCount = resources.filter(r => !costResourceIds.has((r.id || "").toLowerCase())).length;
    if (idleCount > 0) {
      insights.push({
        title: `${idleCount} resources with no spend in period`,
        meta: "Review for deallocation or rightsizing",
        badge: "Optimization",
      });
    }
    
    // VM cost analysis - flag always-running VMs (especially in dev subscriptions)
    const vmCosts = costs.filter(c => 
      c.serviceName?.toLowerCase().includes('virtual machine') ||
      c.meterCategory?.toLowerCase().includes('virtual machine')
    );
    if (vmCosts.length > 0) {
      // Aggregate VM costs by resource
      const vmByResource = new Map();
      vmCosts.forEach(c => {
        const name = c.resourceId?.split('/').pop() || 'Unknown';
        const isDevTest = c.subscriptionName?.toLowerCase().includes('dev') || 
                         c.subscriptionName?.toLowerCase().includes('test');
        const existing = vmByResource.get(name) || { cost: 0, isDevTest, subscription: c.subscriptionName };
        existing.cost += c.dailyCost ?? c.mtdCost ?? 0;
        vmByResource.set(name, existing);
      });
      
      // Flag expensive VMs, especially in dev/test
      const expensiveVms = Array.from(vmByResource.entries())
        .filter(([_, data]) => data.cost > 50)
        .sort((a, b) => b[1].cost - a[1].cost);
      
      if (expensiveVms.length > 0) {
        const devTestVms = expensiveVms.filter(([_, d]) => d.isDevTest);
        if (devTestVms.length > 0) {
          const [vmName, vmData] = devTestVms[0];
          insights.push({
            title: `VM "${vmName}" running in Dev/Test: ${formatCurrency(vmData.cost)}`,
            meta: `⚠️ Consider auto-shutdown schedule or Reserved Instance — ${vmData.subscription}`,
            badge: "VM Savings",
          });
        } else {
          const [vmName, vmData] = expensiveVms[0];
          insights.push({
            title: `Top VM spend: "${vmName}" — ${formatCurrency(vmData.cost)}`,
            meta: "Review sizing and consider Reserved Instances for 1-3 year commitment savings",
            badge: "VM Cost",
          });
        }
      }
    }

    // Untagged resources - hidden cost allocation issue
    const untaggedResources = resources.filter(r => !r.tags || Object.keys(r.tags).length === 0);
    if (untaggedResources.length > 0) {
      const untaggedPct = (untaggedResources.length / resources.length * 100).toFixed(0);
      if (untaggedResources.length >= 5 || parseInt(untaggedPct) >= 20) {
        insights.push({
          title: `${untaggedResources.length} untagged resources (${untaggedPct}%)`,
          meta: "Tag resources for cost attribution and governance",
          badge: "Governance",
        });
      }
    }

    // Azure Advisor cost recommendations
    const advisorRecs = (data.advisorRecommendations || []).filter(r => {
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });
    if (advisorRecs.length > 0) {
      // Calculate total potential savings
      let totalSavings = 0;
      let highImpact = 0;
      advisorRecs.forEach(rec => {
        if (rec.impact === 'High') highImpact++;
        const savings = rec.extendedProperties?.annualSavingsAmount || rec.extendedProperties?.savingsAmount;
        if (savings) {
          const amount = parseFloat(savings);
          if (!isNaN(amount)) totalSavings += amount;
        }
      });
      
      const savingsText = totalSavings > 0 
        ? `${formatCurrency(totalSavings)} potential annual savings`
        : `${advisorRecs.length} optimization opportunities`;
      
      insights.push({
        title: `Azure Advisor: ${advisorRecs.length} cost recommendations`,
        meta: highImpact > 0 
          ? `⚡ ${highImpact} high-impact — ${savingsText}`
          : savingsText,
        badge: highImpact > 0 ? "High Impact" : "Advisor",
      });
    }

    // Service concentration
    const serviceTotals = new Map();
    costs.forEach(row => {
      const key = row.serviceName || row.meterCategory || "Other";
      const val = row.dailyCost ?? row.mtdCost ?? 0;
      serviceTotals.set(key, (serviceTotals.get(key) || 0) + val);
    });
    if (serviceTotals.size > 0 && totalCost > 0) {
      const sorted = [...serviceTotals.entries()].sort((a, b) => b[1] - a[1]);
      const [topService, topVal] = sorted[0];
      const share = topVal / totalCost;
      if (share >= 0.6) {
        insights.push({
          title: `${topService} is ${formatPercent(share * 100)} of spend`,
          meta: "Validate SKU/size; consider commitment discounts",
          badge: "Concentration",
        });
      }
    }

    // Expiring service principal credentials
    const sps = data.servicePrincipals || {};
    const now = new Date();
    const thirtyDays = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    const expiringCredentials = [];
    Object.entries(sps).forEach(([tenantId, spList]) => {
      (spList || []).forEach(sp => {
        (sp.credentials || []).forEach(cred => {
          if (cred.endDateTime) {
            const endDate = new Date(cred.endDateTime);
            if (endDate > now && endDate < thirtyDays) {
              expiringCredentials.push({
                spName: sp.displayName,
                credType: cred.type,
                daysRemaining: Math.ceil((endDate - now) / 86400000)
              });
            }
          }
        });
      });
    });
    if (expiringCredentials.length > 0) {
      const urgentCount = expiringCredentials.filter(c => c.daysRemaining <= 7).length;
      insights.push({
        title: `${expiringCredentials.length} credential${expiringCredentials.length > 1 ? 's' : ''} expiring in 30 days`,
        meta: urgentCount > 0 ? `⚠️ ${urgentCount} expire within 7 days - rotate immediately` : "Schedule credential rotation",
        badge: urgentCount > 0 ? "Urgent" : "Security",
      });
    }

    // MoM anomaly using monthly totals
    const series = getMonthlyTotals(data, selection, { limitToRange: false });
    if (series.length >= 2) {
      const latest = series[series.length - 1][1];
      const prev = series[series.length - 2][1] || 0;
      if (prev > 0) {
        const deltaPct = (latest - prev) / prev;
        if (Math.abs(deltaPct) >= 0.3) {
          insights.push({
            title: `Spend ${deltaPct >= 0 ? "up" : "down"} ${formatPercent(deltaPct * 100)} MoM`,
            meta: `Latest ${formatCurrency(latest)} vs ${formatCurrency(prev)} prior month`,
            badge: "Anomaly",
          });
        }
      }
    }

    // Zero-cost with resources present
    if (totalCost === 0 && resources.length > 0) {
      insights.push({
        title: "Resources present but zero spend",
        meta: "Confirm metering; check tags/reader access",
        badge: "Data Check",
      });
    }

    dom.azureInsights.innerHTML = insights.length ? insights.map(i => {
      // Map badge types to CSS classes
      const badgeClass = getBadgeClass(i.badge);
      return `
      <li>
        <div class="insight-title">${i.title}</div>
        <div class="insight-meta">${i.meta}</div>
        <div class="insight-badge ${badgeClass}">${i.badge}</div>
      </li>
    `;
    }).join("") : `<li class="muted">No optimization flags for the current filters.</li>`;
  }

  // Helper function to get CSS class for insight badges
  function getBadgeClass(badge) {
    switch (badge) {
      case 'Urgent': return 'danger';
      case 'High Impact': return 'high-impact';
      case 'Advisor': return 'advisor';
      case 'Security': return 'security';
      case 'Governance': return 'governance';
      default: return '';
    }
  }

  function renderLicenseInsights(data, selection) {
    if (!dom.licenseInsights) return;
    const insights = [];
    const licenses = filterLicenses(data, selection);

    // Underutilized SKUs (prepaid vs consumed)
    licenses.forEach(l => {
      (l.subscribedSkus || []).forEach(sku => {
        const prepaid = (sku.prepaidUnits && (sku.prepaidUnits.enabled || 0)) || 0;
        const consumed = sku.consumedUnits || 0;
        if (prepaid > 0) {
          const util = consumed / prepaid;
          if (util < 0.7 && prepaid >= 5) {
            const unusedCount = prepaid - consumed;
            const pricePerLicense = getSkuPrice(sku.skuPartNumber) || 0;
            const monthlySavings = unusedCount * pricePerLicense;
            insights.push({
              title: `${sku.skuPartNumber}: ${formatPercent(util * 100)} utilized (${formatNumber(consumed)}/${formatNumber(prepaid)})`,
              meta: monthlySavings > 0 
                ? `${l.tenantName || "Tenant"} — potential savings: ${formatCurrency(monthlySavings)}/mo` 
                : `${l.tenantName || "Tenant"} — consider downsizing or reallocating`,
              badge: "Low Utilization",
            });
          }
        }
      });
    });

    // Build user lookup for last sign-in
    const usersByTenant = data.users || {};
    const paidSkuCache = new Map();
    function isPaidSkuFast(partNumber) {
      if (paidSkuCache.has(partNumber)) return paidSkuCache.get(partNumber);
      const val = isPaidSku(partNumber);
      paidSkuCache.set(partNumber, val);
      return val;
    }

    // Inactive paid users & redundant assignments - with cost estimation
    let inactivePaid = 0;
    let redundant = 0;
    let inactiveWasteCost = 0;
    const staleThresholdDays = 30; // Flag users inactive 30+ days as waste
    const now = new Date();

    licenses.forEach(l => {
      const tenantUsers = usersByTenant[l.tenantId] || [];
      const userLast = new Map();
      tenantUsers.forEach(u => {
        userLast.set(u.id, parseDate(u.lastSignInDateTime));
      });

      (l.userAssignments || []).forEach(assign => {
        const paidSkus = (assign.skuIds || []).filter(id => {
          const skuMeta = (l.subscribedSkus || []).find(s => s.skuId === id);
          return isPaidSkuFast(skuMeta?.skuPartNumber);
        });
        if (paidSkus.length > 1) redundant += 1;

        if (paidSkus.length > 0) {
          const last = userLast.get(assign.userId);
          const diffDays = last ? Math.floor((now - last) / 86400000) : Infinity;
          if (diffDays >= staleThresholdDays) {
            inactivePaid += 1;
            // Estimate waste cost for this user's licenses
            paidSkus.forEach(skuId => {
              const skuMeta = (l.subscribedSkus || []).find(s => s.skuId === skuId);
              if (skuMeta) {
                const price = getSkuPrice(skuMeta.skuPartNumber) || 0;
                inactiveWasteCost += price;
              }
            });
          }
        }
      });
    });

    if (inactivePaid > 0) {
      insights.push({
        title: `${formatNumber(inactivePaid)} users with paid licenses inactive ${staleThresholdDays}+ days`,
        meta: inactiveWasteCost > 0 
          ? `💰 Est. waste: ${formatCurrency(inactiveWasteCost)}/mo (${formatCurrency(inactiveWasteCost * 12)}/yr) — reclaim or downgrade`
          : "Reclaim or downgrade to free SKUs",
        badge: "Inactive",
      });
    }
    if (redundant > 0) {
      insights.push({
        title: `${formatNumber(redundant)} users with overlapping paid SKUs`,
        meta: "Remove redundant assignments to cut cost",
        badge: "Redundant",
      });
    }

    // Unassigned prepaid pools - with cost estimation
    licenses.forEach(l => {
      (l.subscribedSkus || []).forEach(sku => {
        const prepaid = (sku.prepaidUnits && (sku.prepaidUnits.enabled || 0)) || 0;
        const available = (sku.prepaidUnits && (sku.prepaidUnits.enabled || 0)) - (sku.consumedUnits || 0);
        if (prepaid > 0 && available > 0 && isPaidSkuFast(sku.skuPartNumber)) {
          if (available >= Math.max(5, prepaid * 0.1)) {
            const pricePerLicense = getSkuPrice(sku.skuPartNumber) || 0;
            const monthlySavings = available * pricePerLicense;
            insights.push({
              title: `${sku.skuPartNumber}: ${formatNumber(available)} of ${formatNumber(prepaid)} unused`,
              meta: monthlySavings > 0
                ? `${l.tenantName || "Tenant"} — save ${formatCurrency(monthlySavings)}/mo at renewal`
                : `${l.tenantName || "Tenant"} — rebalance or reduce quantity at renewal`,
              badge: "Unused",
            });
          }
        }
      });
    });

    dom.licenseInsights.innerHTML = insights.length ? insights.map(i => {
      const badgeClass = getBadgeClass(i.badge);
      return `
      <li>
        <div class="insight-title">${i.title}</div>
        <div class="insight-meta">${i.meta}</div>
        <div class="insight-badge ${badgeClass}">${i.badge}</div>
      </li>
    `;
    }).join("") : `<li class="muted">No license optimization flags for the current filters.</li>`;
  }

  // List of free SKU part numbers (licenses that don't cost money)
  // ===== License SKU Classifications =====
  // Free SKUs - these have massive prepaid pools that skew utilization
  const FREE_SKUS = new Set([
    'FLOW_FREE', 'POWERAPPS_VIRAL', 'POWERAPPS_DEV', 'STREAM', 'POWER_BI_STANDARD',
    'TEAMS_EXPLORATORY', 'MICROSOFT_TEAMS_EXPLORATORY_DEPT', 'WINDOWS_STORE', 
    'MICROSOFT_BUSINESS_CENTER', 'CCIBOTS_PRIVPREV_VIRAL', 'RIGHTSMANAGEMENT_ADHOC', 
    'FORMS_PRO', 'MCOPSTNC', 'POWER_PAGES_VTRIAL_FOR_MAKERS',
    'DYN365_ENTERPRISE_VIRTUAL_AGENT_VIRAL', 'DYN365_CDS_VIRAL', 
    'DYNAMICS_365_ONBOARDING_SKU', 'SHAREPOINTSTORAGE'
  ]);

  function isPaidSku(skuPartNumber) {
    if (!skuPartNumber) return false;
    const upper = skuPartNumber.toUpperCase();
    // Free indicators
    if (upper.includes('FREE') || upper.includes('VIRAL') || upper.includes('TRIAL')) return false;
    // Check explicit free list
    if (FREE_SKUS.has(upper)) return false;
    return true;
  }

  // ===== Recommendations Rendering =====
  function renderRecommendations(data, selection) {
    const recommendations = generateRecommendations(data, selection);
    
    // Update badge counts
    const totalCount = recommendations.length;
    const recommendationsCountBadge = document.getElementById('recommendations-count');
    const mobileRecommendationsBadge = document.getElementById('mobile-recommendations-badge');
    
    if (recommendationsCountBadge) {
      recommendationsCountBadge.textContent = totalCount;
      recommendationsCountBadge.style.display = totalCount > 0 ? '' : 'none';
    }
    if (mobileRecommendationsBadge) {
      mobileRecommendationsBadge.textContent = totalCount;
      mobileRecommendationsBadge.style.display = totalCount > 0 ? '' : 'none';
    }

    // Show/hide waste alert banner
    const wasteAlert = document.getElementById('waste-alert');
    const wasteAlertTitle = document.getElementById('waste-alert-title');
    const wasteAlertMessage = document.getElementById('waste-alert-message');
    
    if (wasteAlert && totalCount > 0) {
      const totalSavings = recommendations.reduce((sum, r) => sum + (r.savings || 0), 0);
      wasteAlert.classList.remove('hidden');
      if (wasteAlertTitle) {
        wasteAlertTitle.textContent = `${totalCount} Cost Optimization Opportunit${totalCount === 1 ? 'y' : 'ies'} Detected`;
      }
      if (wasteAlertMessage) {
        wasteAlertMessage.textContent = `Potential savings of ${formatCurrency(totalSavings)}/month identified. Review and take action below.`;
      }
    } else if (wasteAlert) {
      wasteAlert.classList.add('hidden');
    }

    // Render KPIs
    const criticalCount = recommendations.filter(r => r.priority === 'critical').length;
    const highValueCount = recommendations.filter(r => r.priority === 'high-value').length;
    const quickWinsCount = recommendations.filter(r => r.priority === 'quick-win').length;
    const totalSavings = recommendations.reduce((sum, r) => sum + (r.savings || 0), 0);

    const recommendationsKpis = document.getElementById('recommendations-kpis');
    if (recommendationsKpis) {
      recommendationsKpis.innerHTML = `
        <div class="kpi">
          <div class="label">Total Opportunities</div>
          <div class="value ${totalCount > 0 ? 'warning' : 'success'}">${totalCount}</div>
          <div class="delta muted">${criticalCount} critical · ${highValueCount} high-value</div>
        </div>
        <div class="kpi">
          <div class="label">Potential Monthly Savings</div>
          <div class="value success">${formatCurrency(totalSavings)}</div>
          <div class="delta muted">${formatCurrency(totalSavings * 12)}/year</div>
        </div>
        <div class="kpi">
          <div class="label">Quick Wins</div>
          <div class="value info">${quickWinsCount}</div>
          <div class="delta muted">Easy optimizations</div>
        </div>
        <div class="kpi">
          <div class="label">Avg. Savings per Action</div>
          <div class="value">${totalCount > 0 ? formatCurrency(totalSavings / totalCount) : '$0.00'}</div>
          <div class="delta muted">Per recommendation</div>
        </div>
      `;
    }

    // Render categorized lists
    const critical = recommendations.filter(r => r.priority === 'critical');
    const highValue = recommendations.filter(r => r.priority === 'high-value');
    const quickWins = recommendations.filter(r => r.priority === 'quick-win');

    const criticalList = document.getElementById('critical-recommendations');
    const highValueList = document.getElementById('high-value-recommendations');
    const quickWinsList = document.getElementById('quick-wins-recommendations');

    if (criticalList) {
      criticalList.innerHTML = critical.length ? critical.slice(0, 5).map(renderRecommendationItem).join('') : 
        '<li class="muted" style="list-style: none;">No critical items at this time. Great work!</li>';
    }
    
    if (highValueList) {
      highValueList.innerHTML = highValue.length ? highValue.slice(0, 5).map(renderRecommendationItem).join('') :
        '<li class=\"muted\" style=\"list-style: none;\">No high-value optimizations available.</li>';
    }
    
    if (quickWinsList) {
      quickWinsList.innerHTML = quickWins.length ? quickWins.slice(0, 5).map(renderRecommendationItem).join('') :
        '<li class=\"muted\" style=\"list-style: none;\">No quick wins identified.</li>';
    }

    // Render full table
    const recommendationsTable = document.querySelector('#recommendations-table tbody');
    if (recommendationsTable) {
      if (recommendations.length === 0) {
        recommendationsTable.innerHTML = `
          <tr><td colspan="7" style="text-align: center; padding: 40px; color: var(--muted);">
            ✅ All clear! No optimization opportunities detected at this time.
          </td></tr>
        `;
      } else {
        recommendationsTable.innerHTML = recommendations.map(r => `
          <tr>
            <td><span class="badge ${getPriorityClass(r.priority)}">${r.priority.replace('-', ' ')}</span></td>
            <td>${r.category}</td>
            <td>${r.title}</td>
            <td>${r.impact}</td>
            <td class="num">${r.savings > 0 ? formatCurrency(r.savings) + '/mo' : 'N/A'}</td>
            <td>${r.effort}</td>
            <td><button class="btn primary small" onclick="alert('Action: ${r.action}')">Take Action</button></td>
          </tr>
        `).join('');
      }
      
      // Apply table enhancements
      const table = document.getElementById('recommendations-table');
      if (table && window.DashboardUtils) {
        window.DashboardUtils.enableTableSearch(table);
        window.DashboardUtils.enableTableSort(table);
        window.DashboardUtils.makeTableResponsive(table);
        window.DashboardUtils.addExportButton(table, 'recommendations');
        window.DashboardUtils.enhanceTableAccessibility(table, 'Cost Optimization Recommendations');
        window.DashboardUtils.enableKeyboardNavigation(table);
      }
    }
  }

  function renderRecommendationItem(r) {
    return `
      <li>
        <span class="recommendation-icon">${r.icon}</span>
        <div class="recommendation-content">
          <div class="recommendation-title">${r.title}</div>
          <div class="recommendation-desc">${r.description}</div>
          <div class="recommendation-meta">
            <span class="meta-item">💰 <strong>${r.savings > 0 ? formatCurrency(r.savings) + '/mo' : 'TBD'}</strong></span>
            <span class="meta-item">⚡ <strong>${r.effort}</strong> effort</span>
            <span class="meta-item">📈 <strong>${r.impact}</strong> impact</span>
          </div>
          <div class="recommendation-actions">
            <button class="btn primary" onclick="alert('Action: ${r.action}')">Take Action</button>
            <button class="btn ghost" onclick="alert('Details: ${r.description}')">View Details</button>
          </div>
        </div>
      </li>
    `;
  }

  function getPriorityClass(priority) {
    switch(priority) {
      case 'critical': return 'danger';
      case 'high-value': return 'warning';
      case 'quick-win': return 'success';
      default: return '';
    }
  }

  function generateRecommendations(data, selection) {
    const recommendations = [];
    
    // Analyze Azure costs
    const costs = filterCostRows(data, selection);
    const resources = (data.resources || []).filter(r => {
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });
    
    // Idle resources (resources with no cost data)
    const costResourceIds = new Set(costs.filter(c => c.resourceId).map(c => c.resourceId.toLowerCase()));
    const idleResources = resources.filter(r => !costResourceIds.has((r.id || '').toLowerCase()));
    
    if (idleResources.length > 0) {
      recommendations.push({
        priority: 'critical',
        category: 'Azure Resources',
        title: `${idleResources.length} idle resources with $0 spend`,
        description: `Found ${idleResources.length} deployed resources generating zero cost. Review for deletion or deallocation.`,
        impact: 'Medium-High',
        savings: 0, // Can't estimate without historical data
        effort: 'Low',
        action: 'Review idle resources list and delete or deallocate unused resources',
        icon: '🗑️'
      });
    }

    // Untagged resources
    const untaggedResources = resources.filter(r => !r.tags || Object.keys(r.tags).length === 0);
    if (untaggedResources.length > 0) {
      const untaggedCost = costs
        .filter(c => c.resourceId && untaggedResources.find(r => r.id?.toLowerCase() === c.resourceId.toLowerCase()))
        .reduce((sum, c) => sum + (c.dailyCost || c.mtdCost || 0), 0);
      
      recommendations.push({
        priority: 'high-value',
        category: 'Governance',
        title: `${untaggedResources.length} resources without tags`,
        description: `Untagged resources worth ${formatCurrency(untaggedCost)}/mo make cost allocation difficult.`,
        impact: 'Medium',
        savings: 0,
        effort: 'Medium',
        action: 'Implement tagging policy and tag all resources with cost center, environment, owner',
        icon: '🏷️'
      });
    }

    // Analyze licenses
    const licenses = filterLicenses(data, selection);
    const users = data.users || {};
    
    let inactivePaid = 0;
    let inactiveCost = 0;
    let underutilizedSkus = 0;
    let underutilizedCost = 0;

    licenses.forEach(l => {
      const tenantUsers = users[l.tenantId] || [];
      const inactiveCutoff = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000);
      
      (l.userAssignments || []).forEach(ua => {
        const isPaid = (ua.skus || []).some(s => isPaidSku(s.skuPartNumber));
        if (!isPaid) return;
        
        const user = tenantUsers.find(u => u.userPrincipalName === ua.userPrincipalName || u.mail === ua.userPrincipalName);
        if (user && user.lastSignInDateTime) {
          const lastSignIn = new Date(user.lastSignInDateTime);
          if (lastSignIn < inactiveCutoff) {
            inactivePaid++;
            ua.skus.forEach(s => {
              const price = getSkuPrice(s.skuPartNumber) || 0;
              inactiveCost += price;
            });
          }
        }
      });

      (l.subscribedSkus || l.skuAssignments || []).forEach(sku => {
        const prepaid = sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 0;
        const consumed = sku.consumedUnits || 0;
        const utilization = prepaid > 0 ? consumed / prepaid : 1;
        
        if (utilization < 0.5 && prepaid > 0 && isPaidSku(sku.skuPartNumber)) {
          underutilizedSkus++;
          const price = getSkuPrice(sku.skuPartNumber) || 0;
          const unused = prepaid - consumed;
          underutilizedCost += unused * price;
        }
      });
    });

    if (inactivePaid > 5) {
      recommendations.push({
        priority: 'critical',
        category: 'M365 Licenses',
        title: `${inactivePaid} inactive users with paid licenses`,
        description: `Users who haven't signed in for 90+ days still have active paid licenses costing ${formatCurrency(inactiveCost)}/month.`,
        impact: 'High',
        savings: inactiveCost,
        effort: 'Low',
        action: 'Remove licenses from inactive users or disable accounts',
        icon: '👤'
      });
    }

    if (underutilizedSkus > 0) {
      recommendations.push({
        priority: 'high-value',
        category: 'M365 Licenses',
        title: `${underutilizedSkus} underutilized license SKUs`,
        description: `SKUs with less than 50% utilization represent ${formatCurrency(underutilizedCost)}/mo in waste.`,
        impact: 'Medium-High',
        savings: underutilizedCost,
        effort: 'Medium',
        action: 'Reduce license count at next renewal or redistribute to other tenants',
        icon: '📦'
      });
    }

    // Dev/Test resources in production
    const devTestResources = resources.filter(r => {
      const name = (r.name || '').toLowerCase();
      const rgName = (r.resourceGroup || '').toLowerCase();
      return (name.includes('dev') || name.includes('test') || rgName.includes('dev') || rgName.includes('test')) &&
             r.location !== 'devtest';
    });

    if (devTestResources.length > 5) {
      const devTestCost = costs
        .filter(c => c.resourceId && devTestResources.find(r => r.id?.toLowerCase() === c.resourceId.toLowerCase()))
        .reduce((sum, c) => sum + (c.dailyCost || c.mtdCost || 0), 0);

      if (devTestCost > 100) {
        recommendations.push({
          priority: 'quick-win',
          category: 'Azure Resources',
          title: `${devTestResources.length} dev/test resources at production pricing`,
          description: `Development and test resources costing ${formatCurrency(devTestCost)}/mo not using Dev/Test pricing.`,
          impact: 'Medium',
          savings: devTestCost * 0.4, // Est 40% savings with dev/test pricing
          effort: 'Low',
          action: 'Move to Dev/Test subscription or enable Dev/Test pricing',
          icon: '🧪'
        });
      }
    }

    // Sort by priority (critical > high-value > quick-win) then by savings
    const priorityOrder = { 'critical': 0, 'high-value': 1, 'quick-win': 2 };
    recommendations.sort((a, b) => {
      if (a.priority !== b.priority) {
        return priorityOrder[a.priority] - priorityOrder[b.priority];
      }
      return (b.savings || 0) - (a.savings || 0);
    });

    return recommendations;
  }

  function renderLicenseKpis(data, selection) {
    const licenses = filterLicenses(data, selection);
    
    let totalSkus = 0;
    let paidSkus = 0;
    let freeSkus = 0;
    let totalConsumed = 0;
    let paidConsumed = 0;
    let totalPrepaid = 0;
    let paidPrepaid = 0;
    let totalUsers = 0;

    // Track paid license details for better reporting
    const paidLicenseDetails = [];

    licenses.forEach(l => {
      // Support both skuAssignments (new format) and subscribedSkus (old format)
      const skus = l.skuAssignments || l.subscribedSkus || [];
      skus.forEach(sku => {
        totalSkus++;
        const consumed = sku.consumedUnits || 0;
        const prepaid = sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 0;
        const isPaid = isPaidSku(sku.skuPartNumber);
        
        totalConsumed += consumed;
        totalPrepaid += prepaid;
        
        if (isPaid) {
          paidSkus++;
          paidConsumed += consumed;
          paidPrepaid += prepaid;
          if (consumed > 0) {
            paidLicenseDetails.push({
              tenant: l.tenantName,
              sku: sku.skuPartNumber,
              consumed,
              prepaid
            });
          }
        } else {
          freeSkus++;
        }
      });
      totalUsers += l.userAssignments?.length || 0;
    });

    // Calculate utilization based on PAID licenses only (excluding massive free SKU pools)
    const paidUtilization = paidPrepaid > 0 ? (paidConsumed / paidPrepaid) * 100 : 0;
    
    // Also show what percentage of licenses are actually paid vs free
    const paidRatio = totalSkus > 0 ? (paidSkus / totalSkus) * 100 : 0;

    dom.licenseKpis.innerHTML = `
      <div class="kpi">
        <div class="label">Total License SKUs</div>
        <div class="value">${totalSkus}</div>
        <div class="delta muted">Across ${licenses.length} tenant(s)</div>
      </div>
      <div class="kpi">
        <div class="label">Total Users</div>
        <div class="value">${formatNumber(totalUsers)}</div>
        <div class="delta muted">With license assignments</div>
      </div>
      <div class="kpi">
        <div class="label">Licenses Consumed</div>
        <div class="value">${formatNumber(paidConsumed)}</div>
        <div class="delta muted">of ${formatNumber(paidPrepaid)} paid prepaid</div>
      </div>
      <div class="kpi">
        <div class="label">Paid License Utilization</div>
        <div class="value">${formatPercent(paidUtilization)}</div>
        <div class="delta ${paidUtilization > 90 ? 'danger' : paidUtilization > 70 ? 'warning' : 'success'}">
          ${paidUtilization > 90 ? '⚠️ Near capacity' : paidUtilization > 70 ? '📊 Good usage' : '✓ Healthy'}
        </div>
      </div>
    `;
  }

  function renderLicenseSummaryTable(data, selection) {
    const licenses = filterLicenses(data, selection);

    if (licenses.length === 0) {
      dom.licenseSummaryTable.innerHTML = `<tr><td colspan="7" class="empty-state">No license data</td></tr>`;
      return;
    }

    dom.licenseSummaryTable.innerHTML = licenses.map(l => {
      const skus = l.skuAssignments || l.subscribedSkus || [];
      
      // Split into paid and free for better visibility
      let paidConsumed = 0, paidPrepaid = 0, freeConsumed = 0, freePrepaid = 0;
      let paidSkuCount = 0, freeSkuCount = 0;
      
      skus.forEach(sku => {
        const consumed = sku.consumedUnits || 0;
        const prepaid = sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 0;
        if (isPaidSku(sku.skuPartNumber)) {
          paidConsumed += consumed;
          paidPrepaid += prepaid;
          paidSkuCount++;
        } else {
          freeConsumed += consumed;
          freePrepaid += prepaid;
          freeSkuCount++;
        }
      });
      
      const paidUtilization = paidPrepaid > 0 ? (paidConsumed / paidPrepaid) * 100 : 0;
      const utilClass = paidUtilization > 90 ? 'danger' : paidUtilization > 70 ? 'warning' : '';
      const userCount = l.userAssignments?.length || 0;

      return `
        <tr>
          <td><strong>${l.tenantName}</strong></td>
          <td class="num">${paidSkuCount} <span class="muted">paid</span> / ${freeSkuCount} <span class="muted">free</span></td>
          <td class="num">${formatNumber(userCount)}</td>
          <td class="num">${formatNumber(paidConsumed)} <span class="muted">/ ${formatNumber(paidPrepaid)}</span></td>
          <td>
            <div class="util-bar-container">
              <div class="util-bar">
                <div class="util-bar-fill ${utilClass}" style="width: ${Math.min(paidUtilization, 100)}%"></div>
              </div>
              <span class="util-percent">${formatPercent(paidUtilization)}</span>
            </div>
          </td>
        </tr>
      `;
    }).join("");

    // Apply table enhancements
    const licSumTableEl = dom.licenseSummaryTable.closest('table');
    if (licSumTableEl) {
      window.DashboardUtils.enableTableSearch(licSumTableEl, ['tenantName']);
      window.DashboardUtils.enableTableSort(licSumTableEl);
      window.DashboardUtils.makeTableResponsive(licSumTableEl);
      window.DashboardUtils.addExportButton(licSumTableEl, 'license-summary');
      window.DashboardUtils.enhanceTableAccessibility(licSumTableEl, 'License summary by tenant table');
      window.DashboardUtils.enableKeyboardNavigation(licSumTableEl);
    }
  }

  function renderLicensesTable(data, selection) {
    const licenses = filterLicenses(data, selection);

    const rows = [];
    licenses.forEach(l => {
      const skus = l.skuAssignments || l.subscribedSkus || [];
      skus.forEach(sku => {
        const prepaid = sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 0;
        const consumed = sku.consumedUnits || 0;
        const available = sku.availableUnits || (prepaid - consumed);
        const utilization = prepaid > 0 ? (consumed / prepaid) * 100 : 0;
        const isPaid = isPaidSku(sku.skuPartNumber);

        rows.push({
          tenantName: l.tenantName,
          skuPartNumber: sku.skuPartNumber || sku.skuId,
          status: sku.capabilityStatus || "Unknown",
          prepaid,
          consumed,
          available,
          utilization,
          isPaid,
        });
      });
    });

    if (rows.length === 0) {
      dom.licensesTable.innerHTML = `<tr><td colspan="8" class="empty-state">No license SKUs found</td></tr>`;
      return;
    }

    const rendered = rows.sort((a, b) => {
      // Sort paid SKUs first, then by consumed
      if (a.isPaid !== b.isPaid) return b.isPaid ? 1 : -1;
      return b.consumed - a.consumed;
    }).map(r => {
      const utilClass = r.utilization > 90 ? 'danger' : r.utilization > 70 ? 'warning' : '';
      const typeClass = r.isPaid ? 'paid' : 'free';
      const typeLabel = r.isPaid ? 'Paid' : 'Free';
      return `
        <tr class="${typeClass}-license">
          <td>${r.tenantName}</td>
          <td><strong>${r.skuPartNumber}</strong></td>
          <td><span class="license-type-badge ${typeClass}">${typeLabel}</span></td>
          <td><span class="status-badge ${r.status === 'Enabled' ? 'enabled' : 'warning'}">${r.status}</span></td>
          <td class="num">${formatNumber(r.prepaid)}</td>
          <td class="num">${formatNumber(r.consumed)}</td>
          <td class="num">${formatNumber(r.available)}</td>
          <td>
            <div class="util-bar-container">
              <div class="util-bar">
                <div class="util-bar-fill ${utilClass}" style="width: ${Math.min(r.utilization, 100)}%"></div>
              </div>
              <span class="util-percent">${formatPercent(r.utilization)}</span>
            </div>
          </td>
        </tr>
      `;
    });

    dom.licensesTable.innerHTML = rendered.join("");

    // Apply table enhancements with pagination and unified filters
    const licTableEl = dom.licensesTable.closest('table');
    if (licTableEl) {
      // Create unified filter header (idempotent)
      const filterContainer = window.dashboard.utils.insertTableFilterHeader(licTableEl, {
        searchPlaceholder: 'Search by SKU or tenant...',
        columnSelect: ['SKU', 'Tenant', 'Status'],
        showBrandTabs: true,
        brands: ['All Brands', 'HTT', 'TLL', 'FN', 'BCC']
      });

      // Apply pagination (idempotent)
      window.dashboard.utils.applyTablePagination(licTableEl, 20);

      // Apply brand filtering
      filterContainer.querySelectorAll('.brand-tab').forEach(tab => {
        tab.addEventListener('click', () => {
          filterContainer.querySelectorAll('.brand-tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          window.dashboard.utils.applyBrandFiltering(licTableEl.closest('.table-wrapper') || licTableEl, tab.dataset.brand);
        });
      });

      // Apply unified search
      const searchInput = filterContainer.querySelector('.table-search-unified');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const term = e.target.value.toLowerCase();
          const tbody = licTableEl.querySelector('tbody');
          let visibleCount = 0;
          tbody.querySelectorAll('tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = text.includes(term);
            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
          });
          const resultsSpan = filterContainer.querySelector('.filter-results');
          if (resultsSpan) resultsSpan.textContent = `${visibleCount} of ${tbody.querySelectorAll('tr').length} items`;
        });
      }

      // Keep existing utilities for sorting and export
      DashboardUtils.enableTableSort(licTableEl);
      DashboardUtils.addExportButton(licTableEl, 'license-skus');
      DashboardUtils.enhanceTableAccessibility(licTableEl, 'License SKU details table');
      DashboardUtils.enableKeyboardNavigation(licTableEl);
    }
  }

  // ===== Invoice Reconciliation =====
  // CSP Billing Sources by Tenant (critical for audit tracking)
  const CSP_BILLING_SOURCES = {
    "Head to Toe Brands (anchor)": { 
      csp: "Logically MSP", 
      type: "Azure + M365",
      billingId: "logically",
      contact: "Logically Support",
      notes: "Primary anchor tenant - Azure consumption + M365 licenses via CSP"
    },
    "The Lash Lounge": { 
      csp: "Sui Generis (SG)", 
      type: "M365 Only",
      billingId: "sg",
      contact: "SG CSP Support",
      notes: "M365 licenses only via CSP; Azure direct to Microsoft"
    },
    "Frenchies": { 
      csp: "FTG (Franchise Technology Group)", 
      type: "M365 Only",
      billingId: "ftg",
      contact: "FTG Support",
      notes: "M365 licenses only via CSP; Azure direct to Microsoft"
    },
    "Bishops": { 
      csp: "Direct to Microsoft", 
      type: "Direct MCA",
      billingId: "direct-bcc",
      contact: "Microsoft Billing",
      notes: "Direct Microsoft Customer Agreement - no CSP"
    }
  };

  // =========================================================================
  // COMPREHENSIVE BILLING DATA - All Sources (2025)
  // =========================================================================

  // LOGICALLY MSP INVOICES (HTT Brands - Azure + M365 via CSP)
  // Source: 2025_Azure_M365_LineItems_CORRECTED.csv
  // Note: Invoices are billed 1 month in arrears (April invoice = March usage)
  const LOGICALLY_INVOICES = {
    "2025-03": { 
      azure: 7834.88, 
      m365: 1003.60, 
      fabric: 0, 
      invoiceDate: "2025-04-15", 
      invoiceNum: "1167103",
      managedServices: 3785.25,
      totalInvoice: 12623.73,
      licenseBreakdown: {
        "Business Premium": { qty: 44, price: 22.00, total: 968.00 },
        "Business Basic": { qty: 3, price: 6.00, total: 18.00 },
        "Entra ID P1": { qty: 1, price: 6.00, total: 6.00 },
        "Clipchamp Premium": { qty: 1, price: 11.99, total: 11.99 },
        "SharePoint Admin": { qty: 1, price: 3.00, total: 3.00 }
      },
      notes: "March baseline - NCE usage-based billing"
    },
    "2025-04": {
      azure: 0,
      m365: 1003.60,
      fabric: 0,
      managedServices: 3785.25,
      notes: "No Azure line item - likely reconciled later"
    },
    "2025-05": {
      azure: 0,
      m365: 0,
      fabric: 0,
      credit: 3395.91,
      invoiceDate: "2025-10-15",
      invoiceNum: "1181728",
      notes: "NCE Sync Credit - reconciliation adjustment"
    },
    "2025-06": {
      azure: 0,
      m365: 1003.60,
      fabric: 0,
      managedServices: 3785.25,
      notes: "Standard M365 month"
    },
    "2025-07": {
      azure: 0,
      m365: 1003.60,
      fabric: 0,
      managedServices: 3785.25,
      notes: "Standard M365 month"
    },
    "2025-08": { 
      azure: 9613.05,
      m365: 1003.60, 
      fabric: 0, 
      invoiceDate: "2025-09-17", 
      invoiceNum: "1179516",
      managedServices: 3785.25,
      totalInvoice: 14196.55,
      notes: "⚠️ Up 22.7% from March - investigate spike"
    },
    "2025-09": { 
      azure: 7848.86,
      m365: 1003.60, 
      fabric: 0, 
      invoiceDate: "2025-11-17", 
      invoiceNum: "1183536",
      managedServices: 3785.25,
      notes: "Back to baseline after August spike"
    },
    "2025-10": { 
      azure: 9613.05,
      m365: 1003.60, 
      fabric: 5152.64,  // PRORATED - F64 started Oct 1
      invoiceDate: "2025-10-15", 
      invoiceNum: "1181728",
      managedServices: 3785.25,
      totalInvoice: 15953.28,
      notes: "⚠️ Fabric F64 added - prorated $5,152.64"
    },
    "2025-11": {
      azure: 0,  // Not yet billed
      m365: 1003.60,
      fabric: 3152.64,  // Full month F64 rate
      invoiceDate: "2025-11-17",
      invoiceNum: "1183536",
      managedServices: 3785.25,
      totalInvoice: 7941.49,
      notes: "Fabric F64 full month = $3,152.64 (64 CU)"
    }
  };

  // DIRECT MICROSOFT INVOICES - HTT (Holdco)
  // Source: 35 PDF invoices from Azure Portal (direct-m365/2025_HTT_*.pdf)
  // Billing Account: a9e871fb-0b77-51e6-6b2a-e3855ac0ad2d:026416ac-f0b8-477c-aadc-9f0c4ef9a6e0_2019-05-31
  // DIRECT MICROSOFT INVOICES - HTT (Head to Toe Brands)
  // Source: 35 PDF invoices from Azure Portal (direct-m365/2025_HTT_*.pdf)
  // Extracted via scripts/extract-invoice-amounts.py on 2025-12-04
  // Total: $12,448.02 YTD
  const HTT_DIRECT_INVOICES = {
    "2025-01": { invoices: 2, total: 1036.50, notes: "G071889929 ($436.50), G072799354 ($600.00)" },
    "2025-02": { invoices: 2, total: 1036.50, notes: "G075998976 ($436.50), G076826031 ($600.00)" },
    "2025-03": { invoices: 2, total: 1036.50, notes: "G080379855 ($436.50), G081080344 ($600.00)" },
    "2025-04": { invoices: 3, total: 1080.94, notes: "G084942109 ($436.50), G085175952 ($44.44), G085597019 ($600.00)" },
    "2025-05": { invoices: 4, total: 1036.50, notes: "G089523960 ($0), G089757937 ($436.50), G090208648 ($600.00), G094174126 ($0)" },
    "2025-06": { invoices: 2, total: 1036.50, notes: "G094637608 ($436.50), G095044383 ($600.00)" },
    "2025-07": { invoices: 3, total: 1043.70, notes: "G099705579 ($436.50), G100080945 ($600.00), G101665169 ($7.20)" },
    "2025-08": { invoices: 5, total: 1329.40, notes: "G104928601 ($604.50), G105019156 ($21.70), G105245626 ($600.00), G106934484 ($7.20), G109955429 ($96.00)" },
    "2025-09": { invoices: 3, total: 1379.70, notes: "G110619321 ($772.50), G110876801 ($600.00), G112765398 ($7.20)" },
    "2025-10": { invoices: 4, total: 1227.30, notes: "G116328204 ($616.50), G116510093 ($3.60), G116661347 ($600.00), G118310922 ($7.20)" },
    "2025-11": { invoices: 4, total: 1204.48, notes: "G121625342 ($590.70), G121803798 ($6.58), G122058596 ($600.00), G123701725 ($7.20)" }
  };

  // DIRECT MICROSOFT INVOICES - BCC (Bishops Cuts)
  // Source: 14 PDF invoices from Azure Portal (direct-m365/2025_BCC_*.pdf)
  // Extracted via scripts/extract-invoice-amounts.py on 2025-12-04
  // Total: $747.10 YTD
  const BCC_DIRECT_INVOICES = {
    "2025-01": { invoices: 1, total: 65.70, notes: "G075497271 ($65.70)" },
    "2025-02": { invoices: 1, total: 65.70, notes: "G079878471 ($65.70)" },
    "2025-03": { invoices: 1, total: 65.70, notes: "G084356112 ($65.70)" },
    "2025-04": { invoices: 1, total: 65.70, notes: "G089046540 ($65.70)" },
    "2025-05": { invoices: 1, total: 65.70, notes: "G093881362 ($65.70)" },
    "2025-06": { invoices: 2, total: 108.90, notes: "G096803009 ($43.20), G098986733 ($65.70)" },
    "2025-07": { invoices: 2, total: 108.90, notes: "G101741459 ($43.20), G104041937 ($65.70)" },
    "2025-08": { invoices: 1, total: 36.00, notes: "G107040056 ($36.00)" },
    "2025-09": { invoices: 1, total: 21.60, notes: "G112918119 ($21.60)" },
    "2025-10": { invoices: 1, total: 21.60, notes: "G118519555 ($21.60)" },
    "2025-11": { invoices: 2, total: 121.60, notes: "G123806729 ($21.60), G125802198 ($100.00)" }
  };

  // DIRECT MICROSOFT INVOICES - TLL (The Lash Lounge)
  // Source: 5 PDF invoices from Azure Portal (direct-m365/2025_TLL_*.pdf)
  // Note: M365 user licenses are billed separately through CSP (Sui Generis)
  const TLL_DIRECT_INVOICES = {
    "2025-06": { invoices: 1, total: 100.00, notes: "G098782301 - Azure RI only" },
    "2025-08": { invoices: 1, total: 100.00, notes: "G106437954 - Azure RI" },
    "2025-09": { invoices: 1, total: 100.00, notes: "G111567502 - Azure RI" },
    "2025-10": { invoices: 1, total: 100.00, notes: "G117193365 - Azure RI" },
    "2025-11": { invoices: 1, total: 100.00, notes: "G123234792 - Azure RI" }
  };

  // DIRECT MICROSOFT INVOICES - FN (Frenchies)
  // Source: 4 PDF invoices from Azure Portal (direct-m365/2025_FN_*.pdf)
  // Note: M365 user licenses are billed separately through CSP (FTG)
  const FN_DIRECT_INVOICES = {
    "2025-08": { invoices: 1, total: 0.00, notes: "G106231033 - $0 (free tier)" },
    "2025-09": { invoices: 1, total: 0.00, notes: "G112231900 - $0" },
    "2025-10": { invoices: 1, total: 0.00, notes: "G117864387 - $0" },
    "2025-11": { invoices: 1, total: 0.00, notes: "G122846648 - $0" }
  };

  // CSP INVOICES - Sui Generis (The Lash Lounge M365)
  // Source: Needs to be obtained from Sui Generis CSP
  // Note: These are ESTIMATES based on Graph API license counts
  const SG_CSP_INVOICES = {
    // TLL has approx 15-20 M365 users based on Graph data
    // Estimated at Business Premium ($22/user)
    "2025-01": { m365Est: 350.00, notes: "Est. ~16 users @ $22 - pending CSP invoice" },
    "2025-02": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-03": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-04": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-05": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-06": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-07": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-08": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-09": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-10": { m365Est: 350.00, notes: "Est. - pending CSP invoice" },
    "2025-11": { m365Est: 350.00, notes: "Est. - pending CSP invoice" }
  };

  // CSP INVOICES - FTG (Frenchies M365)
  // Source: Needs to be obtained from FTG CSP
  // Note: These are ESTIMATES based on Graph API license counts
  const FTG_CSP_INVOICES = {
    // Frenchies has approx 8-10 M365 users based on Graph data
    // Estimated at Business Premium ($22/user)
    "2025-01": { m365Est: 200.00, notes: "Est. ~9 users @ $22 - pending CSP invoice" },
    "2025-02": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-03": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-04": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-05": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-06": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-07": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-08": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-09": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-10": { m365Est: 200.00, notes: "Est. - pending CSP invoice" },
    "2025-11": { m365Est: 200.00, notes: "Est. - pending CSP invoice" }
  };

  // Consolidated monthly billing summary (all sources)
  function getConsolidatedBilling() {
    const months = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06", 
                    "2025-07", "2025-08", "2025-09", "2025-10", "2025-11"];
    
    return months.map(month => {
      const logically = LOGICALLY_INVOICES[month] || {};
      const httDirect = HTT_DIRECT_INVOICES[month] || {};
      const bccDirect = BCC_DIRECT_INVOICES[month] || {};
      const tllDirect = TLL_DIRECT_INVOICES[month] || {};
      const fnDirect = FN_DIRECT_INVOICES[month] || {};
      const sgCsp = SG_CSP_INVOICES[month] || {};
      const ftgCsp = FTG_CSP_INVOICES[month] || {};

      return {
        month,
        // HTT via Logically CSP
        httLogicallyAzure: logically.azure || 0,
        httLogicallyM365: logically.m365 || 0,
        httLogicallyFabric: logically.fabric || 0,
        httLogicallyCredit: logically.credit || 0,
        httLogicallyManaged: logically.managedServices || 0,
        // HTT Direct (additional)
        httDirect: httDirect.total || 0,
        // BCC Direct
        bccDirect: bccDirect.total || 0,
        // TLL Direct Azure + CSP M365
        tllDirectAzure: tllDirect.total || 0,
        tllCspM365: sgCsp.m365Est || 0,
        // FN Direct Azure + CSP M365
        fnDirectAzure: fnDirect.total || 0,
        fnCspM365: ftgCsp.m365Est || 0,
        // Totals
        totalAzure: (logically.azure || 0) + (httDirect.total || 0) + (bccDirect.total || 0) + 
                    (tllDirect.total || 0) + (fnDirect.total || 0) - (logically.credit || 0),
        totalM365: (logically.m365 || 0) + (sgCsp.m365Est || 0) + (ftgCsp.m365Est || 0),
        totalFabric: logically.fabric || 0,
        totalManaged: logically.managedServices || 0,
        grandTotal: (logically.azure || 0) + (logically.m365 || 0) + (logically.fabric || 0) + 
                    (logically.managedServices || 0) - (logically.credit || 0) +
                    (httDirect.total || 0) + (bccDirect.total || 0) + 
                    (tllDirect.total || 0) + (fnDirect.total || 0) +
                    (sgCsp.m365Est || 0) + (ftgCsp.m365Est || 0)
      };
    });
  }

  // MSRP pricing for license cost estimates (monthly per-user)
  // Sources: Microsoft 365 pricing page, Azure documentation
  // Note: These are RETAIL prices - CSP/EA pricing may vary
  const SKU_PRICING = {
    // Microsoft 365 Business Plans
    "SPB": 22.00,                                  // Microsoft 365 Business Premium
    "O365_BUSINESS_PREMIUM": 22.00,               // Microsoft 365 Business Premium (alias)
    "O365_BUSINESS_ESSENTIALS": 6.00,             // Microsoft 365 Business Basic
    "STANDARDPACK": 8.00,                          // Office 365 E1
    "ENTERPRISEPACK": 23.00,                       // Office 365 E3
    "Microsoft_365_E5_(no_Teams)": 54.75,          // M365 E5 (no Teams)
    
    // Exchange & Communication
    "EXCHANGESTANDARD": 4.00,                      // Exchange Online Plan 1
    "Microsoft_Teams_Premium": 10.00,              // Teams Premium add-on
    "Microsoft_Teams_Exploratory_Dept": 0,         // Free trial
    "MCOPSTNC": 0,                                 // Communications Credits (usage-based)
    
    // Identity & Security
    "AAD_PREMIUM": 6.00,                           // Entra ID P1
    "SharePoint_advanced_management_plan_1": 3.00, // SharePoint Advanced Management
    
    // Power Platform
    "POWER_BI_PRO": 10.00,                         // Power BI Pro
    "POWER_BI_PRO_DEPT": 10.00,                    // Power BI Pro (department)
    "POWER_BI_STANDARD": 0,                        // Power BI Free
    "POWERAPPS_DEV": 0,                            // Power Apps Developer
    "POWERAPPS_VIRAL": 0,                          // Power Apps Viral (free)
    "Power_Pages_vTrial_for_Makers": 0,            // Power Pages Trial
    "FLOW_FREE": 0,                                // Power Automate Free
    
    // Productivity Add-ons
    "Clipchamp_Premium": 11.99,                    // Clipchamp Premium
    "Clipchamp_Premium_Add_on": 11.99,             // Clipchamp Premium Add-on
    "STREAM": 0,                                   // Microsoft Stream (free with M365)
    
    // Storage & Other
    "SHAREPOINTSTORAGE": 0.20,                     // SharePoint Storage (per GB)
    "WINDOWS_STORE": 0,                            // Windows Store (free)
    "Dynamics_365_Onboarding_SKU": 0,              // Dynamics trial/onboarding
  };

  function renderInvoiceReconKpis(data) {
    // Get consolidated billing data
    const consolidated = getConsolidatedBilling();
    
    // Calculate YTD totals
    let ytdAzure = 0, ytdM365 = 0, ytdFabric = 0, ytdManaged = 0, ytdCredits = 0, ytdTotal = 0;
    consolidated.forEach(m => {
      ytdAzure += m.totalAzure;
      ytdM365 += m.totalM365;
      ytdFabric += m.totalFabric;
      ytdManaged += m.totalManaged;
      ytdCredits += m.httLogicallyCredit;
      ytdTotal += m.grandTotal;
    });

    // Calculate license estimates from Graph API data (all tenants)
    const licenses = data.license || [];
    let estMonthlyLicense = 0;
    licenses.forEach(l => {
      const skus = l.skuAssignments || l.subscribedSkus || [];
      skus.forEach(sku => {
        const consumed = sku.consumedUnits || 0;
        const price = SKU_PRICING[sku.skuPartNumber] || 0;
        estMonthlyLicense += consumed * price;
      });
    });

    // Get latest month data
    const latestMonth = consolidated[consolidated.length - 1];

    if (!dom.invoiceReconKpis) return;
    
    dom.invoiceReconKpis.innerHTML = `
      <div class="kpi">
        <div class="label">YTD Azure (All Brands)</div>
        <div class="value">${formatCurrency(ytdAzure)}</div>
        <div class="delta muted">HTT + BCC + TLL + FN (net credits)</div>
      </div>
      <div class="kpi">
        <div class="label">YTD M365 Licensing</div>
        <div class="value">${formatCurrency(ytdM365)}</div>
        <div class="delta muted">Logically + SG (est) + FTG (est)</div>
      </div>
      <div class="kpi">
        <div class="label">YTD Fabric Capacity</div>
        <div class="value">${formatCurrency(ytdFabric)}</div>
        <div class="delta warning">F64 started Oct 2025</div>
      </div>
      <div class="kpi">
        <div class="label">YTD Managed Services</div>
        <div class="value">${formatCurrency(ytdManaged)}</div>
        <div class="delta muted">Logically MSP only</div>
      </div>
      <div class="kpi">
        <div class="label">YTD Credits Applied</div>
        <div class="value success">${formatCurrency(ytdCredits)}</div>
        <div class="delta success">NCE reconciliation credits</div>
      </div>
      <div class="kpi">
        <div class="label">YTD Grand Total</div>
        <div class="value">${formatCurrency(ytdTotal)}</div>
        <div class="delta muted">All Microsoft spend 2025</div>
      </div>
    `;
  }

  function renderInvoiceReconTable(data) {
    if (!dom.invoiceReconTable) return;
    
    const consolidated = getConsolidatedBilling();
    const monthlyCosts = data.monthlyCosts || {};
    
    // Build monthly totals from Microsoft Cost Management API
    const msftByMonth = {};
    Object.values(monthlyCosts).forEach(sub => {
      (sub.months || []).forEach(m => {
        if (!msftByMonth[m.month]) msftByMonth[m.month] = 0;
        msftByMonth[m.month] += m.total || 0;
      });
    });

    if (consolidated.length === 0) {
      dom.invoiceReconTable.innerHTML = `<tr><td colspan="10" class="empty-state">No reconciliation data available</td></tr>`;
      return;
    }

    const rows = consolidated.slice().reverse().map(row => {
      const msftApi = msftByMonth[row.month] || 0;
      const invoicedAzure = row.totalAzure;
      const variance = invoicedAzure - msftApi;
      const variancePct = msftApi > 0 ? (variance / msftApi) * 100 : 0;
      
      let status = "muted";
      let statusText = "—";
      let statusClass = "";
      
      if (invoicedAzure > 0 && msftApi > 0) {
        if (Math.abs(variancePct) <= 10) {
          status = "success";
          statusText = "✓ Matched";
          statusClass = "success";
        } else if (variancePct > 10) {
          status = "warning";
          statusText = "⚠️ Over";
          statusClass = "warning";
        } else {
          status = "danger";
          statusText = "📉 Under";
          statusClass = "danger";
        }
      } else if (row.httLogicallyCredit > 0) {
        status = "success";
        statusText = "💰 Credit";
        statusClass = "success";
      }

      const notes = [];
      if (row.httLogicallyCredit > 0) notes.push(`Credit: -${formatCurrency(row.httLogicallyCredit)}`);
      if (row.totalFabric > 0) notes.push(`⚡ Fabric: ${formatCurrency(row.totalFabric)}`);

      return `
        <tr>
          <td><strong>${row.month}</strong></td>
          <td class="num">${row.httLogicallyAzure > 0 || row.httLogicallyM365 > 0 ? formatCurrency(row.httLogicallyAzure + row.httLogicallyM365 + row.totalFabric - row.httLogicallyCredit) : "-"}</td>
          <td class="num">${row.bccDirect > 0 ? formatCurrency(row.bccDirect) : "-"}</td>
          <td class="num">${row.tllDirectAzure > 0 || row.tllCspM365 > 0 ? formatCurrency(row.tllDirectAzure + row.tllCspM365) : "-"}</td>
          <td class="num">${row.fnCspM365 > 0 ? formatCurrency(row.fnCspM365) : "-"}</td>
          <td class="num"><strong>${formatCurrency(row.grandTotal)}</strong></td>
          <td class="num">${msftApi > 0 ? formatCurrency(msftApi) : "-"}</td>
          <td class="num ${statusClass}">${invoicedAzure > 0 && msftApi > 0 ? formatPercent(variancePct) : "-"}</td>
          <td><span class="status-badge ${status}">${statusText}</span></td>
        </tr>
      `;
    });

    dom.invoiceReconTable.innerHTML = rows.join("");

    // Apply table enhancements with pagination
    const invoiceTableEl = dom.invoiceReconTable.closest('table');
    if (invoiceTableEl) {
      // Create unified filter header (idempotent)
      const filterContainer = window.dashboard.utils.insertTableFilterHeader(invoiceTableEl, {
        searchPlaceholder: 'Search by month or brand...',
        columnSelect: ['Month', 'Status'],
        showBrandTabs: false,
        brands: []
      });

      // Apply pagination (idempotent)
      window.dashboard.utils.applyTablePagination(invoiceTableEl, 20);

      // Apply unified search
      const searchInput = filterContainer.querySelector('.table-search-unified');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const term = e.target.value.toLowerCase();
          const tbody = invoiceTableEl.querySelector('tbody');
          let visibleCount = 0;
          tbody.querySelectorAll('tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = text.includes(term);
            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
          });
          const resultsSpan = filterContainer.querySelector('.filter-results');
          if (resultsSpan) resultsSpan.textContent = `${visibleCount} of ${tbody.querySelectorAll('tr').length} items`;
        });
      }

      // Keep existing utilities for sorting and export
      DashboardUtils.enableTableSort(invoiceTableEl);
      DashboardUtils.addExportButton(invoiceTableEl, 'invoice-reconciliation');
      DashboardUtils.enhanceTableAccessibility(invoiceTableEl, 'Invoice reconciliation table');
      DashboardUtils.enableKeyboardNavigation(invoiceTableEl);
    }
  }

  function renderLicenseCostTable(data) {
    if (!dom.licenseCostTable) return;
    
    const licenses = data.license || [];
    
    if (licenses.length === 0) {
      dom.licenseCostTable.innerHTML = `<tr><td colspan="6" class="empty-state">No license data available</td></tr>`;
      return;
    }

    // Calculate costs by tenant
    const brandCosts = licenses.map(l => {
      const skus = l.skuAssignments || l.subscribedSkus || [];
      let paidLicenses = 0;
      let totalUsers = 0;
      let monthlyEst = 0;
      
      skus.forEach(sku => {
        const consumed = sku.consumedUnits || 0;
        const price = SKU_PRICING[sku.skuPartNumber] || 0;
        if (price > 0) {
          paidLicenses += consumed;
          monthlyEst += consumed * price;
        }
      });
      
      totalUsers = l.userAssignments?.length || 0;
      
      // Get billing source from CSP mapping
      const billingInfo = CSP_BILLING_SOURCES[l.tenantName] || { csp: "Unknown", type: "TBD" };
      
      return {
        tenantName: l.tenantName,
        paidLicenses,
        totalUsers,
        monthlyEst,
        annualEst: monthlyEst * 12,
        billingSource: billingInfo.csp,
        billingType: billingInfo.type,
      };
    });

    dom.licenseCostTable.innerHTML = brandCosts.sort((a, b) => b.monthlyEst - a.monthlyEst).map(b => `
      <tr>
        <td><strong>${b.tenantName}</strong></td>
        <td class="num">${formatNumber(b.paidLicenses)}</td>
        <td class="num">${formatNumber(b.totalUsers)}</td>
        <td class="num">${formatCurrency(b.monthlyEst)}</td>
        <td class="num">${formatCurrency(b.annualEst)}</td>
        <td><span class="status-badge ${b.billingSource === 'Unknown/TBD' ? 'warning' : 'info'}">${b.billingSource}</span></td>
      </tr>
    `).join("");
  }

  function renderInvoiceCharts(data) {
    // Invoice comparison chart - now shows all billing sources
    const ctxInvoice = document.getElementById("invoice-comparison-chart");
    if (!ctxInvoice) return;
    
    const consolidated = getConsolidatedBilling();
    const months = consolidated.map(c => c.month);
    
    // Build datasets for each billing source
    const httLogicallyData = consolidated.map(c => c.httLogicallyAzure + c.httLogicallyM365 + c.totalFabric - c.httLogicallyCredit);
    const bccDirectData = consolidated.map(c => c.bccDirect);
    const tllData = consolidated.map(c => c.tllDirectAzure + c.tllCspM365);
    const fnData = consolidated.map(c => c.fnCspM365);

    if (charts.invoiceComparison) charts.invoiceComparison.destroy();
    charts.invoiceComparison = new Chart(ctxInvoice, {
      type: "bar",
      data: {
        labels: months,
        datasets: [
          {
            label: "HTT (Logically)",
            data: httLogicallyData,
            backgroundColor: "rgba(59, 130, 246, 0.7)",
            borderColor: "#3b82f6",
            borderWidth: 1,
          },
          {
            label: "BCC (Direct)",
            data: bccDirectData,
            backgroundColor: "rgba(34, 197, 94, 0.7)",
            borderColor: "#22c55e",
            borderWidth: 1,
          },
          {
            label: "TLL (SG + Direct)",
            data: tllData,
            backgroundColor: "rgba(245, 158, 11, 0.7)",
            borderColor: "#f59e0b",
            borderWidth: 1,
          },
          {
            label: "FN (FTG)",
            data: fnData,
            backgroundColor: "rgba(239, 68, 68, 0.7)",
            borderColor: "#ef4444",
            borderWidth: 1,
          },
        ],
      },
      options: {
        plugins: { 
          legend: { 
            display: true, 
            labels: { color: "#9ca3af" } 
          } 
        },
        scales: {
          y: { 
            stacked: true,
            grid: { color: "#1f2937" }, 
            ticks: { 
              color: "#9ca3af",
              callback: v => "$" + (v/1000).toFixed(0) + "k"
            } 
          },
          x: { 
            stacked: true,
            grid: { display: false }, 
            ticks: { color: "#9ca3af" } 
          },
        },
      },
    });

    // License cost by brand chart
    const ctxLicense = document.getElementById("license-cost-chart");
    if (!ctxLicense) return;
    
    const licenses = data.license || [];
    const brandLabels = [];
    const brandData = [];
    const brandColors = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444"];
    
    licenses.forEach((l, i) => {
      const skus = l.skuAssignments || l.subscribedSkus || [];
      let monthlyEst = 0;
      skus.forEach(sku => {
        const consumed = sku.consumedUnits || 0;
        const price = SKU_PRICING[sku.skuPartNumber] || 0;
        monthlyEst += consumed * price;
      });
      if (monthlyEst > 0) {
        brandLabels.push(l.tenantName.replace("Head to Toe Brands (anchor)", "HTT Brands"));
        brandData.push(monthlyEst);
      }
    });

    if (charts.licenseCost) charts.licenseCost.destroy();
    charts.licenseCost = new Chart(ctxLicense, {
      type: "doughnut",
      data: {
        labels: brandLabels,
        datasets: [{
          data: brandData,
          backgroundColor: brandColors.slice(0, brandLabels.length),
          borderColor: "#111827",
          borderWidth: 2,
        }],
      },
      options: {
        plugins: { 
          legend: { 
            display: true, 
            position: "right",
            labels: { color: "#9ca3af" } 
          } 
        },
      },
    });
  }

  // ===== Charts =====
  function renderCharts(data, selection) {
    const costs = filterCostRows(data, selection);
    const period = selection.period;
    const useMonthly = (period === "6m" || period === "12m" || period === "prev-month") && 
                       (!costs.length || !costs.some(r => r.date));

    // Daily burn chart (or monthly if historical)
    if (useMonthly) {
      // Use monthly data for historical periods
      const monthlyBreakdown = getMonthlyCostsBreakdown(data, selection);
      const monthLabels = monthlyBreakdown.map(m => m.month);
      const monthData = monthlyBreakdown.map(m => m.total);

      const ctxDaily = document.getElementById("daily-chart");
      if (charts.daily) charts.daily.destroy();
      charts.daily = new Chart(ctxDaily, {
        type: "line",
        data: {
          labels: monthLabels,
          datasets: [{
            label: "Monthly cost",
            data: monthData,
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            fill: true,
            tension: 0.4,
          }],
        },
        options: {
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: "#1f2937" }, ticks: { color: "#9ca3af" } },
            x: { grid: { display: false }, ticks: { color: "#9ca3af" } },
          },
        },
      });
    } else {
      // Daily burn chart (for MTD/current period)
      const byDate = new Map();
      costs.forEach(row => {
        if (!row.date || row.dailyCost === undefined) return;
        byDate.set(row.date, (byDate.get(row.date) || 0) + row.dailyCost);
      });

      const dateLabels = Array.from(byDate.keys()).sort();
      const dateData = dateLabels.map(d => byDate.get(d));

      const ctxDaily = document.getElementById("daily-chart");
      if (charts.daily) charts.daily.destroy();
      charts.daily = new Chart(ctxDaily, {
        type: "line",
        data: {
          labels: dateLabels,
          datasets: [{
            label: "Daily cost",
            data: dateData,
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            fill: true,
            tension: 0.4,
          }],
        },
        options: {
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: "#1f2937" }, ticks: { color: "#9ca3af" } },
            x: { grid: { display: false }, ticks: { color: "#9ca3af" } },
          },
        },
      });
    }

    // Top services chart
    // For historical periods, we don't have service breakdown in monthlyCosts
    // So we'll use the available cost data to show service distribution
    const allCostRows = data.costRows || [];
    const byService = new Map();
    
    if (useMonthly) {
      // For historical views, use MTD data to show service distribution pattern
      // This shows "current" service breakdown, which is representative
      allCostRows.forEach(row => {
        const key = row.serviceName || row.meterCategory || "Other";
        const val = row.dailyCost ?? row.mtdCost ?? 0;
        byService.set(key, (byService.get(key) || 0) + val);
      });
    } else {
      // For MTD/current period, use the filtered cost rows
      costs.forEach(row => {
        const key = row.serviceName || row.meterCategory || "Other";
        const val = row.dailyCost ?? row.mtdCost ?? 0;
        byService.set(key, (byService.get(key) || 0) + val);
      });
    }

    const topServices = Array.from(byService.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);

    const ctxServices = document.getElementById("services-chart");
    if (charts.services) charts.services.destroy();
    charts.services = new Chart(ctxServices, {
      type: "bar",
      data: {
        labels: topServices.map(t => t[0]),
        datasets: [{
          data: topServices.map(t => t[1]),
          backgroundColor: "#8b5cf6",
        }],
      },
      options: {
        indexAxis: "y",
        plugins: { 
          legend: { display: false },
          title: { 
            display: useMonthly, 
            text: "Service Distribution (Current Period Data)", 
            color: "#9ca3af" 
          }
        },
        scales: {
          x: { grid: { color: "#1f2937" }, ticks: { color: "#9ca3af" } },
          y: { grid: { display: false }, ticks: { color: "#9ca3af" } },
        },
      },
    });
    
    // Phase 2: Make services chart interactive
    makeChartInteractive(charts.services, 'services');

    // Trend chart (if on trends section)
    renderTrendChart(data, selection);

    // License charts
    renderLicenseCharts(data, selection);

    // Cost section charts
    renderCostCharts(data, selection);

    // Trend helpers
    renderMoMComparison(data, selection);
    renderForecastCard(data, selection);
  }

  function renderTrendChart(data, selection) {
    const ctxTrend = document.getElementById("trend-chart");
    if (!ctxTrend) return;

    // For MTD, use daily cost rows; for longer periods, use monthlyCosts
    const period = selection.period;
    const useMonthly = period === "6m" || period === "12m" || period === "prev-month";

    if (useMonthly && data.monthlyCosts) {
      // Use historical monthly costs data
      renderMonthlyTrendChart(ctxTrend, data, selection);
    } else {
      // Use daily cost rows for MTD
      renderDailyTrendChart(ctxTrend, data, selection);
    }
  }

  function renderMonthlyTrendChart(ctx, data, selection) {
    const range = computeFilterRange(selection.period);
    const monthlyCosts = data.monthlyCosts || {};
    const tenants = data.tenants || [];

    // Build a map of subscriptionId -> tenantId for filtering
    const subToTenant = new Map();
    tenants.forEach(t => {
      (t.subscriptions || []).forEach(s => {
        subToTenant.set(s.subscriptionId, t.tenantId);
      });
    });

    // Aggregate monthly costs, respecting tenant/subscription filters
    const byMonth = new Map();
    const byMonthByTenant = new Map(); // For brand breakdown

    Object.entries(monthlyCosts).forEach(([subId, subData]) => {
      const tenantId = subToTenant.get(subId);
      
      // Apply filters
      if (selection.tenant && tenantId !== selection.tenant) return;
      if (selection.subscription && subId !== selection.subscription) return;

      const tenantName = tenants.find(t => t.tenantId === tenantId)?.tenantName || "Unknown";
      
      (subData.months || []).forEach(m => {
        const monthDate = new Date(m.month + "-01");
        if (range && (monthDate < range.from || monthDate > range.to)) return;
        
        byMonth.set(m.month, (byMonth.get(m.month) || 0) + m.total);
        
        // Track by tenant for stacked view
        if (!byMonthByTenant.has(m.month)) {
          byMonthByTenant.set(m.month, new Map());
        }
        const tenantMap = byMonthByTenant.get(m.month);
        tenantMap.set(tenantName, (tenantMap.get(tenantName) || 0) + m.total);
      });
    });

    const labels = Array.from(byMonth.keys()).sort();
    const values = labels.map(m => byMonth.get(m));

    // Calculate cumulative
    let cumulative = 0;
    const cumulativeData = values.map(v => cumulative += v);

    // Get unique tenant names for stacked datasets
    const tenantNames = new Set();
    byMonthByTenant.forEach(monthMap => {
      monthMap.forEach((_, tenant) => tenantNames.add(tenant));
    });

    const tenantColors = {
      "Head to Toe Brands (anchor)": "#3b82f6",
      "Bishops": "#8b5cf6",
      "Frenchies": "#10b981",
      "The Lash Lounge": "#f59e0b",
    };

    // Create stacked datasets by tenant
    const stackedDatasets = Array.from(tenantNames).map(tenant => ({
      label: tenant,
      data: labels.map(month => byMonthByTenant.get(month)?.get(tenant) || 0),
      backgroundColor: tenantColors[tenant] || "#6b7280",
      stack: "tenants",
    }));

    if (charts.trend) charts.trend.destroy();
    charts.trend = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels.map(m => {
          const d = new Date(m + "-01");
          return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
        }),
        datasets: [
          ...stackedDatasets,
          {
            label: "Cumulative",
            data: cumulativeData,
            borderColor: "#ef4444",
            backgroundColor: "transparent",
            borderDash: [5, 5],
            type: "line",
            tension: 0.4,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        plugins: { legend: { position: "top", labels: { color: "#9ca3af" } } },
        scales: {
          y: { 
            stacked: true,
            grid: { color: "#1f2937" }, 
            ticks: { color: "#9ca3af", callback: v => "$" + v.toLocaleString() } 
          },
          y1: {
            position: "right",
            grid: { display: false },
            ticks: { color: "#ef4444", callback: v => "$" + v.toLocaleString() },
          },
          x: { stacked: true, grid: { display: false }, ticks: { color: "#9ca3af" } },
        },
      },
    });
  }

  function renderDailyTrendChart(ctx, data, selection) {
    const costs = filterCostRows(data, selection);
    const byDate = new Map();
    costs.forEach(row => {
      if (!row.date || row.dailyCost === undefined) return;
      byDate.set(row.date, (byDate.get(row.date) || 0) + row.dailyCost);
    });

    const labels = Array.from(byDate.keys()).sort();
    const values = labels.map(d => byDate.get(d));

    // Calculate cumulative
    let cumulative = 0;
    const cumulativeData = values.map(v => cumulative += v);

    if (charts.trend) charts.trend.destroy();
    charts.trend = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Daily Cost",
            data: values,
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            fill: true,
            tension: 0.4,
            yAxisID: "y",
          },
          {
            label: "Cumulative",
            data: cumulativeData,
            borderColor: "#10b981",
            borderDash: [5, 5],
            tension: 0.4,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        plugins: { legend: { position: "top", labels: { color: "#9ca3af" } } },
        scales: {
          y: { 
            type: "linear", 
            position: "left",
            grid: { color: "#1f2937" }, 
            ticks: { color: "#9ca3af" } 
          },
          y1: {
            type: "linear",
            position: "right",
            grid: { display: false },
            ticks: { color: "#10b981" },
          },
          x: { grid: { display: false }, ticks: { color: "#9ca3af" } },
        },
      },
    });
  }

  function renderLicenseCharts(data, selection) {
    const licenses = filterLicenses(data, selection);

    // License utilization by tenant - PAID LICENSES ONLY
    const ctxUtil = document.getElementById("license-util-chart");
    if (ctxUtil) {
      const tenantData = licenses.map(l => {
        const skus = l.skuAssignments || l.subscribedSkus || [];
        // Filter to paid SKUs only - free SKUs have massive prepaid pools that skew the chart
        const paidSkus = skus.filter(sku => isPaidSku(sku.skuPartNumber));
        const consumed = paidSkus.reduce((s, sku) => s + (sku.consumedUnits || 0), 0);
        const prepaid = paidSkus.reduce((s, sku) => s + (sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 0), 0);
        return { tenant: l.tenantName, consumed, available: Math.max(0, prepaid - consumed) };
      });

      if (charts.licenseUtil) charts.licenseUtil.destroy();
      charts.licenseUtil = new Chart(ctxUtil, {
        type: "bar",
        data: {
          labels: tenantData.map(t => t.tenant),
          datasets: [
            { label: "Consumed", data: tenantData.map(t => t.consumed), backgroundColor: "#3b82f6" },
            { label: "Available", data: tenantData.map(t => t.available), backgroundColor: "#1f2937" },
          ],
        },
        options: {
          plugins: { 
            legend: { position: "top", labels: { color: "#9ca3af" } },
            title: { display: true, text: "Paid License Utilization (Free SKUs Excluded)", color: "#9ca3af" }
          },
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: "#9ca3af" } },
            y: { stacked: true, grid: { color: "#1f2937" }, ticks: { color: "#9ca3af" } },
          },
        },
      });
    }

    // Top SKUs - PAID ONLY with consumption
    const ctxSku = document.getElementById("license-sku-chart");
    if (ctxSku) {
      const allSkus = [];
      licenses.forEach(l => {
        const skus = l.skuAssignments || l.subscribedSkus || [];
        skus.forEach(sku => {
          // Only include paid SKUs with actual consumption
          if (isPaidSku(sku.skuPartNumber) && (sku.consumedUnits || 0) > 0) {
            allSkus.push({
              name: sku.skuPartNumber || sku.skuId,
              consumed: sku.consumedUnits || 0,
            });
          }
        });
      });

      const topSkus = allSkus.sort((a, b) => b.consumed - a.consumed).slice(0, 10);

      if (charts.licenseSku) charts.licenseSku.destroy();
      charts.licenseSku = new Chart(ctxSku, {
        type: "doughnut",
        data: {
          labels: topSkus.map(s => s.name),
          datasets: [{
            data: topSkus.map(s => s.consumed),
            backgroundColor: [
              "#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
              "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
            ],
          }],
        },
        options: {
          plugins: { 
            legend: { position: "right", labels: { color: "#9ca3af" } },
            title: { display: true, text: "Top Paid SKUs by Consumption", color: "#9ca3af" }
          },
        },
      });
    }
  }

  function renderCostCharts(data, selection) {
    const costs = filterCostRows(data, selection);

    // Cost by tenant
    const ctxTenant = document.getElementById("tenant-cost-chart");
    if (ctxTenant) {
      const byTenant = new Map();
      costs.forEach(c => {
        const key = c.tenantName || c.tenantId;
        byTenant.set(key, (byTenant.get(key) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
      });

      const tenantData = Array.from(byTenant.entries()).sort((a, b) => b[1] - a[1]);

      if (charts.tenantCost) charts.tenantCost.destroy();
      charts.tenantCost = new Chart(ctxTenant, {
        type: "pie",
        data: {
          labels: tenantData.map(t => t[0]),
          datasets: [{
            data: tenantData.map(t => t[1]),
            backgroundColor: ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"],
          }],
        },
        options: {
          plugins: { legend: { position: "bottom", labels: { color: "#9ca3af" } } },
        },
      });
    }

    // Cost by service
    const ctxService = document.getElementById("service-cost-chart");
    if (ctxService) {
      const byService = new Map();
      costs.forEach(c => {
        const key = c.serviceName || c.meterCategory || "Other";
        byService.set(key, (byService.get(key) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
      });

      const serviceData = Array.from(byService.entries()).sort((a, b) => b[1] - a[1]).slice(0, 8);

      if (charts.serviceCost) charts.serviceCost.destroy();
      charts.serviceCost = new Chart(ctxService, {
        type: "bar",
        data: {
          labels: serviceData.map(s => s[0]),
          datasets: [{
            data: serviceData.map(s => s[1]),
            backgroundColor: "#8b5cf6",
          }],
        },
        options: {
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: "#1f2937" }, ticks: { color: "#9ca3af" } },
            x: { grid: { display: false }, ticks: { color: "#9ca3af" } },
          },
        },
      });
    }
  }

  // ===== Month-over-Month Comparison & Forecast =====

  function renderMoMComparison(data, selection) {
    if (!dom.momComparison) return;

    // getMonthlyTotals returns array of [month, total] tuples sorted ascending
    const monthlyArray = getMonthlyTotals(data, selection);
    
    if (monthlyArray.length < 2) {
      dom.momComparison.innerHTML = `
        <div class="comparison-grid">
          <p class="muted">Not enough historical data for comparison</p>
        </div>
      `;
      return;
    }

    // Get last two months (array is sorted ascending, so last two are most recent)
    const currentEntry = monthlyArray[monthlyArray.length - 1];
    const previousEntry = monthlyArray[monthlyArray.length - 2];
    
    const currentMonth = currentEntry[0];
    const current = currentEntry[1] || 0;
    const previousMonth = previousEntry[0];
    const previous = previousEntry[1] || 0;
    
    const delta = current - previous;
    const deltaPct = previous > 0 ? (delta / previous) * 100 : 0;

    dom.momComparison.innerHTML = `
      <div class="comparison-grid">
        <div class="comparison-item">
          <span class="comparison-label">Current Month</span>
          <span class="comparison-value">${formatCurrency(current)}</span>
          <span class="comparison-period">${currentMonth}</span>
        </div>
        <div class="comparison-item">
          <span class="comparison-label">Previous Month</span>
          <span class="comparison-value">${formatCurrency(previous)}</span>
          <span class="comparison-period">${previousMonth}</span>
        </div>
        <div class="comparison-item">
          <span class="comparison-label">Change</span>
          <span class="comparison-value ${delta >= 0 ? 'danger' : 'success'}">
            ${delta >= 0 ? '+' : ''}${formatCurrency(delta)}
          </span>
          <span class="comparison-change ${delta >= 0 ? 'danger' : 'success'}">
            ${delta >= 0 ? '↑' : '↓'} ${Math.abs(deltaPct).toFixed(1)}%
          </span>
        </div>
      </div>
    `;
  }

  function renderForecastCard(data, selection) {
    if (!dom.forecastCard) return;

    // Get current month's daily costs to project
    const costRows = filterCostRows(data, selection);
    const now = new Date();
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const dayOfMonth = now.getDate();

    // Sum costs for current month
    const currentMonthCosts = costRows.reduce((sum, c) => sum + (c.dailyCost ?? 0), 0);

    // Simple linear projection
    const dailyAvg = dayOfMonth > 0 ? currentMonthCosts / dayOfMonth : 0;
    const projected = dailyAvg * daysInMonth;

    // Budget comparison if configured
    const budget = cfg.budgetMonthly;
    const budgetStatus = budget ? (projected <= budget ? 'on-track' : 'over-budget') : null;

    dom.forecastCard.innerHTML = `
      <div class="forecast-display">
        <div class="forecast-item">
          <span class="forecast-label">Current Spend</span>
          <span class="forecast-value">${formatCurrency(currentMonthCosts)}</span>
          <span class="forecast-period">Through day ${dayOfMonth}</span>
        </div>
        <div class="forecast-item">
          <span class="forecast-label">Projected EOM</span>
          <span class="forecast-value ${budgetStatus === 'over-budget' ? 'danger' : ''}">${formatCurrency(projected)}</span>
          <span class="forecast-period">Based on daily average</span>
        </div>
        ${budget ? `
          <div class="forecast-item">
            <span class="forecast-label">Budget</span>
            <span class="forecast-value">${formatCurrency(budget)}</span>
            <span class="forecast-status ${budgetStatus}">
              ${budgetStatus === 'on-track' ? '✓ On Track' : '⚠ Over Budget'}
            </span>
          </div>
        ` : ''}
      </div>
    `;
  }

  // ===== Identity & GitHub Rendering Functions =====

  function renderUserLicensesTable(data, selection) {
    if (!dom.userLicensesTable) return;
    
    const users = data.users || {};
    const licenses = data.license || [];
    const now = new Date();
    const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    
    // Build license SKU lookup by tenant
    const skuByTenant = new Map();
    licenses.forEach(l => {
      const skuMap = new Map();
      (l.subscribedSkus || l.skuAssignments || []).forEach(sku => {
        skuMap.set(sku.skuId, sku);
      });
      skuByTenant.set(l.tenantId, skuMap);
    });
    
    const rows = [];
    Object.entries(users).forEach(([tenantId, userList]) => {
      // Apply tenant filter
      if (selection.tenant && tenantId !== selection.tenant) return;
      
      const tenant = (data.tenants || []).find(t => t.tenantId === tenantId);
      const tenantName = tenant?.tenantName || tenantId;
      const tenantShort = tenantName
        .replace("Head to Toe Brands (anchor)", "HTT")
        .replace("The Lash Lounge", "TLL")
        .replace("Frenchies", "FN")
        .replace("Bishops", "BCC");
      const tenantSkus = skuByTenant.get(tenantId) || new Map();
      
      userList.forEach(user => {
        const assignedSkuIds = (user.assignedSkuIds || []).concat(user.groupAssignedSkuIds || []);
        const lastSignIn = user.lastSignInDateTime ? new Date(user.lastSignInDateTime) : null;
        const lastSignInStr = lastSignIn ? lastSignIn.toLocaleDateString() : "Never";
        
        // Calculate days since last sign-in
        const daysSinceSignIn = lastSignIn 
          ? Math.floor((now - lastSignIn) / (24 * 60 * 60 * 1000))
          : Infinity;
        
        // Determine if user is inactive (30+ days)
        const isInactive = daysSinceSignIn >= 30;
        
        // Check for paid licenses
        const paidLicenses = assignedSkuIds.filter(id => {
          const sku = tenantSkus.get(id);
          return sku && isPaidSku(sku.skuPartNumber);
        });
        const hasPaidLicense = paidLicenses.length > 0;
        
        // Check for duplicate/redundant licenses (same type of license)
        const hasDuplicates = assignedSkuIds.length !== new Set(assignedSkuIds).size || 
                             paidLicenses.length > 1;
        
        // Determine waste status
        let wasteStatus = "";
        let wasteClass = "";
        if (isInactive && hasPaidLicense && user.accountEnabled) {
          wasteStatus = `⚠️ Inactive ${daysSinceSignIn}d`;
          wasteClass = "danger";
        } else if (hasDuplicates && hasPaidLicense) {
          wasteStatus = "🔄 Duplicate SKUs";
          wasteClass = "warning";
        } else if (daysSinceSignIn >= 14 && daysSinceSignIn < 30 && hasPaidLicense) {
          wasteStatus = `⏳ ${daysSinceSignIn}d inactive`;
          wasteClass = "warning";
        }
        
        rows.push({
          html: `
            <tr class="${wasteClass ? 'waste-row ' + wasteClass : ''}">
              <td><strong>${tenantShort}</strong></td>
              <td>${user.displayName || "-"}</td>
              <td>${user.mail || user.userPrincipalName || "-"}</td>
              <td>${user.department || "-"}</td>
              <td><span class="badge ${user.accountEnabled ? 'success' : 'danger'}">${user.accountEnabled ? 'Enabled' : 'Disabled'}</span></td>
              <td class="num">${assignedSkuIds.length}${hasPaidLicense ? ' <span class="badge info">Paid</span>' : ''}</td>
              <td>${lastSignInStr}</td>
              <td class="${wasteClass}">${wasteStatus}</td>
            </tr>
          `,
          isWaste: isInactive && hasPaidLicense && user.accountEnabled,
          daysSinceSignIn,
          hasPaidLicense,
          tenantName
        });
      });
    });
    
    if (rows.length === 0) {
      dom.userLicensesTable.innerHTML = `<tr><td colspan="8" class="empty-state">No user license data</td></tr>`;
      return;
    }
    
    // Sort: waste cases first, then by days since sign-in descending
    rows.sort((a, b) => {
      if (a.isWaste !== b.isWaste) return b.isWaste ? 1 : -1;
      return b.daysSinceSignIn - a.daysSinceSignIn;
    });
    
    const htmlRows = rows.map(r => r.html);

    if (htmlRows.length > PAGINATION_THRESHOLD) {
      renderPaginatedTable("user-licenses", htmlRows, dom.userLicensesTable, 8);
    } else {
      dom.userLicensesTable.innerHTML = htmlRows.join("");
    }

    // Apply table enhancements
    const userLicTableEl = dom.userLicensesTable.closest('table');
    if (userLicTableEl) {
      DashboardUtils.enableTableSearch(userLicTableEl, ['displayName', 'mail', 'department']);
      DashboardUtils.enableTableSort(userLicTableEl);
      DashboardUtils.makeTableResponsive(userLicTableEl);
      DashboardUtils.addExportButton(userLicTableEl, 'user-licenses');
      DashboardUtils.enhanceTableAccessibility(userLicTableEl, 'User license assignments table');
      DashboardUtils.enableKeyboardNavigation(userLicTableEl);
    }
    
    // Show waste summary
    const wasteCount = rows.filter(r => r.isWaste).length;
    const wasteContainer = dom.userLicensesTable.closest('.card')?.querySelector('.waste-summary');
    if (wasteCount > 0 && !wasteContainer) {
      const cardBody = dom.userLicensesTable.closest('.card-body');
      if (cardBody) {
        const summary = document.createElement('div');
        summary.className = 'waste-summary alert alert-warning';
        summary.innerHTML = `
          <strong>⚠️ License Waste Detected:</strong> ${wasteCount} enabled users with paid licenses haven't signed in for 30+ days.
          <br><small>Review and consider disabling accounts or reassigning licenses to reduce costs.</small>
        `;
        cardBody.insertBefore(summary, cardBody.firstChild);
      }
    }
  }

  function renderIdentityUsersKpis(data) {
    if (!dom.identityUsersKpis) return;
    
    const users = data.users || {};
    const totalUsers = Object.values(users).reduce((sum, arr) => sum + arr.length, 0);
    const enabledUsers = Object.values(users).reduce((sum, arr) => 
      sum + arr.filter(u => u.accountEnabled).length, 0);
    const disabledUsers = totalUsers - enabledUsers;
    
    const withLicenses = Object.values(users).reduce((sum, arr) => 
      sum + arr.filter(u => (u.assignedSkuIds?.length || 0) > 0).length, 0);
    
    dom.identityUsersKpis.innerHTML = `
      <div class="kpi">
        <div class="label">Total Users</div>
        <div class="value">${formatNumber(totalUsers)}</div>
      </div>
      <div class="kpi">
        <div class="label">Enabled</div>
        <div class="value success">${formatNumber(enabledUsers)}</div>
      </div>
      <div class="kpi">
        <div class="label">Disabled</div>
        <div class="value danger">${formatNumber(disabledUsers)}</div>
      </div>
      <div class="kpi">
        <div class="label">With Licenses</div>
        <div class="value">${formatNumber(withLicenses)}</div>
      </div>
    `;
  }

  function renderIdentityUsersTable(data) {
    if (!dom.identityUsersTable) return;
    
    const users = data.users || {};
    const selection = getSelection();
    const now = new Date();
    const rows = [];
    
    Object.entries(users).forEach(([tenantId, userList]) => {
      // Apply tenant filter
      if (selection.tenant && tenantId !== selection.tenant) return;
      
      const tenant = (data.tenants || []).find(t => t.tenantId === tenantId);
      const tenantName = tenant?.tenantName || tenantId;
      const tenantShort = tenantName
        .replace("Head to Toe Brands (anchor)", "HTT")
        .replace("The Lash Lounge", "TLL")
        .replace("Frenchies", "FN")
        .replace("Bishops", "BCC");
      
      userList.forEach(user => {
        const licenseCount = (user.assignedSkuIds?.length || 0) + (user.groupAssignedSkuIds?.length || 0);
        const lastSignIn = user.lastSignInDateTime ? new Date(user.lastSignInDateTime) : null;
        const lastSignInStr = lastSignIn ? lastSignIn.toLocaleDateString() : "Never";
        const daysSinceSignIn = lastSignIn ? Math.floor((now - lastSignIn) / (24 * 60 * 60 * 1000)) : Infinity;
        
        rows.push({
          html: `
            <tr>
              <td><strong>${tenantShort}</strong></td>
              <td>${user.displayName || "-"}</td>
              <td>${user.userPrincipalName || "-"}</td>
              <td>${user.mail || "-"}</td>
              <td>${user.department || "-"}</td>
              <td><span class="badge ${user.accountEnabled ? 'success' : 'danger'}">${user.accountEnabled ? 'Enabled' : 'Disabled'}</span></td>
              <td class="num">${licenseCount}</td>
              <td>${lastSignInStr}</td>
            </tr>
          `,
          daysSinceSignIn,
          accountEnabled: user.accountEnabled,
          tenantName
        });
      });
    });
    
    if (rows.length === 0) {
      dom.identityUsersTable.innerHTML = `<tr><td colspan="8" class="empty-state">No user data</td></tr>`;
      return;
    }
    
    // Sort by most recent activity first
    rows.sort((a, b) => a.daysSinceSignIn - b.daysSinceSignIn);
    
    const htmlRows = rows.map(r => r.html);
    
    dom.identityUsersTable.innerHTML = htmlRows.join("");

    // Apply table enhancements with pagination and unified filters
    const idUsersTableEl = dom.identityUsersTable.closest('table');
    if (idUsersTableEl) {
      // Create unified filter header (idempotent)
      const filterContainer = window.dashboard.utils.insertTableFilterHeader(idUsersTableEl, {
        searchPlaceholder: 'Search users by name, email, or department...',
        columnSelect: ['Name', 'Email', 'Department', 'Status'],
        showBrandTabs: true,
        brands: ['All Brands', 'HTT', 'TLL', 'FN', 'BCC']
      });

      // Apply pagination (idempotent)
      window.dashboard.utils.applyTablePagination(idUsersTableEl, 20);

      // Apply brand filtering
      filterContainer.querySelectorAll('.brand-tab').forEach(tab => {
        tab.addEventListener('click', () => {
          filterContainer.querySelectorAll('.brand-tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          window.dashboard.utils.applyBrandFiltering(idUsersTableEl.closest('.table-wrapper') || idUsersTableEl, tab.dataset.brand);
        });
      });

      // Apply unified search
      const searchInput = filterContainer.querySelector('.table-search-unified');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const term = e.target.value.toLowerCase();
          const tbody = idUsersTableEl.querySelector('tbody');
          let visibleCount = 0;
          tbody.querySelectorAll('tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = text.includes(term);
            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
          });
          const resultsSpan = filterContainer.querySelector('.filter-results');
          if (resultsSpan) resultsSpan.textContent = `${visibleCount} of ${tbody.querySelectorAll('tr').length} items`;
        });
      }

      // Keep existing utilities for sorting and export
      DashboardUtils.enableTableSort(idUsersTableEl);
      DashboardUtils.addExportButton(idUsersTableEl, 'identity-users');
      DashboardUtils.enhanceTableAccessibility(idUsersTableEl, 'Identity users table');
      DashboardUtils.enableKeyboardNavigation(idUsersTableEl);
    }
  }

  function renderIdentityAppsKpis(data) {
    if (!dom.identityAppsKpis) return;
    
    const sps = data.servicePrincipals || {};
    const totalSPs = Object.values(sps).reduce((sum, arr) => sum + arr.length, 0);
    const enabledSPs = Object.values(sps).reduce((sum, arr) => 
      sum + arr.filter(sp => sp.accountEnabled).length, 0);
    
    // Count credentials expiring in next 30 days
    const now = new Date();
    const thirtyDays = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    const expiringSoon = Object.values(sps).reduce((sum, arr) => {
      return sum + arr.filter(sp => {
        const creds = (sp.credentials || []);
        return creds.some(c => {
          const endDate = c.endDateTime ? new Date(c.endDateTime) : null;
          return endDate && endDate > now && endDate < thirtyDays;
        });
      }).length;
    }, 0);
    
    const withCreds = Object.values(sps).reduce((sum, arr) => 
      sum + arr.filter(sp => (sp.credentials?.length || 0) > 0).length, 0);
    
    dom.identityAppsKpis.innerHTML = `
      <div class="kpi">
        <div class="label">Total Service Principals</div>
        <div class="value">${formatNumber(totalSPs)}</div>
      </div>
      <div class="kpi">
        <div class="label">Enabled</div>
        <div class="value success">${formatNumber(enabledSPs)}</div>
      </div>
      <div class="kpi">
        <div class="label">With Credentials</div>
        <div class="value">${formatNumber(withCreds)}</div>
      </div>
      <div class="kpi">
        <div class="label">Expiring Soon</div>
        <div class="value warning">${formatNumber(expiringSoon)}</div>
      </div>
    `;
  }

  function renderIdentityAppsTable(data) {
    if (!dom.identityAppsTable) return;
    
    const sps = data.servicePrincipals || {};
    const rows = [];
    
    const now = new Date();
    const thirtyDays = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    
    Object.entries(sps).forEach(([tenantId, spList]) => {
      const tenant = (data.tenants || []).find(t => t.tenantId === tenantId);
      const tenantName = tenant?.tenantName || tenantId;
      
      spList.forEach(sp => {
        const passwordCreds = (sp.credentials || []).filter(c => c.type?.toLowerCase() === "password").length;
        const certCreds = (sp.credentials || []).filter(c => c.type?.toLowerCase() === "certificate" || c.type?.toLowerCase() === "asymmetricx509cert").length;
        
        const expiringSoon = (sp.credentials || []).some(c => {
          const endDate = c.endDateTime ? new Date(c.endDateTime) : null;
          return endDate && endDate > now && endDate < thirtyDays;
        });
        
        rows.push(`
          <tr>
            <td><strong>${tenantName}</strong></td>
            <td>${sp.displayName || "-"}</td>
            <td><code>${sp.appId || "-"}</code></td>
            <td><span class="badge ${sp.accountEnabled ? 'success' : 'danger'}">${sp.accountEnabled ? 'Enabled' : 'Disabled'}</span></td>
            <td class="num">${passwordCreds}</td>
            <td class="num">${certCreds}</td>
            <td>${expiringSoon ? '<span class="badge warning">Yes</span>' : '-'}</td>
          </tr>
        `);
      });
    });
    
    if (rows.length === 0) {
      dom.identityAppsTable.innerHTML = `<tr><td colspan="7" class="empty-state">No service principal data</td></tr>`;
      return;
    }
    
    dom.identityAppsTable.innerHTML = rows.join("");

    // Apply table enhancements with pagination and unified filters
    const idAppsTableEl = dom.identityAppsTable.closest('table');
    if (idAppsTableEl) {
      // Create unified filter header (idempotent)
      const filterContainer = window.dashboard.utils.insertTableFilterHeader(idAppsTableEl, {
        searchPlaceholder: 'Search apps by name or ID...',
        columnSelect: ['Name', 'App ID', 'Status'],
        showBrandTabs: true,
        brands: ['All Brands', 'HTT', 'TLL', 'FN', 'BCC']
      });

      // Apply pagination (idempotent)
      window.dashboard.utils.applyTablePagination(idAppsTableEl, 20);

      // Apply brand filtering
      filterContainer.querySelectorAll('.brand-tab').forEach(tab => {
        tab.addEventListener('click', () => {
          filterContainer.querySelectorAll('.brand-tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          window.dashboard.utils.applyBrandFiltering(idAppsTableEl.closest('.table-wrapper') || idAppsTableEl, tab.dataset.brand);
        });
      });

      // Apply unified search
      const searchInput = filterContainer.querySelector('.table-search-unified');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const term = e.target.value.toLowerCase();
          const tbody = idAppsTableEl.querySelector('tbody');
          let visibleCount = 0;
          tbody.querySelectorAll('tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = text.includes(term);
            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
          });
          const resultsSpan = filterContainer.querySelector('.filter-results');
          if (resultsSpan) resultsSpan.textContent = `${visibleCount} of ${tbody.querySelectorAll('tr').length} items`;
        });
      }

      // Keep existing utilities for sorting and export
      DashboardUtils.enableTableSort(idAppsTableEl);
      DashboardUtils.addExportButton(idAppsTableEl, 'identity-service-principals');
      DashboardUtils.enhanceTableAccessibility(idAppsTableEl, 'Service principals table');
      DashboardUtils.enableKeyboardNavigation(idAppsTableEl);
    }
  }

  function renderIdentityAppregsKpis(data) {
    if (!dom.identityAppregsKpis) return;
    
    const apps = data.applications || {};
    const totalApps = Object.values(apps).reduce((sum, arr) => sum + arr.length, 0);
    
    const withOwners = Object.values(apps).reduce((sum, arr) => 
      sum + arr.filter(a => (a.owners?.length || 0) > 0).length, 0);
    const withoutOwners = totalApps - withOwners;
    
    dom.identityAppregsKpis.innerHTML = `
      <div class="kpi">
        <div class="label">Total App Registrations</div>
        <div class="value">${formatNumber(totalApps)}</div>
      </div>
      <div class="kpi">
        <div class="label">With Owners</div>
        <div class="value success">${formatNumber(withOwners)}</div>
      </div>
      <div class="kpi">
        <div class="label">Without Owners</div>
        <div class="value warning">${formatNumber(withoutOwners)}</div>
      </div>
    `;
  }

  function renderIdentityAppregsTable(data) {
    if (!dom.identityAppregsTable) return;
    
    const apps = data.applications || {};
    const rows = [];
    
    Object.entries(apps).forEach(([tenantId, appList]) => {
      const tenant = (data.tenants || []).find(t => t.tenantId === tenantId);
      const tenantName = tenant?.tenantName || tenantId;
      
      appList.forEach(app => {
        const owners = (app.owners || []).join(", ") || "None";
        
        rows.push({
          tenantName,
          displayName: app.displayName,
          appId: app.appId,
          signInAudience: app.signInAudience || "-",
          owners,
        });
      });
    });
    
    if (rows.length === 0) {
      dom.identityAppregsTable.innerHTML = `<tr><td colspan="5" class="empty-state">No application data</td></tr>`;
      return;
    }
    
    dom.identityAppregsTable.innerHTML = rows.map(r => `
      <tr>
        <td><strong>${r.tenantName}</strong></td>
        <td>${r.displayName}</td>
        <td><code>${r.appId}</code></td>
        <td>${r.signInAudience}</td>
        <td>${r.owners}</td>
      </tr>
    `).join("");

    // Apply table enhancements with pagination and unified filters
    const idAppregsTableEl = dom.identityAppregsTable.closest('table');
    if (idAppregsTableEl) {
      // Create unified filter header (idempotent)
      const filterContainer = window.dashboard.utils.insertTableFilterHeader(idAppregsTableEl, {
        searchPlaceholder: 'Search apps by name, ID, or audience...',
        columnSelect: ['Name', 'App ID', 'Audience'],
        showBrandTabs: true,
        brands: ['All Brands', 'HTT', 'TLL', 'FN', 'BCC']
      });

      // Apply pagination (idempotent)
      window.dashboard.utils.applyTablePagination(idAppregsTableEl, 20);

      // Apply brand filtering
      filterContainer.querySelectorAll('.brand-tab').forEach(tab => {
        tab.addEventListener('click', () => {
          filterContainer.querySelectorAll('.brand-tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          window.dashboard.utils.applyBrandFiltering(idAppregsTableEl.closest('.table-wrapper') || idAppregsTableEl, tab.dataset.brand);
        });
      });

      // Apply unified search
      const searchInput = filterContainer.querySelector('.table-search-unified');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const term = e.target.value.toLowerCase();
          const tbody = idAppregsTableEl.querySelector('tbody');
          let visibleCount = 0;
          tbody.querySelectorAll('tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = text.includes(term);
            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
          });
          const resultsSpan = filterContainer.querySelector('.filter-results');
          if (resultsSpan) resultsSpan.textContent = `${visibleCount} of ${tbody.querySelectorAll('tr').length} items`;
        });
      }

      // Keep existing utilities for sorting and export
      DashboardUtils.enableTableSort(idAppregsTableEl);
      DashboardUtils.addExportButton(idAppregsTableEl, 'app-registrations');
      DashboardUtils.enhanceTableAccessibility(idAppregsTableEl, 'Application registrations table');
      DashboardUtils.enableKeyboardNavigation(idAppregsTableEl);
    }
  }

  function renderIdentityCapKpis(data) {
    if (!dom.identityCapKpis) return;
    
    const caps = data.conditionalAccess || {};
    const totalPolicies = Object.values(caps).reduce((sum, arr) => sum + arr.length, 0);
    
    const enabled = Object.values(caps).reduce((sum, arr) => 
      sum + arr.filter(p => p.state === "enabled").length, 0);
    const disabled = Object.values(caps).reduce((sum, arr) => 
      sum + arr.filter(p => p.state === "disabled").length, 0);
    const reportOnly = Object.values(caps).reduce((sum, arr) => 
      sum + arr.filter(p => p.state === "enabledForReportingButNotEnforced").length, 0);
    
    dom.identityCapKpis.innerHTML = `
      <div class="kpi">
        <div class="label">Total Policies</div>
        <div class="value">${formatNumber(totalPolicies)}</div>
      </div>
      <div class="kpi">
        <div class="label">Enabled</div>
        <div class="value success">${formatNumber(enabled)}</div>
      </div>
      <div class="kpi">
        <div class="label">Disabled</div>
        <div class="value danger">${formatNumber(disabled)}</div>
      </div>
      <div class="kpi">
        <div class="label">Report Only</div>
        <div class="value warning">${formatNumber(reportOnly)}</div>
      </div>
    `;
  }

  function renderIdentityCapTable(data) {
    if (!dom.identityCapTable) return;
    
    const caps = data.conditionalAccess || {};
    const rows = [];
    
    Object.entries(caps).forEach(([tenantId, capList]) => {
      const tenant = (data.tenants || []).find(t => t.tenantId === tenantId);
      const tenantName = tenant?.tenantName || tenantId;
      
      capList.forEach(cap => {
        rows.push({
          tenantName,
          displayName: cap.displayName,
          id: cap.id,
          state: cap.state,
        });
      });
    });
    
    if (rows.length === 0) {
      dom.identityCapTable.innerHTML = `<tr><td colspan="4" class="empty-state">No conditional access policy data</td></tr>`;
      return;
    }
    
    const stateBadge = (state) => {
      if (state === "enabled") return '<span class="badge success">Enabled</span>';
      if (state === "disabled") return '<span class="badge danger">Disabled</span>';
      if (state === "enabledForReportingButNotEnforced") return '<span class="badge warning">Report Only</span>';
      return `<span class="badge">${state}</span>`;
    };
    
    dom.identityCapTable.innerHTML = rows.map(r => `
      <tr>
        <td><strong>${r.tenantName}</strong></td>
        <td>${r.displayName}</td>
        <td><code>${r.id}</code></td>
        <td>${stateBadge(r.state)}</td>
      </tr>
    `).join("");

    // Apply table enhancements with pagination and unified filters
    const idCapTableEl = dom.identityCapTable.closest('table');
    if (idCapTableEl) {
      // Create unified filter header (idempotent)
      const filterContainer = window.dashboard.utils.insertTableFilterHeader(idCapTableEl, {
        searchPlaceholder: 'Search policies by name or ID...',
        columnSelect: ['Name', 'Policy ID', 'State'],
        showBrandTabs: true,
        brands: ['All Brands', 'HTT', 'TLL', 'FN', 'BCC']
      });

      // Apply pagination (idempotent)
      window.dashboard.utils.applyTablePagination(idCapTableEl, 20);

      // Apply brand filtering
      filterContainer.querySelectorAll('.brand-tab').forEach(tab => {
        tab.addEventListener('click', () => {
          filterContainer.querySelectorAll('.brand-tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          window.dashboard.utils.applyBrandFiltering(idCapTableEl.closest('.table-wrapper') || idCapTableEl, tab.dataset.brand);
        });
      });

      // Apply unified search
      const searchInput = filterContainer.querySelector('.table-search-unified');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const term = e.target.value.toLowerCase();
          const tbody = idCapTableEl.querySelector('tbody');
          let visibleCount = 0;
          tbody.querySelectorAll('tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = text.includes(term);
            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
          });
          const resultsSpan = filterContainer.querySelector('.filter-results');
          if (resultsSpan) resultsSpan.textContent = `${visibleCount} of ${tbody.querySelectorAll('tr').length} items`;
        });
      }

      // Keep existing utilities for sorting and export
      DashboardUtils.enableTableSort(idCapTableEl);
      DashboardUtils.addExportButton(idCapTableEl, 'conditional-access-policies');
      DashboardUtils.enhanceTableAccessibility(idCapTableEl, 'Conditional access policies table');
      DashboardUtils.enableKeyboardNavigation(idCapTableEl);
    }
  }

  function renderGitHubBillingKpis(data) {
    if (!dom.githubBillingKpis) return;
    
    const github = data.github || {};
    const months = github.months || [];
    
    if (months.length === 0) {
      dom.githubBillingKpis.innerHTML = `
        <div class="kpi" style="grid-column: 1 / -1">
          <div class="label">GitHub Billing</div>
          <div class="value muted">No data available</div>
          <div class="delta">Configure GITHUB_TOKEN to collect billing data</div>
        </div>
      `;
      return;
    }
    
    const latest = months[months.length - 1];
    const totalCost = months.reduce((sum, m) => sum + (m.totalAmount || 0), 0);
    const avgCost = totalCost / months.length;
    
    dom.githubBillingKpis.innerHTML = `
      <div class="kpi">
        <div class="label">Latest Month</div>
        <div class="value">${formatCurrency(latest.totalAmount || 0)}</div>
        <div class="delta">${latest.month || "Unknown"}</div>
      </div>
      <div class="kpi">
        <div class="label">12-Month Total</div>
        <div class="value">${formatCurrency(totalCost)}</div>
      </div>
      <div class="kpi">
        <div class="label">Monthly Average</div>
        <div class="value">${formatCurrency(avgCost)}</div>
      </div>
      <div class="kpi">
        <div class="label">Current Seats</div>
        <div class="value">${formatNumber(latest.seats || 0)}</div>
      </div>
    `;
  }

  function renderGitHubBillingTable(data) {
    if (!dom.githubBillingTable) return;
    
    const github = data.github || {};
    const months = github.months || [];
    
    if (months.length === 0) {
      dom.githubBillingTable.innerHTML = `<tr><td colspan="6" class="empty-state">No GitHub billing data available</td></tr>`;
      return;
    }
    
    const reversed = months.reverse();
    dom.githubBillingTable.innerHTML = reversed.map(m => `
      <tr>
        <td><strong>${m.month || "Unknown"}</strong></td>
        <td class="num">${formatNumber(m.seats || 0)}</td>
        <td class="num">${formatCurrency(m.seatsPrice || 0)}</td>
        <td class="num">${formatNumber(m.actionsMinutes || 0)}</td>
        <td class="num">${formatNumber(m.storageGB || 0)}</td>
        <td class="num"><strong>${formatCurrency(m.totalAmount || 0)}</strong></td>
      </tr>
    `).join("");

    // Apply table enhancements with pagination
    const githubTableEl = dom.githubBillingTable.closest('table');
    if (githubTableEl) {
      // Create unified filter header (idempotent)
      const filterContainer = window.dashboard.utils.insertTableFilterHeader(githubTableEl, {
        searchPlaceholder: 'Search by month...',
        columnSelect: [],
        showBrandTabs: false,
        brands: []
      });

      // Apply pagination (idempotent)
      window.dashboard.utils.applyTablePagination(githubTableEl, 20);

      // Apply unified search
      const searchInput = filterContainer.querySelector('.table-search-unified');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const term = e.target.value.toLowerCase();
          const tbody = githubTableEl.querySelector('tbody');
          let visibleCount = 0;
          tbody.querySelectorAll('tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = text.includes(term);
            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
          });
          const resultsSpan = filterContainer.querySelector('.filter-results');
          if (resultsSpan) resultsSpan.textContent = `${visibleCount} of ${tbody.querySelectorAll('tr').length} items`;
        });
      }

      // Keep existing utilities for sorting and export
      DashboardUtils.enableTableSort(githubTableEl);
      DashboardUtils.addExportButton(githubTableEl, 'github-billing');
      DashboardUtils.enhanceTableAccessibility(githubTableEl, 'GitHub billing table');
      DashboardUtils.enableKeyboardNavigation(githubTableEl);
    }
  }

  function renderGitHubBillingCharts(data) {
    const github = data.github || {};
    const months = github.months || [];
    
    if (months.length === 0) return;
    
    // Billing trend chart
    const ctxTrend = document.getElementById("github-billing-chart");
    if (ctxTrend) {
      if (charts.githubTrend) charts.githubTrend.destroy();
      charts.githubTrend = new Chart(ctxTrend, {
        type: "line",
        data: {
          labels: months.map(m => m.month || "Unknown"),
          datasets: [{
            label: "Total Cost",
            data: months.map(m => m.totalAmount || 0),
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            tension: 0.3,
          }],
        },
        options: {
          plugins: { legend: { display: false } },
          scales: {
            y: {
              grid: { color: "#1f2937" },
              ticks: { color: "#9ca3af", callback: (v) => formatCurrency(v) },
            },
            x: { grid: { display: false }, ticks: { color: "#9ca3af" } },
          },
        },
      });
    }
    
    // Cost breakdown chart
    const ctxBreakdown = document.getElementById("github-cost-chart");
    if (ctxBreakdown) {
      const latest = months[months.length - 1];
      const seatsPrice = latest.seatsPrice || 0;
      // Approximate actions/storage costs (GitHub doesn't break these out separately in free tier)
      const otherCosts = (latest.totalAmount || 0) - seatsPrice;
      
      if (charts.githubCost) charts.githubCost.destroy();
      charts.githubCost = new Chart(ctxBreakdown, {
        type: "doughnut",
        data: {
          labels: ["Seats", "Actions & Storage"],
          datasets: [{
            data: [seatsPrice, otherCosts],
            backgroundColor: ["#3b82f6", "#8b5cf6"],
          }],
        },
        options: {
          plugins: {
            legend: { position: "bottom", labels: { color: "#9ca3af" } },
          },
        },
      });
    }
  }

  // ===== Cloud Topology Section =====
  /**
   * Generate topology data from existing tenant/subscription/cost data
   * @param {Object} data - Full dashboard data
   * @returns {Object} Generated topology structure
   */
  function generateTopologyFromData(data) {
    const tenants = data.tenants || [];
    const costRows = data.costRows || [];
    const resources = data.resources || [];
    
    // Calculate costs by tenant
    const costByTenant = new Map();
    const costBySubscription = new Map();
    costRows.forEach(c => {
      const tid = c.tenantId;
      const sid = c.subscriptionId;
      const cost = c.dailyCost ?? c.mtdCost ?? 0;
      costByTenant.set(tid, (costByTenant.get(tid) || 0) + cost);
      costBySubscription.set(sid, (costBySubscription.get(sid) || 0) + cost);
    });
    
    // Build tenant objects for topology
    const topologyTenants = tenants.map(t => {
      const isAnchor = t.tenantName?.includes('anchor') || t.tenantName?.includes('HTT') || t.tenantName?.includes('Head to Toe');
      const id = t.tenantName?.toLowerCase().includes('bishops') ? 'bcc' :
                 t.tenantName?.toLowerCase().includes('lash') ? 'tll' :
                 t.tenantName?.toLowerCase().includes('french') ? 'fn' : 'htt';
      
      // Build subscriptions with costs and resource groups
      const subscriptions = (t.subscriptions || []).map(sub => {
        const subResources = resources.filter(r => r.subscriptionId === sub.subscriptionId);
        const rgMap = new Map();
        subResources.forEach(r => {
          const rg = r.resourceGroup || 'default';
          if (!rgMap.has(rg)) rgMap.set(rg, { name: rg, resourceCount: 0, topResources: [] });
          const entry = rgMap.get(rg);
          entry.resourceCount++;
          if (entry.topResources.length < 3) entry.topResources.push(r.name);
        });
        
        return {
          id: sub.subscriptionId,
          name: sub.displayName || sub.subscriptionId,
          mtdCost: costBySubscription.get(sub.subscriptionId) || 0,
          purpose: sub.displayName?.includes('Dev') ? 'Development & Testing' :
                   sub.displayName?.includes('FABRIC') ? 'Analytics & BI' :
                   sub.displayName?.includes('Web') ? 'Web Integrations' : 'Core Infrastructure',
          resourceGroups: Array.from(rgMap.values())
        };
      });
      
      return {
        id,
        name: t.tenantName,
        displayName: id.toUpperCase(),
        tenantId: t.tenantId,
        role: isAnchor ? 'anchor' : 'spoke',
        domain: t.defaultDomain || t.organizationDisplayName || t.tenantName,
        billingModel: isAnchor ? 'Logically MSP (CSP)' :
                      id === 'bcc' ? 'Direct Microsoft' :
                      id === 'tll' ? 'Sui Generis CSP' : 'FTG CSP',
        githubOrg: id === 'htt' ? 'HTT-BRANDS' :
                   id === 'bcc' ? 'Bishops-Co' :
                   id === 'tll' ? 'The-Lash-Lounge' : null,
        subscriptions
      };
    });
    
    // Calculate cost summary
    const totalMTD = Array.from(costByTenant.values()).reduce((a, b) => a + b, 0);
    const byTenant = {};
    topologyTenants.forEach(t => {
      byTenant[t.id] = costByTenant.get(t.tenantId) || 0;
    });
    
    // Top services
    const serviceMap = new Map();
    costRows.forEach(c => {
      const svc = c.serviceName || c.meterCategory || 'Other';
      serviceMap.set(svc, (serviceMap.get(svc) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
    });
    const topServices = Array.from(serviceMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name, cost]) => ({ name, cost }));
    
    // Build connections (identity flow from anchor to spokes)
    const anchorTenant = topologyTenants.find(t => t.role === 'anchor');
    const spokeTenants = topologyTenants.filter(t => t.role === 'spoke');
    const connections = anchorTenant ? [
      {
        id: 'b2b-identity',
        type: 'identity',
        subtype: 'B2B Guest Access',
        description: 'B2B guest accounts for cross-tenant access',
        targets: spokeTenants.map(t => t.id)
      },
      {
        id: 'devops-flow',
        type: 'devops',
        subtype: 'CI/CD Pipelines',
        description: 'GitHub Actions deploying to Azure subscriptions',
        targets: spokeTenants.map(t => t.id)
      }
    ] : [];
    
    return {
      description: 'HTT Brands Multi-tenant Azure + M365 Architecture',
      tenants: topologyTenants,
      connections,
      layers: {
        identity: { name: 'Identity', enabled: true },
        network: { name: 'Network', enabled: true },
        compute: { name: 'Compute', enabled: true },
        data: { name: 'Data', enabled: true },
        devops: { name: 'DevOps', enabled: true }
      },
      costSummary: {
        totalMTD,
        byTenant,
        topServices
      }
    };
  }

  /**
   * Render the interactive cloud topology diagram
   * Uses DashboardTopology module if available
   * @param {Object} data - Full dashboard data including cloudTopology
   */
  function renderTopologySection(data) {
    const container = document.getElementById("topology-container");
    if (!container) return;

    // Generate topology from existing data if not present
    const topology = data.cloudTopology || generateTopologyFromData(data);
    if (!topology || !topology.tenants || topology.tenants.length === 0) {
      container.innerHTML = `
        <div class="topology-empty">
          <div class="empty-icon">🗺️</div>
          <h3>Cloud Topology Not Available</h3>
          <p class="muted">No tenant data available to generate topology.</p>
          <p class="muted">Ensure data collection has completed successfully.</p>
        </div>
      `;
      return;
    }

    // Check for DashboardTopology module
    if (typeof window.DashboardTopology === "undefined") {
      console.warn("DashboardTopology module not loaded");
      container.innerHTML = `
        <div class="topology-empty">
          <div class="empty-icon">⚠️</div>
          <h3>Topology Module Not Loaded</h3>
          <p class="muted">The topology visualization module failed to load.</p>
          <p class="muted">Check browser console for errors.</p>
        </div>
      `;
      return;
    }

    // Render the topology using the module
    try {
      window.DashboardTopology.renderTopologyView(container, topology);
    } catch (err) {
      console.error("Failed to render topology:", err);
      container.innerHTML = `
        <div class="topology-empty">
          <div class="empty-icon">❌</div>
          <h3>Topology Render Error</h3>
          <p class="muted">${err.message}</p>
        </div>
      `;
    }
  }

  // ===== Main Render =====
  // ===== TASK-CENTRIC SECTIONS RENDERING (Phase 4 UX Redesign) =====

  const BRAND_SECTIONS = {
    htt: {
      key: 'htt',
      title: 'HTT (Head to Toe)',
      summaryEl: () => dom.brandHTTSummary,
      kpisEl: () => dom.brandHTTKpis,
      costChartEl: () => dom.brandHTTCostChart,
      licenseEl: () => dom.brandHTTLicenses,
      matchers: [/head to toe/i, /\bhtt\b/]
    },
    bishops: {
      key: 'bishops',
      title: 'Bishops',
      summaryEl: () => dom.brandBishopsSummary,
      kpisEl: () => dom.brandBishopsKpis,
      costChartEl: () => dom.brandBishopsCostChart,
      licenseEl: () => dom.brandBishopsLicenses,
      matchers: [/bishop/i]
    },
    lash: {
      key: 'lash',
      title: 'The Lash Lounge',
      summaryEl: () => dom.brandLashSummary,
      kpisEl: () => dom.brandLashKpis,
      costChartEl: () => dom.brandLashCostChart,
      licenseEl: () => dom.brandLashLicenses,
      matchers: [/lash lounge/i, /\btll\b/]
    },
    frenchies: {
      key: 'frenchies',
      title: 'Frenchies',
      summaryEl: () => dom.brandFrenchiesSummary,
      kpisEl: () => dom.brandFrenchiesKpis,
      costChartEl: () => dom.brandFrenchiesCostChart,
      licenseEl: () => dom.brandFrenchiesLicenses,
      matchers: [/frenchies/i, /fn\b/i]
    }
  };

  function normalizeBrandLabel(name) {
    return (name || 'Unknown')
      .replace("Head to Toe Brands (anchor)", "HTT")
      .replace("The Lash Lounge", "TLL")
      .replace("Frenchies", "FN")
      .replace("Bishops", "BCC");
  }

  function findBrandTenants(data, brandKey) {
    const cfg = BRAND_SECTIONS[brandKey];
    if (!cfg) return [];
    return (data.tenants || []).filter(t => 
      cfg.matchers.some(rx => rx.test(t.tenantName || t.name || ""))
    );
  }

  function filterCostsForTenants(data, tenantIds, selection) {
    const range = computeFilterRange(selection.period);
    if (!range) return [];
    const tenantSet = new Set(tenantIds);
    return (data.costRows || []).filter(row => {
      if (!tenantSet.has(row.tenantId)) return false;
      if (selection.subscription && row.subscriptionId !== selection.subscription) return false;
      if (row.date) {
        const d = parseDate(row.date);
        return d ? dateInRange(d, range.from, range.to) : false;
      }
      if (row.mtdCost !== undefined) {
        const now = new Date();
        const start = startOfMonth(now);
        const end = endOfMonth(now);
        return range.from <= end && range.to >= start;
      }
      return true;
    });
  }

  function summarizeLicensesForTenants(data, tenantIds) {
    const tenantSet = new Set(tenantIds);
    const licenses = (data.license || []).filter(l => tenantSet.has(l.tenantId));
    
    let paidConsumed = 0;
    let paidPrepaid = 0;
    let totalUsers = 0;
    const paidSkus = [];

    licenses.forEach(l => {
      const skus = l.skuAssignments || l.subscribedSkus || [];
      skus.forEach(sku => {
        if (!isPaidSku(sku.skuPartNumber)) return;
        const consumed = sku.consumedUnits || 0;
        const prepaid = sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 0;
        paidConsumed += consumed;
        paidPrepaid += prepaid;
        paidSkus.push({
          sku: sku.skuPartNumber || sku.skuId,
          consumed,
          prepaid,
          utilization: prepaid > 0 ? (consumed / prepaid) * 100 : 0
        });
      });
      totalUsers += l.userAssignments?.length || 0;
    });

    const utilization = paidPrepaid > 0 ? (paidConsumed / paidPrepaid) * 100 : 0;
    return { paidConsumed, paidPrepaid, utilization, totalUsers, paidSkus };
  }

  function countInactiveUsersForTenants(data, tenantIds) {
    const users = data.users || {};
    const now = new Date();
    const tenantSet = new Set(tenantIds);
    let inactive = 0;

    Object.entries(users).forEach(([tenantId, userList]) => {
      if (!tenantSet.has(tenantId)) return;
      userList.forEach(user => {
        const last = user.lastSignInDateTime ? new Date(user.lastSignInDateTime) : null;
        const days = last ? Math.floor((now - last) / (24 * 60 * 60 * 1000)) : Infinity;
        if (days >= 30 && user.accountEnabled) inactive++;
      });
    });
    return inactive;
  }

  function renderBrandSection(data, selection, brandKey) {
    const cfg = BRAND_SECTIONS[brandKey];
    if (!cfg) return;

    const summaryEl = cfg.summaryEl();
    const kpisEl = cfg.kpisEl();
    const costCanvas = cfg.costChartEl();
    const licenseEl = cfg.licenseEl();

    // If no containers exist, skip rendering
    if (!summaryEl && !kpisEl && !costCanvas && !licenseEl) return;

    const tenants = findBrandTenants(data, brandKey);
    const tenantIds = tenants.map(t => t.tenantId);
    const costs = filterCostsForTenants(data, tenantIds, selection);
    const resources = (data.resources || []).filter(r => tenantIds.includes(r.tenantId));
    const subscriptions = tenants.flatMap(t => t.subscriptions || []);
    const licenseSummary = summarizeLicensesForTenants(data, tenantIds);
    const inactiveUsers = countInactiveUsersForTenants(data, tenantIds);

    const totalCost = costs.reduce((sum, r) => sum + (r.dailyCost ?? r.mtdCost ?? 0), 0);
    const topService = costs
      .reduce((map, c) => {
        const key = c.serviceName || c.meterCategory || "Other";
        map.set(key, (map.get(key) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
        return map;
      }, new Map());
    const topServiceEntry = Array.from(topService.entries()).sort((a, b) => b[1] - a[1])[0];

    if (summaryEl) {
      summaryEl.innerHTML = `
        <div class="brand-hero">
          <div class="brand-title">${cfg.title}</div>
          <div class="brand-meta">
            <span>${tenants.length} tenant${tenants.length === 1 ? '' : 's'}</span>
            <span>${subscriptions.length} subscription${subscriptions.length === 1 ? '' : 's'}</span>
            <span>${resources.length} resources</span>
          </div>
          <div class="brand-highlight">
            <div><strong>${formatCurrency(totalCost)}</strong><span class="muted"> MTD spend</span></div>
            <div><strong>${formatPercent(licenseSummary.utilization)}</strong><span class="muted"> paid license util.</span></div>
            <div><strong>${inactiveUsers}</strong><span class="muted"> inactive users</span></div>
          </div>
        </div>
      `;
    }

    if (kpisEl) {
      kpisEl.innerHTML = `
        <div class="kpi">
          <div class="label">MTD Spend</div>
          <div class="value">${formatCurrency(totalCost)}</div>
          <div class="delta muted">${topServiceEntry ? `${topServiceEntry[0]} leading` : 'Awaiting cost data'}</div>
        </div>
        <div class="kpi">
          <div class="label">Subscriptions</div>
          <div class="value">${subscriptions.length}</div>
          <div class="delta muted">${tenants.length} tenant${tenants.length === 1 ? '' : 's'}</div>
        </div>
        <div class="kpi">
          <div class="label">Paid License Utilization</div>
          <div class="value ${licenseSummary.utilization > 90 ? 'danger' : licenseSummary.utilization > 70 ? 'warning' : 'success'}">
            ${formatPercent(licenseSummary.utilization)}
          </div>
          <div class="delta muted">${formatNumber(licenseSummary.paidConsumed)} of ${formatNumber(licenseSummary.paidPrepaid)} consumed</div>
        </div>
        <div class="kpi">
          <div class="label">Inactive (30d)</div>
          <div class="value ${inactiveUsers > 0 ? 'warning' : ''}">${inactiveUsers}</div>
          <div class="delta muted">Users with paid licenses</div>
        </div>
      `;
    }

    if (costCanvas) {
      const byService = new Map();
      costs.forEach(c => {
        const key = c.serviceName || c.meterCategory || "Other";
        byService.set(key, (byService.get(key) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
      });
      const serviceData = Array.from(byService.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6);
      if (charts[`brand-${brandKey}-costs`]) charts[`brand-${brandKey}-costs`].destroy();
      charts[`brand-${brandKey}-costs`] = new Chart(costCanvas, {
        type: "bar",
        data: {
          labels: serviceData.map(s => s[0]),
          datasets: [{
            data: serviceData.map(s => s[1]),
            backgroundColor: "#3b82f6"
          }]
        },
        options: {
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: "#1f2937" }, ticks: { color: "#9ca3af", callback: v => "$" + v.toLocaleString() } },
            x: { grid: { display: false }, ticks: { color: "#9ca3af" } },
          }
        }
      });
    }

    if (licenseEl) {
      const paidSkus = licenseSummary.paidSkus.sort((a, b) => b.consumed - a.consumed).slice(0, 4);
      if (paidSkus.length === 0) {
        licenseEl.innerHTML = `<p class="muted">No paid license data for this brand.</p>`;
      } else {
        licenseEl.innerHTML = paidSkus.map(s => `
          <div class="mini-kpi">
            <div class="label">${s.sku}</div>
            <div class="value">${formatNumber(s.consumed)} / ${formatNumber(s.prepaid)}</div>
            <div class="delta ${s.utilization > 90 ? 'danger' : s.utilization > 70 ? 'warning' : 'success'}">
              ${formatPercent(s.utilization)} utilized
            </div>
          </div>
        `).join("");
      }
    }
  }

  function renderAllBrandSections(data, selection) {
    Object.keys(BRAND_SECTIONS).forEach(key => renderBrandSection(data, selection, key));
  }

  function renderCostManagementSection(data, selection) {
    const kpiEl = dom.costMgmtKpis;
    const wasteListEl = dom.costWasteList;
    const forecastEl = dom.costForecastSummary;
    const budgetAlert = dom.costBudgetAlert;
    const budgetMessage = dom.costBudgetMessage;

    const costs = filterCostRows(data, selection);
    const totalCost = costs.reduce((sum, r) => sum + (r.dailyCost ?? r.mtdCost ?? 0), 0);
    const range = computeFilterRange(selection.period);
    const daysInRange = range ? Math.max(1, Math.floor((range.to - range.from) / (24 * 60 * 60 * 1000)) + 1) : 1;
    const avgDaily = daysInRange > 0 ? totalCost / daysInRange : 0;
    const subscriptions = (data.tenants || []).filter(t => !selection.tenant || t.tenantId === selection.tenant)
      .flatMap(t => t.subscriptions || []);
    const recommendations = generateRecommendations(data, selection);
    const potentialSavings = recommendations.reduce((sum, r) => sum + (r.savings || 0), 0);

    if (kpiEl) {
      kpiEl.innerHTML = `
        <div class="kpi">
          <div class="label">MTD Spend</div>
          <div class="value">${formatCurrency(totalCost)}</div>
          <div class="delta muted">Across ${subscriptions.length} subscription${subscriptions.length === 1 ? '' : 's'}</div>
        </div>
        <div class="kpi">
          <div class="label">Avg Daily</div>
          <div class="value">${formatCurrency(avgDaily)}</div>
          <div class="delta muted">${selection.period.toUpperCase()} window</div>
        </div>
        <div class="kpi">
          <div class="label">Potential Savings</div>
          <div class="value ${potentialSavings > 0 ? 'warning' : 'success'}">${formatCurrency(potentialSavings)}</div>
          <div class="delta muted">${recommendations.length} opportunities</div>
        </div>
        <div class="kpi">
          <div class="label">Budget Utilization</div>
          <div class="value">${formatPercent((totalCost / (cfg.budgetMonthly || 15000)) * 100)}</div>
          <div class="delta muted">Monthly budget ${formatCurrency(cfg.budgetMonthly || 15000)}</div>
        </div>
      `;
    }

    if (budgetAlert) {
      const budgetMonthly = cfg.budgetMonthly || 15000;
      const utilization = budgetMonthly > 0 ? totalCost / budgetMonthly : 0;
      const alerting = utilization >= 0.8;
      budgetAlert.style.display = alerting ? '' : 'none';
      if (budgetMessage) {
        budgetMessage.textContent = alerting
          ? `Tracking at ${(utilization * 100).toFixed(1)}% of budget (${formatCurrency(totalCost)} of ${formatCurrency(budgetMonthly)})`
          : 'On track against configured budget.';
      }
    }

    // Cost by brand chart
    if (dom.costByBrandChart) {
      const byBrand = new Map();
      costs.forEach(c => {
        const brand = normalizeBrandLabel(c.tenantName || "Unknown");
        byBrand.set(brand, (byBrand.get(brand) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
      });
      const brandData = Array.from(byBrand.entries()).sort((a, b) => b[1] - a[1]);
      if (charts.costMgmtByBrand) charts.costMgmtByBrand.destroy();
      charts.costMgmtByBrand = new Chart(dom.costByBrandChart, {
        type: "doughnut",
        data: {
          labels: brandData.map(b => b[0]),
          datasets: [{
            data: brandData.map(b => b[1]),
            backgroundColor: ["#3b82f6", "#8b5cf6", "#f59e0b", "#10b981"]
          }]
        },
        options: { plugins: { legend: { position: "right", labels: { color: "#9ca3af" } } } }
      });
    }

    // Cost trend chart
    if (dom.costTrendChart) {
      const monthlyTotals = getMonthlyTotals(data, selection, { limitToRange: false }).slice(-12);
      if (charts.costMgmtTrend) charts.costMgmtTrend.destroy();
      charts.costMgmtTrend = new Chart(dom.costTrendChart, {
        type: "line",
        data: {
          labels: monthlyTotals.map(([month]) => month),
          datasets: [{
            label: "Monthly Spend",
            data: monthlyTotals.map(([, total]) => total),
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.15)",
            fill: true,
            tension: 0.3
          }]
        },
        options: {
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: "#1f2937" }, ticks: { color: "#9ca3af", callback: v => "$" + v.toLocaleString() } },
            x: { grid: { display: false }, ticks: { color: "#9ca3af" } }
          }
        }
      });
    }

    if (forecastEl) {
      const now = new Date();
      const daysInMonth = new Date(now.getUTCFullYear(), now.getUTCMonth() + 1, 0).getUTCDate();
      const dayOfMonth = now.getUTCDate();
      const currentMonthCosts = costs.filter(c => c.date && c.date.startsWith(formatMonthKey(now)))
        .reduce((sum, c) => sum + (c.dailyCost ?? 0), 0);
      const dailyAvg = dayOfMonth > 0 ? currentMonthCosts / dayOfMonth : 0;
      const projected = dailyAvg * daysInMonth;
      forecastEl.innerHTML = `
        <div class="forecast-summary">
          <div><strong>${formatCurrency(currentMonthCosts)}</strong><span class="muted"> month-to-date</span></div>
          <div><strong>${formatCurrency(projected)}</strong><span class="muted"> projected EOM</span></div>
          <div><strong>${formatCurrency(cfg.budgetMonthly || 15000)}</strong><span class="muted"> budget</span></div>
        </div>
      `;
    }

    if (wasteListEl) {
      if (recommendations.length === 0) {
        wasteListEl.innerHTML = `<p class="muted">No optimization opportunities detected for the current filters.</p>`;
      } else {
        wasteListEl.innerHTML = recommendations.slice(0, 5).map(r => `
          <div class="recommendation-card ${r.priority}">
            <div class="title">${r.icon || '💡'} ${r.title}</div>
            <div class="meta">${r.category} · ${r.effort || 'Effort n/a'}</div>
            <div class="impact">${r.savings ? formatCurrency(r.savings) + '/mo' : 'Impact pending'}</div>
            <div class="desc">${r.description || ''}</div>
          </div>
        `).join("");
      }
    }
  }

  function collectLicenseWasteCases(data, selection) {
    const licenses = filterLicenses(data, selection);
    const users = data.users || {};
    const now = new Date();
    const cases = [];

    licenses.forEach(l => {
      const tenantUsers = users[l.tenantId] || [];
      const userMap = new Map(tenantUsers.map(u => [(u.id || u.userPrincipalName || "").toLowerCase(), u]));
      const skuLookup = new Map();
      (l.subscribedSkus || l.skuAssignments || []).forEach(sku => {
        skuLookup.set(sku.skuId, sku);
      });

      (l.userAssignments || []).forEach(assign => {
        const user = userMap.get((assign.userId || "").toLowerCase());
        const last = user?.lastSignInDateTime ? new Date(user.lastSignInDateTime) : null;
        const days = last ? Math.floor((now - last) / (24 * 60 * 60 * 1000)) : Infinity;
        const bucket = days >= 90 ? 'critical' : days >= 60 ? 'high' : days >= 30 ? 'medium' : null;
        if (!bucket) return;

        const paidSkuIds = (assign.skuIds || []).filter(id => {
          const sku = skuLookup.get(id);
          return sku && isPaidSku(sku.skuPartNumber);
        });
        if (paidSkuIds.length === 0) return;

        const estCost = paidSkuIds.reduce((sum, id) => {
          const sku = skuLookup.get(id);
          return sum + (getSkuPrice(sku?.skuPartNumber) || 0);
        }, 0);

        cases.push({
          bucket,
          tenant: l.tenantName,
          user: user?.displayName || user?.mail || assign.userId,
          daysInactive: days === Infinity ? 999 : days,
          estCost
        });
      });
    });

    return cases;
  }

  function renderWasteList(container, items, emptyMessage) {
    if (!container) return;
    if (items.length === 0) {
      container.innerHTML = `<p class="muted">${emptyMessage}</p>`;
      return;
    }
    container.innerHTML = items.map(item => `
      <div class="waste-item">
        <div class="waste-main">
          <strong>${item.user}</strong> <span class="muted">· ${normalizeBrandLabel(item.tenant)}</span>
        </div>
        <div class="waste-meta">
          <span>${item.daysInactive === 999 ? 'No sign-in' : item.daysInactive + 'd inactive'}</span>
          <span class="muted">${item.estCost ? formatCurrency(item.estCost) + '/mo' : 'Cost est. pending'}</span>
        </div>
      </div>
    `).join("");
  }

  function renderLicenseOptimizationSection(data, selection) {
    const kpiEl = dom.licenseOptKpis;
    const alertEl = dom.licenseWasteAlert;
    const alertMsg = dom.licenseWasteMessage;
    const wasteCases = collectLicenseWasteCases(data, selection);

    const licenses = filterLicenses(data, selection);
    const tenantIds = licenses.map(l => l.tenantId);
    const licenseSummary = summarizeLicensesForTenants(data, tenantIds);
    const totalWaste = wasteCases.reduce((sum, c) => sum + (c.estCost || 0), 0);

    if (kpiEl) {
      kpiEl.innerHTML = `
        <div class="kpi">
          <div class="label">Paid Utilization</div>
          <div class="value">${formatPercent(licenseSummary.utilization)}</div>
          <div class="delta muted">${formatNumber(licenseSummary.paidConsumed)} of ${formatNumber(licenseSummary.paidPrepaid)} consumed</div>
        </div>
        <div class="kpi">
          <div class="label">Inactive Users</div>
          <div class="value ${wasteCases.length > 0 ? 'warning' : 'success'}">${wasteCases.length}</div>
          <div class="delta muted">30+ days inactive with paid SKUs</div>
        </div>
        <div class="kpi">
          <div class="label">Est. Waste</div>
          <div class="value ${totalWaste > 0 ? 'danger' : ''}">${formatCurrency(totalWaste)}</div>
          <div class="delta muted">Monthly estimate</div>
        </div>
        <div class="kpi">
          <div class="label">Assigned Users</div>
          <div class="value">${formatNumber(licenseSummary.totalUsers)}</div>
          <div class="delta muted">Across ${licenses.length} tenant${licenses.length === 1 ? '' : 's'}</div>
        </div>
      `;
    }

    if (alertEl) {
      alertEl.style.display = wasteCases.length > 0 ? '' : 'none';
      if (alertMsg) {
        alertMsg.textContent = wasteCases.length > 0
          ? `${wasteCases.length} inactive paid license holder${wasteCases.length === 1 ? '' : 's'} detected`
          : 'License waste is under control.';
      }
    }

    const critical = wasteCases.filter(c => c.bucket === 'critical');
    const high = wasteCases.filter(c => c.bucket === 'high');
    const medium = wasteCases.filter(c => c.bucket === 'medium');

    renderWasteList(dom.criticalWasteList, critical, 'No 90+ day inactive users.');
    renderWasteList(dom.highWasteList, high, 'No 60-89 day inactive users.');
    renderWasteList(dom.mediumWasteList, medium, 'No 30-59 day inactive users.');

    if (dom.fixWasteBtn && !dom.fixWasteBtn.dataset.bound) {
      dom.fixWasteBtn.dataset.bound = 'true';
      dom.fixWasteBtn.addEventListener('click', () => {
        navigateToSection('user-licenses');
        document.getElementById('section-user-licenses')?.scrollIntoView({ behavior: 'smooth' });
      });
    }
  }
  
  /**
   * Render new task-centric sections by directly calling rendering functions
   * instead of cloning (which doesn't work when source sections haven't rendered yet)
   */
  function renderTaskCentricSections(data, selection) {
    renderCostManagementSection(data, selection);
    renderLicenseOptimizationSection(data, selection);
    renderAllBrandSections(data, selection);
  }

  // ===== MAIN RENDER FUNCTION =====

  function render() {
    try {
      console.log('[dashboard.render] Called with rawData:', rawData ? 'EXISTS' : 'NULL');
      if (!rawData) {
        console.error('[dashboard.render] rawData is null, cannot render');
        showErrorState('No data available for rendering');
        return;
      }
      console.log('[dashboard.render] rawData.costRows:', rawData.costRows?.length || 0);
      console.log('[dashboard.render] rawData.licenses:', rawData.licenses ? Object.keys(rawData.licenses).length : 0);
      
      const selection = getSelection();
      console.log('[dashboard.render] Selection:', selection);

      console.log('[dashboard.render] Calling renderMeta...');
      renderMeta(rawData);
      console.log('[dashboard.render] Calling renderDataHealth...');
      renderDataHealth(rawData, selection);
      console.log('[dashboard.render] Calling updateSidebarCounts...');
      updateSidebarCounts(rawData);
    
    // Overview section
    renderKpis(rawData, selection);
    renderTenantSummary(rawData, selection);
    renderCharts(rawData, selection);
    renderAzureInsights(rawData, selection);
    renderLicenseInsights(rawData, selection);
    renderTopMovers(rawData, selection);

    // Recommendations section (NEW)
    renderRecommendations(rawData, selection);

    // Tenants section
    renderTenantsTable(rawData);

    // Management groups section
    renderManagementGroupsTree(rawData);

    // Subscriptions section
    renderSubscriptionsTable(rawData, selection);

    // Resource groups section
    renderResourceGroupsTable(rawData, selection);

    // Resources section
    renderResourcesTable(rawData, selection);

    // Cost breakdown section
    renderCostBreakdown(rawData, selection);

    // License sections
    renderLicenseKpis(rawData, selection);
    renderLicenseSummaryTable(rawData, selection);
    renderLicensesTable(rawData, selection);
    renderUserLicensesTable(rawData, selection);

    // Invoice Reconciliation section
    renderInvoiceReconKpis(rawData);
    renderInvoiceReconTable(rawData);
    renderLicenseCostTable(rawData);
    renderInvoiceCharts(rawData);

    // Identity sections
    renderIdentityUsersKpis(rawData);
    renderIdentityUsersTable(rawData);
    renderIdentityAppsKpis(rawData);
    renderIdentityAppsTable(rawData);
    renderIdentityAppregsKpis(rawData);
    renderIdentityAppregsTable(rawData);
    renderIdentityCapKpis(rawData);
    renderIdentityCapTable(rawData);

    // GitHub sections
    renderGitHubBillingKpis(rawData);
    renderGitHubBillingTable(rawData);
    renderGitHubBillingCharts(rawData);

    // Topology section - renders interactive cloud architecture diagram
    renderTopologySection(rawData);

    // NEW: Populate task-centric sections (Phase 4 UX redesign)
    renderTaskCentricSections(rawData, selection);
    
    } catch (e) {
      console.error('[dashboard.render] ❌ Critical error during render:', e);
      console.error(e.stack);
      showErrorState('Dashboard rendering error: ' + e.message);
    }
  }

  // ===== Event Handlers =====
  function onPeriodChange() {
    const isCustom = dom.period.value === "custom";
    document.querySelectorAll(".date-range").forEach(el => {
      el.classList.toggle("visible", isCustom);
    });
    render();
  }

  function bindControls() {
    dom.period.addEventListener("change", onPeriodChange);
    dom.from.addEventListener("change", render);
    dom.to.addEventListener("change", render);
    dom.tenant.addEventListener("change", () => {
      // Cascade: update subscription dropdown when tenant changes
      updateSubscriptionDropdown(rawData, dom.tenant.value);
      render();
    });
    dom.subscription.addEventListener("change", render);

    dom.refreshBtn.addEventListener("click", async () => {
      dom.refreshBtn.disabled = true;
      dom.refreshBtn.innerHTML = '<span class="btn-icon">↻</span> Loading...';
      try {
        rawData = await fetchData();
        buildSelections(rawData);
        render();
      } catch (err) {
        alert(`Failed to refresh: ${err.message}`);
      } finally {
        dom.refreshBtn.disabled = false;
        dom.refreshBtn.innerHTML = '<span class="btn-icon">↻</span> Refresh';
      }
    });

    dom.triggerBtn?.addEventListener("click", () => {
      if (cfg.refreshWorkflowUrl) {
        window.open(cfg.refreshWorkflowUrl, "_blank");
      } else {
        alert("No refresh workflow URL configured");
      }
    });

    // Take Action button on recommendations page
    const takeActionBtn = document.getElementById('take-action-btn');
    if (takeActionBtn) {
      takeActionBtn.addEventListener('click', () => {
        // Navigate to the critical recommendations section
        const criticalSection = document.getElementById('critical-recommendations');
        if (criticalSection) {
          criticalSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    }
    
    // Phase 2: Bookmark and Views buttons
    const bookmarkBtn = document.getElementById('bookmark-btn');
    if (bookmarkBtn) {
      bookmarkBtn.addEventListener('click', saveCurrentView);
    }
    
    const viewsBtn = document.getElementById('views-btn');
    if (viewsBtn) {
      viewsBtn.addEventListener('click', showViewsModal);
    }
    
    const viewsModalClose = document.getElementById('views-modal-close');
    if (viewsModalClose) {
      viewsModalClose.addEventListener('click', closeViewsModal);
    }
    
    // Close modal on overlay click
    const viewsModal = document.getElementById('views-modal');
    if (viewsModal) {
      viewsModal.addEventListener('click', (e) => {
        if (e.target === viewsModal || e.target.classList.contains('modal-overlay')) {
          closeViewsModal();
        }
      });
    }
    
    // Budget alert action button
    const budgetAlertAction = document.getElementById('budget-alert-action');
    if (budgetAlertAction) {
      budgetAlertAction.addEventListener('click', () => {
        navigateToSection('costs', { updateHistory: true });
      });
    }
    
    // Hero banner action buttons
    const budgetDetailsBtn = document.getElementById('budget-details-btn');
    if (budgetDetailsBtn) {
      budgetDetailsBtn.addEventListener('click', () => {
        navigateToSection('cost-licenses', { updateHistory: true });
      });
    }
    
    const budgetForecastBtn = document.getElementById('budget-forecast-btn');
    if (budgetForecastBtn) {
      budgetForecastBtn.addEventListener('click', () => {
        navigateToSection('overview', { updateHistory: false });
        // Scroll to forecast section
        setTimeout(() => {
          const forecastSection = document.querySelector('#section-overview .card h3:contains("Forecasting")');
          if (forecastSection) {
            forecastSection.closest('.card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }, 100);
      });
    }
    
    // Email digest modal
    const emailDigestBtn = document.getElementById('email-digest-btn');
    if (emailDigestBtn) {
      emailDigestBtn.addEventListener('click', showEmailDigestModal);
    }
    
    const emailModalClose = document.getElementById('email-modal-close');
    if (emailModalClose) {
      emailModalClose.addEventListener('click', closeEmailDigestModal);
    }
    
    const emailPreferencesForm = document.getElementById('email-preferences-form');
    if (emailPreferencesForm) {
      emailPreferencesForm.addEventListener('submit', saveEmailPreferences);
    }
    
    const emailPreviewBtn = document.getElementById('email-preview-btn');
    if (emailPreviewBtn) {
      emailPreviewBtn.addEventListener('click', previewEmailDigest);
    }
    
    // Close email modal on overlay click
    const emailModal = document.getElementById('email-modal');
    if (emailModal) {
      emailModal.addEventListener('click', (e) => {
        if (e.target === emailModal || e.target.classList.contains('modal-overlay')) {
          closeEmailDigestModal();
        }
      });
    }
  }

  function renderTopMovers(data, selection) {
    if (!dom.topMoversTenants || !dom.topMoversServices) return;

    // Tenant movers
    const tenantMonthly = getTenantMonthlyTotals(data, selection);
    const tenants = data.tenants || [];
    const tenantMovers = [];
    tenantMonthly.forEach((monthMap, tenantId) => {
      const label = tenants.find(t => t.tenantId === tenantId)?.tenantName || tenantId;
      const months = [...monthMap.entries()].sort((a, b) => a[0].localeCompare(b[0]));
      if (months.length < 2) return;
      const [prevMonth, prevVal] = months[months.length - 2];
      const [latestMonth, latestVal] = months[months.length - 1];
      const delta = latestVal - prevVal;
      const pct = prevVal ? (delta / prevVal) * 100 : null;
      tenantMovers.push({ label, delta, pct, latestMonth, prevMonth });
    });
    tenantMovers.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    const topTenants = tenantMovers.slice(0, 5);

    dom.topMoversTenants.innerHTML = topTenants.length ? topTenants.map(m => `
      <li>
        <div class="insight-title">${m.label}</div>
        <div class="insight-meta">${m.prevMonth} → ${m.latestMonth}</div>
        <div class="insight-badge">${m.delta >= 0 ? "Increase" : "Decrease"}</div>
        <div class="insight-meta">${formatCurrency(m.delta)} (${m.pct === null ? "n/a" : formatPercent(m.pct)})</div>
      </li>
    `).join("") : `<li class="muted">Not enough history to calculate tenant movers.</li>`;

    // Service movers (uses serviceMonthlyCosts if present, otherwise derives from dated costRows)
    const serviceMonthly = getServiceMonthlyTotals(data, selection);
    const serviceMovers = [];
    serviceMonthly.forEach((monthMap, service) => {
      const months = [...monthMap.entries()].sort((a, b) => a[0].localeCompare(b[0]));
      if (months.length < 2) return;
      const [prevMonth, prevVal] = months[months.length - 2];
      const [latestMonth, latestVal] = months[months.length - 1];
      const delta = latestVal - prevVal;
      const pct = prevVal ? (delta / prevVal) * 100 : null;
      serviceMovers.push({ label: service, delta, pct, latestMonth, prevMonth });
    });
    serviceMovers.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    const topServices = serviceMovers.slice(0, 5);

    dom.topMoversServices.innerHTML = topServices.length ? topServices.map(m => `
      <li>
        <div class="insight-title">${m.label}</div>
        <div class="insight-meta">${m.prevMonth} → ${m.latestMonth}</div>
        <div class="insight-badge">${m.delta >= 0 ? "Increase" : "Decrease"}</div>
        <div class="insight-meta">${formatCurrency(m.delta)} (${m.pct === null ? "n/a" : formatPercent(m.pct)})</div>
      </li>
    `).join("") : `<li class="muted">Not enough history to calculate service movers.</li>`;
  }

  // ===== Phase 3: ML Forecasting =====
  function generateForecast(data, method = 'linear-regression', horizon = 3) {
    const selection = getSelection();
    const monthlyTotals = getMonthlyTotals(data, selection);
    
    if (monthlyTotals.length < 3) {
      return { error: 'Insufficient historical data (minimum 3 months required)' };
    }
    
    // Prepare time series data
    const timeSeries = monthlyTotals.map((item, index) => ({
      x: index,
      y: item.totalCost,
      month: item.month
    }));
    
    let predictions = [];
    
    if (method === 'linear-regression') {
      // Calculate linear regression coefficients
      const n = timeSeries.length;
      const sumX = timeSeries.reduce((sum, p) => sum + p.x, 0);
      const sumY = timeSeries.reduce((sum, p) => sum + p.y, 0);
      const sumXY = timeSeries.reduce((sum, p) => sum + p.x * p.y, 0);
      const sumX2 = timeSeries.reduce((sum, p) => sum + p.x * p.x, 0);
      
      const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
      const intercept = (sumY - slope * sumX) / n;
      
      // Calculate confidence interval (standard error)
      const yPredicted = timeSeries.map(p => slope * p.x + intercept);
      const residuals = timeSeries.map((p, i) => p.y - yPredicted[i]);
      const sse = residuals.reduce((sum, r) => sum + r * r, 0);
      const standardError = Math.sqrt(sse / (n - 2));
      
      // Generate predictions for next horizon months
      for (let i = 1; i <= horizon; i++) {
        const x = n + i - 1;
        const predicted = slope * x + intercept;
        const margin = 1.96 * standardError; // 95% confidence interval
        
        predictions.push({
          value: Math.max(0, predicted),
          lower: Math.max(0, predicted - margin),
          upper: predicted + margin,
          confidence: 0.95
        });
      }
    } else if (method === 'exponential-smoothing') {
      // Simple exponential smoothing with alpha = 0.3
      const alpha = 0.3;
      let smoothed = timeSeries[0].y;
      
      for (let i = 1; i < timeSeries.length; i++) {
        smoothed = alpha * timeSeries[i].y + (1 - alpha) * smoothed;
      }
      
      // Use last smoothed value as prediction with increasing uncertainty
      for (let i = 1; i <= horizon; i++) {
        const margin = smoothed * 0.1 * i; // 10% margin per month
        predictions.push({
          value: smoothed,
          lower: Math.max(0, smoothed - margin),
          upper: smoothed + margin,
          confidence: Math.max(0.5, 0.95 - 0.1 * i)
        });
      }
    } else if (method === 'moving-average') {
      // Use 3-month moving average
      const windowSize = Math.min(3, timeSeries.length);
      const recentValues = timeSeries.slice(-windowSize).map(p => p.y);
      const average = recentValues.reduce((sum, v) => sum + v, 0) / windowSize;
      const stdDev = Math.sqrt(
        recentValues.reduce((sum, v) => sum + Math.pow(v - average, 2), 0) / windowSize
      );
      
      for (let i = 1; i <= horizon; i++) {
        const margin = 1.96 * stdDev;
        predictions.push({
          value: average,
          lower: Math.max(0, average - margin),
          upper: average + margin,
          confidence: 0.95
        });
      }
    }
    
    return {
      method,
      historical: timeSeries,
      predictions,
      horizon,
      lastMonth: monthlyTotals[monthlyTotals.length - 1].month
    };
  }
  
  function renderForecastChart(forecast) {
    const canvas = document.getElementById('forecast-chart');
    if (!canvas || forecast.error) return;
    
    const ctx = canvas.getContext('2d');
    
    // Destroy existing chart
    if (charts.forecast) {
      charts.forecast.destroy();
    }
    
    // Generate future month labels
    const lastMonth = forecast.lastMonth;
    const lastDate = new Date(lastMonth + '-01');
    const futureMonths = [];
    for (let i = 1; i <= forecast.horizon; i++) {
      const futureDate = new Date(lastDate);
      futureDate.setMonth(futureDate.getMonth() + i);
      futureMonths.push(futureDate.toISOString().slice(0, 7));
    }
    
    const labels = [...forecast.historical.map(h => h.month), ...futureMonths];
    const historicalData = forecast.historical.map(h => h.y);
    const predictionData = new Array(forecast.historical.length).fill(null).concat(
      forecast.predictions.map(p => p.value)
    );
    const lowerBound = new Array(forecast.historical.length).fill(null).concat(
      forecast.predictions.map(p => p.lower)
    );
    const upperBound = new Array(forecast.historical.length).fill(null).concat(
      forecast.predictions.map(p => p.upper)
    );
    
    charts.forecast = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Historical',
            data: historicalData,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            fill: true,
            tension: 0.4
          },
          {
            label: 'Forecast',
            data: predictionData,
            borderColor: '#8b5cf6',
            backgroundColor: 'rgba(139, 92, 246, 0.1)',
            borderDash: [5, 5],
            fill: false,
            tension: 0.4
          },
          {
            label: 'Lower Bound',
            data: lowerBound,
            borderColor: 'rgba(139, 92, 246, 0.3)',
            backgroundColor: 'transparent',
            borderDash: [2, 2],
            fill: false,
            pointRadius: 0
          },
          {
            label: 'Upper Bound',
            data: upperBound,
            borderColor: 'rgba(139, 92, 246, 0.3)',
            backgroundColor: 'rgba(139, 92, 246, 0.05)',
            borderDash: [2, 2],
            fill: '-1',
            pointRadius: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: 'top'
          },
          tooltip: {
            mode: 'index',
            intersect: false,
            callbacks: {
              label: function(context) {
                let label = context.dataset.label || '';
                if (label) {
                  label += ': ';
                }
                if (context.parsed.y !== null) {
                  label += formatCurrency(context.parsed.y);
                }
                return label;
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: value => formatCurrency(value)
            }
          }
        }
      }
    });
  }
  
  function renderForecastKpis(forecast) {
    const container = document.getElementById('forecast-kpis');
    if (!container || forecast.error) {
      if (container) {
        container.innerHTML = `<div class="kpi"><div class="value danger">${forecast.error}</div></div>`;
      }
      return;
    }
    
    const nextMonth = forecast.predictions[0];
    const threeMonthTotal = forecast.predictions.reduce((sum, p) => sum + p.value, 0);
    const avgConfidence = forecast.predictions.reduce((sum, p) => sum + p.confidence, 0) / forecast.predictions.length;
    
    container.innerHTML = `
      <div class="kpi">
        <div class="label">Next Month Forecast</div>
        <div class="value">${formatCurrency(nextMonth.value)}</div>
        <div class="context">±${formatCurrency(nextMonth.value - nextMonth.lower)} (${formatPercent(avgConfidence * 100)} confidence)</div>
      </div>
      <div class="kpi">
        <div class="label">${forecast.horizon}-Month Projection</div>
        <div class="value">${formatCurrency(threeMonthTotal)}</div>
        <div class="context">Using ${forecast.method.replace('-', ' ')}</div>
      </div>
      <div class="kpi">
        <div class="label">Trend</div>
        <div class="value ${forecast.predictions[forecast.horizon - 1].value > forecast.historical[forecast.historical.length - 1].y ? 'danger' : 'success'}">
          ${forecast.predictions[forecast.horizon - 1].value > forecast.historical[forecast.historical.length - 1].y ? '📈 Increasing' : '📉 Decreasing'}
        </div>
        <div class="context">${formatPercent(((forecast.predictions[forecast.horizon - 1].value - forecast.historical[forecast.historical.length - 1].y) / forecast.historical[forecast.historical.length - 1].y) * 100)} vs current</div>
      </div>
    `;
  }
  
  // ===== Phase 3: Automated Actions =====
  function renderAutomatedActionsList() {
    const container = document.getElementById('automated-actions-list');
    if (!container) return;
    
    const config = window.DASHBOARD_CONFIG || {};
    const automation = config.automation || { enabled: false };
    
    if (!automation.enabled) {
      container.innerHTML = '<p class="muted">Automated actions are disabled. Enable in config.js to see available actions.</p>';
      return;
    }
    
    const actions = [
      {
        id: 'auto-tag',
        name: 'Auto-tag Untagged Resources',
        description: 'Automatically add default tags to resources missing cost center tags',
        enabled: automation.autoTag,
        lastRun: null,
        nextRun: 'Manual trigger required'
      },
      {
        id: 'auto-disable-inactive',
        name: 'Disable Inactive Users',
        description: 'Disable user accounts with no sign-in activity for 90+ days',
        enabled: automation.autoDisableInactive,
        lastRun: null,
        nextRun: 'Manual trigger required'
      },
      {
        id: 'auto-cleanup',
        name: 'Resource Cleanup',
        description: 'Remove orphaned disks, unused storage accounts, and idle VMs',
        enabled: automation.autoCleanup,
        lastRun: null,
        nextRun: 'Manual trigger required'
      }
    ];
    
    container.innerHTML = actions.map(action => `
      <div class="action-item ${action.enabled ? 'enabled' : 'disabled'}">
        <div class="action-header">
          <h4>${action.enabled ? '✅' : '⏸️'} ${action.name}</h4>
          <button class="btn secondary btn-sm" onclick="executeAutomatedAction('${action.id}')" ${!action.enabled || automation.approvalRequired ? '' : 'disabled'}>
            ${automation.approvalRequired ? 'Review & Execute' : 'Execute Now'}
          </button>
        </div>
        <p class="muted">${action.description}</p>
        <div class="action-meta">
          <span>Last run: ${action.lastRun || 'Never'}</span>
          <span>Next run: ${action.nextRun}</span>
        </div>
      </div>
    `).join('');
  }
  
  window.executeAutomatedAction = function(actionId) {
    const config = window.DASHBOARD_CONFIG || {};
    const automation = config.automation || {};
    
    if (!automation.enabled) {
      alert('Automated actions are disabled in configuration');
      return;
    }
    
    if (automation.approvalRequired) {
      const confirmed = confirm(`This will execute the automated action: ${actionId}\n\nThis is a demo mode - no actual changes will be made.\n\nIn production, this would:\n- Scan resources matching criteria\n- Generate change plan\n- Require manual approval\n- Execute changes with full audit trail\n\nProceed with demo?`);
      if (!confirmed) return;
    }
    
    // Demo: Simulate execution
    alert(`✅ Automated action "${actionId}" executed successfully (demo mode)\n\nIn production, results would appear here:\n- Resources affected: 12\n- Estimated savings: $450/month\n- Audit log: /logs/automation/${actionId}-${Date.now()}`);
    
    // Refresh the list
    renderAutomatedActionsList();
  };
  
  // ===== Phase 3: Report Builder =====
  function showReportBuilder() {
    const modal = document.getElementById('report-builder-modal');
    if (modal) {
      modal.classList.remove('hidden');
    }
  }
  
  function closeReportBuilder() {
    const modal = document.getElementById('report-builder-modal');
    if (modal) {
      modal.classList.add('hidden');
    }
  }
  
  function generateReport() {
    const form = document.getElementById('report-builder-form');
    if (!form) return;
    
    const formData = new FormData(form);
    const reportName = formData.get('report-name');
    const reportType = formData.get('report-type');
    const format = formData.get('format');
    const sections = formData.getAll('sections');
    
    if (!reportName || sections.length === 0) {
      alert('Please provide a report name and select at least one section');
      return;
    }
    
    // Demo: Show what would be generated
    const reportConfig = {
      name: reportName,
      type: reportType,
      format,
      sections,
      generatedAt: new Date().toISOString()
    };
    
    console.log('Report configuration:', reportConfig);
    
    alert(`📊 Report Generated (Demo Mode)\n\nReport: ${reportName}\nType: ${reportType}\nFormat: ${format}\nSections: ${sections.join(', ')}\n\nIn production, this would:\n- Generate ${format.toUpperCase()} file\n- Include selected data sections\n- Add charts and visualizations\n- Apply branding and formatting\n- Save to reports library\n- Optionally email to recipients`);
    
    // Add to saved reports list
    const savedReportsList = document.getElementById('saved-reports-list');
    if (savedReportsList) {
      const reportItem = document.createElement('div');
      reportItem.className = 'saved-item';
      reportItem.innerHTML = `
        <span>📄 ${reportName} (${format.toUpperCase()})</span>
        <span class="muted">${new Date().toLocaleDateString()}</span>
      `;
      savedReportsList.insertBefore(reportItem, savedReportsList.firstChild);
    }
    
    closeReportBuilder();
    form.reset();
  }
  
  function previewReport() {
    alert('📋 Report Preview\n\nThis would show a live preview of the report with current data, charts, and formatting based on selected sections and type.\n\nPreview features:\n- Real-time data rendering\n- Interactive chart previews\n- Page layout visualization\n- Export simulation');
  }
  
  function saveReportTemplate() {
    const form = document.getElementById('report-builder-form');
    if (!form) return;
    
    const formData = new FormData(form);
    const reportName = formData.get('report-name');
    
    if (!reportName) {
      alert('Please provide a template name');
      return;
    }
    
    alert(`💾 Template Saved: "${reportName}"\n\nThis template can be reused for future reports with the same configuration.`);
  }
  
  // ===== Phase 3: Ticketing Integration =====
  function showCreateTicketModal(recommendation = null) {
    const modal = document.getElementById('create-ticket-modal');
    if (!modal) return;
    
    modal.classList.remove('hidden');
    
    // Pre-fill if recommendation provided
    if (recommendation) {
      const form = document.getElementById('create-ticket-form');
      if (form) {
        form.querySelector('[name="ticket-title"]').value = recommendation.title || '';
        form.querySelector('[name="ticket-description"]').value = recommendation.description || '';
        form.querySelector('[name="ticket-priority"]').value = recommendation.priority || 'medium';
      }
    }
  }
  
  function closeCreateTicketModal() {
    const modal = document.getElementById('create-ticket-modal');
    if (modal) {
      modal.classList.add('hidden');
      const form = document.getElementById('create-ticket-form');
      if (form) form.reset();
    }
  }
  
  function createTicket() {
    const form = document.getElementById('create-ticket-form');
    if (!form) return;
    
    const formData = new FormData(form);
    const system = formData.get('ticket-system');
    const title = formData.get('ticket-title');
    const description = formData.get('ticket-description');
    const priority = formData.get('ticket-priority');
    const assignee = formData.get('ticket-assignee');
    
    if (!title || !description) {
      alert('Please provide a title and description');
      return;
    }
    
    const config = window.DASHBOARD_CONFIG || {};
    const integrations = config.integrations || {};
    const systemConfig = integrations[system === 'azure-devops' ? 'azureDevOps' : system];
    
    if (!systemConfig || !systemConfig.enabled) {
      alert(`${system} integration is not enabled. Please configure in config.js`);
      return;
    }
    
    // Demo: Simulate API call
    const ticket = {
      system,
      title,
      description,
      priority,
      assignee,
      createdAt: new Date().toISOString()
    };
    
    console.log('Creating ticket:', ticket);
    
    alert(`🎫 Ticket Created (Demo Mode)\n\nSystem: ${system}\nTitle: ${title}\nPriority: ${priority}\nAssignee: ${assignee || 'Unassigned'}\n\nIn production, this would:\n- Call ${system} REST API\n- Create work item with details\n- Attach cost data and charts\n- Add tags for tracking\n- Return ticket URL\n\nDemo ticket ID: DEMO-${Math.floor(Math.random() * 10000)}`);
    
    closeCreateTicketModal();
  }
  
  window.showCreateTicketModal = showCreateTicketModal;
  
  // ===== Phase 3: Public API =====
  // Note: This is a client-side demo. In production, these would be server-side endpoints
  window.DashboardAPI = {
    version: 'v1',
    
    async getCosts(params = {}) {
      // Demo: Return current cost data
      const selection = getSelection();
      const data = rawData;
      const monthly = getMonthlyTotals(data, selection);
      
      return {
        success: true,
        data: {
          monthly,
          total: monthly.reduce((sum, m) => sum + m.totalCost, 0),
          period: { from: selection.from, to: selection.to }
        }
      };
    },
    
    async getRecommendations() {
      // Demo: Return current recommendations
      const recommendations = generateRecommendations();
      
      return {
        success: true,
        data: {
          recommendations,
          count: recommendations.length,
          totalSavings: recommendations.reduce((sum, r) => sum + (r.savings || 0), 0)
        }
      };
    },
    
    async getForecast(method = 'linear-regression', horizon = 3) {
      // Demo: Return current forecast
      const forecast = generateForecast(rawData, method, horizon);
      
      return {
        success: true,
        data: forecast
      };
    },
    
    async generateReport(config) {
      // Demo: Simulate report generation
      return {
        success: true,
        data: {
          reportId: `report-${Date.now()}`,
          url: '/reports/demo-report.pdf',
          config
        }
      };
    }
  };
  
  // Expose API for external use
  console.log('📡 Dashboard API initialized. Available methods:', Object.keys(window.DashboardAPI));
  console.log('Example: await DashboardAPI.getCosts()');
  
  // ===== Initialize =====
  async function init() {
    initNavigation();
    initRoleSelector(); // Phase 2: Initialize role-based views
    bindControls();
    
    // Phase 3: Initialize new features
    const reportBuilderBtn = document.getElementById('report-builder-btn');
    if (reportBuilderBtn) {
      reportBuilderBtn.addEventListener('click', showReportBuilder);
    }
    
    const reportBuilderForm = document.getElementById('report-builder-form');
    if (reportBuilderForm) {
      reportBuilderForm.addEventListener('submit', (e) => {
        e.preventDefault();
        generateReport();
      });
      
      const previewBtn = reportBuilderForm.querySelector('.btn.secondary');
      if (previewBtn) {
        previewBtn.addEventListener('click', (e) => {
          e.preventDefault();
          previewReport();
        });
      }
      
      const saveTemplateBtn = reportBuilderForm.querySelectorAll('.btn.secondary')[1];
      if (saveTemplateBtn) {
        saveTemplateBtn.addEventListener('click', (e) => {
          e.preventDefault();
          saveReportTemplate();
        });
      }
    }
    
    const closeReportBuilderBtn = document.querySelector('#report-builder-modal .modal-close');
    if (closeReportBuilderBtn) {
      closeReportBuilderBtn.addEventListener('click', closeReportBuilder);
    }
    
    const reportBuilderModal = document.getElementById('report-builder-modal');
    if (reportBuilderModal) {
      reportBuilderModal.addEventListener('click', (e) => {
        if (e.target === reportBuilderModal || e.target.classList.contains('modal-overlay')) {
          closeReportBuilder();
        }
      });
    }
    
    const createTicketForm = document.getElementById('create-ticket-form');
    if (createTicketForm) {
      createTicketForm.addEventListener('submit', (e) => {
        e.preventDefault();
        createTicket();
      });
    }
    
    const closeCreateTicketBtn = document.querySelector('#create-ticket-modal .modal-close');
    if (closeCreateTicketBtn) {
      closeCreateTicketBtn.addEventListener('click', closeCreateTicketModal);
    }
    
    const createTicketModal = document.getElementById('create-ticket-modal');
    if (createTicketModal) {
      createTicketModal.addEventListener('click', (e) => {
        if (e.target === createTicketModal || e.target.classList.contains('modal-overlay')) {
          closeCreateTicketModal();
        }
      });
    }
    
    showLoadingState();

    try {
      // Load SKU pricing and main data in parallel
      const [_, data] = await Promise.all([
        loadSkuPricing(),
        fetchData()
      ]);
      rawData = data;
      buildSelections(rawData);
      render();
      
      // Phase 3: Render forecasting and automation features
      const config = window.DASHBOARD_CONFIG || {};
      if (config.forecasting && config.forecasting.enabled) {
        const forecast = generateForecast(
          rawData, 
          config.forecasting.method || 'linear-regression',
          config.forecasting.horizon || 3
        );
        renderForecastKpis(forecast);
        renderForecastChart(forecast);
      }
      
      if (config.automation && config.automation.enabled) {
        renderAutomatedActionsList();
      }
    } catch (err) {
      console.error("Failed to load dashboard data:", err);
      showErrorState(err.message);
    }
  }

  // Expose dashboard globally for dashboardInit to call
  window.dashboard = {
    // Core API methods
    renderAll: function(data) {
      console.log('[dashboard.renderAll] ===== CALLED WITH DATA =====');
      console.log('[dashboard.renderAll] Data type:', typeof data);
      console.log('[dashboard.renderAll] Data exists:', !!data);
      
      try {
        if (data) {
          console.log('[dashboard.renderAll] Data.costRows:', data.costRows?.length || 0);
          console.log('[dashboard.renderAll] Setting rawData variable...');
          rawData = data;
          console.log('[dashboard.renderAll] rawData variable is now:', !!rawData);
          console.log('[dashboard.renderAll] Calling buildSelections...');
          buildSelections(rawData);
          console.log('[dashboard.renderAll] buildSelections complete');
        } else {
          console.error('[dashboard.renderAll] ❌ No data passed to renderAll!');
          console.error('[dashboard.renderAll] Attempting to use fallback data...');
          // If no data, try to use cached data or load from config
          if (window.dashboardState?.rawData) {
            console.log('[dashboard.renderAll] Found data in dashboardState, using that');
            rawData = window.dashboardState.rawData;
          } else {
            console.error('[dashboard.renderAll] ❌ No fallback data available!');
          }
        }
        
        console.log('[dashboard.renderAll] Calling render()...');
        render();
        console.log('[dashboard.renderAll] render() complete');
      } catch (e) {
        console.error('[dashboard.renderAll] ❌ Error in renderAll:', e);
        console.error(e.stack);
        showErrorState('Failed to render dashboard: ' + e.message);
      }
    },
    // Error handling
    renderError: showErrorState,
    setData: function(data) {
      rawData = data;
      buildSelections(rawData);
    },
    // UX improvement utilities
    utils: {
      paginate: paginate,
      createPaginationControls: createPaginationControls,
      createBrandTabs: createBrandTabs,
      createTableFilterHeader: createTableFilterHeader,
      insertTableFilterHeader: insertTableFilterHeader,
      applyTablePagination: applyTablePagination,
      applyBrandFiltering: applyBrandFiltering
    }
  };

  // Production Deployment: 2025-12-04
  // All fixes deployed: error boundaries, module coordination, function exports
  // Data source: https://httcostcenter.blob.core.windows.net/cost-reports/latest-report.json
  // Localhost fallback: ./data/latest-report.json
  
  // ===== UX IMPROVEMENT UTILITIES =====
  // Pagination helper: returns paginated data
  function paginate(data, pageSize = 20) {
    const totalPages = Math.ceil(data.length / pageSize);
    const pages = [];
    for (let i = 0; i < totalPages; i++) {
      pages.push(data.slice(i * pageSize, (i + 1) * pageSize));
    }
    return pages;
  }

  // Create pagination controls HTML
  function createPaginationControls(totalRows, currentPage = 1, pageSize = 20) {
    const totalPages = Math.ceil(totalRows / pageSize);
    const start = (currentPage - 1) * pageSize + 1;
    const end = Math.min(currentPage * pageSize, totalRows);

    const controlsHtml = `
      <div class="pagination-controls">
        <div class="pagination-info">
          Showing ${start}-${end} of ${totalRows} items
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
          <select class="pagination-page-size" data-current-page="${currentPage}">
            <option value="10" ${pageSize === 10 ? 'selected' : ''}>10 per page</option>
            <option value="20" ${pageSize === 20 ? 'selected' : ''}>20 per page</option>
            <option value="50" ${pageSize === 50 ? 'selected' : ''}>50 per page</option>
          </select>
          <button class="pagination-prev" data-page="${currentPage - 1}" ${currentPage === 1 ? 'disabled' : ''}>← Previous</button>
          <span class="pagination-status">Page ${currentPage} of ${totalPages}</span>
          <button class="pagination-next" data-page="${currentPage + 1}" ${currentPage === totalPages ? 'disabled' : ''}>Next →</button>
        </div>
      </div>
    `;
    return controlsHtml;
  }

  // Create brand filter tabs
  function createBrandTabs(brands = [], activeBrand = null) {
    const defaultBrands = ['All Brands', 'HTT', 'Bishops', 'Lash Lounge', 'Frenchies'];
    const brandList = brands.length > 0 ? brands : defaultBrands;
    
    let tabsHtml = '<div class="brand-tabs">';
    brandList.forEach(brand => {
      const isActive = brand === activeBrand || (!activeBrand && brand === 'All Brands');
      tabsHtml += `<button class="brand-tab ${isActive ? 'active' : ''}" data-brand="${brand}">${brand}</button>`;
    });
    tabsHtml += '</div>';
    return tabsHtml;
  }

  // Create unified filter header
  function createTableFilterHeader(config = {}) {
    const {
      searchPlaceholder = 'Search...',
      columnSelect = [],
      showBrandTabs = true,
      brands = []
    } = config;

    let headerHtml = '<div class="table-filter-header">';
    
    headerHtml += `<input type="text" class="table-search-unified" placeholder="${searchPlaceholder}" style="flex: 1; min-width: 200px;" />`;
    
    if (columnSelect.length > 0) {
      headerHtml += `<select class="table-column-filter" style="min-width: 150px;">
        <option value="">Search all columns</option>`;
      columnSelect.forEach(col => {
        headerHtml += `<option value="${col}">${col}</option>`;
      });
      headerHtml += '</select>';
    }

    headerHtml += '<span class="filter-results" style="flex: 1; text-align: right;"></span>';
    headerHtml += '</div>';

    if (showBrandTabs) {
      headerHtml += createBrandTabs(brands);
    }

    return headerHtml;
  }

  // Apply pagination to table rows
  function applyTablePagination(tableElement, pageSize = 20) {
    // Remove any existing pagination controls to avoid duplicates on re-render
    const existingControls = Array.from(tableElement.parentNode.querySelectorAll('.pagination-controls'));
    existingControls.forEach(el => el.parentNode?.removeChild(el));
    const rows = Array.from(tableElement.querySelectorAll('tbody tr'));
    const totalRows = rows.length;
    let currentPage = 1;

    function showPage(page) {
      const start = (page - 1) * pageSize;
      const end = start + pageSize;
      rows.forEach((row, index) => {
        row.style.display = index >= start && index < end ? '' : 'none';
      });
      currentPage = page;
      updateControls();
    }

    function updateControls() {
      const controls = tableElement.parentNode.querySelector('.pagination-controls');
      if (!controls) return;
      
      const totalPages = Math.ceil(totalRows / pageSize);
      const start = (currentPage - 1) * pageSize + 1;
      const end = Math.min(currentPage * pageSize, totalRows);
      
      controls.querySelector('.pagination-info').textContent = `Showing ${start}-${end} of ${totalRows} items`;
      controls.querySelector('.pagination-status').textContent = `Page ${currentPage} of ${totalPages}`;
      
      const nextBtn = controls.querySelector('.pagination-next');
      const prevBtn = controls.querySelector('.pagination-prev');
      if (nextBtn) nextBtn.disabled = currentPage === totalPages;
      if (prevBtn) prevBtn.disabled = currentPage === 1;
    }

    // Create and insert pagination controls
    const controlsDiv = document.createElement('div');
    controlsDiv.innerHTML = createPaginationControls(totalRows, currentPage, pageSize);
    tableElement.parentNode.insertBefore(controlsDiv, tableElement.nextSibling);

    // Attach event listeners
    controlsDiv.querySelector('.pagination-next')?.addEventListener('click', (e) => {
      const nextPage = parseInt(e.target.dataset.page);
      const totalPages = Math.ceil(totalRows / pageSize);
      if (nextPage <= totalPages) showPage(nextPage);
    });

    controlsDiv.querySelector('.pagination-prev')?.addEventListener('click', (e) => {
      const prevPage = parseInt(e.target.dataset.page);
      if (prevPage >= 1) showPage(prevPage);
    });

    controlsDiv.querySelector('.pagination-page-size')?.addEventListener('change', (e) => {
      const newPageSize = parseInt(e.target.value);
      pageSize = newPageSize;
      showPage(1);
      const oldControls = tableElement.parentNode.querySelector('.pagination-controls');
      oldControls?.parentNode.removeChild(oldControls);
      applyTablePagination(tableElement, newPageSize);
    });

    showPage(1);
  }

  // Insert a unified filter header before a table, ensuring idempotency
  function insertTableFilterHeader(tableElement, config = {}) {
    const parent = tableElement.parentNode;
    // Remove prior headers/tabs created earlier
    parent.querySelectorAll('.table-filter-wrapper, .table-filter-header, .brand-tabs').forEach(el => el.remove());
    // Create wrapper so callers can query within a single container
    const wrapper = document.createElement('div');
    wrapper.className = 'table-filter-wrapper';
    wrapper.innerHTML = createTableFilterHeader(config);
    parent.insertBefore(wrapper, tableElement);
    return wrapper;
  }

  // Apply brand filtering to table rows
  function applyBrandFiltering(containerElement, activeBrand) {
    const rows = containerElement.querySelectorAll('tbody tr');
    let visibleCount = 0;

    rows.forEach(row => {
      let matches = true;
      
      if (activeBrand && activeBrand !== 'All Brands') {
        // Look for brand name in the row text
        const rowText = row.textContent.toUpperCase();
        matches = rowText.includes(activeBrand.toUpperCase());
      }

      row.style.display = matches ? '' : 'none';
      if (matches) visibleCount++;
    });

    // Update results count
    const resultsSpan = containerElement.querySelector('.filter-results');
    if (resultsSpan) {
      resultsSpan.textContent = `${visibleCount} of ${rows.length} items`;
    }
  }
  
  // Initialize using new pattern from dashboardInit
  // With defer, scripts load in order but need to wait for modules to execute
  document.addEventListener('DOMContentLoaded', async () => {
    console.log('[dashboard] DOMContentLoaded fired, checking for dashboardInit...');
    console.log('[dashboard] CACHE BUSTER:', new Date().getTime()); // Force invalidate any cached response
    
    try {
      // Wait up to 5 seconds for dashboardInit to be available
      let retries = 0;
      while (!window.dashboardInit && retries < 50) {
        await new Promise(resolve => setTimeout(resolve, 100));
        retries++;
      }
      
      if (window.dashboardInit && window.dashboardInit.initializeDashboard) {
        console.log('✅ Using dashboardInit.initializeDashboard()');
        await window.dashboardInit.initializeDashboard();
        console.log('✅ dashboardInit completed successfully');
        // Initialize navigation and controls after data is loaded
        console.log('[dashboard] Initializing navigation and controls...');
        init();
        console.log('[dashboard] Navigation and controls initialized');
      } else {
        console.error('❌ dashboardInit not available after 5 seconds');
        console.error('window.dashboardInit:', !!window.dashboardInit);
        console.log('⚠️ Falling back to legacy init');
        init();
      }
    } catch (initErr) {
      console.error('❌ Error during initialization:', initErr);
      console.error(initErr.stack);
      showErrorState('Initialization failed: ' + initErr.message);
    }
  });
})();
