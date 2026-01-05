// Auto-detect localhost and use appropriate data source
// Production Deployment: 2025-12-04 - Dashboard Data Pipeline Ready
const isLocalDev = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/i.test(window.location.href);
console.log('[config] Detected environment:', isLocalDev ? 'LOCALHOST' : 'PRODUCTION');
console.log('[config] Data URL will be:', isLocalDev ? 'LOCAL' : 'AZURE BLOB STORAGE');

window.DASHBOARD_CONFIG = {
  // Production: Try blob storage first, fallback to local
  // Localhost: Use local file (no CORS issues)
  dataUrl: "https://httcostcenter.blob.core.windows.net/cost-reports/latest-report.json",
  localDataUrl: "./data/latest-report.json",
  // Try local first if blob fails (better UX than blank page)
  fallbackToLocal: true,
  refreshWorkflowUrl:
    "https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA/actions/workflows/cost-center-audit.yml",
  
  // Budget tracking (monthly)
  budgetMonthly: 15000,
  budgetAlert: 0.8, // Alert at 80% utilization
  budgetCritical: 0.95, // Critical at 95% utilization
  
  // Saved views and bookmarks
  savedViews: [
    { id: 'finance-overview', name: 'Finance Overview', section: 'overview', filters: { period: 'mtd' }, role: 'finance' },
    { id: 'it-resources', name: 'IT Resources', section: 'resources', filters: { period: 'mtd' }, role: 'it' },
    { id: 'exec-summary', name: 'Executive Summary', section: 'overview', filters: { period: '6m' }, role: 'executive' },
    { id: 'waste-audit', name: 'Waste Audit', section: 'recommendations', filters: { period: 'mtd' }, role: 'finance' }
  ],
  
  // Role-based defaults (aligned with simplified 4-view navigation)
  roleDefaults: {
    finance: { 
      sections: ['overview', 'cost-licenses', 'data-explorer'], 
      defaultView: 'cost-licenses',
      description: 'Cost analysis, budget tracking, license optimization'
    },
    it: { 
      sections: ['overview', 'it-operations', 'data-explorer'], 
      defaultView: 'it-operations',
      description: 'Resource inventory, identity management, topology'
    },
    executive: { 
      sections: ['overview', 'brands', 'cost-licenses'], 
      defaultView: 'overview',
      description: 'High-level KPIs, brand performance, strategic insights'
    },
    admin: { 
      sections: [], // Admin sees all
      defaultView: 'overview',
      description: 'Full access to all views and data'
    }
  },
  
  // Phase 3: Forecasting and ML
  forecasting: {
    enabled: true,
    method: 'linear-regression', // 'linear-regression', 'exponential-smoothing', 'moving-average'
    horizon: 3, // Months to forecast
    confidence: 0.95, // 95% confidence interval
    minHistoricalMonths: 3 // Minimum data required
  },
  
  // Phase 3: Automated actions
  automation: {
    enabled: true,
    autoTag: false, // Auto-tag untagged resources (requires write permissions)
    autoDisableInactive: false, // Auto-disable inactive users (requires admin consent)
    autoCleanup: false, // Auto-delete idle resources (DANGEROUS - requires approval)
    approvalRequired: true // Require manual approval for all actions
  },
  
  // Phase 3: Integrations
  integrations: {
    jira: {
      enabled: false,
      url: '',
      project: 'COST',
      apiKey: '' // Store in environment variable
    },
    azureDevOps: {
      enabled: false,
      organization: 'HTT-BRANDS',
      project: 'Cost-Optimization',
      pat: '' // Store in environment variable
    },
    teams: {
      enabled: false,
      webhookUrl: '' // Teams webhook for notifications
    },
    slack: {
      enabled: false,
      webhookUrl: '' // Slack webhook for notifications
    }
  },
  
  // Phase 3: Public API
  api: {
    enabled: true,
    baseUrl: '/api',
    version: 'v1',
    rateLimitPerMinute: 60
  }
};
