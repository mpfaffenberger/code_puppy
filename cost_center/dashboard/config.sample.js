// Copy to docs/config.js and set to your data endpoint.
// If not provided, the dashboard falls back to ./data/sample-report.json.
window.DASHBOARD_CONFIG = {
  dataUrl: "https://<storage-account>.blob.core.windows.net/<container>/cost-reports/latest.json",
  refreshWorkflowUrl:
    "https://github.com/HTT-BRANDS/microsoft-cost-center-agent/actions/workflows/multi-tenant-audit.yml",
};
