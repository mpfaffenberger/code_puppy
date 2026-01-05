/**
 * Data Freshness UI Module
 *
 * Shows how current the dashboard data is with visual indicators:
 * - Green dot: <6 hours old (fresh)
 * - Yellow dot: 6-24 hours old (stale)
 * - Red dot: >24 hours old (very stale)
 *
 * Dependencies: dashboardState
 */

(function(global) {
  'use strict';

  const FreshnessUI = {};

  /**
   * Initialize freshness UI
   */
  FreshnessUI.initialize = function() {
    // Update freshness indicator
    this.updateFreshness();

    // Auto-update every minute
    setInterval(() => this.updateFreshness(), 60000);
  };

  /**
   * Update freshness indicator
   */
  FreshnessUI.updateFreshness = function() {
    const state = global.dashboardState;
    if (!state || !state.meta || !state.meta.lastUpdated) {
      this.showUnknown();
      return;
    }

    const lastUpdated = new Date(state.meta.lastUpdated);
    const now = new Date();
    const hours = (now - lastUpdated) / 3600000;

    this.updateIndicator(lastUpdated, hours);
    this.updateDatasetMeta(state.meta);
  };

  /**
   * Update freshness indicator (dot + text)
   */
  FreshnessUI.updateIndicator = function(lastUpdated, hours) {
    const dot = document.querySelector('.freshness-dot');
    const text = document.querySelector('.freshness-text');

    if (!dot || !text) return;

    // Determine color and status
    let color, status;
    if (hours < 6) {
      color = 'green';
      status = 'fresh';
    } else if (hours < 24) {
      color = 'yellow';
      status = 'stale';
    } else {
      color = 'red';
      status = 'very-stale';
    }

    // Update dot color
    dot.className = `freshness-dot ${color}`;
    dot.setAttribute('data-status', status);

    // Update text
    const relativeTime = this.formatRelativeTime(lastUpdated);
    text.textContent = `Last updated: ${relativeTime}`;

    // Show warning if very stale
    if (status === 'very-stale') {
      this.showStaleDataWarning(hours);
    }
  };

  /**
   * Update dataset metadata badge
   */
  FreshnessUI.updateDatasetMeta = function(meta) {
    const badge = document.getElementById('dataset-meta');
    if (!badge) return;

    const parts = [];
    if (meta.tenantCount) parts.push(`${meta.tenantCount} tenants`);
    if (meta.subscriptionCount) parts.push(`${meta.subscriptionCount} subs`);

    badge.textContent = parts.join(' • ');
  };

  /**
   * Show unknown freshness
   */
  FreshnessUI.showUnknown = function() {
    const dot = document.querySelector('.freshness-dot');
    const text = document.querySelector('.freshness-text');

    if (dot) {
      dot.className = 'freshness-dot gray';
      dot.setAttribute('data-status', 'unknown');
    }

    if (text) {
      text.textContent = 'Loading...';
    }
  };

  /**
   * Show stale data warning banner
   */
  FreshnessUI.showStaleDataWarning = function(hours) {
    const banner = document.getElementById('data-health');
    if (!banner) return;

    const days = Math.floor(hours / 24);
    const message = days > 0
      ? `Data is ${days} day${days > 1 ? 's' : ''} old. Click "Full Sync" to refresh.`
      : `Data is ${Math.floor(hours)} hours old. Consider refreshing.`;

    banner.innerHTML = `
      <div class="alert-banner warning">
        <div class="alert-content">
          <span class="alert-icon">⚠️</span>
          <div class="alert-text">
            <strong>Stale Data</strong>
            <p>${message}</p>
          </div>
          <button class="btn primary" id="trigger-refresh-from-warning">Full Sync</button>
        </div>
      </div>
    `;

    banner.classList.remove('hidden');

    // Wire up button
    const btn = document.getElementById('trigger-refresh-from-warning');
    if (btn) {
      btn.addEventListener('click', () => this.triggerFullSync());
    }
  };

  /**
   * Trigger full data sync (GitHub Actions workflow)
   */
  FreshnessUI.triggerFullSync = function() {
    // Trigger sync directly without DOM coupling
    console.log('[FreshnessUI] Triggering full sync...');
    
    // Dispatch custom event that controllers can listen to
    const syncEvent = new CustomEvent('dashboard:fullsync', { detail: { timestamp: Date.now() } });
    document.dispatchEvent(syncEvent);
    
    // Also update UI feedback
    const triggerBtn = document.getElementById('trigger-btn');
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.textContent = 'Syncing...';
      setTimeout(() => {
        triggerBtn.disabled = false;
        triggerBtn.textContent = 'Full Sync';
      }, 2000);
    }
  };

  /**
   * Format relative time (e.g., "2 hours ago", "3 days ago")
   */
  FreshnessUI.formatRelativeTime = function(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return 'just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays < 30) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

    const diffMonths = Math.floor(diffDays / 30);
    return `${diffMonths} month${diffMonths > 1 ? 's' : ''} ago`;
  };

  // Export to global scope
  global.FreshnessUI = FreshnessUI;

  // Auto-initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => FreshnessUI.initialize());
  } else {
    FreshnessUI.initialize();
  }

})(window);
