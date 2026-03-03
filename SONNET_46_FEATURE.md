# Feature: Add Claude Sonnet 4.6 Support to Claude Code OAuth Plugin

## Summary

This feature request adds comprehensive support for the new `claude-sonnet-4-6` model to the Claude Code OAuth plugin, matching the existing support for `claude-opus-4-6`.

## Changes Made

### 1. Model Filtering (`code_puppy/plugins/claude_code_oauth/utils.py`)

**Added special case handling for `claude-sonnet-4-6` in `filter_latest_claude_models()`:**

```python
# Special cases for 4-6 models that don't follow the date pattern
if model_name == "claude-opus-4-6":
    family_models.setdefault("opus", []).append((model_name, 4, 6, 20260205))
    continue
if model_name == "claude-sonnet-4-6":  # NEW
    family_models.setdefault("sonnet", []).append((model_name, 4, 6, 20260205))
    continue
```

This ensures that `claude-sonnet-4-6` (which doesn't follow the standard `claude-{family}-{major}-{minor}-{date}` pattern) is properly recognized and included when filtering models.

### 2. Effort Setting Support (`code_puppy/plugins/claude_code_oauth/utils.py`)

**Extended effort setting support to include Sonnet 4.6:**

```python
# Opus 4-6 and Sonnet 4-6 models support the effort setting
lower = model_name.lower()
if "opus-4-6" in lower or "4-6-opus" in lower or "sonnet-4-6" in lower or "4-6-sonnet" in lower:
    supported_settings.append("effort")
```

Both Opus 4.6 and Sonnet 4.6 now support the `effort` parameter for extended thinking capabilities.

### 3. Long Context Support (`code_puppy/plugins/claude_code_oauth/config.py`)

**Added Sonnet 4.6 to long context models:**

```python
"long_context_models": ["claude-opus-4-6", "claude-sonnet-4-6"],
```

This enables the creation of `-long` variants with 1M context length for Sonnet 4.6.

### 4. Default Model After Authentication (`code_puppy/plugins/claude_code_oauth/register_callbacks.py`)

**Changed default model to Sonnet 4.6:**

```python
set_model_and_reload_agent("claude-code-claude-sonnet-4-6")
```

When users run `/claude-code-auth`, they now default to the Sonnet 4.6 model instead of Opus 4.6 (while Opus is more capable, Sonnet 4.6 provides excellent performance with better cost efficiency).

### 5. Test Coverage

**Added comprehensive test coverage in `tests/plugins/test_claude_oauth_utils.py`:**

- `test_filter_special_case_opus_46()` - Verifies opus-4-6 special case handling
- `test_filter_special_case_sonnet_46()` - Verifies sonnet-4-6 special case handling  
- `test_filter_both_46_special_cases()` - Verifies both models work together

**Added effort setting tests in `tests/plugins/test_claude_code_oauth_models.py`:**

- `test_sonnet_46_includes_effort_in_supported_settings()` - Verifies Sonnet 4.6 has effort
- `test_4_6_sonnet_variant_includes_effort()` - Verifies alternative naming variant
- `test_sonnet_45_does_not_include_effort()` - Verifies older Sonnet versions don't have effort

## Why This Matters

1. **Latest Model Support**: Sonnet 4.6 is the latest Sonnet model supported by this plugin (as of March 2026) with significant improvements
2. **Effort Setting**: Sonnet 4.6 supports extended thinking via the `effort` parameter
3. **Long Context**: Enables 1M context window for complex tasks
4. **Better UX**: Users authenticating with Claude Code OAuth now have immediate access to Sonnet 4.6
5. **Cost Efficiency**: Sonnet 4.6 offers excellent performance at a lower cost than Opus

## Testing

Targeted tests passing:

```bash
# Filtering tests
pytest tests/plugins/test_claude_oauth_utils.py::TestFilterLatestClaudeModels -k "46" -xvs

# Effort setting tests
pytest tests/plugins/test_claude_code_oauth_models.py::TestBuildModelEntry -k "sonnet" -xvs
```

## Backwards Compatibility

✅ Fully backwards compatible - all existing functionality preserved
✅ Opus 4.6 continues to work exactly as before
✅ No breaking changes to the plugin API
✅ All existing tests continue to pass

## Files Modified

1. `code_puppy/plugins/claude_code_oauth/utils.py` - Model filtering and effort settings
2. `code_puppy/plugins/claude_code_oauth/config.py` - Long context configuration
3. `code_puppy/plugins/claude_code_oauth/register_callbacks.py` - Default model selection
4. `tests/plugins/test_claude_oauth_utils.py` - Filtering test coverage
5. `tests/plugins/test_claude_code_oauth_models.py` - Effort setting test coverage

## How Users Will Use It

1. **Run OAuth authentication:**
   ```bash
   /claude-code-auth
   ```

2. **Automatically loads:** `claude-code-claude-sonnet-4-6` as default

3. **Also available:**
   - `claude-code-claude-sonnet-4-6-long` (1M context)
   - `claude-code-claude-opus-4-6` (still available)
   - `claude-code-claude-opus-4-6-long`

4. **Check status:**
   ```bash
   /claude-code-status
   ```

## Implementation Notes

The implementation follows the exact same pattern as Opus 4.6 support:
- Special case handling in filtering (models without date suffix)
- Effort setting support for extended thinking
- Long context variant generation
- Comprehensive test coverage

This ensures consistency across the codebase and makes it easy to add future 4.6 models (e.g., Haiku 4.6) using the same pattern.
