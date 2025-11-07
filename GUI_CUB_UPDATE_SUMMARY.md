# GUI-Cub System Prompt Update - Quick Reference

**TL;DR:** GUI-Cub got major upgrades! Update the system prompt to reflect new tools and improved accuracy.

---

## 🚀 What's New?

### 1. 🎯 Two-Stage VQA (HUGE Improvement!)

**Before:**
- Single-stage VQA
- 82% success rate
- 3.4px mean error
- 50-100px offset warnings

**After:**
- Two-stage coarse-to-fine VQA
- **93% success rate** ↑
- **2.1px mean error** ↓
- Saves 4 debug images automatically
- Bounding box detection (30% more accurate)

**Tool:** `desktop_vqa_click_two_stage(element_description, window_title, save_debug=True)`

---

### 2. ⚡ Multi-Strategy Smart Click

**What it does:**
Automatically tries multiple clicking methods in order:
1. Accessibility API (±1px) →
2. OCR with SmartClickCalculator (±5-10px) →
3. Manual coordinates (fallback)

**Tool:** `desktop_click_element_smart(search_text, element_type, verify_click=True)`

**Why it's awesome:**
- No more manual fallback logic
- Element-type-aware offsets (button, link, checkbox, etc.)
- Automatic verification
- Retry strategies built-in
- Logs all attempts for debugging

**Example:**
```python
result = desktop_click_element_smart(
    search_text="Submit",
    element_type="button",
    verify_click=True,
    verify_text="Success"
)
# Automatically tries Accessibility → OCR → Manual!
```

---

### 3. 📦 Parameterized Workflows

**Before:**
Workflows were static YAML files with hardcoded values.

**After:**
Workflows are reusable, type-safe functions with:
- Typed parameters (string, number, boolean, array, object)
- Structured JSON outputs
- Conditional execution (`condition: "${var} == value"`)
- Parent agent orchestration
- Output variables (`output_variable: "patient_name"`)

**Example Workflow:**
```yaml
name: "Patient Lookup"
parameters:
  - name: patient_id
    type: string
    required: true
outputs:
  - name: patient_name
  - name: screenshot

steps:
  - action: type
    text: "${patient_id}"
  - action: extract_text
    region: {x: 100, y: 200, width: 300, height: 50}
    output_variable: "patient_name"
```

**Execution:**
```python
result = gui_cub_execute_workflow(
    name="patient_lookup",
    parameters={"patient_id": "PAT-67890"}
)
# Returns: {"patient_name": "John Doe", "screenshot": "/path/..."}
```

---

### 4. 🔒 Manual Steps (User Intervention)

**New workflow action for sensitive/manual tasks:**

```yaml
- action: manual_step
  message: "Please enter your password and click Continue"
# Workflow pauses, user completes action, clicks Continue
# Workflow resumes automatically
```

**Use cases:**
- 🔒 Passwords, MFA codes, API keys
- 🤖 CAPTCHA solving
- 🎯 User decisions
- ✅ Visual confirmations

---

### 5. ⏱️ Hover Defaults

**Before:** No default duration for hover operations

**After:** `duration=0.5` seconds (sensible default)

**Tool:** `desktop_hover_and_verify(x, y, duration=0.5)`

---

## 🛠️ What to Update in System Prompt

### ✅ Quick Checklist

1. **VQA Section:**
   - [ ] Change "50-100px offset" → "93% success, 2.1px error"
   - [ ] Mention "two-stage coarse-to-fine" strategy
   - [ ] Add "saves 4 debug images automatically"
   - [ ] Update tool name to `desktop_vqa_click_two_stage()`

2. **Add Smart Click:**
   - [ ] Add `desktop_click_element_smart()` to common patterns
   - [ ] Explain auto-fallback (Accessibility → OCR → Manual)
   - [ ] Include element types (button, link, checkbox, etc.)
   - [ ] Show verification options

3. **Add Parameterized Workflows:**
   - [ ] Add section on parameter types and conditional execution
   - [ ] Show output collection with `output_variable`
   - [ ] Include structured JSON response example
   - [ ] Explain parent agent orchestration

4. **Add Manual Steps:**
   - [ ] Add `manual_step` to supported actions
   - [ ] Explain use cases (passwords, MFA, CAPTCHA)
   - [ ] Show YAML example

5. **Update Tool Descriptions:**
   - [ ] OCR: Mention "SmartClickCalculator" and element-specific offsets
   - [ ] VQA: Update to two-stage stats
   - [ ] Add hover default duration

6. **Update Critical Rules:**
   - [ ] Add smart click recommendation
   - [ ] Update VQA rule with two-stage improvement
   - [ ] Keep all security rules (terminals!)

---

## 📊 Performance Improvements Summary

| Feature | Before | After | Improvement |
|---------|--------|-------|-------------|
| VQA Success Rate | 82% | **93%** | +13% ↑ |
| VQA Mean Error | 3.4px | **2.1px** | -38% ↓ |
| Click Fallback | Manual logic | **Auto-fallback** | Automated |
| Workflows | Static YAML | **Parameterized** | Type-safe |
| User Input | Not supported | **Manual steps** | Secure |
| Hover Duration | No default | **0.5s default** | Sensible |

---

## 🐾 What NOT to Change

**Keep these unchanged:**
- ✅ Operating modes (Building vs Running)
- ✅ Tier priority (Keyboard → Accessibility → OCR → VQA)
- ✅ Security rules (terminal restrictions)
- ✅ Standard workflow pattern
- ✅ Knowledge base management
- ✅ Communication strategy
- ✅ Friendly 🐻 personality
- ✅ Platform-specific guidance

---

## 📝 Where to Find Full Details

See `GUI_CUB_SYSTEM_PROMPT_UPDATE.md` for:
- Complete section-by-section updates
- Full code examples
- Implementation prompt
- Validation checklist
- References to source files

---

## 🎉 Bottom Line

GUI-Cub is now **more accurate, more intelligent, and more flexible!**

**Key wins:**
1. **93% VQA success** (was 82%)
2. **Smart click auto-fallback** (no more manual logic)
3. **Parameterized workflows** (reusable, type-safe)
4. **Manual steps** (secure user intervention)
5. **Better defaults** (0.5s hover)

Update the prompt to let users know about these awesome improvements! 🐾🐻
