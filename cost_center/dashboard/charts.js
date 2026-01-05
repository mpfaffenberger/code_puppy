/**
 * Chart Rendering Module
 * All Chart.js visualization functions for the cost center dashboard.
 * 
 * This module provides reusable chart rendering functions.
 * Requires Chart.js to be loaded before this script.
 * Uses DashboardUtils for formatting functions.
 */

(function(global) {
  'use strict';

  const DashboardCharts = {};

  // Chart instances registry
  let charts = {};

  // Common chart colors
  DashboardCharts.COLORS = {
    primary: "#3b82f6",
    secondary: "#8b5cf6",
    success: "#10b981",
    warning: "#f59e0b",
    danger: "#ef4444",
    cyan: "#06b6d4",
    pink: "#ec4899",
    lime: "#84cc16",
    orange: "#f97316",
    indigo: "#6366f1",
    gray: "#6b7280",
    dark: "#1f2937",
    textMuted: "#9ca3af",
  };

  DashboardCharts.TENANT_COLORS = {
    "Head to Toe Brands (anchor)": DashboardCharts.COLORS.primary,
    "Bishops": DashboardCharts.COLORS.secondary,
    "Frenchies": DashboardCharts.COLORS.success,
    "The Lash Lounge": DashboardCharts.COLORS.warning,
  };

  // Chart management
  DashboardCharts.getCharts = function() { return charts; };
  
  DashboardCharts.destroyChart = function(name) {
    if (charts[name]) {
      charts[name].destroy();
      delete charts[name];
    }
  };

  DashboardCharts.destroyAllCharts = function() {
    Object.keys(charts).forEach(name => {
      if (charts[name]) charts[name].destroy();
    });
    charts = {};
  };

  // Helper to get formatting functions
  function fmt() {
    return global.DashboardUtils || {
      formatCurrency: v => `$${Number(v || 0).toFixed(2)}`,
      formatPercent: v => `${(v || 0).toFixed(1)}%`,
      isPaidSku: () => true
    };
  }

  /**
   * Render monthly trend chart
   */
  DashboardCharts.renderMonthlyTrendChart = function(ctx, data, selection, computeFilterRange) {
    const utils = fmt();
    const range = computeFilterRange(selection.period);
    const monthlyCosts = data.monthlyCosts || {};
    const tenants = data.tenants || [];

    const subToTenant = new Map();
    tenants.forEach(t => {
      (t.subscriptions || []).forEach(s => {
        subToTenant.set(s.subscriptionId, t.tenantId);
      });
    });

    const byMonth = new Map();
    const byMonthByTenant = new Map();

    Object.entries(monthlyCosts).forEach(([subId, subData]) => {
      const tenantId = subToTenant.get(subId);
      if (selection.tenant && tenantId !== selection.tenant) return;
      if (selection.subscription && subId !== selection.subscription) return;

      const tenantName = tenants.find(t => t.tenantId === tenantId)?.tenantName || "Unknown";
      
      (subData.months || []).forEach(m => {
        const monthDate = new Date(m.month + "-01");
        if (range && (monthDate < range.from || monthDate > range.to)) return;
        
        byMonth.set(m.month, (byMonth.get(m.month) || 0) + m.total);
        
        if (!byMonthByTenant.has(m.month)) {
          byMonthByTenant.set(m.month, new Map());
        }
        byMonthByTenant.get(m.month).set(tenantName, (byMonthByTenant.get(m.month).get(tenantName) || 0) + m.total);
      });
    });

    const labels = Array.from(byMonth.keys()).sort();
    const values = labels.map(m => byMonth.get(m));
    let cumulative = 0;
    const cumulativeData = values.map(v => cumulative += v);

    const tenantNames = new Set();
    byMonthByTenant.forEach(monthMap => {
      monthMap.forEach((_, tenant) => tenantNames.add(tenant));
    });

    const stackedDatasets = Array.from(tenantNames).map(tenant => ({
      label: tenant,
      data: labels.map(month => byMonthByTenant.get(month)?.get(tenant) || 0),
      backgroundColor: DashboardCharts.TENANT_COLORS[tenant] || DashboardCharts.COLORS.gray,
      stack: "tenants",
    }));

    DashboardCharts.destroyChart('trend');
    charts.trend = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels.map(m => {
          const [year, month] = m.split("-");
          return new Date(year, parseInt(month) - 1).toLocaleDateString(undefined, { month: "short", year: "2-digit" });
        }),
        datasets: [
          ...stackedDatasets,
          {
            label: "Cumulative",
            data: cumulativeData,
            type: "line",
            borderColor: DashboardCharts.COLORS.warning,
            backgroundColor: "transparent",
            yAxisID: "y1",
            tension: 0.3,
            pointRadius: 4,
          },
        ],
      },
      options: {
        plugins: {
          legend: { position: "top", labels: { color: DashboardCharts.COLORS.textMuted } },
          title: { display: true, text: "Monthly Azure Costs by Brand", color: DashboardCharts.COLORS.textMuted },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${utils.formatCurrency(ctx.raw)}` } }
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: DashboardCharts.COLORS.textMuted } },
          y: { stacked: true, grid: { color: DashboardCharts.COLORS.dark }, ticks: { color: DashboardCharts.COLORS.textMuted, callback: v => utils.formatCurrency(v) } },
          y1: { position: "right", grid: { display: false }, ticks: { color: DashboardCharts.COLORS.textMuted, callback: v => utils.formatCurrency(v) } },
        },
      },
    });
  };

  /**
   * Render daily trend chart
   */
  DashboardCharts.renderDailyTrendChart = function(ctx, data, selection, filterCostRows) {
    const utils = fmt();
    const costs = filterCostRows(data, selection);
    
    const byDate = new Map();
    costs.forEach(c => {
      if (c.date && c.dailyCost !== undefined) {
        byDate.set(c.date, (byDate.get(c.date) || 0) + c.dailyCost);
      }
    });

    const labels = Array.from(byDate.keys()).sort();
    const values = labels.map(d => byDate.get(d));

    DashboardCharts.destroyChart('trend');
    charts.trend = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels.map(d => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" })),
        datasets: [{
          label: "Daily Cost",
          data: values,
          borderColor: DashboardCharts.COLORS.primary,
          backgroundColor: "rgba(59, 130, 246, 0.1)",
          fill: true,
          tension: 0.3,
        }],
      },
      options: {
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => utils.formatCurrency(ctx.raw) } } },
        scales: {
          y: { grid: { color: DashboardCharts.COLORS.dark }, ticks: { color: DashboardCharts.COLORS.textMuted, callback: v => utils.formatCurrency(v) } },
          x: { grid: { display: false }, ticks: { color: DashboardCharts.COLORS.textMuted } },
        },
      },
    });
  };

  /**
   * Render license charts
   */
  DashboardCharts.renderLicenseCharts = function(data, selection, filterLicenses) {
    const utils = fmt();
    const licenses = filterLicenses(data, selection);

    const ctxUtil = document.getElementById("license-util-chart");
    if (ctxUtil) {
      const tenantData = licenses.map(l => {
        const skus = l.skuAssignments || l.subscribedSkus || [];
        const paidSkus = skus.filter(sku => utils.isPaidSku(sku.skuPartNumber));
        const consumed = paidSkus.reduce((s, sku) => s + (sku.consumedUnits || 0), 0);
        const prepaid = paidSkus.reduce((s, sku) => s + (sku.totalPrepaidUnits || sku.prepaidUnits?.enabled || 0), 0);
        return { tenant: l.tenantName, consumed, available: Math.max(0, prepaid - consumed) };
      });

      DashboardCharts.destroyChart('licenseUtil');
      charts.licenseUtil = new Chart(ctxUtil, {
        type: "bar",
        data: {
          labels: tenantData.map(t => t.tenant),
          datasets: [
            { label: "Consumed", data: tenantData.map(t => t.consumed), backgroundColor: DashboardCharts.COLORS.primary },
            { label: "Available", data: tenantData.map(t => t.available), backgroundColor: DashboardCharts.COLORS.dark },
          ],
        },
        options: {
          plugins: { 
            legend: { position: "top", labels: { color: DashboardCharts.COLORS.textMuted } },
            title: { display: true, text: "Paid License Utilization", color: DashboardCharts.COLORS.textMuted }
          },
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: DashboardCharts.COLORS.textMuted } },
            y: { stacked: true, grid: { color: DashboardCharts.COLORS.dark }, ticks: { color: DashboardCharts.COLORS.textMuted } },
          },
        },
      });
    }

    const ctxSku = document.getElementById("license-sku-chart");
    if (ctxSku) {
      const allSkus = [];
      licenses.forEach(l => {
        (l.skuAssignments || l.subscribedSkus || []).forEach(sku => {
          if (utils.isPaidSku(sku.skuPartNumber) && (sku.consumedUnits || 0) > 0) {
            allSkus.push({ name: sku.skuPartNumber || sku.skuId, consumed: sku.consumedUnits || 0 });
          }
        });
      });

      const topSkus = allSkus.sort((a, b) => b.consumed - a.consumed).slice(0, 10);

      DashboardCharts.destroyChart('licenseSku');
      charts.licenseSku = new Chart(ctxSku, {
        type: "doughnut",
        data: {
          labels: topSkus.map(s => s.name),
          datasets: [{
            data: topSkus.map(s => s.consumed),
            backgroundColor: Object.values(DashboardCharts.COLORS).slice(0, 10),
          }],
        },
        options: {
          plugins: { 
            legend: { position: "right", labels: { color: DashboardCharts.COLORS.textMuted } },
            title: { display: true, text: "Top Paid SKUs", color: DashboardCharts.COLORS.textMuted }
          },
        },
      });
    }
  };

  /**
   * Render cost breakdown charts
   */
  DashboardCharts.renderCostCharts = function(data, selection, filterCostRows) {
    const utils = fmt();
    const costs = filterCostRows(data, selection);

    const ctxTenant = document.getElementById("tenant-cost-chart");
    if (ctxTenant) {
      const byTenant = new Map();
      costs.forEach(c => {
        const key = c.tenantName || c.tenantId;
        byTenant.set(key, (byTenant.get(key) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
      });

      const tenantData = Array.from(byTenant.entries()).sort((a, b) => b[1] - a[1]);

      DashboardCharts.destroyChart('tenantCost');
      charts.tenantCost = new Chart(ctxTenant, {
        type: "pie",
        data: {
          labels: tenantData.map(t => t[0]),
          datasets: [{
            data: tenantData.map(t => t[1]),
            backgroundColor: [DashboardCharts.COLORS.primary, DashboardCharts.COLORS.secondary, DashboardCharts.COLORS.success, DashboardCharts.COLORS.warning],
          }],
        },
        options: {
          plugins: { 
            legend: { position: "bottom", labels: { color: DashboardCharts.COLORS.textMuted } },
            tooltip: { callbacks: { label: ctx => `${ctx.label}: ${utils.formatCurrency(ctx.raw)}` } }
          },
        },
      });
    }

    const ctxService = document.getElementById("service-cost-chart");
    if (ctxService) {
      const byService = new Map();
      costs.forEach(c => {
        const key = c.serviceName || c.meterCategory || "Other";
        byService.set(key, (byService.get(key) || 0) + (c.dailyCost ?? c.mtdCost ?? 0));
      });

      const serviceData = Array.from(byService.entries()).sort((a, b) => b[1] - a[1]).slice(0, 8);

      DashboardCharts.destroyChart('serviceCost');
      charts.serviceCost = new Chart(ctxService, {
        type: "bar",
        data: {
          labels: serviceData.map(s => s[0]),
          datasets: [{ data: serviceData.map(s => s[1]), backgroundColor: DashboardCharts.COLORS.secondary }],
        },
        options: {
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => utils.formatCurrency(ctx.raw) } } },
          scales: {
            y: { grid: { color: DashboardCharts.COLORS.dark }, ticks: { color: DashboardCharts.COLORS.textMuted, callback: v => utils.formatCurrency(v) } },
            x: { grid: { display: false }, ticks: { color: DashboardCharts.COLORS.textMuted } },
          },
        },
      });
    }
  };

  /**
   * Render invoice trend chart
   */
  DashboardCharts.renderInvoiceCharts = function(billingData) {
    const utils = fmt();
    const ctxInvoice = document.getElementById("invoice-trend-chart");
    if (!ctxInvoice) return;

    const labels = billingData.map(b => {
      const [year, month] = b.month.split("-");
      return new Date(year, parseInt(month) - 1).toLocaleDateString(undefined, { month: "short" });
    });

    DashboardCharts.destroyChart('invoiceTrend');
    charts.invoiceTrend = new Chart(ctxInvoice, {
      type: "bar",
      data: {
        labels,
        datasets: [
          { label: "HTT", data: billingData.map(b => b.htt.total), backgroundColor: DashboardCharts.COLORS.primary, stack: "tenants" },
          { label: "BCC", data: billingData.map(b => b.bcc.total), backgroundColor: DashboardCharts.COLORS.secondary, stack: "tenants" },
          { label: "TLL", data: billingData.map(b => b.tll.total), backgroundColor: DashboardCharts.COLORS.success, stack: "tenants" },
          { label: "FN", data: billingData.map(b => b.fn.total), backgroundColor: DashboardCharts.COLORS.warning, stack: "tenants" },
        ],
      },
      options: {
        plugins: { 
          legend: { position: "top", labels: { color: DashboardCharts.COLORS.textMuted } },
          title: { display: true, text: "Monthly Billing by Tenant", color: DashboardCharts.COLORS.textMuted },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${utils.formatCurrency(ctx.raw)}` } }
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: DashboardCharts.COLORS.textMuted } },
          y: { stacked: true, grid: { color: DashboardCharts.COLORS.dark }, ticks: { color: DashboardCharts.COLORS.textMuted, callback: v => utils.formatCurrency(v) } },
        },
      },
    });
  };

  // Expose to global
  global.DashboardCharts = DashboardCharts;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardCharts;
  }

})(typeof window !== 'undefined' ? window : this);
