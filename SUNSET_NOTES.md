# Sunset Notice: microsoft-cost-center-agent

**Status**: ⏳ Pending Migration Completion  
**New Repository**: [code_puppy-HTT-INFRA](https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA)  
**Effective Date**: TBD (after 2-week validation period)

## Migration Summary

The Cost Center Dashboard functionality has been migrated to the `code_puppy-HTT-INFRA` repository with significant improvements:

### What Moved Where

| Component | Old Location | New Location |
|-----------|-------------|--------------|
| **Backend (Python)** | `src/*.ts` (TypeScript) | `cost_center/collectors/*.py` |
| **Dashboard Frontend** | `docs/` | `cost_center/dashboard/` |
| **Configuration** | `config/tenants.json` | `cost_center/config/tenants.json` |
| **Internal Documentation** | `docs-internal/` | `docs/cost-center/` |
| **CI/CD Workflows** | `.github/workflows/multi-tenant-audit.yml` | `.github/workflows/cost-center-audit.yml` |
| **Scripts** | `scripts/*.sh` | `cost_center/scripts/*.py` |

### Key Improvements

✅ **Complete Python Rewrite**: Modern Azure Python SDK with async/await  
✅ **Better Engineering**: CI/CD, security scanning, devcontainer, comprehensive tests  
✅ **Single Repository**: Consolidated with code_puppy infrastructure tools  
✅ **OIDC Authentication**: No long-lived secrets in GitHub Actions  
✅ **Type Safety**: Pydantic models throughout  
✅ **Enhanced Testing**: pytest with coverage reporting  

## For Users

### Dashboard Access

The dashboard URL remains **unchanged**:
- Production: https://nice-meadow-0532b3e0f.5.azurestaticapps.net
- Data updates: Daily at 10:00 UTC (same as before)
- Features: All existing functionality preserved

### For Developers

#### New Repository Setup

```bash
# Clone new repository
gh repo clone HTT-BRANDS/code_puppy-HTT-INFRA
cd code_puppy-HTT-INFRA

# Install dependencies
pip install uv
uv sync

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run data collection
uv run python -m cost_center.collectors.main
```

#### Documentation

- **README**: [docs/cost-center/README.md](https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA/blob/main/docs/cost-center/README.md)
- **Architecture**: [docs/cost-center/architecture/](https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA/tree/main/docs/cost-center/architecture)
- **Runbooks**: [docs/cost-center/runbooks/](https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA/tree/main/docs/cost-center/runbooks)

## Archive Timeline

1. **Now - Jan 11**: Migration in progress, both repos active
2. **Jan 12 - Jan 25**: Parallel operation, monitoring new repo
3. **Jan 26**: Archive this repository (read-only)
4. **Feb 1**: Final notice emails to all stakeholders

## What Happens to This Repository

After archiving:
- ✅ Repository becomes read-only
- ✅ All code and history preserved
- ✅ Issues closed with redirect notices
- ✅ README updated with prominent redirect banner
- ❌ GitHub Actions workflows disabled
- ❌ No new commits accepted

## Azure Resources

### Unchanged
- Storage Account: `httcostcenter` (same)
- Container: `cost-reports` (same)
- Static Web App: `htt-cost-dashboard` (same)
- Resource Group: `rg-cost-center` (same)

### Updated
- App Registration federated credentials: Now trust `code_puppy-HTT-INFRA` repo
- GitHub Actions: Now run from new repository

## Breaking Changes

### None for Dashboard Users
- Dashboard URL unchanged
- Data format unchanged
- Update schedule unchanged

### For Developers
- ❌ TypeScript backend no longer maintained
- ❌ Old npm scripts won't work
- ✅ Python backend with same functionality
- ✅ Better testing and type safety

## Migration Checklist

Before archiving, verify:

- [ ] New repo workflows running successfully for 2 weeks
- [ ] All tenants collecting data correctly
- [ ] Dashboard displaying current data
- [ ] Zero critical issues
- [ ] All team members notified
- [ ] Documentation updated
- [ ] External links redirected
- [ ] GitHub repo settings configured (archived, read-only)

## Support

For questions or issues:
1. **New repository issues**: [code_puppy-HTT-INFRA/issues](https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA/issues)
2. **Migration questions**: Contact @tygranlund
3. **Dashboard issues**: Check [troubleshooting guide](https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA/blob/main/docs/cost-center/README.md#troubleshooting)

## Historical Reference

This repository will remain available (read-only) for:
- Reviewing commit history
- Accessing old documentation
- Comparing implementations
- Auditing historical data collection

## Acknowledgments

Thank you to all contributors who built the original Cost Center Dashboard. Your work continues in the new repository with enhanced capabilities and better maintainability.

---

**Last Updated**: January 5, 2026  
**Archived**: TBD  
**New Home**: https://github.com/HTT-BRANDS/code_puppy-HTT-INFRA
