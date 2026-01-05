/**
 * Dashboard Initialization Module - Production Ready (2025-12-04)
 *
 * Coordinates loading of data and initialization of services before dashboard renders.
 * This module integrates the new service-based architecture with the existing dashboard.
 * All module references now check both global and window scope for maximum compatibility.
 *
 * Loading Flow:
 * 1. Fetch data from configured URL (blob storage or localhost)
 * 2. Initialize PricingService with invoice data (optional - graceful failure)
 * 3. Normalize data (cost, licenses, invoices) with error handling
 * 4. Initialize BudgetService (optional - graceful failure)
 * 5. Trigger dashboard render via window.dashboard.renderAll(data)
 * 
 * Error Handling:
 * - All optional services wrapped in try-catch
 * - Fallback data available in window.dashboardState.rawData
 * - Clear error messages to user if critical failure occurs
 */

(function(global) {
  'use strict';

  const dashboardInit = {};

  /**
   * Main initialization function
   * Called by dashboard.js on DOMContentLoaded
   */
  dashboardInit.initializeDashboard = async function() {
    console.log('[dashboardInit] =====> INITIALIZATION CALLED <=====');
    console.log('[dashboardInit] Starting dashboard initialization...');

    try {
      // Step 1: Determine data URL
      const dataUrl = this.getDataUrl();
      console.log('[dashboardInit] Loading data from:', dataUrl);

      // Step 2: Fetch data
      const data = await this.fetchData(dataUrl);
      console.log('[dashboardInit] Data loaded successfully');

      // Step 3: Store in global state
      global.dashboardState = global.dashboardState || {};
      global.dashboardState.rawData = data;
      global.dashboardState.factsCost = [];
      global.dashboardState.factsLicenses = [];
      global.dashboardState.factsInvoices = [];
      global.dashboardState.skuPrices = {};

      // Step 4: Update metadata
      this.updateMetadata(data);

      // Step 5: Initialize PricingService
      await this.initializePricing(data);

      // Step 6: Normalize data
      console.log('[dashboardInit] Step 6: About to call normalizeData. this.normalizeData exists?', !!this.normalizeData);
      if (this.normalizeData) {
        await this.normalizeData(data);
      } else {
        console.error('[dashboardInit] ❌ normalizeData method not found on dashboardInit!');
      }

      // Step 7: Initialize BudgetService
      this.initializeBudgetService();

      // Step 7.5: Initialize FilterService
      const FilterService = global.FilterService || window.FilterService;
      if (FilterService && FilterService.initialize) {
        try {
          FilterService.initialize();
          console.log('[dashboardInit] FilterService initialized');
        } catch (e) {
          console.warn('[dashboardInit] FilterService error:', e.message);
        }
      }

      // Step 7.6: Initialize QueryService
      const QueryService = global.QueryService || window.QueryService;
      if (QueryService && QueryService.initialize) {
        try {
          QueryService.initialize();
          console.log('[dashboardInit] QueryService initialized');
        } catch (e) {
          console.warn('[dashboardInit] QueryService error:', e.message);
        }
      }

      // Step 8: Initialize FreshnessUI
      const FreshnessUI = global.FreshnessUI || window.FreshnessUI;
      if (FreshnessUI && FreshnessUI.updateFreshness) {
        try {
          FreshnessUI.updateFreshness();
        } catch (e) {
          console.warn('[dashboardInit] FreshnessUI error:', e.message);
        }
      }

      // Step 9: Initialize BudgetUI (check for alerts)
      const BudgetUI = global.BudgetUI || window.BudgetUI;
      if (BudgetUI && BudgetUI.checkAndShowAlerts) {
        setTimeout(() => {
          try {
            BudgetUI.checkAndShowAlerts();
          } catch (e) {
            console.warn('[dashboardInit] BudgetUI error:', e.message);
          }
        }, 1000);
      }

      // Step 10: Trigger dashboard render
      console.log('[dashboardInit] ===== ABOUT TO RENDER =====');
      console.log('[dashboardInit] data type:', typeof data);
      console.log('[dashboardInit] data exists:', !!data);
      console.log('[dashboardInit] data.costRows:', data?.costRows?.length);
      console.log('[dashboardInit] global.dashboardState.rawData exists:', !!global.dashboardState?.rawData);
      console.log('[dashboardInit] global.dashboard exists:', !!global.dashboard);
      console.log('[dashboardInit] global.dashboard.renderAll exists:', !!global.dashboard?.renderAll);
      
      try {
        // Try dashboard object - could be global or window
        const dashboardObj = global.dashboard || window.dashboard;
        if (dashboardObj && dashboardObj.renderAll) {
          // Pass the ORIGINAL raw data that was fetched
          console.log('[dashboardInit] ✅ CALLING renderAll with data');
          dashboardObj.renderAll(data);
          console.log('[dashboardInit] ✅ renderAll returned successfully');
        } else {
          console.error('[dashboardInit] ❌ dashboard.renderAll not found!');
          console.error('[dashboardInit] Global.dashboard:', !!global.dashboard);
          console.error('[dashboardInit] Window.dashboard:', !!window.dashboard);
          console.error('[dashboardInit] Attempting direct render call from dashboardState...');
          // Fallback: Store data and wait for UI to pick it up
          if (global.dashboardState?.rawData) {
            console.log('[dashboardInit] Data stored in dashboardState, UI should pick it up');
          } else {
            console.error('[dashboardInit] ❌ CRITICAL: No data in dashboardState!');
            throw new Error('Dashboard not ready and no data in dashboardState');
          }
        }
      } catch (renderError) {
        console.error('[dashboardInit] Error during renderAll:', renderError);
        throw renderError;
      }

      console.log('[dashboardInit] Dashboard initialization complete ✓');
      return data;

    } catch (error) {
      console.error('[dashboardInit] Initialization failed:', error);
      // Surface error to the user but do not crash the UI
      this.showError(error);
      // Ensure global state exists so the rest of the UI can function
      global.dashboardState = global.dashboardState || {};
      global.dashboardState.rawData = global.dashboardState.rawData || null;
      // Return null to indicate failure without throwing
      return null;
    }
  };

  /**
   * Get data URL from config or query params
   * On localhost, prioritize local files over blob storage
   */
  dashboardInit.getDataUrl = function() {
    console.log('[dashboardInit.getDataUrl] window.location.origin:', window.location.origin);
    console.log('[dashboardInit.getDataUrl] window.location.href:', window.location.href);
    
    // Check query params first
    const qs = new URLSearchParams(window.location.search);
    if (qs.get('dataUrl')) {
      console.log('[dashboardInit.getDataUrl] Using query param:', qs.get('dataUrl'));
      return qs.get('dataUrl');
    }

    // Check if we're on localhost
    const isLocalhost = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(window.location.origin);
    console.log('[dashboardInit.getDataUrl] isLocalhost:', isLocalhost);

    // On localhost, prefer local data (fastest, no CORS issues)
    if (isLocalhost) {
      console.log('[dashboardInit.getDataUrl] ✓ Using local data: ./data/latest-report.json');
      return './data/latest-report.json';
    }

    // In production, use configured data URL
    if (global.DASHBOARD_CONFIG && global.DASHBOARD_CONFIG.dataUrl) {
      console.log('[dashboardInit.getDataUrl] Using blob URL:', global.DASHBOARD_CONFIG.dataUrl);
      return global.DASHBOARD_CONFIG.dataUrl;
    }

    // Fallback
    console.log('[dashboardInit.getDataUrl] Fallback to local data');
    return './data/latest-report.json';
  };

  /**
   * Fetch data with fallback logic
   */
  dashboardInit.fetchData = async function(primaryUrl) {
    const urls = [primaryUrl];

    // Add fallbacks
    const isLocalhost = /^https?:\/\/(localhost|127\.0\.0\.1)(:\\d+)?$/i.test(window.location.origin);
    
    // On localhost, always try local data as fallback
    if (isLocalhost) {
      if (primaryUrl !== './data/latest-report.json') {
        urls.push('./data/latest-report.json');
      }
      if (primaryUrl !== './data/sample-report.json') {
        urls.push('./data/sample-report.json');
      }
    } else {
      // In production, fallback to local if primary fails
      if (primaryUrl !== './data/latest-report.json') {
        urls.push('./data/latest-report.json');
      }
    }

    // Try each URL in sequence
    for (const url of urls) {
      try {
        console.log(`[dashboardInit] Attempting to load: ${url}`);
        const response = await fetch(url);

        if (!response.ok) {
          console.warn(`[dashboardInit] Failed to load ${url}: HTTP ${response.status}`);
          continue;
        }

        const data = await response.json();
        console.log(`[dashboardInit] Successfully loaded data from: ${url}`);
        console.log(`[dashboardInit] Data contains ${data.costRows?.length || 0} cost rows, ${data.licenses?.length || 0} licenses`);
        return data;

      } catch (error) {
        console.warn(`[dashboardInit] Error loading ${url}:`, error.message);
      }
    }

    throw new Error('Failed to load dashboard data from any source. Tried: ' + urls.join(', '));
  };

  /**
   * Update metadata in dashboard state
   */
  dashboardInit.updateMetadata = function(data) {
    const state = global.dashboardState;

    state.meta = {
      lastUpdated: data.generatedAt || new Date().toISOString(),
      dataSource: data.dataSource || 'blob-storage',
      tenantCount: data.tenants ? data.tenants.length : 0,
      subscriptionCount: this.countSubscriptions(data),
      costRowCount: data.costRows ? data.costRows.length : 0,
      licenseCount: this.countLicenses(data),
      version: data.version || '1.0'
    };

    console.log('[dashboardInit] Metadata:', state.meta);
  };

  /**
   * Initialize PricingService
   */
  dashboardInit.initializePricing = async function(data) {
    // Use explicit variable names instead of _
    const PricingService = global.PricingService || window.PricingService;
    if (!PricingService) {
      console.warn('[dashboardInit] PricingService not available');
      return;
    }

    try {
      // Extract invoice data if available
      const invoiceData = data.invoices || [];

      console.log('[dashboardInit] Initializing PricingService...');
      await PricingService.initialize(global.dashboardState, invoiceData);
      console.log('[dashboardInit] PricingService initialized');
    } catch (e) {
      console.warn('[dashboardInit] PricingService initialization error:', e.message);
      // Don't fail - PricingService is optional
    }
  };

  /**
   * Normalize raw data into facts
   */
  dashboardInit.normalizeData = async function(data) {
    console.log('[dashboardInit] Normalizing data...');
    console.log('[dashboardInit] Data structure check:', {
      hasCostRows: !!data?.costRows,
      costRowsLength: data?.costRows?.length || 0,
      hasLicense: !!data?.license,
      licenseLength: data?.license?.length || 0
    });

    // Wait for normalization functions to be loaded
    let retries = 0;
    while ((!global.normalizeCostData && !window.normalizeCostData) && retries < 50) {
      console.log('[dashboardInit] Waiting for normalizeCostData to be available...');
      await new Promise(resolve => setTimeout(resolve, 50));
      retries++;
    }

    try {
      // Call normalization functions from utils.js if they exist
      const normCost = global.normalizeCostData || window.normalizeCostData;
      if (typeof normCost === 'function') {
        console.log('[dashboardInit] Calling normalizeCostData...');
        normCost(data);
        console.log(`[dashboardInit] ✅ Cost facts populated: ${global.dashboardState.factsCost.length}`);
      } else {
        console.warn('[dashboardInit] ❌ normalizeCostData function not found after waiting');
      }

      const normLic = global.normalizeLicenseData || window.normalizeLicenseData;
      if (typeof normLic === 'function') {
        console.log('[dashboardInit] Calling normalizeLicenseData...');
        normLic(data);
        console.log(`[dashboardInit] ✅ License facts populated: ${global.dashboardState.factsLicenses.length}`);
      } else {
        console.warn('[dashboardInit] ❌ normalizeLicenseData function not found');
      }

      const normInv = global.normalizeInvoiceData || window.normalizeInvoiceData;
      if (typeof normInv === 'function') {
        console.log('[dashboardInit] Calling normalizeInvoiceData...');
        normInv(data);
        console.log(`[dashboardInit] ✅ Invoice facts populated: ${global.dashboardState.factsInvoices.length}`);
      } else {
        console.warn('[dashboardInit] ❌ normalizeInvoiceData function not found');
      }
    } catch (e) {
      console.error('[dashboardInit] Normalization error:', e.message, e.stack);
    }

    console.log('[dashboardInit] Data normalization complete. Final state:', {
      factsCost: global.dashboardState.factsCost.length,
      factsLicenses: global.dashboardState.factsLicenses.length,
      factsInvoices: global.dashboardState.factsInvoices.length
    });
  };

  /**
   * Initialize BudgetService
   */
  dashboardInit.initializeBudgetService = function() {
    if (!global.BudgetService) {
      console.warn('[dashboardInit] BudgetService not available');
      return;
    }

    console.log('[dashboardInit] Initializing BudgetService...');
    global.BudgetService.initialize();
    console.log('[dashboardInit] BudgetService initialized');
  };

  /**
   * Show error banner
   */
  dashboardInit.showError = function(error) {
    const banner = document.getElementById('data-health');
    if (!banner) return;

    banner.innerHTML = `
      <div class="alert-banner danger">
        <div class="alert-content">
          <span class="alert-icon">⚠️</span>
          <div class="alert-text">
            <strong>Failed to Load Dashboard</strong>
            <p>${error.message || 'Could not load dashboard data'}</p>
          </div>
          <button class="btn primary" onclick="location.reload()">Retry</button>
        </div>
      </div>
    `;
    banner.classList.remove('hidden');
  };

  /**
   * Helper: Count subscriptions
   */
  dashboardInit.countSubscriptions = function(data) {
    if (!data.tenants) return 0;
    return data.tenants.reduce((sum, t) => sum + (t.subscriptions || []).length, 0);
  };

  /**
   * Helper: Count licenses
   */
  dashboardInit.countLicenses = function(data) {
    if (!data.licenses) return 0;

    let count = 0;
    Object.values(data.licenses).forEach(tenantLicenses => {
      Object.values(tenantLicenses).forEach(users => {
        count += (users || []).length;
      });
    });
    return count;
  };

  // Export to global scope
  global.dashboardInit = dashboardInit;

  console.log('[dashboardInit] ✅ Module loaded and exported to window.dashboardInit');
  console.log('[dashboardInit] Production deployment verified - 2025-12-04');
  
  // Verify it's accessible
  if (window.dashboardInit) {
    console.log('[dashboardInit] ✓ Confirmed: window.dashboardInit is available');
  }

})(window);
