/**
 * FilterService - Centralized filtering for all dashboard data
 * Eliminates duplicate filter logic, ensures consistency
 */

(function(global) {
  'use strict';

  const BRAND_MAP = {
    'HTT': { id: '0c0e35dc-188a-4eb3-b8ba-61752154b407', name: 'HTT Brands' },
    'BCC': { id: 'b5380912-79ec-452d-a6ca-6d897b19b294', name: 'Bishops' },
    'TLL': { id: '3c7d2bf3-b597-4766-b5cb-2b489c2904d6', name: 'The Lash Lounge' },
    'FN':  { id: '98723287-044b-4bbb-9294-19857d4128a0', name: 'Frenchies' }
  };

  class FilterService {
    static initialize() {
      console.log('[FilterService] Initializing...');

      this.filters = {
        period: 'last-month',
        from: null,
        to: null,
        tenant: null,
        brand: null,
        subscription: null
      };

      this.cache = {
        costs: null,
        licenses: null,
        resources: null,
        dateRange: null,
        timestamp: null
      };

      this.attachListeners();
      this.updateDateRange();
      console.log('[FilterService] Ready');
    }

    static attachListeners() {
      const handlers = {
        '#period-select': (val) => {
          const normalized = this.normalizePeriod(val);
          this.filters.period = normalized;
          if (normalized !== 'custom') this.updateDateRange();
          this.onChange();
        },
        '#from-date': (val) => {
          this.filters.from = val ? new Date(val) : null;
          this.filters.period = 'custom';
          this.updateDateRange();
          this.onChange();
        },
        '#to-date': (val) => {
          this.filters.to = val ? new Date(val) : null;
          this.filters.period = 'custom';
          this.updateDateRange();
          this.onChange();
        },
        '#tenant-select': (val) => {
          this.filters.tenant = val === 'all' ? null : val;
          this.filters.brand = this.tenantToBrand(val);
          this.onChange();
        },
        '#subscription-select': (val) => {
          this.filters.subscription = val === 'all' ? null : val;
          this.onChange();
        }
      };

      Object.entries(handlers).forEach(([selector, handler]) => {
        const el = document.querySelector(selector);
        if (el) {
          el.addEventListener('change', (e) => handler(e.target.value));
        }
      });
    }

    static updateDateRange() {
      const range = this.computeDateRange(this.filters.period);
      this.filters.from = range.from;
      this.filters.to = range.to;
      this.cache.dateRange = range;
    }

    static normalizePeriod(val) {
      switch (val) {
        case 'prev-month':
          return 'last-month';
        case '6m':
          return 'last-6-months';
        case '12m':
          return 'last-12-months';
        default:
          return val;
      }
    }

    static computeDateRange(period) {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      let from, to;

      switch (period) {
        case 'mtd':
          from = new Date(now.getFullYear(), now.getMonth(), 1);
          to = today;
          break;
        case 'last-month':
          from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
          to = new Date(now.getFullYear(), now.getMonth(), 0);
          break;
        case 'prev-month':
          from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
          to = new Date(now.getFullYear(), now.getMonth(), 0);
          break;
        case 'last-3-months':
          from = new Date(now.getFullYear(), now.getMonth() - 3, 1);
          to = today;
          break;
        case '6m':
        case 'last-6-months':
          from = new Date(now.getFullYear(), now.getMonth() - 6, 1);
          to = today;
          break;
        case 'ytd':
          from = new Date(now.getFullYear(), 0, 1);
          to = today;
          break;
        case '12m':
        case 'last-12-months':
          from = new Date(now.getFullYear(), now.getMonth() - 12, 1);
          to = today;
          break;
        case 'custom':
          from = this.filters.from || today;
          to = this.filters.to || today;
          break;
        default:
          from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
          to = new Date(now.getFullYear(), now.getMonth(), 0);
      }

      return { from, to };
    }

    static getCostData() {
      if (this.cache.costs && this.isCacheValid()) return this.cache.costs;

      const state = global.dashboardState;
      if (!state?.factsCost) return [];

      const { from, to, tenant, subscription } = this.filters;

      const filtered = state.factsCost.filter(row => {
        if (row.date) {
          const d = new Date(row.date);
          if (d < from || d > to) return false;
        }
        if (tenant && row.tenantId !== tenant) return false;
        if (subscription && row.subscriptionId !== subscription) return false;
        return true;
      });

      this.cache.costs = filtered;
      this.cache.timestamp = Date.now();
      return filtered;
    }

    static getLicenseData() {
      if (this.cache.licenses && this.isCacheValid()) return this.cache.licenses;

      const state = global.dashboardState;
      if (!state?.factsLicenses) return [];

      const { tenant } = this.filters;
      const filtered = state.factsLicenses.filter(row => {
        if (tenant && row.tenantId !== tenant) return false;
        return true;
      });

      this.cache.licenses = filtered;
      this.cache.timestamp = Date.now();
      return filtered;
    }

    static getResourceData() {
      if (this.cache.resources && this.isCacheValid()) return this.cache.resources;

      const state = global.dashboardState;
      if (!state?.rawData?.resources) return [];

      const { tenant, subscription } = this.filters;
      const filtered = state.rawData.resources.filter(row => {
        if (tenant && row.tenantId !== tenant) return false;
        if (subscription && row.subscriptionId !== subscription) return false;
        return true;
      });

      this.cache.resources = filtered;
      this.cache.timestamp = Date.now();
      return filtered;
    }

    static getDateRange() {
      return this.cache.dateRange || this.computeDateRange(this.filters.period);
    }

    static getFilters() {
      return { ...this.filters };
    }

    static invalidateCache() {
      this.cache = { costs: null, licenses: null, resources: null, dateRange: null, timestamp: null };
    }

    static isCacheValid() {
      return this.cache.timestamp && (Date.now() - this.cache.timestamp) < 5000;
    }

    static onChange() {
      this.invalidateCache();
      window.dispatchEvent(new CustomEvent('filtersChanged', { detail: { filters: this.getFilters() } }));
    }

    static tenantToBrand(tenantId) {
      for (const [code, info] of Object.entries(BRAND_MAP)) {
        if (info.id === tenantId) return code;
      }
      return null;
    }

    static brandToTenant(brandCode) {
      return BRAND_MAP[brandCode]?.id || null;
    }
  }

  global.FilterService = FilterService;
  console.log('[FilterService] Module loaded');

})(window);
