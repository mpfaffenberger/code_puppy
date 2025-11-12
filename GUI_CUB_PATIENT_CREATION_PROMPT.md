# GUI Cub Prompt for Connexus (Windows) - Patient Creation Workflow

You are GUI Cub targeting Connexus Pharmacy Management System (Windows). We are building the **Patient Creation** workflow based on successful Boot and Login workflows already completed.

## Session Context

### Completed Workflows ✅

1. **BootConnexus.yaml** - Application launch (tested, working)
   - Location: `connexus_locator_library/workflows/BootConnexus.yaml`
   - Boot time: ~12 seconds
   - Status: Production ready

2. **LoginConnexus.yaml v1.1** - Authentication (tested, working)
   - Location: `connexus_locator_library/workflows/LoginConnexus.yaml`
   - Login time: ~48 seconds
   - Popups cleared: 3 (Security Warning + 2x Warning!)
   - Status: Production ready

### Critical Learnings from Login Workflow 🔥

**MANDATORY: Focus Management for Fullscreen Apps**

Connexus runs FULLSCREEN and loses focus when navigating between modules. You MUST:

```python
# Focus ONCE when entering a module/dialog
windows_focus_window(window_title="Connexus")  # or "Wal*Mart Connexus" after login
desktop_sleep(0.5)  # Let focus settle

# Fill multiple fields WITHOUT refocusing
desktop_keyboard_type("field1")
desktop_keyboard_press("tab")
desktop_keyboard_type("field2")
desktop_keyboard_press("tab")
desktop_keyboard_type("field3")

# Refocus BEFORE navigation action (Enter/Accept that changes screens)
windows_focus_window(window_title="Connexus")
desktop_sleep(0.3)
desktop_keyboard_press("enter")  # Submit/navigate
```

**Applies to:**
- Before entering a new module/dialog (focus once)
- Before pressing Enter/Accept that navigates to new screen
- After popups are dismissed

**NOT needed:**
- Between field entries in same module
- Between Tab presses in same dialog
- Within continuous typing sequences

### Element Locator Strategy

**This RXPC uses NAME-BASED locators**, not automation_id:

```yaml
# Use this pattern:
control_type: Edit  # or Button, CheckBox, MenuItem
name: "Field Name"  # Actual visible name
fuzzy: true
fuzzy_threshold: 0.7
```

**Example from login workflow:**
- Password field: `control_type: Edit, name: Password`
- Accept button: `control_type: Button, name: Accept`
- HomeOffice checkbox: `control_type: CheckBox, name: HomeOffice User`

---

## Patient Creation Workflow - To Build

### Objective

Create a new patient record in Connexus by:
1. Opening Patient Search dialog
2. Filling search fields (Name, DOB, Phone)
3. Triggering search with Enter (NOT "Search Now" button!)
4. Filling Zip code in dynamically-appearing field
5. Waiting for automatic Host Look Up
6. Clicking "New" button to open patient creation form

### Known Workflow Steps (from KB)

#### Step 1: Open Patient Search Dialog

**Keyboard Shortcut:** `Ctrl+Shift+P`

```python
windows_focus_window(window_title="Wal*Mart Connexus")
desktop_sleep(0.3)
desktop_keyboard_hotkey(["ctrl", "shift", "p"])
desktop_sleep(2)

# Verify Patient Search window opened
# Look for window title or "Search For" / "Patient" text
```

**Success Criteria:**
- Patient Search dialog visible
- Name field is focused (cursor in field)
- "Search For" text visible

#### Step 2-4: Fill Search Fields (Name, DOB, Phone)

**Fields:** Name → DOB → Phone (continuous sequence)

```python
# Focus ONCE at start of Patient Search dialog
windows_focus_window(window_title="Patient")  # Or exact window title
desktop_sleep(0.5)

# Fill all fields WITHOUT refocusing between them
desktop_keyboard_type("Test Patient")
desktop_sleep(0.5)
desktop_keyboard_press("tab")
desktop_sleep(0.3)
desktop_keyboard_type("01/01/1990")  # MM/DD/YYYY format
desktop_sleep(0.5)
desktop_keyboard_press("tab")
desktop_sleep(0.3)
desktop_keyboard_type("1234567890")  # 10 digits, no formatting
desktop_sleep(0.5)

# VERIFY: Use OCR to confirm all fields filled correctly
```

**⚠️ CRITICAL:** Verify text landed in correct fields before proceeding!

#### Step 5: Trigger Search with Enter ⚠️ (Navigation Action)

**🔑 KEY DISCOVERY:** Press `Enter` in any text field, do NOT click "Search Now" button!

**Why?**
- Clicking "Search Now" causes dialog to close unexpectedly
- Pressing Enter triggers search AND keeps dialog open
- Zip field only appears AFTER search is triggered

```python
# Refocus BEFORE Enter (this is a navigation-like action)
windows_focus_window(window_title="Patient")
desktop_sleep(0.3)
desktop_keyboard_press("enter")
desktop_sleep(2)

# VERIFY: Zip field should now be visible
```

#### Step 6-7: Navigate to Zip Field and Fill

**⚠️ GOTCHA:** Zip field appears dynamically after search. Tab order may vary.

```python
# Tab to Zip field (may require multiple tabs)
# No refocus needed - still in same dialog
desktop_keyboard_press("tab")
desktop_sleep(0.3)

# Use OCR to verify cursor is in Zip field
# If wrong field, use Shift+Tab to go back or Tab to go forward

# Fill Zip code (no refocus needed)
desktop_keyboard_type("12345")
desktop_sleep(0.5)

# 🚨 CRITICAL VERIFICATION: Confirm zip code is in Zip field,
# NOT in Name or Phone fields!
```

#### Step 8: Wait for Automatic Host Look Up

**🔑 KEY DISCOVERY:** Host Look Up runs automatically after Zip is filled!

```python
# Wait for Host Look Up to complete
desktop_sleep(5)

# Indicators:
# - "New" button becomes enabled
# - Search results grid may populate (if patient exists)
# - No "searching" or "loading" indicator visible
```

#### Step 9: Click "New" Button (Navigation Action)

```python
# Tab to New button (no refocus needed yet)
desktop_keyboard_press("tab")
desktop_sleep(0.3)

# Refocus BEFORE pressing Enter (navigation to new form)
windows_focus_window(window_title="Patient")
desktop_sleep(0.3)
desktop_keyboard_press("enter")
desktop_sleep(2)

# VERIFY: New Patient creation form is open
# Look for "Patient Information" text or new window title
```

---

## Element Locators (Pre-Captured)

### From PatientManagement.yaml

These are automation_ids from existing locator library. **May need to use name-based locators instead** on this RXPC:

**Patient Maintenance Page:**
- `txtFirstName` (automation_id)
- `txtLastName` (automation_id)
- `txtMiddleName` (automation_id)
- `mtbDateofBirth` (automation_id)
- `mtbPhone1` (automation_id)
- `ZipTextBox` (automation_id)
- `rdbMale` / `rdbFemale` (automation_id)
- `chkSameAsPatient` (automation_id)

**Patient Search Dialog:**
- Need to capture element tree when dialog opens
- Likely name-based locators: "Name", "Date of Birth", "Phone", "Zip"
- "Search Now" button (avoid clicking!)
- "New" button (target after Host Look Up)

---

## Workflow Files to Create

### 1. PatientSearch.yaml

**Purpose:** Open Patient Search dialog and fill search fields

**Steps:**
1. Open dialog (Ctrl+Shift+P)
2. Fill Name
3. Fill DOB
4. Fill Phone
5. Trigger search (Enter)
6. Verify Zip field appears

**Output:** Patient Search dialog ready for Zip entry

### 2. PatientCreation.yaml

**Purpose:** Complete patient creation from search dialog

**Prerequisites:** PatientSearch.yaml completed

**Steps:**
1. Fill Zip code
2. Wait for Host Look Up (automatic)
3. Click "New" button
4. Verify patient creation form opened

**Output:** Patient creation form ready for data entry

---

## Testing Strategy

### Phase 1: Element Discovery

1. **Assume Connexus is already logged in** (from LoginConnexus workflow)
2. Open Patient Search dialog (Ctrl+Shift+P)
3. **List elements** with `ui_list_elements(mode="flat", depth=5)`
4. **Identify actual element names** (not automation_ids)
5. **Document tab order** by testing navigation
6. **Capture element tree** at each step

### Phase 2: Build Workflow

1. Create PatientSearch.yaml with discovered locators
2. Create PatientCreation.yaml as continuation
3. **Test each step** with refocus before every action
4. **Verify with OCR** after each field entry
5. **Document findings** to knowledge base

### Phase 3: Validation

1. Execute complete workflow start-to-finish
2. Verify patient creation form opens
3. Log timing observations (adaptive)
4. Update knowledge base with test results

---

## Verification Strategy

**After Each Field Entry:**
```python
# Use OCR to verify text in correct field
desktop_extract_text(use_active_window=True)
# Check extracted text contains expected value near expected label
```

**After Each Step:**
```python
# List elements to confirm UI state
ui_list_elements(mode="flat", depth=3)
# Check for expected elements
```

**Report Progress:**
```python
# Every 2-3 actions:
agent_share_your_reasoning(
    reasoning="Just completed X, verified Y, next doing Z",
    next_steps="..."
)
```

---

### Known Issues & Tips

### From Previous Testing

1. **Tab order can be unpredictable** - Verify focus with OCR before typing
2. **Zip field appears dynamically** - Only visible after search triggered
3. **Search Now button causes issues** - Always use Enter instead
4. **Host Look Up is automatic** - No manual button click needed
5. **Values can land in wrong fields** - Verify EVERY field entry
6. **Focus is stable within modules** - Only refocus before navigation actions
7. **Navigation actions need refocus** - Enter/Accept that change screens

### Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| Typing in wrong field | Verify focus with OCR before typing |
| Dialog closes unexpectedly | Use Enter, not "Search Now" button |
| Zip field not found | Trigger search first, then look for Zip |
| Focus lost mid-workflow | Refocus before navigation actions (Enter/Accept) |
| Values overwrite each other | Verify each field after entry |

---

## File Locations

**Workflow Files:**
- `connexus_locator_library/workflows/PatientSearch.yaml` (to create)
- `connexus_locator_library/workflows/PatientCreation.yaml` (to create)

**Knowledge Base:**
- `GUI_CUB_CONNEXUS_WORKFLOWS_KB.md` (update with findings)

**Reference Files:**
- `connexus_locator_library/workflows/BootConnexus.yaml` (completed)
- `connexus_locator_library/workflows/LoginConnexus.yaml` (completed)
- `connexus_locator_library/workflows/PatientManagement.yaml` (element library)
- `CONNEXUS_RPA_KNOWLEDGE_ARTICLE.md` (detailed patient creation steps)

---

## Ready to Start

**Assumptions:**
1. Connexus is already running and logged in (via BootConnexus + LoginConnexus)
2. Main window title: "Wal*Mart Connexus"
3. Heavy tooling (OCR) is permitted for this session
4. You will focus once per module, refocus before navigation actions
5. You will verify field entries with OCR at key checkpoints
6. You will report progress every 2-3 actions

**First Steps:**
1. Focus main Connexus window
2. Open Patient Search dialog (Ctrl+Shift+P)
3. List elements to discover actual names
4. Begin building PatientSearch.yaml workflow
5. Test and iterate

**Go! 🐻**