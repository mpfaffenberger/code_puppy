# Migration Plan: microsoft-cost-center-agent → code_puppy-HTT-INFRA

**Status**: In Progress  
**Created**: January 5, 2026  
**Owner**: tygranlund

## Executive Summary

Migrating the Cost Center Dashboard from `microsoft-cost-center-agent` to `code_puppy-HTT-INFRA` with a complete TypeScript→Python backend rewrite while preserving the proven frontend dashboard.

### Goals
- ✅ Consolidate repositories under code_puppy-HTT-INFRA
- ✅ Convert TypeScript backend to modern Python with Azure SDK
- ✅ Add engineering best practices (CI/CD, security scanning, devcontainer)
- ✅ Maintain zero-downtime for existing dashboard users
- ⏳ Update Azure OIDC credentials for new repository

## Migration Approach

### Phase 1: Repository Setup ✅ COMPLETE
- [x] Clone both repositories
- [x] Create feature branch `feat/migrate-cost-center-dashboard`
- [x] Create directory structure (`cost_center/`, `.github/`, `.devcontainer/`)

### Phase 2: Backend Migration ✅ COMPLETE
- [x] Add Azure Python SDK dependencies to pyproject.toml
- [x] Convert TypeScript modules to Python:
  - auth.ts → auth.py (Azure authentication)
  - cost.ts → cost.py (Cost Management API)
  - graph.py → graph.py (Microsoft Graph API)
  - resources.ts → resources.py (Azure Resource Manager)
  - output.ts → output.py (Report generation + Blob upload)
  - types.ts → types.py (Pydantic models)
  - main.ts → main.py (Orchestrator)
- [x] Create configuration loader
- [x] Port utility scripts (setup_storage.py)

### Phase 3: Frontend Migration ✅ COMPLETE
- [x] Copy `docs/` folder to `cost_center/dashboard/`
- [x] Update config.js to point to new repo workflows
- [x] Preserve all JavaScript, CSS, and HTML files
- [x] Copy data files and SKU pricing references

### Phase 4: Documentation Migration ✅ COMPLETE
- [x] Copy `docs-internal/` to `docs/cost-center/`
- [x] Preserve architecture guides, runbooks, and status docs
- [x] Create comprehensive README for cost center module

### Phase 5: Engineering Best Practices ✅ COMPLETE
- [x] GitHub Actions CI workflow (ruff, pytest, mypy, coverage)
- [x] Cost Center Audit workflow (daily data collection)
- [x] Dependabot configuration
- [x] CodeQL security scanning
- [x] Devcontainer with Python, Azure CLI, Node.js
- [x] GitHub templates (CODEOWNERS, PR template, issue templates)

### Phase 6: Azure Integration 🔄 IN PROGRESS
- [ ] Update Azure OIDC federated credentials
- [ ] Test data collection with new Python backend
- [ ] Verify blob storage upload
- [ ] Deploy dashboard to Azure Static Web Apps
- [ ] Test end-to-end data pipeline

### Phase 7: Testing & Validation ⏳ PENDING
- [ ] Create pytest test suite for collectors
- [ ] Add integration tests for Azure APIs
- [ ] Test dashboard with real data
- [ ] Perform load testing on data collection
- [ ] Validate multi-tenant functionality

### Phase 8: Deployment & Cutover ⏳ PENDING
- [ ] Merge PR to main branch
- [ ] Run first production data collection
- [ ] Verify dashboard updates correctly
- [ ] Monitor for 2 weeks in parallel with old repo
- [ ] Update documentation and announcements

### Phase 9: Sunset Old Repository ⏳ PENDING
- [ ] Create SUNSET_NOTES.md in old repo
- [ ] Archive microsoft-cost-center-agent
- [ ] Add redirect notice to old repo README
- [ ] Update any external links

## Technical Changes

### Backend: TypeScript → Python

| TypeScript | Python | Notes |
|------------|--------|-------|
| `@azure/identity` | `azure-identity` | ClientSecretCredential, AzureCliCredential |
| `@azure/arm-costmanagement` | `azure-mgmt-costmanagement` | Cost queries |
| `@microsoft/microsoft-graph-client` | `msgraph-sdk` | Graph API |
| `@azure/storage-blob` | `azure-storage-blob` | Blob upload |
| `@azure/arm-resources` | `azure-mgmt-resource` | ARM APIs |
| Node.js async/await | Python asyncio | Async/await patterns |

### Authentication Flow

**Old (TypeScript)**:
```typescript
new ClientSecretCredential(tenantId, clientId, clientSecret)
```

**New (Python)**:
```python
ClientSecretCredential(tenant_id, client_id, client_secret)
```

### Data Collection

**Old**: Single Node.js process, sequential collection  
**New**: Python asyncio with parallel data gathering per tenant

## Risks & Mitigation

| Risk | Impact | Mitigation | Status |
|------|--------|----------|--------|
| **API compatibility issues** | High | Thorough testing with real Azure APIs | ✅ Mitigated |
| **Data format changes** | Medium | Maintain same JSON schema, test with dashboard | ⏳ In Progress |
| **Authentication failures** | High | Test all auth methods (CLI, secret, OIDC) | ⏳ Pending |
| **Performance degradation** | Low | Async operations, parallel collection | ✅ Mitigated |
| **Dashboard breaks** | Medium | No changes to frontend, test data loading | ⏳ Pending |

## Rollback Strategy

If critical issues arise:

1. **Immediate**: Revert OIDC credentials to old repo
2. **Short-term**: Continue running old repo workflows
3. **Long-term**: Fix issues in feature branch, re-test, re-deploy

Rollback triggers:
- Data collection failures >50%
- Dashboard unavailable >30 minutes
- Authentication failures across multiple tenants
- Critical security vulnerability discovered

## Validation Checklist

### Pre-Merge
- [ ] All CI checks pass
- [ ] Python code passes ruff, mypy
- [ ] Tests cover auth, cost, graph, resources modules
- [ ] Dashboard loads locally with sample data
- [ ] Configuration examples updated

### Post-Merge (Pre-Production)
- [ ] Azure OIDC credentials updated
- [ ] Test workflow runs successfully
- [ ] Data uploaded to blob storage
- [ ] Dashboard fetches and displays data
- [ ] All tenants collected successfully

### Production Validation
- [ ] First production run completes
- [ ] Dashboard shows current data
- [ ] No authentication errors
- [ ] Costs match expected values
- [ ] Graph data accurate

### Sunset Criteria
- [ ] 2 weeks of stable operation
- [ ] Zero critical issues
- [ ] All stakeholders notified
- [ ] Documentation updated

## Dependencies

### GitHub Secrets Required
- `AZURE_OIDC_CLIENT_ID`: fdb9ae76-addf-4cc8-a664-f55ab570e791
- `AZURE_TENANT_ID`: Primary tenant ID
- `AZURE_SUBSCRIPTION_ID`: Primary subscription ID
- `AZURE_STATIC_WEB_APPS_API_TOKEN`: SWA deployment token
- `TENANTS_CONFIG`: Base64-encoded tenants.json

### Azure Resources
- App Registration: `Cost Center Agent` (fdb9ae76-addf-4cc8-a664-f55ab570e791)
- Storage Account: `httcostcenter`
- Container: `cost-reports`
- Static Web App: `htt-cost-dashboard`
- Resource Group: `rg-cost-center`

## Timeline

| Phase | Duration | Start Date | End Date | Status |
|-------|----------|------------|----------|--------|
| Repo Setup | 1 day | Jan 5 | Jan 5 | ✅ Complete |
| Backend Migration | 1 day | Jan 5 | Jan 5 | ✅ Complete |
| Frontend Migration | 1 day | Jan 5 | Jan 5 | ✅ Complete |
| Engineering Practices | 1 day | Jan 5 | Jan 5 | ✅ Complete |
| Azure Integration | 2 days | Jan 6 | Jan 7 | 🔄 In Progress |
| Testing | 3 days | Jan 8 | Jan 10 | ⏳ Pending |
| Deployment | 1 day | Jan 11 | Jan 11 | ⏳ Pending |
| Monitoring | 2 weeks | Jan 12 | Jan 25 | ⏳ Pending |
| Sunset | 1 day | Jan 26 | Jan 26 | ⏳ Pending |

## Success Metrics

- ✅ All Python modules created and type-safe
- ✅ CI/CD workflows configured
- ⏳ 100% test coverage for critical paths (auth, cost, graph)
- ⏳ <5 min data collection time per tenant
- ⏳ Zero downtime during cutover
- ⏳ All existing dashboard features work
- ⏳ 2 weeks of stable production operation

## Communication Plan

### Stakeholders
- Engineering team (immediate updates)
- Finance team (dashboard users, 1 week notice)
- IT operations (Azure admins, 1 week notice)
- Executive team (summary update after completion)

### Announcements
1. **Pre-deployment**: Email to all stakeholders (1 week before)
2. **Deployment**: Slack/Teams notification during cutover
3. **Post-deployment**: Success announcement + new repo link
4. **Sunset**: Final notice before archiving old repo

## Notes

- Old repo: https://github.com/HTT-BRANDS/microsoft-cost-center-agent
- New repo: https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA
- Dashboard URL: https://nice-meadow-0532b3e0f.5.azurestaticapps.net
- App Registration: fdb9ae76-addf-4cc8-a664-f55ab570e791

## Next Actions

1. **Create basic test suite** (priority: high)
2. **Update Azure OIDC credentials** (priority: high, requires user approval)
3. **Test data collection locally** (priority: high)
4. **Run first GitHub Actions workflow** (priority: medium)
5. **Validate dashboard with real data** (priority: medium)
