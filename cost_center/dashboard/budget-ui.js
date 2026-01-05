/**
 * Budget UI Module - User interface for budget tracking
 *
 * Features:
 * - Budget alert banner (auto-shows on page load if over budget)
 * - Budget management modal
 * - Real-time budget status updates
 *
 * Dependencies: BudgetService.js, dashboardState
 */

(function(global) {
  'use strict';

  const BudgetUI = {};

  /**
   * Initialize budget UI components
   */
  BudgetUI.initialize = function() {
    console.log('[BudgetUI] Initializing...');

    // Initialize BudgetService
    if (global.BudgetService) {
      global.BudgetService.initialize();
    }

    // Set up event listeners
    this.attachEventListeners();

    // Check for budget alerts on load
    setTimeout(() => this.checkAndShowAlerts(), 1000);
  };

  /**
   * Attach event listeners to budget UI elements
   */
  BudgetUI.attachEventListeners = function() {
    // Budget alert action button
    const alertAction = document.getElementById('budget-alert-action');
    if (alertAction) {
      alertAction.addEventListener('click', () => {
        this.navigateToCostManagement();
      });
    }

    // Listen for budget updates
    window.addEventListener('budgetUpdated', (e) => {
      console.log('[BudgetUI] Budget updated:', e.detail);
      this.checkAndShowAlerts();
    });

    // Add budget management button to header if it doesn't exist
    this.addBudgetButton();
  };

  /**
   * Add "Manage Budgets" button to header
   */
  BudgetUI.addBudgetButton = function() {
    const headerActions = document.querySelector('.header-actions');
    if (!headerActions || document.getElementById('manage-budgets-btn')) return;

    const budgetBtn = document.createElement('button');
    budgetBtn.id = 'manage-budgets-btn';
    budgetBtn.className = 'btn ghost';
    budgetBtn.setAttribute('aria-label', 'Manage budgets');
    budgetBtn.innerHTML = `
      <span class="btn-icon" aria-hidden="true">💰</span>
      Budgets
    `;
    budgetBtn.addEventListener('click', () => this.openBudgetModal());

    // Insert before refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
      headerActions.insertBefore(budgetBtn, refreshBtn);
    } else {
      headerActions.appendChild(budgetBtn);
    }
  };

  /**
   * Check budgets and show alert banner if needed
   */
  BudgetUI.checkAndShowAlerts = function() {
    if (!global.BudgetService || !global.dashboardState) return;

    // Calculate current costs by brand
    const costsByBrand = this.calculateCostsByBrand();

    // Get budget status
    const status = global.BudgetService.getBudgetStatus(costsByBrand);

    // Check overall budget first
    if (status.all && status.all.alert) {
      this.showBudgetAlert(status.all.alert, 'all', status.all.actual);
      return;
    }

    // Check per-brand budgets
    for (const [brand, brandStatus] of Object.entries(status)) {
      if (brand !== 'all' && brandStatus.alert) {
        this.showBudgetAlert(brandStatus.alert, brand, brandStatus.actual);
        return; // Show only one alert at a time
      }
    }

    // No alerts - hide banner
    this.hideBudgetAlert();
  };

  /**
   * Calculate current month costs by brand
   */
  BudgetUI.calculateCostsByBrand = function() {
    const state = global.dashboardState;
    if (!state || !state.factsCost) return {};

    const currentMonth = new Date().toISOString().slice(0, 7);
    const costsByBrand = {};

    state.factsCost.forEach(fact => {
      if (fact.date && fact.date.startsWith(currentMonth)) {
        const brand = fact.brand || 'Unknown';
        costsByBrand[brand] = (costsByBrand[brand] || 0) + (fact.amount || 0);
      }
    });

    return costsByBrand;
  };

  /**
   * Show budget alert banner
   */
  BudgetUI.showBudgetAlert = function(alert, scope, actualCost) {
    const banner = document.getElementById('budget-alert');
    if (!banner) return;

    const title = document.getElementById('budget-alert-title');
    const message = document.getElementById('budget-alert-message');

    if (title) {
      title.textContent = scope === 'all'
        ? 'Budget Alert'
        : `${scope} Budget Alert`;
    }

    if (message) {
      message.textContent = alert.message;
    }

    // Update severity class
    banner.className = 'alert-banner';
    banner.classList.add(alert.severity === 'critical' ? 'danger' : 'warning');

    // Show banner
    banner.classList.remove('hidden');
  };

  /**
   * Hide budget alert banner
   */
  BudgetUI.hideBudgetAlert = function() {
    const banner = document.getElementById('budget-alert');
    if (banner) {
      banner.classList.add('hidden');
    }
  };

  /**
   * Open budget management modal
   */
  BudgetUI.openBudgetModal = function() {
    // Create modal if it doesn't exist
    if (!document.getElementById('budget-modal')) {
      this.createBudgetModal();
    }

    const modal = document.getElementById('budget-modal');
    if (!modal) return;

    // Load current budgets into form
    this.loadBudgetsIntoForm();

    // Show modal
    modal.classList.remove('hidden');
  };

  /**
   * Create budget management modal HTML
   */
  BudgetUI.createBudgetModal = function() {
    const modalHTML = `
      <div class="modal hidden" id="budget-modal">
        <div class="modal-overlay"></div>
        <div class="modal-content">
          <div class="modal-header">
            <h2>💰 Budget Management</h2>
            <button class="modal-close" id="budget-modal-close" aria-label="Close modal">×</button>
          </div>
          <div class="modal-body">
            <p class="modal-description">
              Set monthly budget targets for overall spend and per-brand.
              You'll receive alerts when spending reaches 90% or exceeds 100% of budget.
            </p>

            <form id="budget-form">
              <div class="form-group">
                <label for="budget-all">
                  <strong>Total Monthly Budget</strong>
                  <span class="label-hint">All brands combined</span>
                </label>
                <div class="input-group">
                  <span class="input-prefix">$</span>
                  <input type="number" id="budget-all" name="all" min="0" step="100" placeholder="11500" />
                </div>
              </div>

              <hr class="form-divider" />

              <h3 class="form-section-title">Per-Brand Budgets</h3>

              <div class="form-group">
                <label for="budget-htt">HTT (Head to Toe)</label>
                <div class="input-group">
                  <span class="input-prefix">$</span>
                  <input type="number" id="budget-htt" name="HTT" min="0" step="100" placeholder="5000" />
                </div>
              </div>

              <div class="form-group">
                <label for="budget-bishops">Bishops</label>
                <div class="input-group">
                  <span class="input-prefix">$</span>
                  <input type="number" id="budget-bishops" name="Bishops" min="0" step="100" placeholder="3500" />
                </div>
              </div>

              <div class="form-group">
                <label for="budget-lash">The Lash Lounge</label>
                <div class="input-group">
                  <span class="input-prefix">$</span>
                  <input type="number" id="budget-lash" name="The Lash Lounge" min="0" step="100" placeholder="2000" />
                </div>
              </div>

              <div class="form-group">
                <label for="budget-frenchies">Frenchies</label>
                <div class="input-group">
                  <span class="input-prefix">$</span>
                  <input type="number" id="budget-frenchies" name="Frenchies" min="0" step="100" placeholder="1000" />
                </div>
              </div>

              <div class="form-actions">
                <button type="submit" class="btn primary">Save Budgets</button>
                <button type="button" class="btn ghost" id="budget-reset-btn">Reset to Defaults</button>
                <button type="button" class="btn ghost" id="budget-cancel-btn">Cancel</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);

    // Attach modal event listeners
    this.attachModalListeners();
  };

  /**
   * Attach event listeners to budget modal
   */
  BudgetUI.attachModalListeners = function() {
    const modal = document.getElementById('budget-modal');
    const form = document.getElementById('budget-form');
    const closeBtn = document.getElementById('budget-modal-close');
    const cancelBtn = document.getElementById('budget-cancel-btn');
    const resetBtn = document.getElementById('budget-reset-btn');

    if (!modal || !form) return;

    // Close modal
    const closeModal = () => modal.classList.add('hidden');

    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

    // Click overlay to close
    modal.querySelector('.modal-overlay').addEventListener('click', closeModal);

    // Submit form
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      this.saveBudgetsFromForm();
      closeModal();
    });

    // Reset to defaults
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        // Create modern modal instead of browser confirm()
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
          <div class="modal-content">
            <h3>Reset Budgets</h3>
            <p>Reset all budgets to default values?</p>
            <div class="modal-buttons">
              <button class="btn primary">Reset</button>
              <button class="btn secondary">Cancel</button>
            </div>
          </div>
        `;
        document.body.appendChild(modal);
        
        const buttons = modal.querySelectorAll('button');
        buttons[0].addEventListener('click', () => {
          global.BudgetService.setDefaultBudgets();
          this.loadBudgetsIntoForm();
          modal.remove();
        });
        buttons[1].addEventListener('click', () => modal.remove());
      });
    }
  };

  /**
   * Load current budgets into form
   */
  BudgetUI.loadBudgetsIntoForm = function() {
    if (!global.BudgetService) return;

    const budgets = global.BudgetService.getBudgets();
    const form = document.getElementById('budget-form');
    if (!form) return;

    // Load each budget value
    Object.entries(budgets).forEach(([scope, config]) => {
      const input = form.querySelector(`[name="${scope}"]`);
      if (input) {
        input.value = config.amount || '';
      }
    });
  };

  /**
   * Save budgets from form
   */
  BudgetUI.saveBudgetsFromForm = function() {
    if (!global.BudgetService) return;

    const form = document.getElementById('budget-form');
    if (!form) return;

    const formData = new FormData(form);
    const budgets = {};

    for (const [scope, value] of formData.entries()) {
      const amount = parseFloat(value);
      if (amount > 0) {
        budgets[scope] = amount;
      }
    }

    // Save budgets
    global.BudgetService.saveBudgets(budgets);

    // Show success message
    this.showToast('✓ Budgets saved successfully');

    // Refresh alerts
    this.checkAndShowAlerts();
  };

  /**
   * Navigate to cost management section
   */
  BudgetUI.navigateToCostManagement = function() {
    // Hide alert
    this.hideBudgetAlert();

    // Navigate to cost management
    if (global.dashboard && global.dashboard.navigateToSection) {
      global.dashboard.navigateToSection('cost-management');
    } else {
      window.location.hash = '#cost-management';
    }
  };

  /**
   * Show toast notification
   */
  BudgetUI.showToast = function(message, duration = 3000) {
    // Create toast if it doesn't exist
    let toast = document.getElementById('budget-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'budget-toast';
      toast.className = 'toast';
      document.body.appendChild(toast);
    }

    toast.textContent = message;
    toast.classList.add('show');

    setTimeout(() => {
      toast.classList.remove('show');
    }, duration);
  };

  // Export to global scope
  global.BudgetUI = BudgetUI;

  // Auto-initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => BudgetUI.initialize());
  } else {
    BudgetUI.initialize();
  }

})(window);
