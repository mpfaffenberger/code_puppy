# BigQuery SQL Query Safety Fix

## 🐛 Problem Statement

After authentication with `/bigquery_auth`, even simple SELECT queries were being blocked with the error:

```
Only read-only SELECT queries are allowed.
Dangerous operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, etc.) are blocked.
```

## 🔍 Root Cause Analysis

**The Issue:**
- `sqlparse` is an **optional dependency** in `pyproject.toml` (under `[project.optional-dependencies]`)
- `/bigquery_auth` only installs `google-cloud-bigquery` but NOT `sqlparse`
- When `_is_safe_query()` runs, it checks if `sqlparse is None`
- If `sqlparse` is not installed, it returns `False` and **rejects ALL queries** (even safe SELECT statements)

**Code Flow:**
```python
# bigquery_client.py line 315-319 (before fix)
if sqlparse is None:
    emit_warning(
        "sqlparse not installed. Install with: uv pip install .[bigquery]"
    )
    return False  # ❌ Rejects ALL queries!
```

**Why it happened:**
```python
# bigquery_auth.py line 259-261 (before fix)
packages = [
    "google-cloud-bigquery>=3.0.0",
    # sqlparse is MISSING!
]
```

## ✅ Solution

### **Fix 1: Add sqlparse to installation**

**File:** `code_puppy/plugins/walmart_specific/bigquery_auth.py`

**Change:** Add `sqlparse` to the packages list in `_install_python_dependencies()`

```python
# Line 259-262 (after fix)
packages = [
    "google-cloud-bigquery>=3.0.0",
    "sqlparse>=0.4.0",  # ✅ Now included!
]
```

### **Fix 2: Improve error message**

**File:** `code_puppy/plugins/walmart_specific/bigquery_client.py`

**Change:** Make the error message more actionable

```python
# Line 315-321 (after fix)
if sqlparse is None:
    emit_warning(
        "⚠️  sqlparse not installed - cannot validate query safety.\n"
        "Please run '/bigquery_auth' again to install all dependencies.\n"
        "Or manually install: uv pip install sqlparse>=0.4.0"
    )
    return False
```

## 📊 Impact

| Aspect | Before | After |
|--------|--------|-------|
| **sqlparse installed?** | ❌ No (missing from install) | ✅ Yes (auto-installed) |
| **SELECT queries work?** | ❌ No (blocked by safety check) | ✅ Yes (validated properly) |
| **Error message clarity** | ⚠️ Vague | ✅ Actionable |

## 🧪 Testing

### Test Case 1: Fresh Installation
```bash
1. Run: /bigquery_auth
   Expected: Installs both google-cloud-bigquery AND sqlparse
   
2. Switch to agent: /agent bigquery-explorer

3. Run query: "SELECT * FROM project.dataset.table LIMIT 10"
   Expected: ✅ Query executes successfully
```

### Test Case 2: Safety Validation
```bash
Safe queries (should PASS):
- SELECT * FROM table
- SELECT COUNT(*) FROM table WHERE condition
- WITH cte AS (SELECT ...) SELECT * FROM cte

Dangerous queries (should FAIL):
- INSERT INTO table VALUES (...)
- DELETE FROM table WHERE ...
- DROP TABLE table
- UPDATE table SET ...
```

### Test Case 3: Manual Verification
```python
import sqlparse

query = "SELECT * FROM dataset.table LIMIT 10"
parsed = sqlparse.parse(query)
print(parsed[0].get_type())  # Should print: SELECT
```

## 📝 Files Changed

1. **`bigquery_auth.py`**
   - Line 261: Added `"sqlparse>=0.4.0"` to packages list
   - Impact: Now installs sqlparse during `/bigquery_auth`

2. **`bigquery_client.py`**
   - Lines 315-321: Improved error message
   - Impact: Better user feedback if sqlparse is somehow still missing

## 🚀 User Action Required

For users who already ran `/bigquery_auth` and are experiencing this issue:

**Option 1: Re-run authentication (RECOMMENDED)**
```bash
/bigquery_auth
```
This will install sqlparse automatically.

**Option 2: Manual install**
```bash
uv pip install sqlparse>=0.4.0
```

## 🔒 Security Note

The safety validation logic using `sqlparse` is **critical for security**:
- Blocks destructive operations: INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, REPLACE, MERGE
- Only allows read-only SELECT queries and CTEs (WITH)
- Protects against accidental data modification or deletion
- Provides SQL injection protection through statement type validation

**The fix ensures this security layer works properly!**

## 📊 Summary

**Problem:** SELECT queries blocked because `sqlparse` wasn't installed  
**Root Cause:** `sqlparse` missing from `/bigquery_auth` installation  
**Solution:** Add `sqlparse>=0.4.0` to packages list  
**Impact:** 2 files, 2 lines changed  
**Risk:** Very Low (adding missing dependency)  
**Result:** ✅ SELECT queries now work as expected!  

---

**Status: FIXED** 🎉
