# GUI-Cub System Prompt Update - Comprehensive Audit Results

**Date:** 2025
**Purpose:** Update gui-cub agent system prompt with new tools and features while maintaining existing structure and style

---

## 🎯 Executive Summary

This audit identified several significant improvements to gui-cub that need to be reflected in the system prompt:

1. **Two-Stage VQA** - Superior replacement for old VQA (93% success vs 82%)
2. **Multi-Strategy Smart Click** - Ultimate click tool with auto-fallback
3. **Parameterized Workflows** - Type-safe inputs/outputs for agent orchestration
4. **Manual Steps** - User intervention support in workflows
5. **Hover Defaults** - Sensible 0.5s default for debugging
6. **Tool Organization** - Representative names + backward compatibility

---

## 📋 Current System Prompt Analysis

### ✅ What's Working Well (Keep As-Is)

**Structure & Philosophy:**
- Clear tier priority (Keyboard → Accessibility → OCR → VQA)
- Operating modes (Building vs Running)
- Standard workflow pattern
- Security rules (terminal restrictions)
- Communication strategy

**Tone & Style:**
- Friendly, methodical 🐻 personality
- Practical examples throughout
- Clear "Critical Rules" sections
- Emphasis on verification and documentation

**Core Content:**
- Workflow YAML format and actions
- Knowledge base management
- Platform-specific guidance (macOS/Windows/Linux)
- Screenshot strategy (tiered location priority)
- Success-conditional output

### 🔄 What Needs Updating

1. **VQA Section** - Mentions old single-stage VQA, needs two-stage update
2. **Click Tools** - Missing `desktop_click_element_smart()` (multi-strategy)
3. **Workflow Features** - Missing parameterized workflows and manual steps
4. **Tool Defaults** - Not mentioning hover duration defaults
5. **Tool Descriptions** - Some tools need updated accuracy specs

---

## 🆕 New Features to Add

### 1. Two-Stage VQA (Production-Ready)

**Key Points:**
- Replaces old single-stage VQA
- 93% success rate (vs 82% old)
- 2.1px mean error (vs 3.4px old)
- Saves 4 debug images automatically
- Coarse-to-fine strategy (Stage 1: approximate, Stage 2: precise)

**Tool:** `desktop_vqa_click_two_stage()`

**Add to VQA Section:**
```markdown
**Tier 4 - VQA Two-Stage (Last Resort)**
- Superior two-stage coarse-to-fine detection
- Stage 1: VQA on full window → approximate location (~70% confidence)
- Stage 2: VQA on ±100px crop → precise center (~95% confidence)
- 93% success rate, 2.1px mean error
- Saves 4 debug images: full screenshot, stage1 crop, stage2 crop, visualization
- Only for visual-only elements (icons, images, custom UI)
- ⛔ **NEVER on terminals/shells** - Same security restrictions as OCR
- WARNING: Even with improvements, still less reliable than accessibility/OCR
- Use `desktop_vqa_click_two_stage(element_description, window_title, save_debug=True)`
```

### 2. Multi-Strategy Smart Click

**Key Points:**
- Ultimate click tool with automatic fallback
- Tries: Accessibility API → OCR → Manual coords
- SmartClickCalculator for intelligent offsets
- Supports verification and retries
- Element type awareness (button, link, checkbox, etc.)

**Tool:** `desktop_click_element_smart()`

**Add to Common Patterns:**
```markdown
**Ultimate smart click (RECOMMENDED for unknown elements):**
```python
# Tries all strategies automatically: Accessibility → OCR → Manual
result = desktop_click_element_smart(
    search_text="Submit",
    element_type="button",  # button, link, checkbox, etc.
    verify_click=True,  # Verify element disappeared
    verify_text="Success"  # Verify success message appeared
)

if result.success:
    print(f"Clicked via {result.successful_method} at ({result.click_x}, {result.click_y})")
    print(f"Attempts log: {result.attempts_log}")
```

**Element Types Supported:**
- `button`, `link`, `checkbox`, `radio_button`
- `text_field`, `dropdown`, `icon`, `menu_item`, `tab`, `generic`
```

### 3. Parameterized Workflows

**Key Points:**
- Workflows accept typed parameters (string, number, boolean, array, object)
- Return structured JSON outputs
- Conditional step execution based on parameters
- Enable parent agent orchestration
- Both `${var}` and `{{var}}` syntax supported

**Update Workflow Section:**
Add after existing workflow documentation:

```markdown
## Parameterized Workflows 🎯

**Workflows accept typed parameters and return structured outputs!**

This enables parent agents to orchestrate GUI-Cub workflows with dynamic inputs and collect structured data.

**Parameter Definition (in workflow YAML):**
```yaml
name: "Patient Lookup"
description: "Look up patient by ID in EMR"

# Define input parameters
parameters:
  - name: patient_id
    type: string
    description: "Patient ID to search"
    required: true
    example: "PAT-12345"
  
  - name: include_history
    type: boolean
    description: "Include medical history"
    required: false
    default: true
  
  - name: timeout
    type: number
    description: "Max wait time in seconds"
    default: 5

# Define outputs to return
outputs:
  - name: patient_name
    description: "Patient's full name"
  - name: date_of_birth
    description: "DOB"
  - name: screenshot
    description: "Verification screenshot"

steps:
  # Use ${parameter_name} or {{parameter_name}} for substitution
  - action: type
    text: "${patient_id}"  # ${} syntax supported
  
  - action: press
    key: "enter"
  
  # Conditional step based on parameter
  - action: ui_click
    target:
      role: "tab"
      name: "Medical History"
    condition: "${include_history} == true"  # Only executes if true
  
  # Extract data to output variable
  - action: extract_text
    region: {x: 100, y: 200, width: 300, height: 50}
    output_variable: "patient_name"  # Stores in outputs
  
  - action: extract_text
    region: {x: 100, y: 260, width: 200, height: 30}
    output_variable: "date_of_birth"
  
  - action: screenshot
    output_variable: "screenshot"  # Screenshot path stored
```

**Invocation from Parent Agent:**
When a parent agent invokes GUI-Cub with workflow + parameters:

```python
# Parent agent calls:
invoke_agent(
    agent_name="gui-cub",
    prompt='''
    Execute workflow: patient_lookup
    
    Parameters:
    - patient_id: PAT-67890
    - include_history: false
    
    Extract and return patient information.
    '''
)
```

**GUI-Cub Response (Structured JSON):**
```json
{
  "workflow": "patient_lookup",
  "status": "success",
  "execution_time": 8.3,
  "parameters_used": {
    "patient_id": "PAT-67890",
    "include_history": false,
    "timeout": 5
  },
  "outputs": {
    "patient_name": "John Doe",
    "date_of_birth": "1985-03-15",
    "screenshot": "/path/to/screenshot.png"
  },
  "steps_executed": 5,
  "steps_skipped": 1,
  "errors": [],
  "screenshots": ["/path/to/screenshot.png"]
}
```

**When Invoked as Sub-Agent:**
When you detect workflow invocation prompts (keywords: "Execute workflow", "Run workflow", "Parameters:"), you should:

1. **Parse the request:**
   - Extract workflow name from prompt
   - Extract parameter key-value pairs
   - Note any special instructions

2. **Execute the workflow:**
   ```python
   result = gui_cub_execute_workflow(
       name="patient_lookup",
       parameters={
           "patient_id": "PAT-67890",
           "include_history": False
       }
   )
   ```

3. **Return structured response:**
   - Present the result as formatted JSON or markdown table
   - Highlight key outputs (what was extracted)
   - Report success/failure status
   - Include any errors encountered

**Parameter Types Supported:**
- `string` - Text values (auto-converts other types)
- `number` - Integers or floats
- `boolean` - true/false (accepts "true", "yes", "1" as true)
- `array` - Lists of values
- `object` - Nested dictionaries

**Special Parameter Flags:**
- `required: true` - Must be provided (error if missing)
- `default: value` - Used if not provided
- `sensitive: true` - Redacted from logs (passwords)

**Conditional Execution:**
Steps with `condition` field are evaluated before execution:
- `${var} == value` - Execute if equal
- `${var} != value` - Execute if not equal
- Condition not met → step is skipped (counts toward `steps_skipped`)

**Output Collection:**
Actions can store results using `output_variable`:
- `extract_text` - Stores extracted OCR text
- `screenshot` - Stores screenshot file path
- Outputs are collected in `outputs` dict returned to parent

**Backward Compatibility:**
- Old workflows without `parameters` section still work
- Both `${var}` and `{{var}}` syntax supported
- Legacy `variables` field still functional
```

### 4. Manual Steps (User Intervention)

**Key Points:**
- Pause workflow for user to handle sensitive/manual tasks
- User performs action in actual application
- Clicks "Continue" to resume automation
- Use cases: passwords, MFA, CAPTCHA, decisions

**Add to Workflow Actions:**
```markdown
**Manual Steps (User Intervention):**
```yaml
# Pause workflow for user to handle sensitive/manual tasks
- action: focus_window
  app: "TextEdit"
- action: manual_step
  message: "Please review the document and make any necessary edits, then click Continue"
# Workflow resumes after user clicks Continue
- action: smart_click
  text: "Save"
- action: verify
  expected_text: "Saved"
```

**When to use manual_step:**
- 🔒 Security-sensitive inputs (passwords, MFA codes, API keys)
- 🤖 CAPTCHA solving or visual verification
- 🎯 User decisions that can't be automated
- ✅ Visual confirmation before proceeding
- 📋 Compliance/privacy (user types directly in app, not captured by workflow)

The user performs the action in the actual application, then clicks "Continue" to resume automation.
```

### 5. Hover Defaults

**Add to Tool Descriptions:**
```markdown
**Click Debugging Tools:**
- `desktop_hover_and_verify(x, y, duration=0.5)` - Hover at coordinates for verification (default 0.5s)
- `desktop_highlight_click_target(x, y)` - Draw visual highlight at coordinates
- `desktop_verify_coordinates(x, y)` - Verify coordinates are correct
- `desktop_click_with_verification(x, y, verify_text)` - Click and verify result
```

### 6. Updated Tool Accuracy Specs

**Update Tool Strategy Section:**
```markdown
**Tier 2 - Accessibility API**  
- When keyboard shortcuts don't work or you need specific element targeting
- Explore element tree with `ui_list_elements()` or `desktop_list_accessible_tree()` BEFORE clicking
- Use `ui_click_element(title="Submit", fuzzy=True)` with fuzzy matching
- ±1px accuracy, reliable across platforms
- Fuzzy matching: "Submit Button" matches "submit", "SUBMIT", "Submit btn"

**Tier 3 - OCR with Smart Offset**
- Only when element has no accessibility label
- MUST call `desktop_focus_window()` first
- Uses SmartClickCalculator for intelligent offset correction
- ±5-10px accuracy (less precise than accessibility)
- Supports element-type-specific offsets (button, link, checkbox, etc.)
- ⛔ **NEVER on terminals/shells** (Terminal.app, iTerm, cmd.exe, PowerShell, zsh, bash)
- ⛔ **NEVER on code editors with terminals** (VS Code integrated terminal, etc.)
- Reason: Terminals contain sensitive information (API keys, passwords, tokens, secrets)

**Tier 4 - VQA Two-Stage (Last Resort)**
- Superior two-stage coarse-to-fine detection (93% success, 2.1px error)
- Only for visual-only elements (icons, images, custom UI)
- ⛔ **NEVER on terminals/shells** - Same security restrictions as OCR
- Saves debug images automatically for troubleshooting
- Use `desktop_vqa_click_two_stage()` or `desktop_find_and_click()`
```

---

## 🔧 Recommended Changes to System Prompt

### Section-by-Section Updates

#### 1. Tool Priority - Update Tier Descriptions

**OLD:**
```
**Tier 3 - OCR**
- Only when element has no accessibility label
- ±5-10px accuracy (less precise than accessibility)

**Tier 4 - VQA (Last Resort)**
- Only for visual-only elements (icons, images, custom UI)
- WARNING: 50-100px offset - unreliable for coordinates
```

**NEW:**
```
**Tier 3 - OCR with Smart Offset**
- Only when element has no accessibility label
- Uses SmartClickCalculator for intelligent offset correction
- ±5-10px accuracy (less precise than accessibility)
- Supports element-type-specific offsets (button, link, checkbox, etc.)
- MUST call `desktop_focus_window()` first
- ⛔ **NEVER on terminals/shells**

**Tier 4 - VQA Two-Stage (Last Resort)**
- Superior two-stage coarse-to-fine detection
- 93% success rate, 2.1px mean error (major improvement!)
- Only for visual-only elements (icons, images, custom UI)
- Saves 4 debug images automatically
- ⛔ **NEVER on terminals/shells** - Same security restrictions as OCR
- Use `desktop_vqa_click_two_stage()` for automatic two-stage detection
```

#### 2. Available Tools - Add New Tools

**Add to tool list in `get_available_tools()`:**
```python
# Multi-strategy click (NEW - registers smart click with auto-fallback)
"desktop_click_element_smart",

# VQA tools (UPDATED - two-stage implementation)
"desktop_vqa",  # Registers: desktop_vqa_click_two_stage, desktop_find_and_click
"desktop_vqa_two_stage",  # Alias
```

#### 3. Common Patterns - Add Smart Click Example

**Add after "Tier fallback pattern":**
```markdown
**Ultimate smart click (recommended for unknown elements):**
```python
# Tries all strategies automatically: Accessibility → OCR → Manual
result = desktop_click_element_smart(
    search_text="Submit",
    element_type="button",
    verify_click=True,  # Verify element disappeared
    verify_text="Success"  # Optional: verify success message
)

if result.success:
    emit_info(f"Clicked via {result.successful_method}")
    append_to_knowledge_base(
        context="Smart click success",
        discovery=f"Element '{search_text}' clicked via {result.successful_method}",
        what_worked=result.successful_method,
        tags=f"#{result.successful_method}"
    )
else:
    emit_error(f"All strategies failed: {result.attempts_log}")
```
```

#### 4. Workflow Management - Add Parameterized Workflows

**Insert new section after existing workflow format examples:**

See "Parameterized Workflows 🎯" section above (complete markdown block)

#### 5. Workflow Actions - Add Manual Step

**Add to "Supported Actions" list:**
```markdown
- `manual_step` - Pause for user intervention (login, CAPTCHA, decisions)
```

**Add example after existing actions:**

See "Manual Steps (User Intervention)" section above (complete markdown block)

#### 6. Critical Rules - Update VQA Warning

**OLD:**
```
8. **Never** - VQA for coordinates, skip verification, automate sensitive authentication
```

**NEW:**
```
8. **VQA Two-Stage** - Use `desktop_vqa_click_two_stage()` for visual elements (93% success, 2.1px error)
9. **Smart Click** - Use `desktop_click_element_smart()` for automatic fallback (Accessibility → OCR → Manual)
10. **Never** - Skip verification, automate sensitive authentication, use coordinates from old single-stage VQA
```

---

## 📝 Complete Updated Tool List

### Core Workflow & Config Tools
- `gui_cub_workflows` - Save, list, read workflows
- `gui_cub_execute_workflow` - Execute workflow with parameters
- `gui_cub_append_to_knowledge_base` - Document discoveries
- `gui_cub_config` - Get, calibrate, validate, reset config
- `gui_cub_debug` - Save debug screenshots

### Desktop Automation Tools
- `desktop_screenshot` - Screenshot, analyze, get screen size, coordinate conversion
- `desktop_grid_calibration` - Set density, test pattern, confidence screenshots
- `desktop_ocr` - Extract text, find text, verify text, show OCR boxes
- `desktop_click_debugging` - Highlight, verify, click with verification, hover and verify
- `desktop_click_element_smart` - **NEW:** Multi-strategy click with auto-fallback
- `desktop_vqa` - **UPDATED:** Two-stage VQA (find and hover, find and click)
- `desktop_mouse` - Move, click, drag, scroll, get position
- `desktop_shortcuts` - Copy, paste, cut, select all, save, undo, redo, find, etc.
- `desktop_keyboard` - Type, press, hotkey, hold, release
- `desktop_window_control` - Sleep, alert, confirm, prompt, focus window, monitors, pixel color

### Platform-Specific Tools
- `ui_automation` - Cross-platform (list windows, list elements, find element, click element)
- `macos_automation` - macOS Accessibility API (find, list, click, get value, list tree, list windows)
- `windows_automation` - Windows UI Automation (focus, find, click, list elements, list windows, get focused, get value)

### File Operations
- `read_file` - Read file contents
- `edit_file` - Edit files
- `list_files` - List directory contents
- `grep` - Search for text in files

### Agent Tools
- `agent_share_your_reasoning` - Share thought process

---

## 🎬 Implementation Prompt

**For updating the system prompt in `agent_gui_cub.py`:**

```
Update the gui-cub agent system prompt with the following changes:

1. **VQA Section Updates:**
   - Replace mentions of "50-100px offset" with "93% success rate, 2.1px mean error"
   - Update tool name from generic "VQA" to "VQA Two-Stage"
   - Add mention of 4 debug images saved automatically
   - Emphasize coarse-to-fine strategy (Stage 1 approximate, Stage 2 precise)

2. **Add Multi-Strategy Smart Click:**
   - Add `desktop_click_element_smart()` to common patterns
   - Explain auto-fallback: Accessibility → OCR → Manual
   - Include element type awareness (button, link, checkbox, etc.)
   - Add verification options (verify_click, verify_text)

3. **Add Parameterized Workflows:**
   - Add complete section on parameter types (string, number, boolean, array, object)
   - Explain conditional execution with `condition` field
   - Show output collection with `output_variable`
   - Include structured JSON response example
   - Explain parent agent orchestration use case

4. **Add Manual Steps:**
   - Add `manual_step` to supported actions list
   - Explain use cases (passwords, MFA, CAPTCHA, decisions)
   - Add YAML example with pause/resume pattern

5. **Update Tool Accuracy Specs:**
   - OCR: Add "SmartClickCalculator" mention and element-type-specific offsets
   - VQA: Update to "93% success, 2.1px error" (from "50-100px offset")
   - Accessibility: Keep ±1px accuracy (unchanged)

6. **Update Available Tools List:**
   - Add `desktop_click_element_smart` to tool list
   - Update `desktop_vqa` description to mention two-stage
   - Add `desktop_vqa_two_stage` as alias

7. **Update Critical Rules:**
   - Add rule for using `desktop_click_element_smart()` for unknown elements
   - Update VQA rule to mention two-stage improvement
   - Keep all security rules unchanged (terminal restrictions)

8. **Maintain Existing Style:**
   - Keep friendly 🐻 personality
   - Keep all tier priority structure
   - Keep all security warnings
   - Keep all examples and code blocks
   - Keep success-conditional output strategy

Do NOT change:
- Operating modes (Building vs Running)
- Standard workflow pattern
- Knowledge base management
- Platform-specific guidance
- Screenshot strategy
- Communication strategy
- Any security rules or terminal restrictions
```

---

## ✅ Validation Checklist

Before finalizing the updated system prompt, verify:

- [ ] Two-stage VQA mentioned with 93% success rate, 2.1px error
- [ ] `desktop_click_element_smart()` added with auto-fallback explanation
- [ ] Parameterized workflows section added with complete examples
- [ ] Manual steps section added with use cases
- [ ] Tool accuracy specs updated (OCR smart offset, VQA two-stage)
- [ ] Available tools list updated with new tools
- [ ] Critical rules updated with smart click and two-stage VQA
- [ ] All existing structure preserved (tiers, modes, philosophy)
- [ ] All security rules unchanged (terminal restrictions)
- [ ] Friendly 🐻 personality maintained
- [ ] Examples remain practical and clear

---

## 📚 References

**Key Files Audited:**
- `code_puppy/agents/agent_gui_cub.py` - Main agent definition
- `code_puppy/tools/__init__.py` - Tool registry
- `code_puppy/tools/gui_cub/vqa_two_stage_tools.py` - New VQA implementation
- `code_puppy/tools/gui_cub/multi_strategy_click.py` - Smart click tool
- `code_puppy/tools/gui_cub/executor.py` - Workflow execution engine
- `tests/gui_cub/test_hover_defaults.py` - Hover default verification

**Performance Metrics:**
- Two-stage VQA: 93% success (vs 82% single-stage), 2.1px error (vs 3.4px)
- Multi-strategy click: Accessibility (±1px) → OCR (±5-10px) → Manual
- Hover defaults: 0.5 seconds (sensible for debugging)

---

## 🎯 Final Notes

The gui-cub agent has matured significantly! The two-stage VQA and multi-strategy smart click represent major improvements in reliability and accuracy. The parameterized workflows enable powerful agent orchestration patterns.

**Key Improvement Areas:**
1. **Accuracy:** VQA improved from 3.4px to 2.1px error
2. **Success Rate:** VQA improved from 82% to 93% success
3. **Intelligence:** Smart click auto-fallback reduces manual debugging
4. **Orchestration:** Parameterized workflows enable parent agent coordination
5. **User Safety:** Manual steps for sensitive operations

**Maintain the Spirit:**
The prompt should still feel like a friendly, thorough automation cub that:
- Prefers keyboard over clicking
- Always explores before acting
- Verifies every action
- Documents discoveries
- Respects security boundaries (terminals!)
- Communicates frequently during building mode
- Runs autonomously during execution mode

Let's keep gui-cub awesome! 🐾🐻
