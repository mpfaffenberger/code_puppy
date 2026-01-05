/**
 * QueryService - High-performance data aggregation engine
 * Pre-computes common queries with intelligent caching
 */

(function(global) {
  'use strict';

  class QueryService {
    static initialize() {
      console.log('[QueryService] Initializing...');
      
      this.cache = new Map();
      this.CACHE_TTL = 10000;

      window.addEventListener('filtersChanged', () => this.invalidateAll());
      window.addEventListener('dashboardDataReady', () => this.invalidateAll());

      console.log('[QueryService] Ready');
    }

    static getCostByBrand() {
      return this.cached('costByBrand', () => {
        const costs = global.FilterService.getCostData();
        const byBrand = {};

        costs.forEach(row => {
          const brand = row.tenantName || 'Unknown';
          byBrand[brand] = (byBrand[brand] || 0) + (row.dailyCost || row.mtdCost || 0);
        });

        return Object.entries(byBrand).map(([brand, amount]) => ({ brand, amount }));
      });
    }

    static getCostByService() {
      return this.cached('costByService', () => {
        const costs = global.FilterService.getCostData();
        const byService = {};

        costs.forEach(row => {
          const service = row.serviceName || row.meterCategory || 'Unknown';
          byService[service] = (byService[service] || 0) + (row.dailyCost || row.mtdCost || 0);
        });

        return Object.entries(byService)
          .map(([service, amount]) => ({ service, amount }))
          .sort((a, b) => b.amount - a.amount)
          .slice(0, 10);
      });
    }

    static getCostTrend() {
      return this.cached('costTrend', () => {
        const costs = global.FilterService.getCostData();
        const byMonth = {};

        costs.forEach(row => {
          if (!row.date) return;
          const month = row.date.substring(0, 7);
          byMonth[month] = (byMonth[month] || 0) + (row.dailyCost || 0);
        });

        return Object.entries(byMonth)
          .map(([month, amount]) => ({ month, amount }))
          .sort((a, b) => a.month.localeCompare(b.month));
      });
    }

    static getTotalCost() {
      return this.cached('totalCost', () => {
        const costs = global.FilterService.getCostData();
        return costs.reduce((sum, row) => sum + (row.dailyCost || row.mtdCost || 0), 0);
      });
    }

    static getLicenseUtilization() {
      return this.cached('licenseUtil', () => {
        const state = global.dashboardState;
        if (!state?.rawData?.licenses) return [];

        const licenses = state.rawData.licenses;
        const filters = global.FilterService?.getFilters();
        const byTenant = {};

        licenses.forEach(lic => {
          if (filters?.tenant && lic.tenantId !== filters.tenant) return;
          
          const tenant = lic.tenantName || 'Unknown';
          if (!byTenant[tenant]) {
            byTenant[tenant] = { assigned: 0, available: 0, prepaid: 0 };
          }

          byTenant[tenant].assigned += lic.assigned || 0;
          byTenant[tenant].available += lic.available || 0;
          byTenant[tenant].prepaid += lic.prepaid || 0;
        });

        return Object.entries(byTenant).map(([tenant, counts]) => ({
          tenant,
          ...counts,
          utilization: counts.prepaid > 0 ? (counts.assigned / counts.prepaid) * 100 : 0
        }));
      });
    }

    static getLicenseWaste() {
      return this.cached('licenseWaste', () => {
        const licenses = global.FilterService.getLicenseData();
        const now = new Date();

        const waste = { critical: [], high: [], medium: [] };

        licenses.forEach(lic => {
          if (!lic.isPaidSku || !lic.lastSignIn) return;

          const lastSignIn = new Date(lic.lastSignIn);
          const daysInactive = Math.floor((now - lastSignIn) / (1000 * 60 * 60 * 24));

          const wasteRecord = {
            user: lic.userId || lic.userPrincipalName,
            sku: lic.skuPartNumber,
            daysInactive,
            monthlyCost: lic.monthlyCost || 0
          };

          if (daysInactive >= 90) waste.critical.push(wasteRecord);
          else if (daysInactive >= 60) waste.high.push(wasteRecord);
          else if (daysInactive >= 30) waste.medium.push(wasteRecord);
        });

        return waste;
      });
    }

    static getResourcesByType() {
      return this.cached('resourcesByType', () => {
        const resources = global.FilterService.getResourceData();
        const byType = {};

        resources.forEach(r => {
          const type = r.type?.split('/').pop() || 'Unknown';
          byType[type] = (byType[type] || 0) + 1;
        });

        return Object.entries(byType)
          .map(([type, count]) => ({ type, count }))
          .sort((a, b) => b.count - a.count);
      });
    }

    static calculateKPIs() {
      return this.cached('kpis', () => {
        const totalCost = this.getTotalCost();
        const costByBrand = this.getCostByBrand();
        const licenseUtil = this.getLicenseUtilization();
        const waste = this.getLicenseWaste();

        const totalWasteCost = [...waste.critical, ...waste.high, ...waste.medium]
          .reduce((sum, w) => sum + w.monthlyCost, 0);

        return {
          totalCost,
          brandCount: costByBrand.length,
          avgUtilization: licenseUtil.length > 0
            ? licenseUtil.reduce((sum, u) => sum + u.utilization, 0) / licenseUtil.length
            : 0,
          wasteCount: waste.critical.length + waste.high.length + waste.medium.length,
          wasteCost: totalWasteCost
        };
      });
    }

    static cached(key, computeFn) {
      const entry = this.cache.get(key);
      const now = Date.now();

      if (entry && (now - entry.timestamp) < this.CACHE_TTL) {
        return entry.value;
      }

      const value = computeFn();
      this.cache.set(key, { value, timestamp: now });
      return value;
    }

    static invalidateAll() {
      this.cache.clear();
      console.log('[QueryService] Cache invalidated');
    }

    static invalidate(key) {
      this.cache.delete(key);
    }
  }

  global.QueryService = QueryService;
  console.log('[QueryService] Module loaded');

})(window);
