# GUI-Cub System Prompt - Duplication Analysis & Recommendations

**Date:** 2025-01-15  
**Status:** Analysis Complete  
**Priority:** Medium - Prompt optimization for clarity and token efficiency  

---

## Executive Summary

Analyzed the GUI-Cub system prompt (~7500 tokens) for duplications, redundancies, and organizational issues. Found several areas for improvement:

- **Major duplications:** 5 instances
- **Minor redundancies:** 8 instances  
- **Organizational improvements:** 3 recommendations
- **Estimated savings:** 800-1200 tokens (10-15% reduction)

---

## Major Duplications Found

### 1. ✅ FIXED: Critical Rules Section (DUPLICATE REMOVED)

**Status:** Already fixed - duplicate section removed

**Original Issue:**
- Line 612: Detailed bullet-point version
- Line 787: Numbered summary version (removed)

**Resolution:** Kept detailed version, removed duplicate

---

### 2. 🔴 Tool Priority Hierarchy (3 LOCATIONS)

**Duplication:** The tool tier priority is explained in 3 different places:

**Location 1 - Core Philosophy (Line ~208):**
```
**Tool Priority:** Keyboard shortcuts → Accessibility API → OCR → VQA (last resort)
```

**Location 2 - Tool Strategy Section (Lines ~545-600):**
```
**Tier 1 - Keyboard (PREFERRED)**
- Most reliable method for automation
- Try keyboard shortcuts, Tab navigation, arrow keys, and hotkeys FIRST
...

**Tier 2 - Accessibility API**
...

**Tier 3 - OCR with Smart Offset**
...

**Tier 4 - VQA Two-Stage (Last Resort)**
...
```

**Location 3 - Critical Rules (Line ~615):**
```
- ALWAYS try keyboard shortcuts FIRST before exploring element tree or clicking
```

**Recommendation:**
- **KEEP:** Detailed "Tool Strategy - Priority Order" section (most comprehensive)
- **CONDENSE:** Core Philosophy to just say "See Tool Strategy section for priority hierarchy"
- **KEEP:** Critical Rules reminder (short, actionable)

**Estimated Savings:** 50-100 tokens

---

### 3. 🔴 Window Focusing Requirement (3 LOCATIONS)

**Duplication:** Window focusing is mentioned in multiple places:

**Location 1 - Tool Strategy / Tier 3 (Line ~570):**
```
- MUST call `desktop_focus_window()` first
```

**Location 2 - Critical Rules (Line ~612):**
```
🚨 **ALWAYS focus the target window FIRST** - Call `desktop_focus_window(app_name)` or 
`ui_focus_window(title)` BEFORE any interaction
  - Before screenshots (captures wrong window otherwise)
  - Before mouse clicks (clicks wrong application otherwise)
  - Before keyboard input (types in wrong application otherwise)
  - Before OCR operations (analyzes wrong content otherwise)
```

**Location 3 - Standard Workflow Step 3 (Line ~631):**
```
3. **🚨 CRITICAL: Focus the target window FIRST** - ALWAYS call `desktop_focus_window(app_name)` 
   or `ui_focus_window(title)` BEFORE any interaction
   - **Why:** Screenshots, mouse clicks, and keyboard input go to the wrong application
   - **When:** Before EVERY screenshot, click, keyboard action, or OCR operation
   - **Example:** `desktop_focus_window("Calculator")` then `screenshot()`
```

**Recommendation:**
- **KEEP:** Critical Rules version (comprehensive with examples)
- **KEEP:** Standard Workflow step 3 (reinforces in workflow context)
- **REMOVE:** Tier 3 mention (redundant, already covered in Critical Rules)

**Estimated Savings:** 20-30 tokens

---

### 4. 🔴 Terminal/Shell Security Warning (3 LOCATIONS)

**Duplication:** Terminal security warning appears 3 times:

**Location 1 - Tier 3 OCR (Lines ~572-575):**
```
- ⛔ **NEVER on terminals/shells** (Terminal.app, iTerm, cmd.exe, PowerShell, zsh, bash)
- ⛔ **NEVER on code editors with terminals** (VS Code integrated terminal, etc.)
- Reason: Terminals contain sensitive information (API keys, passwords, tokens, secrets)
```

**Location 2 - Tier 4 VQA (Line ~583):**
```
- ⛔ **NEVER on terminals/shells** - Same security restrictions as OCR
```

**Location 3 - Critical Rules (Lines ~620-623):**
```
- ⛔ **NEVER use OCR or VQA on terminals/shells** (Terminal, iTerm, cmd.exe, PowerShell, 
  VS Code terminal, etc.)
  - Terminals contain sensitive data: API keys, passwords, tokens, secrets, environment variables
  - Taking screenshots or analyzing terminal content is a SECURITY VIOLATION
  - Use keyboard shortcuts or accessibility API only for terminal interaction
```

**Recommendation:**
- **KEEP:** Critical Rules version (most comprehensive, includes reasoning and alternatives)
- **CONDENSE:** Tier 3/4 to: "⛔ **NEVER on terminals/shells** (see Critical Rules)"
- This maintains the warning visibility while reducing repetition

**Estimated Savings:** 80-120 tokens

---

### 5. 🟡 Workflow Checking Reminder (2 LOCATIONS)

**Duplication:** Reminder to check existing workflows:

**Location 1 - Workflow Management Header (Line ~235):**
```
**ALWAYS check existing workflows before starting new automations!**
```

**Location 2 - Standard Workflow Step 1 (Line ~628):**
```
1. **Check for existing workflows** - `gui_cub_list_workflows()` BEFORE starting
```

**Recommendation:**
- **KEEP BOTH:** First is a general reminder, second is actionable workflow step
- **ACCEPTABLE DUPLICATION:** Different contexts, both useful

**No action needed**

---

## Minor Redundancies

### 6. 🟡 Fuzzy Matching Examples

**Issue:** Fuzzy matching explanation appears twice:

**Location 1 - Tier 2 (Line ~552):**
```
Fuzzy matching: "Submit Button" matches "submit", "SUBMIT", "Submit btn"
```

**Location 2 - Workflow YAML example (Line ~268):**
```
fuzzy: true
```

**Recommendation:**
- **KEEP BOTH:** One explains concept, one shows usage
- **ACCEPTABLE:** Different audiences (learners vs. implementers)

**No action needed**

---

### 7. 🟡 Common Patterns Examples Missing Window Focus

**Issue:** Common Patterns section (Lines ~680-750) has examples that were updated to include window focusing, but some are inconsistent:

**Missing focus in:**
- "Form filling" example (Line ~684) - MISSING `desktop_focus_window("Settings")`
- "Element tree exploration" (Line ~692) - MISSING `desktop_focus_window("MyApp")`
- "Tier fallback pattern" (Line ~699) - MISSING `desktop_focus_window("MyApp")`

**Recommendation:**
- **UPDATE:** Add `desktop_focus_window()` to ALL code examples for consistency
- **WHY:** Reinforces the critical requirement through repetition

**Action needed:** Add window focusing to all code examples

---

### 8. 🟡 VQA Two-Stage Mentioned Multiple Times

**Locations:**
- Tier 4 section (detailed explanation)
- Critical Rules ("NEVER use old single-stage VQA")
- Common Patterns (smart click example)

**Recommendation:**
- **KEEP ALL:** Different contexts, each serves a purpose
- **ACCEPTABLE DUPLICATION:** Emphasizes deprecation of old method

**No action needed**

---

## Organizational Improvements

### 9. 📋 Section Ordering Could Be Improved

**Current Order:**
1. Core Philosophy
2. Operating Modes
3. Workflow Management (very long ~400 lines)
4. Knowledge Base & Session Management
5. Tool Strategy - Priority Order
6. Critical Rules
7. Standard Workflow
8. Platform Support
9. Common Patterns
10. Screenshot Strategy
11. Communication Strategy

**Recommended Order:**
1. Core Philosophy (brief)
2. **Critical Rules** (move up - most important!)
3. **Standard Workflow** (move up - high-level process)
4. Tool Strategy - Priority Order
5. Operating Modes
6. Workflow Management
7. Platform Support
8. Common Patterns
9. Screenshot Strategy
10. Communication Strategy
11. Knowledge Base & Session Management

**Rationale:**
- Critical Rules should be near the top (most important)
- Standard Workflow gives high-level overview before details
- Tool Strategy explains the "how" before diving into specifics

---

### 10. 📋 Workflow Management Section Too Long

**Issue:** Workflow Management section is ~400 lines (over 50% of prompt)

**Contains:**
- YAML format examples
- Supported actions list
- Manual steps
- Markdown format
- Workflow chaining
- Parameterized workflows (very detailed)
- Sub-agent invocation
- Parameter types
- Conditional execution
- Output collection
- Backward compatibility

**Recommendation:**
- **CONDENSE:** Parameterized Workflows section (currently ~150 lines)
- **APPROACH:** Move detailed parameter docs to separate reference
- **KEEP:** Basic workflow format, supported actions, manual_step
- **LINK:** "See WORKFLOW_PARAMETERS.md for detailed parameter documentation"

**Estimated Savings:** 200-300 tokens

---

### 11. 📋 Create Quick Reference Summary

**Recommendation:** Add a "Quick Reference" section at the top:

```markdown
## Quick Reference - Most Important Rules

🚨 **#1: ALWAYS focus window first** - `desktop_focus_window(app)` before ANY action
⌨️ **#2: Keyboard shortcuts FIRST** - Try hotkeys before clicking
🔍 **#3: Explore before clicking** - `ui_list_elements()` before `ui_click_element()`
⛔ **#4: NEVER OCR/VQA terminals** - Security violation (contains secrets)
✅ **#5: Verify actions** - Screenshot or OCR to confirm success
📝 **#6: Check workflows first** - `gui_cub_list_workflows()` before building new

**Tool Priority:** Keyboard → Accessibility → OCR → VQA
**Workflow:** Focus window → Try keyboard → Explore tree → Click → Verify
```

**Benefit:** Immediate actionable guidance for common scenarios

---

## Summary of Recommendations

### High Priority (Do First)

1. ✅ **DONE:** Remove duplicate Critical Rules section
2. 🔴 **TODO:** Condense terminal security warnings (save ~100 tokens)
3. 🔴 **TODO:** Add window focusing to all code examples (consistency)
4. 🔴 **TODO:** Reorder sections (Critical Rules → Standard Workflow → Tool Strategy)

### Medium Priority (Nice to Have)

5. 🟡 **TODO:** Condense Tool Priority mentions in Core Philosophy
6. 🟡 **TODO:** Condense Parameterized Workflows section (save ~250 tokens)
7. 🟡 **TODO:** Add Quick Reference summary at top

### Low Priority (Optional)

8. 🟢 **OPTIONAL:** Create separate WORKFLOW_PARAMETERS.md reference doc
9. 🟢 **OPTIONAL:** Create COMMON_PATTERNS.md cheat sheet

---

## Estimated Impact

**Token Reduction:**
- Terminal warnings consolidation: ~100 tokens
- Parameterized workflows condensing: ~250 tokens
- Tool priority consolidation: ~50 tokens
- **Total savings:** ~400 tokens (5% reduction)

**Clarity Improvement:**
- Better section ordering (Critical Rules near top)
- Consistent code examples (all include window focusing)
- Quick Reference for common scenarios

**Maintainability:**
- Less duplication = easier to update
- Clear single source of truth for each concept
- Reference docs for detailed information

---

## Implementation Plan

### Phase 1: Critical Fixes (30 minutes)
1. ✅ Remove duplicate Critical Rules (DONE)
2. Consolidate terminal security warnings
3. Add window focusing to all code examples
4. Reorder sections for better flow

### Phase 2: Optimizations (1 hour)
1. Condense Parameterized Workflows section
2. Add Quick Reference summary
3. Consolidate Tool Priority mentions

### Phase 3: Reference Docs (2 hours - optional)
1. Create WORKFLOW_PARAMETERS.md
2. Create COMMON_PATTERNS.md
3. Update prompt to reference external docs

---

## Specific Edits Needed

### Edit 1: Consolidate Terminal Security Warnings

**In Tier 3 OCR section, replace:**
```
- ⛔ **NEVER on terminals/shells** (Terminal.app, iTerm, cmd.exe, PowerShell, zsh, bash)
- ⛔ **NEVER on code editors with terminals** (VS Code integrated terminal, etc.)
- Reason: Terminals contain sensitive information (API keys, passwords, tokens, secrets)
```

**With:**
```
- ⛔ **NEVER on terminals/shells** (see Critical Rules for security requirements)
```

**In Tier 4 VQA section, replace:**
```
- ⛔ **NEVER on terminals/shells** - Same security restrictions as OCR
```

**With:**
```
- ⛔ **NEVER on terminals/shells** (see Critical Rules)
```

**Keep full explanation only in Critical Rules section.**

---

### Edit 2: Add Window Focusing to Code Examples

**Form filling example:**
```python
# 🚨 CRITICAL: Focus window FIRST
desktop_focus_window("Settings")
desktop_keyboard_press("tab")  # Navigate to first field
desktop_keyboard_type("John Doe")
```

**Element tree exploration:**
```python
# 🚨 CRITICAL: Focus window FIRST
desktop_focus_window("MyApp")
elements = ui_list_elements()  # Explore BEFORE clicking
ui_click_element(title="Submit", fuzzy=True)
```

**Tier fallback pattern:**
```python
# 🚨 CRITICAL: Focus window FIRST
desktop_focus_window("MyApp")

# Try keyboard first
desktop_keyboard_hotkey("cmd", "s")
desktop_sleep(0.3)
```

---

### Edit 3: Section Reordering

**Move these sections up (after Core Philosophy):**
1. Critical Rules (currently line ~612)
2. Standard Workflow (currently line ~628)
3. Tool Strategy - Priority Order (currently line ~545)

**New order:**
```
## Core Philosophy
## Critical Rules  ← MOVED UP
## Standard Workflow  ← MOVED UP
## Tool Strategy - Priority Order  ← MOVED UP
## Operating Modes
## Workflow Management
## Platform Support
## Common Patterns
## Screenshot Strategy
## Communication Strategy
## Knowledge Base & Session Management
```

---

### Edit 4: Condense Parameterized Workflows

**Replace the 150-line detailed parameter documentation with:**

```markdown
## Parameterized Workflows 🎯

**Workflows accept typed parameters and return structured outputs!**

This enables parent agents to orchestrate GUI-Cub workflows with dynamic inputs.

**Quick Example:**
```yaml
parameters:
  - name: patient_id
    type: string
    required: true
  - name: timeout
    type: number
    default: 5

outputs:
  - name: patient_name
  - name: screenshot

steps:
  - action: type
    text: "${patient_id}"  # Use ${} or {{}} for substitution
  
  - action: extract_text
    region: {x: 100, y: 200, width: 300, height: 50}
    output_variable: "patient_name"
```

**Parameter Types:** string, number, boolean, array, object  
**Special Flags:** required, default, sensitive  
**Conditional Execution:** `condition: "${var} == value"`  
**Output Collection:** `output_variable: "name"`  

For detailed parameter documentation, see workflow examples in `~/.code_puppy/agents/gui-cub/workflows/`
```

**Estimated savings:** ~200 tokens

---

## Notes

**Acceptable Duplications:**
- Workflow checking reminder (different contexts)
- Fuzzy matching examples (concept vs. usage)
- VQA two-stage mentions (emphasizes deprecation)

**Philosophy on Duplication:**
- ✅ **Keep:** When different contexts or audiences
- ✅ **Keep:** Critical safety warnings (terminals)
- ✅ **Keep:** Key concepts that need reinforcement
- ❌ **Remove:** Exact same information in same section
- ❌ **Remove:** Verbose examples that could be condensed

**Token Budget:**
- Current: ~7500 tokens
- Target after optimization: ~6800-7000 tokens
- Reduction: ~500-700 tokens (7-10%)

---

**Last Updated:** 2025-01-15  
**Status:** Analysis complete, recommendations ready for implementation  
**Next Step:** Implement Phase 1 edits  
