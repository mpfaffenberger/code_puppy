/**
 * Insights and Recommendations Module
 * Azure cost optimization and license insights generation.
 * 
 * This module provides functions to generate optimization insights.
 * Uses DashboardUtils for formatting functions.
 */

(function(global) {
  'use strict';

  const DashboardInsights = {};

  // Helper to get formatting functions from utils
  function fmt() {
    return global.DashboardUtils || {
      formatCurrency: v => `$${Number(v || 0).toFixed(2)}`,
      formatPercent: v => `${(v || 0).toFixed(1)}%`,
      formatNumber: v => String(v || 0),
      parseDate: s => s ? new Date(s) : null,
      getBadgeClass: () => '',
      isPaidSku: () => true
    };
  }

  /**
   * Generate Azure cost optimization insights
   */
  DashboardInsights.generateAzureInsights = function(data, selection, helpers) {
    const utils = fmt();
    const { filterCostRows, calculateMonthlyCostsTotal, getMonthlyTotals } = helpers;
    const insights = [];
    const costs = filterCostRows(data, selection);
    const totalCost = costs.reduce((sum, r) => sum + (r.dailyCost ?? r.mtdCost ?? 0), 0) || calculateMonthlyCostsTotal(data, selection);

    // Filter resources by selection
    const resources = (data.resources || []).filter(r => {
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });

    // Idle resources
    const costResourceIds = new Set(costs.filter(c => c.resourceId && (c.dailyCost || c.mtdCost)).map(c => c.resourceId.toLowerCase()));
    const idleCount = resources.filter(r => !costResourceIds.has((r.id || "").toLowerCase())).length;
    if (idleCount > 0) {
      insights.push({
        title: `${idleCount} resources with no spend in period`,
        meta: "Review for deallocation or rightsizing",
        badge: "Optimization",
      });
    }

    // Untagged resources
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

    // Azure Advisor recommendations
    const advisorRecs = (data.advisorRecommendations || []).filter(r => {
      if (selection.tenant && r.tenantId !== selection.tenant) return false;
      if (selection.subscription && r.subscriptionId !== selection.subscription) return false;
      return true;
    });
    if (advisorRecs.length > 0) {
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
        ? `${utils.formatCurrency(totalSavings)} potential annual savings`
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
      serviceTotals.set(key, (serviceTotals.get(key) || 0) + (row.dailyCost ?? row.mtdCost ?? 0));
    });
    if (serviceTotals.size > 0 && totalCost > 0) {
      const sorted = [...serviceTotals.entries()].sort((a, b) => b[1] - a[1]);
      const [topService, topVal] = sorted[0];
      const share = topVal / totalCost;
      if (share >= 0.6) {
        insights.push({
          title: `${topService} is ${utils.formatPercent(share * 100)} of spend`,
          meta: "Validate SKU/size; consider commitment discounts",
          badge: "Concentration",
        });
      }
    }

    // Expiring credentials
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

    // MoM anomaly
    const series = getMonthlyTotals(data, selection, { limitToRange: false });
    if (series.length >= 2) {
      const latest = series[series.length - 1][1];
      const prev = series[series.length - 2][1] || 0;
      if (prev > 0) {
        const deltaPct = (latest - prev) / prev;
        if (Math.abs(deltaPct) >= 0.3) {
          insights.push({
            title: `Spend ${deltaPct >= 0 ? "up" : "down"} ${utils.formatPercent(deltaPct * 100)} MoM`,
            meta: `Latest ${utils.formatCurrency(latest)} vs ${utils.formatCurrency(prev)} prior month`,
            badge: "Anomaly",
          });
        }
      }
    }

    // Zero-cost with resources
    if (totalCost === 0 && resources.length > 0) {
      insights.push({
        title: "Resources present but zero spend",
        meta: "Confirm metering; check tags/reader access",
        badge: "Data Check",
      });
    }

    return insights;
  };

  /**
   * Generate license optimization insights
   */
  DashboardInsights.generateLicenseInsights = function(data, selection, helpers) {
    const utils = fmt();
    const { filterLicenses, getSkuPrice } = helpers;
    const insights = [];
    const licenses = filterLicenses(data, selection);

    // Underutilized SKUs
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
              title: `${sku.skuPartNumber}: ${utils.formatPercent(util * 100)} utilized (${utils.formatNumber(consumed)}/${utils.formatNumber(prepaid)})`,
              meta: monthlySavings > 0 
                ? `${l.tenantName || "Tenant"} — potential savings: ${utils.formatCurrency(monthlySavings)}/mo` 
                : `${l.tenantName || "Tenant"} — consider downsizing or reallocating`,
              badge: "Low Utilization",
            });
          }
        }
      });
    });

    // Inactive paid users
    const usersByTenant = data.users || {};
    let inactivePaid = 0;
    let redundant = 0;
    let inactiveWasteCost = 0;
    const staleThresholdDays = 60;
    const now = new Date();

    licenses.forEach(l => {
      const tenantUsers = usersByTenant[l.tenantId] || [];
      const userLast = new Map();
      tenantUsers.forEach(u => {
        userLast.set(u.id, utils.parseDate(u.lastSignInDateTime));
      });

      (l.userAssignments || []).forEach(assign => {
        const paidSkus = (assign.skuIds || []).filter(id => {
          const skuMeta = (l.subscribedSkus || []).find(s => s.skuId === id);
          return utils.isPaidSku(skuMeta?.skuPartNumber);
        });
        if (paidSkus.length > 1) redundant += 1;

        if (paidSkus.length > 0) {
          const last = userLast.get(assign.userId);
          const diffDays = last ? Math.floor((now - last) / 86400000) : Infinity;
          if (diffDays >= staleThresholdDays) {
            inactivePaid += 1;
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
        title: `${utils.formatNumber(inactivePaid)} users with paid licenses inactive ${staleThresholdDays}+ days`,
        meta: inactiveWasteCost > 0 
          ? `💰 Est. waste: ${utils.formatCurrency(inactiveWasteCost)}/mo (${utils.formatCurrency(inactiveWasteCost * 12)}/yr) — reclaim or downgrade`
          : "Reclaim or downgrade to free SKUs",
        badge: "Inactive",
      });
    }
    if (redundant > 0) {
      insights.push({
        title: `${utils.formatNumber(redundant)} users with overlapping paid SKUs`,
        meta: "Remove redundant assignments to cut cost",
        badge: "Redundant",
      });
    }

    // Unused prepaid pools
    licenses.forEach(l => {
      (l.subscribedSkus || []).forEach(sku => {
        const prepaid = (sku.prepaidUnits && (sku.prepaidUnits.enabled || 0)) || 0;
        const available = prepaid - (sku.consumedUnits || 0);
        if (prepaid > 0 && available > 0 && utils.isPaidSku(sku.skuPartNumber)) {
          if (available >= Math.max(5, prepaid * 0.1)) {
            const pricePerLicense = getSkuPrice(sku.skuPartNumber) || 0;
            const monthlySavings = available * pricePerLicense;
            insights.push({
              title: `${sku.skuPartNumber}: ${utils.formatNumber(available)} of ${utils.formatNumber(prepaid)} unused`,
              meta: monthlySavings > 0
                ? `${l.tenantName || "Tenant"} — save ${utils.formatCurrency(monthlySavings)}/mo at renewal`
                : `${l.tenantName || "Tenant"} — rebalance or reduce quantity at renewal`,
              badge: "Unused",
            });
          }
        }
      });
    });

    return insights;
  };

  /**
   * Render insights to DOM element
   */
  DashboardInsights.renderInsightsList = function(container, insights, emptyMessage) {
    if (!container) return;
    const utils = fmt();
    
    container.innerHTML = insights.length ? insights.map(i => {
      const badgeClass = utils.getBadgeClass(i.badge);
      return `
        <li>
          <div class="insight-title">${i.title}</div>
          <div class="insight-meta">${i.meta}</div>
          <div class="insight-badge ${badgeClass}">${i.badge}</div>
        </li>
      `;
    }).join("") : `<li class="muted">${emptyMessage || "No insights available."}</li>`;
  };

  /**
   * Generate top movers data
   */
  DashboardInsights.generateTopMovers = function(data, selection, helpers) {
    const { getTenantMonthlyTotals, getServiceMonthlyTotals } = helpers;
    
    const tenantMonthly = getTenantMonthlyTotals(data, selection);
    const tenantMovers = [];
    tenantMonthly.forEach((monthMap, tenant) => {
      const months = [...monthMap.entries()].sort((a, b) => a[0].localeCompare(b[0]));
      if (months.length < 2) return;
      const [prevMonth, prevVal] = months[months.length - 2];
      const [latestMonth, latestVal] = months[months.length - 1];
      const delta = latestVal - prevVal;
      const pct = prevVal ? (delta / prevVal) * 100 : null;
      tenantMovers.push({ label: tenant, delta, pct, latestMonth, prevMonth });
    });
    tenantMovers.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

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

    return {
      tenants: tenantMovers.slice(0, 5),
      services: serviceMovers.slice(0, 5)
    };
  };

  /**
   * Render top movers to DOM
   */
  DashboardInsights.renderTopMovers = function(container, movers, emptyMessage) {
    if (!container) return;
    const utils = fmt();
    
    container.innerHTML = movers.length ? movers.map(m => `
      <li>
        <div class="insight-title">${m.label}</div>
        <div class="insight-meta">${m.prevMonth} → ${m.latestMonth}</div>
        <div class="insight-badge">${m.delta >= 0 ? "Increase" : "Decrease"}</div>
        <div class="insight-meta">${utils.formatCurrency(m.delta)} (${m.pct === null ? "n/a" : utils.formatPercent(m.pct)})</div>
      </li>
    `).join("") : `<li class="muted">${emptyMessage || "Not enough data."}</li>`;
  };

  // Expose to global
  global.DashboardInsights = DashboardInsights;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardInsights;
  }

})(typeof window !== 'undefined' ? window : this);
