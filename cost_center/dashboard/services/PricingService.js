/**
 * PricingService - Manages SKU pricing from multiple sources
 *
 * Priority order:
 * 1. Invoice data (actual billed prices from CSP)
 * 2. Microsoft Marketplace API (MSRP)
 * 3. Fallback estimates (last resort)
 *
 * Usage:
 *   await PricingService.initialize(dashboardState, invoiceData);
 *   const price = PricingService.getPrice('SPE_E3'); // Returns { monthlyPrice, currency, source }
 */

(function(global) {
  'use strict';

  class PricingService {
    /**
     * Initialize SKU pricing from available sources
     * @param {Object} state - Dashboard state object
     * @param {Array} invoiceData - CSP/MSP invoice data (optional)
     */
    static async initialize(state, invoiceData = null) {
      console.log('[PricingService] Initializing SKU pricing...');

      // Start with baseline prices (conservative estimates)
      this.initializeBaseline(state);

      // Enrich from invoice data if available
      if (invoiceData && invoiceData.length > 0) {
        this.enrichFromInvoices(state, invoiceData);
      }

      // TODO: Future enhancement - fetch from Microsoft Marketplace API
      // await this.fetchMarketplacePrices(state);

      console.log(`[PricingService] Initialized ${Object.keys(state.skuPrices).length} SKU prices`);
    }

    /**
     * Initialize baseline pricing (conservative estimates)
     * These are fallback prices if no invoice data is available
     */
    static initializeBaseline(state) {
      const baselinePrices = {
        // Microsoft 365 Suites
        "SPE_E3": { monthlyPrice: 36.00, currency: 'USD', source: 'baseline' },
        "SPE_E5": { monthlyPrice: 57.00, currency: 'USD', source: 'baseline' },
        "ENTERPRISEPACK": { monthlyPrice: 23.00, currency: 'USD', source: 'baseline' },
        "ENTERPRISEPREMIUM": { monthlyPrice: 38.00, currency: 'USD', source: 'baseline' },
        "M365_F1_COMM": { monthlyPrice: 4.00, currency: 'USD', source: 'baseline' },
        "O365_BUSINESS_PREMIUM": { monthlyPrice: 12.50, currency: 'USD', source: 'baseline' },
        "O365_BUSINESS_ESSENTIALS": { monthlyPrice: 6.00, currency: 'USD', source: 'baseline' },

        // Office Apps
        "VISIOCLIENT": { monthlyPrice: 15.00, currency: 'USD', source: 'baseline' },
        "PROJECTPROFESSIONAL": { monthlyPrice: 30.00, currency: 'USD', source: 'baseline' },

        // Power Platform
        "POWER_BI_PRO": { monthlyPrice: 10.00, currency: 'USD', source: 'baseline' },
        "PBI_PREMIUM_PER_USER": { monthlyPrice: 20.00, currency: 'USD', source: 'baseline' },
        "POWERAPPS_PER_USER": { monthlyPrice: 20.00, currency: 'USD', source: 'baseline' },
        "FLOW_PER_USER": { monthlyPrice: 15.00, currency: 'USD', source: 'baseline' },

        // Exchange
        "EXCHANGESTANDARD": { monthlyPrice: 4.00, currency: 'USD', source: 'baseline' },
        "EXCHANGEENTERPRISE": { monthlyPrice: 8.00, currency: 'USD', source: 'baseline' },

        // Security & Compliance
        "ATP_ENTERPRISE": { monthlyPrice: 2.00, currency: 'USD', source: 'baseline' },
        "THREAT_INTELLIGENCE": { monthlyPrice: 5.00, currency: 'USD', source: 'baseline' },
        "DEFENDER_ENDPOINT_P1": { monthlyPrice: 3.00, currency: 'USD', source: 'baseline' },
        "DEFENDER_ENDPOINT_P2": { monthlyPrice: 5.00, currency: 'USD', source: 'baseline' },

        // EMS & Identity
        "INTUNE_A": { monthlyPrice: 8.00, currency: 'USD', source: 'baseline' },
        "EMS_E3": { monthlyPrice: 10.50, currency: 'USD', source: 'baseline' },
        "EMS_E5": { monthlyPrice: 15.00, currency: 'USD', source: 'baseline' },
        "AAD_PREMIUM_P1": { monthlyPrice: 6.00, currency: 'USD', source: 'baseline' },
        "AAD_PREMIUM_P2": { monthlyPrice: 9.00, currency: 'USD', source: 'baseline' },
        "INFORMATION_PROTECTION_P1": { monthlyPrice: 2.00, currency: 'USD', source: 'baseline' },
        "INFORMATION_PROTECTION_P2": { monthlyPrice: 5.00, currency: 'USD', source: 'baseline' },
        "RIGHTSMANAGEMENT": { monthlyPrice: 2.00, currency: 'USD', source: 'baseline' },

        // Dynamics 365
        "CRMSTANDARD": { monthlyPrice: 65.00, currency: 'USD', source: 'baseline' },
        "D365_SALES_ENT": { monthlyPrice: 95.00, currency: 'USD', source: 'baseline' },
        "D365_CUSTOMER_SERVICE_ENT": { monthlyPrice: 95.00, currency: 'USD', source: 'baseline' },
      };

      // Copy baseline prices to state
      Object.entries(baselinePrices).forEach(([sku, priceInfo]) => {
        state.skuPrices[sku] = priceInfo;
      });
    }

    /**
     * Enrich pricing from invoice data (most accurate source)
     * @param {Object} state - Dashboard state
     * @param {Array} invoiceData - Invoice line items
     */
    static enrichFromInvoices(state, invoiceData) {
      let enrichedCount = 0;

      invoiceData.forEach(invoice => {
        if (!invoice.lineItems) return;

        invoice.lineItems.forEach(item => {
          // Extract SKU from description (format varies by CSP)
          const sku = this.extractSKUFromDescription(item.description);
          if (!sku) return;

          // Calculate unit price (handle negative quantities for refunds/credits)
          const unitPrice = item.quantity !== 0 ? item.total / Math.abs(item.quantity) : 0;

          // Only update if we have a valid price
          if (unitPrice > 0) {
            state.skuPrices[sku] = {
              monthlyPrice: unitPrice,
              currency: invoice.currency || 'USD',
              source: 'invoice',
              billingSource: invoice.billingSource,
              lastInvoiceDate: invoice.month
            };
            enrichedCount++;
          }
        });
      });

      console.log(`[PricingService] Enriched ${enrichedCount} SKUs from invoice data`);
    }

    /**
     * Extract SKU code from invoice line item description
     * Different CSPs format this differently
     */
    static extractSKUFromDescription(description) {
      if (!description) return null;

      // Try to extract SKU code from common formats:
      // "Microsoft 365 E3 (SPE_E3)"
      // "M365 E3 - SPE_E3"
      // "Office 365 E3 [ENTERPRISEPACK]"

      const patterns = [
        /\(([A-Z0-9_]+)\)/,       // (SKU_CODE)
        /\[([A-Z0-9_]+)\]/,       // [SKU_CODE]
        /SKU[:\s]+([A-Z0-9_]+)/i, // SKU: CODE
        /-\s*([A-Z0-9_]{3,})\s*$/,// - SKU_CODE at end
      ];

      for (const pattern of patterns) {
        const match = description.match(pattern);
        if (match && match[1]) {
          return match[1].toUpperCase();
        }
      }

      return null;
    }

    /**
     * Get price for a SKU
     * @param {string} skuCode - SKU identifier
     * @returns {Object|null} Price info or null if not found
     */
    static getPrice(state, skuCode) {
      if (!skuCode) return null;
      const upper = skuCode.toUpperCase();
      return state.skuPrices[upper] || null;
    }

    /**
     * Get monthly cost for a SKU (just the number)
     * @param {string} skuCode - SKU identifier
     * @returns {number} Monthly price or 0
     */
    static getMonthlyCost(state, skuCode) {
      const priceInfo = this.getPrice(state, skuCode);
      return priceInfo ? priceInfo.monthlyPrice : 0;
    }

    /**
     * Check if a SKU has invoice-backed pricing
     * @param {string} skuCode - SKU identifier
     * @returns {boolean}
     */
    static hasInvoicePrice(state, skuCode) {
      const priceInfo = this.getPrice(state, skuCode);
      return priceInfo && priceInfo.source === 'invoice';
    }

    /**
     * Future: Fetch MSRP from Microsoft Commercial Marketplace API
     * Requires Partner Center API access
     */
    static async fetchMarketplacePrices(state) {
      // TODO: Implement Microsoft Partner Center API integration
      // https://docs.microsoft.com/en-us/partner-center/develop/get-a-list-of-skus-for-a-product

      console.log('[PricingService] Marketplace API integration not yet implemented');

      /*
      Example implementation:

      const products = await fetch('https://api.partnercenter.microsoft.com/v1/products');
      const skus = await fetch('https://api.partnercenter.microsoft.com/v1/products/{productId}/skus');

      skus.forEach(sku => {
        state.skuPrices[sku.id] = {
          monthlyPrice: sku.pricing.price,
          currency: sku.pricing.currencyCode,
          source: 'marketplace'
        };
      });
      */
    }

    /**
     * Export pricing data for debugging
     */
    static exportPricingReport(state) {
      const report = {
        totalSKUs: Object.keys(state.skuPrices).length,
        bySources: {},
        skus: []
      };

      Object.entries(state.skuPrices).forEach(([sku, info]) => {
        const source = info.source || 'unknown';
        report.bySources[source] = (report.bySources[source] || 0) + 1;

        report.skus.push({
          sku,
          price: info.monthlyPrice,
          currency: info.currency,
          source: info.source,
          billingSource: info.billingSource || 'N/A'
        });
      });

      report.skus.sort((a, b) => b.price - a.price);
      return report;
    }
  }

  // Export to global scope
  global.PricingService = PricingService;

})(window);
