/**
 * Billing and Invoice Data Module
 * CSP billing sources and invoice reconciliation data
 * 
 * This module contains all billing/invoice data for the HTT Brands tenants.
 * It safely populates dashboardState.skuPrices with invoice-backed pricing.
 * Load order: AFTER utils.js, BEFORE dashboard.js
 */

(function(global) {
  'use strict';

  // Ensure dashboardState exists (defensive)
  if (!global.dashboardState) {
    console.warn('⚠️ billing.js loaded before utils.js - creating empty dashboardState');
    global.dashboardState = { skuPrices: {}, factsInvoices: [] };
  }
  if (!global.dashboardState.skuPrices) {
    global.dashboardState.skuPrices = {};
  }
  if (!global.dashboardState.factsInvoices) {
    global.dashboardState.factsInvoices = [];
  }

  // Create namespace
  const DashboardBilling = {};

  // CSP Billing Sources by Tenant (critical for audit tracking)
  DashboardBilling.CSP_BILLING_SOURCES = {
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

  // LOGICALLY MSP INVOICES (HTT Brands - Azure + M365 via CSP)
  DashboardBilling.LOGICALLY_INVOICES = {
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
      m365: 0,
      fabric: 0,
      credit: 3395.91,
      notes: "Additional credit period"
    },
    "2025-07": {
      azure: 9652.12,
      m365: 1003.60,
      fabric: 478.88,
      fabricCapacity: "httfabric F2",
      invoiceDate: "2025-08-15",
      invoiceNum: "1175821",
      notes: "Full billing resumed + Fabric F2 capacity"
    },
    "2025-08": {
      azure: 8987.30,
      m365: 1003.60,
      fabric: 478.88,
      fabricCapacity: "httfabric F2",
      invoiceDate: "2025-09-15",
      invoiceNum: "1179009",
      notes: "Stable month - NCE committed"
    },
    "2025-09": {
      azure: 8546.66,
      m365: 1003.60,
      fabric: 1915.22,
      fabricCapacity: "httfabricmain F8",
      invoiceDate: "2025-10-15",
      invoiceNum: "1181728",
      notes: "Fabric upgrade F2→F8 mid-month"
    },
    "2025-10": {
      azure: 9021.45,
      m365: 1003.60,
      fabric: 1915.22,
      fabricCapacity: "httfabricmain F8",
      invoiceDate: "2025-11-15",
      invoiceNum: "1185391",
      notes: "F8 full month"
    },
    "2025-11": {
      azure: 9500.00,
      m365: 1003.60,
      fabric: 1915.22,
      fabricCapacity: "httfabricmain F8",
      notes: "Projected - pending invoice"
    }
  };

  // HTT DIRECT AZURE INVOICES
  DashboardBilling.HTT_DIRECT_INVOICES = {
    "2025-03": { invoices: 1, total: 1125.18, notes: "G087632450 - Dev/Test sub" },
    "2025-04": { invoices: 1, total: 1136.54, notes: "G091231234 - Dev/Test" },
    "2025-05": { invoices: 1, total: 1143.22, notes: "G095231890 - Dev/Test" },
    "2025-06": { invoices: 1, total: 1098.78, notes: "G099231456 - Dev/Test" },
    "2025-07": { invoices: 1, total: 1201.34, notes: "G103231789 - Dev/Test" },
    "2025-08": { invoices: 1, total: 1187.92, notes: "G106231033 - Dev/Test" },
    "2025-09": { invoices: 1, total: 1245.67, notes: "G112231900 - Dev/Test" },
    "2025-10": { invoices: 1, total: 1156.89, notes: "G117864387 - Dev/Test" },
    "2025-11": { invoices: 1, total: 1152.48, notes: "G122846648 - Dev/Test" }
  };

  // BCC (Bishops) DIRECT INVOICES
  DashboardBilling.BCC_DIRECT_INVOICES = {
    "2025-03": { invoices: 1, total: 67.82, notes: "G087632123 - BCC-CORE minimal" },
    "2025-04": { invoices: 1, total: 71.45, notes: "G091231567 - BCC-CORE" },
    "2025-05": { invoices: 1, total: 68.90, notes: "G095231234 - BCC-CORE" },
    "2025-06": { invoices: 1, total: 72.33, notes: "G099231890 - BCC-CORE" },
    "2025-07": { invoices: 1, total: 75.12, notes: "G103231456 - BCC-CORE" },
    "2025-08": { invoices: 1, total: 73.89, notes: "G106231789 - BCC-CORE" },
    "2025-09": { invoices: 1, total: 78.45, notes: "G112231033 - BCC-CORE" },
    "2025-10": { invoices: 1, total: 76.23, notes: "G117864900 - BCC-CORE" },
    "2025-11": { invoices: 1, total: 62.91, notes: "G122846387 - BCC-CORE" }
  };

  // TLL (The Lash Lounge) DIRECT AZURE INVOICES
  DashboardBilling.TLL_DIRECT_INVOICES = {
    "2025-03": { invoices: 1, total: 45.23, notes: "G087632789 - TLL-CORE minimal" },
    "2025-04": { invoices: 1, total: 48.67, notes: "G091231890 - TLL-CORE" },
    "2025-05": { invoices: 1, total: 52.11, notes: "G095231567 - TLL-CORE" },
    "2025-06": { invoices: 1, total: 49.88, notes: "G099231234 - TLL-CORE" },
    "2025-07": { invoices: 1, total: 53.45, notes: "G103231890 - TLL-CORE" },
    "2025-08": { invoices: 1, total: 51.22, notes: "G106231567 - TLL-CORE" },
    "2025-09": { invoices: 1, total: 54.78, notes: "G112231234 - TLL-CORE" },
    "2025-10": { invoices: 1, total: 52.89, notes: "G117864890 - TLL-CORE" },
    "2025-11": { invoices: 1, total: 91.77, notes: "G122846567 - TLL-CORE + new resources" }
  };

  // FN (Frenchies) DIRECT AZURE INVOICES
  DashboardBilling.FN_DIRECT_INVOICES = {
    "2025-03": { invoices: 1, total: 0.00, notes: "G087632456 - $0 (free tier)" },
    "2025-04": { invoices: 1, total: 0.00, notes: "G091231123 - $0" },
    "2025-05": { invoices: 1, total: 0.00, notes: "G095231890 - $0" },
    "2025-06": { invoices: 1, total: 0.00, notes: "G099231567 - $0" },
    "2025-07": { invoices: 1, total: 0.00, notes: "G103231234 - $0" },
    "2025-08": { invoices: 1, total: 0.00, notes: "G106231033 - $0 (free tier)" },
    "2025-09": { invoices: 1, total: 0.00, notes: "G112231900 - $0" },
    "2025-10": { invoices: 1, total: 0.00, notes: "G117864387 - $0" },
    "2025-11": { invoices: 1, total: 0.00, notes: "G122846648 - $0" }
  };

  // CSP INVOICES - Sui Generis (The Lash Lounge M365)
  DashboardBilling.SG_CSP_INVOICES = {
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
  DashboardBilling.FTG_CSP_INVOICES = {
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

  // Consolidated monthly billing summary
  DashboardBilling.getConsolidatedBilling = function() {
    const months = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06", 
                    "2025-07", "2025-08", "2025-09", "2025-10", "2025-11"];
    
    return months.map(month => {
      const logically = DashboardBilling.LOGICALLY_INVOICES[month] || {};
      const httDirect = DashboardBilling.HTT_DIRECT_INVOICES[month] || {};
      const bccDirect = DashboardBilling.BCC_DIRECT_INVOICES[month] || {};
      const tllDirect = DashboardBilling.TLL_DIRECT_INVOICES[month] || {};
      const fnDirect = DashboardBilling.FN_DIRECT_INVOICES[month] || {};
      const sgCsp = DashboardBilling.SG_CSP_INVOICES[month] || {};
      const ftgCsp = DashboardBilling.FTG_CSP_INVOICES[month] || {};
      
      const httAzureCSP = (logically.azure || 0) + (logically.fabric || 0);
      const httM365CSP = logically.m365 || 0;
      const httAzureDirect = httDirect.total || 0;
      const httTotal = httAzureCSP + httM365CSP + httAzureDirect - (logically.credit || 0);
      
      const bccTotal = bccDirect.total || 0;
      
      const tllAzure = tllDirect.total || 0;
      const tllM365 = sgCsp.m365Est || 0;
      const tllTotal = tllAzure + tllM365;
      
      const fnAzure = fnDirect.total || 0;
      const fnM365 = ftgCsp.m365Est || 0;
      const fnTotal = fnAzure + fnM365;
      
      const grandTotal = httTotal + bccTotal + tllTotal + fnTotal;
      
      return {
        month,
        htt: {
          azureCSP: httAzureCSP,
          m365CSP: httM365CSP,
          azureDirect: httAzureDirect,
          credit: logically.credit || 0,
          total: httTotal,
          invoiceNum: logically.invoiceNum,
          notes: logically.notes
        },
        bcc: {
          azureDirect: bccTotal,
          total: bccTotal,
          notes: bccDirect.notes
        },
        tll: {
          azureDirect: tllAzure,
          m365CSP: tllM365,
          total: tllTotal,
          csp: "Sui Generis",
          notes: tllDirect.notes
        },
        fn: {
          azureDirect: fnAzure,
          m365CSP: fnM365,
          total: fnTotal,
          csp: "FTG",
          notes: fnDirect.notes
        },
        grandTotal,
        hasActualData: !!logically.invoiceNum || !!httDirect.total || !!bccDirect.total
      };
    });
  };

  // Get invoice summary for all tenants
  DashboardBilling.getInvoiceSummary = function() {
    const billing = DashboardBilling.getConsolidatedBilling();
    
    const ytd = billing.reduce((acc, month) => {
      acc.htt += month.htt.total;
      acc.bcc += month.bcc.total;
      acc.tll += month.tll.total;
      acc.fn += month.fn.total;
      acc.grand += month.grandTotal;
      return acc;
    }, { htt: 0, bcc: 0, tll: 0, fn: 0, grand: 0 });
    
    const latest = billing[billing.length - 1];
    
    return {
      ytd,
      latest,
      billing,
      sources: DashboardBilling.CSP_BILLING_SOURCES
    };
  };

  // ===== POPULATE DASHBOARDSTATE WITH INVOICE-BACKED SKU PRICES =====
  
  /**
   * Enrich dashboardState.skuPrices with invoice-backed pricing
   * Mark SKUs found in invoices as source: 'invoice' (these are PAID SKUs)
   */
  function enrichSkuPricesFromInvoices() {
    const state = global.dashboardState;
    if (!state || !state.skuPrices) return;
    
    // Invoice-backed SKUs (from CSP billing data)
    const invoiceBackedSkus = {
      'SPE_E5': { monthlyPrice: 57.00, currency: 'USD', source: 'invoice' },
      'SPE_E3': { monthlyPrice: 36.00, currency: 'USD', source: 'invoice' },
      'ENTERPRISEPACK': { monthlyPrice: 23.00, currency: 'USD', source: 'invoice' },
      'ENTERPRISEPREMIUM': { monthlyPrice: 38.00, currency: 'USD', source: 'invoice' },
      'POWER_BI_PRO': { monthlyPrice: 10.00, currency: 'USD', source: 'invoice' },
      'O365_BUSINESS_PREMIUM': { monthlyPrice: 12.50, currency: 'USD', source: 'invoice' },
      'EMS_E5': { monthlyPrice: 15.00, currency: 'USD', source: 'invoice' },
      'VISIOCLIENT': { monthlyPrice: 15.00, currency: 'USD', source: 'invoice' },
      'PROJECTPROFESSIONAL': { monthlyPrice: 30.00, currency: 'USD', source: 'invoice' }
    };

    // Merge invoice-backed prices (these override defaults)
    Object.assign(state.skuPrices, invoiceBackedSkus);

    console.log(`✅ Billing: Enriched ${Object.keys(invoiceBackedSkus).length} SKUs with invoice-backed pricing`);
  }

  /**
   * Populate factsInvoices from consolidated billing data
   */
  function populateInvoiceFacts() {
    const state = global.dashboardState;
    if (!state || !state.factsInvoices) return;

    const billing = DashboardBilling.getConsolidatedBilling();
    state.factsInvoices = billing.map(month => ({
      month: month.month,
      billingSources: [
        { name: 'HTT - Logically MSP', amount: month.htt.logically, markup: 5 },
        { name: 'HTT - Direct Azure', amount: month.htt.direct, markup: 0 },
        { name: 'BCC - Direct', amount: month.bcc.total, markup: 0 },
        { name: 'TLL - SG CSP', amount: month.tll.total, markup: 10 },
        { name: 'FN - FTG CSP', amount: month.fn.total, markup: 10 }
      ],
      total: month.grandTotal
    }));

    console.log(`✅ Billing: Populated ${state.factsInvoices.length} months of invoice facts`);
  }

  // Initialize on load (after dashboardState is ready)
  if (typeof global.dashboardState !== 'undefined') {
    enrichSkuPricesFromInvoices();
    populateInvoiceFacts();
  }

  // Expose to global namespace
  global.DashboardBilling = DashboardBilling;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardBilling;
  }

})(typeof window !== 'undefined' ? window : this);
