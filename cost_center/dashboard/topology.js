/**
 * Dashboard Topology Module
 * Renders interactive cross-tenant Azure + M365 architecture visualization
 * 
 * @namespace DashboardTopology
 * @version 1.0.0
 */

(function(global) {
  'use strict';

  // ============================================================================
  // CONSTANTS
  // ============================================================================

  const TENANT_COLORS = {
    htt: { primary: '#2563eb', secondary: '#3b82f6', text: '#ffffff', border: '#1e40af' },
    bcc: { primary: '#dc2626', secondary: '#ef4444', text: '#ffffff', border: '#b91c1c' },
    fn: { primary: '#059669', secondary: '#10b981', text: '#ffffff', border: '#047857' },
    tll: { primary: '#7c3aed', secondary: '#8b5cf6', text: '#ffffff', border: '#6d28d9' }
  };

  const CONNECTION_COLORS = {
    identity: '#3b82f6',  // Blue
    data: '#10b981',      // Green
    network: '#f59e0b',   // Orange
    devops: '#8b5cf6'     // Purple
  };

  const LAYER_ICONS = {
    identity: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
    network: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
    compute: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>`,
    data: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>`,
    devops: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"></line><circle cx="18" cy="6" r="3"></circle><circle cx="6" cy="18" r="3"></circle><path d="M18 9a9 9 0 0 1-9 9"></path></svg>`
  };

  // ============================================================================
  // RENDERING FUNCTIONS
  // ============================================================================

  /**
   * Render the main topology view
   * @param {HTMLElement} container - Container element
   * @param {Object} topology - Topology data from cloudTopology
   */
  function renderTopologyView(container, topology) {
    if (!container || !topology) return;

    container.innerHTML = `
      <div class="topology-container">
        <div class="topology-header">
          <h2>Cloud Architecture</h2>
          <p class="topology-subtitle">${topology.description || 'Multi-tenant Azure + M365 Architecture'}</p>
          <div class="topology-controls">
            <div class="layer-toggles" role="group" aria-label="Layer visibility">
              ${renderLayerToggles(topology.layers)}
            </div>
            <div class="view-toggles">
              <button class="view-btn active" data-view="diagram" aria-pressed="true">Diagram</button>
              <button class="view-btn" data-view="list" aria-pressed="false">List View</button>
            </div>
          </div>
        </div>
        
        <div class="topology-main">
          <div class="topology-diagram" id="topology-diagram">
            ${renderDiagram(topology)}
          </div>
          <div class="topology-list hidden" id="topology-list">
            ${renderListView(topology)}
          </div>
        </div>
        
        <div class="topology-sidebar">
          <div class="topology-legend">
            <h3>Legend</h3>
            ${renderLegend()}
          </div>
          <div class="topology-details" id="topology-details">
            <h3>Details</h3>
            <p class="hint">Click a tenant or resource to see details</p>
          </div>
          <div class="topology-cost-summary">
            <h3>Cost Summary (MTD)</h3>
            ${renderCostSummary(topology.costSummary)}
          </div>
        </div>
      </div>
    `;

    // Attach event handlers
    attachTopologyEventHandlers(container, topology);
  }

  /**
   * Render layer toggle buttons
   */
  function renderLayerToggles(layers) {
    if (!layers) return '';
    
    return Object.entries(layers).map(([key, layer]) => `
      <label class="layer-toggle">
        <input type="checkbox" data-layer="${key}" checked />
        <span class="layer-icon">${LAYER_ICONS[key] || ''}</span>
        <span class="layer-name">${layer.name}</span>
      </label>
    `).join('');
  }

  /**
   * Render the interactive SVG diagram
   */
  function renderDiagram(topology) {
    const tenants = topology.tenants || [];
    const connections = topology.connections || [];
    
    // Calculate positions for hub-spoke layout
    const centerX = 400;
    const centerY = 300;
    const spokesRadius = 250;
    
    const anchorTenant = tenants.find(t => t.role === 'anchor');
    const spokeTenants = tenants.filter(t => t.role === 'spoke');
    
    let svg = `
      <svg viewBox="0 0 800 600" class="topology-svg" role="img" aria-label="Cross-tenant architecture diagram">
        <defs>
          ${renderSvgDefs()}
        </defs>
        
        <!-- Connections -->
        <g class="connections-layer">
          ${renderConnections(connections, anchorTenant, spokeTenants, centerX, centerY, spokesRadius)}
        </g>
        
        <!-- Tenants -->
        <g class="tenants-layer">
          ${anchorTenant ? renderTenantNode(anchorTenant, centerX, centerY, true) : ''}
          ${spokeTenants.map((tenant, i) => {
            const angle = (i * (2 * Math.PI / spokeTenants.length)) - Math.PI / 2;
            const x = centerX + spokesRadius * Math.cos(angle);
            const y = centerY + spokesRadius * Math.sin(angle);
            return renderTenantNode(tenant, x, y, false);
          }).join('')}
        </g>
        
        <!-- GitHub (top right) -->
        <g class="github-layer" transform="translate(700, 50)">
          ${renderGitHubNode(tenants)}
        </g>
      </svg>
    `;
    
    return svg;
  }

  /**
   * Render SVG definitions (gradients, markers, filters)
   */
  function renderSvgDefs() {
    return `
      <!-- Gradients for tenants -->
      ${Object.entries(TENANT_COLORS).map(([id, colors]) => `
        <linearGradient id="grad-${id}" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" style="stop-color:${colors.primary};stop-opacity:1" />
          <stop offset="100%" style="stop-color:${colors.secondary};stop-opacity:1" />
        </linearGradient>
      `).join('')}
      
      <!-- Arrow markers for connections -->
      ${Object.entries(CONNECTION_COLORS).map(([type, color]) => `
        <marker id="arrow-${type}" viewBox="0 0 10 10" refX="9" refY="5"
                markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="${color}" />
        </marker>
      `).join('')}
      
      <!-- Drop shadow filter -->
      <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.15"/>
      </filter>
      
      <!-- Glow filter for hover -->
      <filter id="glow">
        <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
        <feMerge>
          <feMergeNode in="coloredBlur"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
    `;
  }

  /**
   * Render a tenant node
   */
  function renderTenantNode(tenant, x, y, isAnchor) {
    const colors = TENANT_COLORS[tenant.id] || TENANT_COLORS.htt;
    const size = isAnchor ? 80 : 60;
    const subscriptions = tenant.subscriptions || [];
    const totalCost = subscriptions.reduce((sum, s) => sum + (s.mtdCost || 0), 0);
    
    return `
      <g class="tenant-node" data-tenant="${tenant.id}" tabindex="0" role="button"
         aria-label="${tenant.name}: ${subscriptions.length} subscriptions, $${totalCost.toFixed(2)} MTD">
        <circle cx="${x}" cy="${y}" r="${size}" 
                fill="url(#grad-${tenant.id})" 
                stroke="${colors.border}" stroke-width="3"
                filter="url(#shadow)"
                class="tenant-circle" />
        
        ${isAnchor ? `
          <circle cx="${x}" cy="${y}" r="${size + 8}" 
                  fill="none" stroke="${colors.primary}" stroke-width="2" 
                  stroke-dasharray="5,5" opacity="0.5" />
        ` : ''}
        
        <text x="${x}" y="${y - 8}" text-anchor="middle" 
              fill="${colors.text}" font-weight="600" font-size="14">
          ${tenant.displayName || tenant.name}
        </text>
        <text x="${x}" y="${y + 10}" text-anchor="middle" 
              fill="${colors.text}" font-size="11" opacity="0.9">
          ${subscriptions.length} sub${subscriptions.length !== 1 ? 's' : ''}
        </text>
        <text x="${x}" y="${y + 26}" text-anchor="middle" 
              fill="${colors.text}" font-size="12" font-weight="500">
          $${totalCost.toFixed(0)}/mo
        </text>
      </g>
    `;
  }

  /**
   * Render connections between tenants
   */
  function renderConnections(connections, anchor, spokes, cx, cy, radius) {
    if (!anchor || !connections) return '';
    
    const spokePositions = {};
    spokes.forEach((tenant, i) => {
      const angle = (i * (2 * Math.PI / spokes.length)) - Math.PI / 2;
      spokePositions[tenant.id] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle)
      };
    });
    
    return connections.map(conn => {
      const color = CONNECTION_COLORS[conn.type] || '#64748b';
      const targets = Array.isArray(conn.targets) ? conn.targets : [conn.targets];
      
      return targets.map(targetId => {
        const target = spokePositions[targetId];
        if (!target) return '';
        
        // Calculate control points for curved lines
        const midX = (cx + target.x) / 2;
        const midY = (cy + target.y) / 2;
        const offset = 30;
        const perpX = -(target.y - cy) / radius * offset;
        const perpY = (target.x - cx) / radius * offset;
        
        return `
          <g class="connection" data-connection="${conn.id}" data-type="${conn.type}">
            <path d="M ${cx} ${cy} Q ${midX + perpX} ${midY + perpY} ${target.x} ${target.y}"
                  stroke="${color}" stroke-width="2" fill="none"
                  marker-end="url(#arrow-${conn.type})"
                  opacity="0.7"
                  class="connection-path" />
            <title>${conn.description || conn.subtype}</title>
          </g>
        `;
      }).join('');
    }).join('');
  }

  /**
   * Render GitHub node
   */
  function renderGitHubNode(tenants) {
    const orgs = tenants.map(t => t.githubOrg).filter(Boolean);
    
    return `
      <g class="github-node" tabindex="0" role="button" aria-label="GitHub: ${orgs.length} organizations">
        <rect x="-40" y="-25" width="80" height="50" rx="8" 
              fill="#24292f" stroke="#1b1f23" stroke-width="2" filter="url(#shadow)" />
        <text x="0" y="-5" text-anchor="middle" fill="#fff" font-size="12" font-weight="600">GitHub</text>
        <text x="0" y="12" text-anchor="middle" fill="#8b949e" font-size="10">${orgs.length} orgs</text>
      </g>
    `;
  }

  /**
   * Render the list view alternative
   */
  function renderListView(topology) {
    const tenants = topology.tenants || [];
    
    return `
      <div class="topology-list-view">
        ${tenants.map(tenant => `
          <div class="tenant-card" data-tenant="${tenant.id}" style="border-left: 4px solid ${TENANT_COLORS[tenant.id]?.primary || '#64748b'}">
            <div class="tenant-card-header">
              <h3>${tenant.name}</h3>
              <span class="tenant-role badge ${tenant.role}">${tenant.role}</span>
            </div>
            <div class="tenant-card-meta">
              <span>🏢 ${tenant.domain}</span>
              <span>💳 ${tenant.billingModel}</span>
              <span>🐙 ${tenant.githubOrg || 'N/A'}</span>
            </div>
            <div class="subscription-list">
              ${(tenant.subscriptions || []).map(sub => `
                <div class="subscription-item">
                  <div class="sub-header">
                    <strong>${sub.name}</strong>
                    <span class="sub-cost">$${(sub.mtdCost || 0).toFixed(2)}</span>
                  </div>
                  <div class="sub-purpose">${sub.purpose}</div>
                  ${(sub.resourceGroups || []).length > 0 ? `
                    <div class="rg-list">
                      ${sub.resourceGroups.map(rg => `
                        <div class="rg-item">
                          <span class="rg-name">📁 ${rg.name}</span>
                          <span class="rg-count">${rg.resourceCount} resource${rg.resourceCount !== 1 ? 's' : ''}</span>
                        </div>
                      `).join('')}
                    </div>
                  ` : ''}
                </div>
              `).join('')}
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  /**
   * Render the legend
   */
  function renderLegend() {
    return `
      <div class="legend-section">
        <h4>Tenants</h4>
        <div class="legend-item">
          <span class="legend-marker" style="background: ${TENANT_COLORS.htt.primary}"></span>
          <span>Anchor Tenant</span>
        </div>
        <div class="legend-item">
          <span class="legend-marker" style="background: #64748b"></span>
          <span>Spoke Tenant</span>
        </div>
      </div>
      <div class="legend-section">
        <h4>Connections</h4>
        ${Object.entries(CONNECTION_COLORS).map(([type, color]) => `
          <div class="legend-item">
            <span class="legend-line" style="background: ${color}"></span>
            <span>${type.charAt(0).toUpperCase() + type.slice(1)}</span>
          </div>
        `).join('')}
      </div>
    `;
  }

  /**
   * Render cost summary
   */
  function renderCostSummary(costSummary) {
    if (!costSummary) return '<p>No cost data available</p>';
    
    return `
      <div class="cost-summary">
        <div class="total-cost">
          <span class="cost-label">Total MTD</span>
          <span class="cost-value">$${(costSummary.totalMTD || 0).toFixed(2)}</span>
        </div>
        <div class="cost-by-tenant">
          ${Object.entries(costSummary.byTenant || {}).map(([id, cost]) => `
            <div class="tenant-cost">
              <span class="tenant-dot" style="background: ${TENANT_COLORS[id]?.primary || '#64748b'}"></span>
              <span class="tenant-label">${id.toUpperCase()}</span>
              <span class="tenant-cost-value">$${(cost || 0).toFixed(2)}</span>
            </div>
          `).join('')}
        </div>
        ${costSummary.topServices ? `
          <div class="top-services">
            <h4>Top Services</h4>
            ${costSummary.topServices.slice(0, 5).map(svc => `
              <div class="service-cost">
                <span class="service-name">${svc.name}</span>
                <span class="service-value">$${(svc.cost || 0).toFixed(2)}</span>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  }

  /**
   * Attach event handlers for interactivity
   */
  function attachTopologyEventHandlers(container, topology) {
    // View toggle
    const viewBtns = container.querySelectorAll('.view-btn');
    viewBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        viewBtns.forEach(b => {
          b.classList.remove('active');
          b.setAttribute('aria-pressed', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-pressed', 'true');
        
        const view = btn.dataset.view;
        container.querySelector('#topology-diagram').classList.toggle('hidden', view !== 'diagram');
        container.querySelector('#topology-list').classList.toggle('hidden', view !== 'list');
      });
    });
    
    // Layer toggles
    const layerToggles = container.querySelectorAll('.layer-toggle input');
    layerToggles.forEach(toggle => {
      toggle.addEventListener('change', () => {
        const layer = toggle.dataset.layer;
        const svg = container.querySelector('.topology-svg');
        if (!svg) return;
        
        const connections = svg.querySelectorAll(`.connection[data-type="${layer}"]`);
        connections.forEach(conn => {
          conn.style.display = toggle.checked ? '' : 'none';
        });
      });
    });
    
    // Tenant node click
    const tenantNodes = container.querySelectorAll('.tenant-node, .tenant-card');
    tenantNodes.forEach(node => {
      node.addEventListener('click', () => {
        const tenantId = node.dataset.tenant;
        const tenant = (topology.tenants || []).find(t => t.id === tenantId);
        if (tenant) {
          showTenantDetails(container, tenant);
        }
      });
      
      // Keyboard support
      node.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          node.click();
        }
      });
    });
  }

  /**
   * Show tenant details in sidebar
   */
  function showTenantDetails(container, tenant) {
    const detailsEl = container.querySelector('#topology-details');
    if (!detailsEl) return;
    
    const colors = TENANT_COLORS[tenant.id] || TENANT_COLORS.htt;
    const subscriptions = tenant.subscriptions || [];
    const totalCost = subscriptions.reduce((sum, s) => sum + (s.mtdCost || 0), 0);
    
    detailsEl.innerHTML = `
      <h3 style="color: ${colors.primary}">${tenant.name}</h3>
      <div class="detail-section">
        <div class="detail-row">
          <span class="detail-label">Role</span>
          <span class="detail-value badge ${tenant.role}">${tenant.role}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Domain</span>
          <span class="detail-value">${tenant.domain}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Billing</span>
          <span class="detail-value">${tenant.billingModel}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">GitHub</span>
          <span class="detail-value">
            <a href="https://github.com/${tenant.githubOrg}" target="_blank" rel="noopener">
              ${tenant.githubOrg || 'N/A'}
            </a>
          </span>
        </div>
        <div class="detail-row">
          <span class="detail-label">MTD Cost</span>
          <span class="detail-value cost">$${totalCost.toFixed(2)}</span>
        </div>
      </div>
      
      <h4>Subscriptions (${subscriptions.length})</h4>
      <div class="subscriptions-detail">
        ${subscriptions.map(sub => `
          <div class="sub-detail">
            <div class="sub-detail-header">
              <strong>${sub.name}</strong>
              <span>$${(sub.mtdCost || 0).toFixed(2)}</span>
            </div>
            <div class="sub-detail-purpose">${sub.purpose}</div>
            ${(sub.resourceGroups || []).length > 0 ? `
              <div class="sub-detail-rgs">
                ${sub.resourceGroups.map(rg => `
                  <div class="rg-detail">
                    <span>📁 ${rg.name}</span>
                    <span class="rg-resources">${rg.topResources?.join(', ') || ''}</span>
                  </div>
                `).join('')}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    `;
  }

  // ============================================================================
  // PUBLIC API
  // ============================================================================

  const DashboardTopology = {
    TENANT_COLORS,
    CONNECTION_COLORS,
    LAYER_ICONS,
    renderTopologyView,
    renderDiagram,
    renderListView,
    renderCostSummary,
    showTenantDetails
  };

  // Export as UMD module
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardTopology;
  } else {
    global.DashboardTopology = DashboardTopology;
  }

})(typeof window !== 'undefined' ? window : this);