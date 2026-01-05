/**
 * BudgetService - Manages budget tracking and alerts
 *
 * Features:
 * - Monthly budget tracking (overall and per-brand)
 * - Budget alerts (warning at 90%, critical at 100%)
 * - Forecasting (predict next month based on trends)
 * - Variance analysis (actual vs budget)
 *
 * Storage: LocalStorage (can be upgraded to backend API later)
 *
 * Usage:
 *   BudgetService.initialize();
 *   BudgetService.setBudget('all', 11500);
 *   const alert = BudgetService.checkAlert('all', actualCost);
 */

(function(global) {
  'use strict';

  class BudgetService {
    /**
     * Initialize the budget service
     * Loads saved budgets from localStorage
     */
    static initialize() {
      console.log('[BudgetService] Initializing...');

      // Set default budgets if none exist
      const budgets = this.getBudgets();
      if (Object.keys(budgets).length === 0) {
        this.setDefaultBudgets();
      }
    }

    /**
     * Get all budgets
     * @returns {Object} Budget configuration
     */
    static getBudgets() {
      const stored = localStorage.getItem('dashboardBudgets');
      if (!stored) return {};

      try {
        return JSON.parse(stored);
      } catch (error) {
        console.error('[BudgetService] Failed to parse budgets:', error);
        return {};
      }
    }

    /**
     * Set budget for a scope
     * @param {string} scope - 'all', 'htt', 'bishops', 'lash', 'frenchies'
     * @param {number} amount - Monthly budget amount
     */
    static setBudget(scope, amount) {
      const budgets = this.getBudgets();
      budgets[scope] = {
        amount: Number(amount),
        currency: 'USD',
        period: 'monthly',
        lastUpdated: new Date().toISOString()
      };

      localStorage.setItem('dashboardBudgets', JSON.stringify(budgets));
      console.log(`[BudgetService] Set budget for ${scope}: $${amount}`);

      // Dispatch event for UI updates
      window.dispatchEvent(new CustomEvent('budgetUpdated', {
        detail: { scope, amount }
      }));
    }

    /**
     * Save multiple budgets at once
     * @param {Object} budgets - { scope: amount, ... }
     */
    static saveBudgets(budgets) {
      Object.entries(budgets).forEach(([scope, amount]) => {
        this.setBudget(scope, amount);
      });
    }

    /**
     * Get budget for a specific scope
     * @param {string} scope - 'all', 'htt', etc.
     * @returns {number} Budget amount or 0
     */
    static getBudget(scope) {
      const budgets = this.getBudgets();
      return budgets[scope] ? budgets[scope].amount : 0;
    }

    /**
     * Set default budgets (for new users)
     */
    static setDefaultBudgets() {
      const defaults = {
        all: 11500,    // Total monthly budget
        'Head to Toe Brands': 5000,     // HTT
        'Bishops': 3500, // BCC
        'The Lash Lounge': 2000,   // TLL
        'Frenchies': 1000 // FN
      };

      console.log('[BudgetService] Setting default budgets...');
      this.saveBudgets(defaults);
    }

    /**
     * Check if actual cost triggers a budget alert
     * @param {string} scope - Budget scope
     * @param {number} actualCost - Current spend
     * @returns {Object|null} Alert details or null
     */
    static checkAlert(scope, actualCost) {
      const budget = this.getBudget(scope);
      if (!budget || budget === 0) return null;

      const percent = (actualCost / budget) * 100;

      if (percent >= 100) {
        return {
          severity: 'critical',
          level: 'over',
          percent: percent,
          message: `${percent.toFixed(0)}% of budget ($${actualCost.toLocaleString()} of $${budget.toLocaleString()})`,
          overage: actualCost - budget,
          recommendation: `You are $${(actualCost - budget).toLocaleString()} over budget. Review spending immediately.`
        };
      } else if (percent >= 90) {
        return {
          severity: 'warning',
          level: 'approaching',
          percent: percent,
          message: `${percent.toFixed(0)}% of budget ($${actualCost.toLocaleString()} of $${budget.toLocaleString()})`,
          overage: actualCost - budget,
          recommendation: `You are approaching your budget limit. $${(budget - actualCost).toLocaleString()} remaining.`
        };
      }

      return null; // No alert needed
    }

    /**
     * Get budget status for all scopes
     * @param {Object} costsByBrand - { brand: amount, ... }
     * @returns {Object} Status for each scope
     */
    static getBudgetStatus(costsByBrand) {
      const budgets = this.getBudgets();
      const status = {};

      // Calculate total
      const totalCost = Object.values(costsByBrand).reduce((sum, cost) => sum + cost, 0);
      const totalBudget = this.getBudget('all');

      status.all = {
        budget: totalBudget,
        actual: totalCost,
        remaining: totalBudget - totalCost,
        percent: totalBudget > 0 ? (totalCost / totalBudget) * 100 : 0,
        alert: this.checkAlert('all', totalCost)
      };

      // Calculate per-brand
      Object.entries(costsByBrand).forEach(([brand, cost]) => {
        const budget = this.getBudget(brand);
        status[brand] = {
          budget: budget,
          actual: cost,
          remaining: budget - cost,
          percent: budget > 0 ? (cost / budget) * 100 : 0,
          alert: this.checkAlert(brand, cost)
        };
      });

      return status;
    }

    /**
     * Forecast next month's cost based on historical data
     * Uses simple linear regression on last 6 months
     * @param {Array} monthlyCosts - [{ month, amount }, ...]
     * @returns {number} Predicted next month cost
     */
    static forecast(monthlyCosts) {
      if (!monthlyCosts || monthlyCosts.length < 3) {
        // Not enough data for forecasting
        return null;
      }

      // Take last 6 months
      const recent = monthlyCosts.slice(-6);

      // Simple linear regression
      const n = recent.length;
      let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;

      recent.forEach((point, index) => {
        const x = index;
        const y = point.amount;
        sumX += x;
        sumY += y;
        sumXY += x * y;
        sumX2 += x * x;
      });

      // Protect against division by zero when all x values are identical
      const denominator = (n * sumX2 - sumX * sumX);
      if (Math.abs(denominator) < 0.0001) {
        // All x values are identical - return last y value
        return Math.max(0, yValues[yValues.length - 1]);
      }
      
      const slope = (n * sumXY - sumX * sumY) / denominator;
      const intercept = (sumY - slope * sumX) / n;

      // Predict next month (index = n)
      const forecast = slope * n + intercept;

      return Math.max(0, forecast); // Don't predict negative costs
    }

    /**
     * Get forecast with confidence interval
     * @param {Array} monthlyCosts - Historical monthly costs
     * @returns {Object} Forecast details
     */
    static getForecastDetails(monthlyCosts) {
      const prediction = this.forecast(monthlyCosts);
      if (!prediction) {
        return {
          predicted: 0,
          confidence: 'low',
          message: 'Not enough historical data for forecasting'
        };
      }

      // Calculate average and standard deviation
      const recent = monthlyCosts.slice(-6);
      const avg = recent.reduce((sum, m) => sum + m.amount, 0) / recent.length;
      const variance = recent.reduce((sum, m) => sum + Math.pow(m.amount - avg, 2), 0) / recent.length;
      const stdDev = Math.sqrt(variance);

      // Confidence based on standard deviation
      const cv = stdDev / avg; // Coefficient of variation
      let confidence;
      if (cv < 0.1) confidence = 'high';
      else if (cv < 0.2) confidence = 'medium';
      else confidence = 'low';

      return {
        predicted: prediction,
        low: Math.max(0, prediction - stdDev),
        high: prediction + stdDev,
        confidence: confidence,
        trend: prediction > avg ? 'increasing' : 'decreasing',
        message: `Predicted: $${prediction.toLocaleString()} (${confidence} confidence)`
      };
    }

    /**
     * Calculate variance analysis (actual vs budget)
     * @param {number} actual - Actual cost
     * @param {number} budget - Budget amount
     * @returns {Object} Variance details
     */
    static calculateVariance(actual, budget) {
      if (!budget || budget === 0) {
        return {
          amount: 0,
          percent: 0,
          status: 'no-budget',
          message: 'No budget set'
        };
      }

      const variance = actual - budget;
      const percent = (variance / budget) * 100;

      let status;
      if (percent > 10) status = 'unfavorable';
      else if (percent > 0) status = 'over';
      else if (percent > -10) status = 'on-track';
      else status = 'favorable';

      return {
        amount: variance,
        percent: percent,
        status: status,
        message: variance > 0
          ? `Over budget by $${Math.abs(variance).toLocaleString()} (${Math.abs(percent).toFixed(1)}%)`
          : `Under budget by $${Math.abs(variance).toLocaleString()} (${Math.abs(percent).toFixed(1)}%)`
      };
    }

    /**
     * Clear all budgets (reset)
     */
    static clearBudgets() {
      localStorage.removeItem('dashboardBudgets');
      console.log('[BudgetService] Cleared all budgets');
    }

    /**
     * Export budget configuration
     * @returns {Object} Budget export data
     */
    static exportConfig() {
      return {
        budgets: this.getBudgets(),
        exportedAt: new Date().toISOString(),
        version: '1.0'
      };
    }

    /**
     * Import budget configuration
     * @param {Object} config - Exported budget data
     */
    static importConfig(config) {
      if (config.budgets) {
        localStorage.setItem('dashboardBudgets', JSON.stringify(config.budgets));
        console.log('[BudgetService] Imported budget configuration');
      }
    }
  }

  // Export to global scope
  global.BudgetService = BudgetService;

})(window);
