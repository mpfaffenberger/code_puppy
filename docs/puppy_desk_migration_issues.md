# Puppy Desk Migration - Active Issue List

## Open / Tracked

1. **Model switch failure**  
   `Failed to switch to model gpt-5.5: CodePuppyAgent object has no attribute set_session_model`  
   - Status: **Fixed in commit `772e52ed`**

2. **Post-CWD-change chat failure**  
   `Agent run failed (no result returned)` after `set_working_directory`  
   - Root cause: raw dict injection into agent message history
   - Status: **Fix committed in `5c205a85`**

3. **Config schema endpoint crash**  
   `ImportError: cannot import name 'CONFIG_SCHEMA' from code_puppy.config` on `/config/schema`  
   - Status: **Fix committed in `5c205a85`**

## Residual Migration Gaps

- `code_puppy/api/` and related ws/runtime files are still largely untracked in this branch and need staged migration/normalization.
- Additional end-to-end GUI validation is pending after full API migration commit set.
