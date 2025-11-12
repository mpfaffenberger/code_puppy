# GUI Cub - Connexus Full Workflow Execution Prompt
# Four Workflows Back-to-Back: Boot → Login → Create Patient → Search Patient
# Focus: Speed and efficiency with minimal validation (final steps only)

## Mission Objective
Execute 4 Connexus workflows in sequence for recording/demonstration:
1. **BootConnexus** - Launch application
2. **LoginConnexus** - Authenticate user
3. **PatientCreation** - Create new patient (TESTERSON, JOHN)
4. **PatientSearch** - Search and verify patient exists

## Core Principles for This Run
- **SPEED FIRST**: Minimize waits, no unnecessary verifications
- **KEYBOARD ONLY**: No mouse clicks except for non-tabbable elements (HUMAN radio, Gender, Allergies)
- **VALIDATE AT MODULE BOUNDARIES**: Only verify at workflow completion points and popups
- **NO OCR/VQA** except: HUMAN radio button, Male radio, Allergies/Medical Conditions radios
- **NO TERMINAL OCR**: Never focus or OCR terminal/shell windows
- **REPORT EVERY 2-3 ACTIONS**: Use agent_share_your_reasoning to show progress

## Workflow Reference Files
All workflows documented in:
- `connexus_locator_library/workflows/BootConnexus.yaml`
- `connexus_locator_library/workflows/LoginConnexus.yaml`
- `connexus_locator_library/workflows/PatientCreation.yaml` (v2.0)
- `connexus_locator_library/workflows/PatientSearch.yaml` (v2.0)

---

## WORKFLOW 1: BootConnexus

**Goal:** Launch Connexus application

**Steps:**
1. Execute application launch command/shortcut
2. Wait for main window "Wal*Mart Connexus" to appear
3. **VALIDATE:** Main window visible (via windows_list_windows)
4. **Report:** "Connexus booted successfully"

**Timing:** ~5-10 seconds for application startup

**Validation:** Main window title contains "Connexus"

---

## WORKFLOW 2: LoginConnexus

**Goal:** Authenticate to Connexus

**Steps:**
1. Focus Connexus window
2. Enter credentials (keyboard only)
3. Submit login (Enter or Tab to button + Enter)
4. Wait for login to complete
5. **VALIDATE:** Main Connexus interface loaded (specific indicator TBD from LoginConnexus.yaml)
6. **Report:** "Login successful"

**Timing:** ~2-5 seconds for authentication

**Validation:** Login screen disappears, main interface visible

**Notes:** 
- Use stored credentials or workflow-defined test credentials
- Refer to LoginConnexus.yaml for field automation IDs

---

## WORKFLOW 3: PatientCreation (CRITICAL - Most Complex)

**Goal:** Create new patient TESTERSON, JOHN with DOB 01/02/1990

**Reference:** `connexus_locator_library/workflows/PatientCreation.yaml` v2.0

### Step-by-Step Execution:

#### 3.1 Open Patient Search
```
1. Focus "Wal*Mart Connexus" window (ONE TIME ONLY)
2. Wait 0.5s
3. Ctrl+Shift+P (open Search)
4. Wait 0.5s
5. DO NOT FOCUS SEARCH WINDOW AFTER OPENING
```

#### 3.2 Fill Search Fields (NO VALIDATION - just type)
```
# Name field is PRESELECTED - type immediately
1. Type "Testerson" (interval: 0.02)
2. Tab
3. Type "01021990" (DOB - auto-formats to 01/02/1990)
4. Tab
5. Type "1234567890" (Phone)
```

**Field Automation IDs (for reference only, no validation needed):**
- Name: "1001"
- DOB: "mtbDOB"
- Phone: "txtPatientPhone"

#### 3.3 Execute Pre-New Patient Actions
```
1. Alt+O (operation key)
2. Wait 0.3s
3. Tab (from Phone)
4. Tab (to Zip)
5. Tab (to Zip field focus)
6. Type "72712"
7. Alt+H (Host Look Up)
8. Wait 0.6s
```

**Popup Handling:**
- IF "Additional Patient Information Needed" modal appears: Press Enter
- ELSE: Continue

#### 3.4 Open Patient Maintenance
```
1. Alt+N (New patient)
2. Wait 0.7s
3. VALIDATE: windows_list_windows shows "Patient Maintenance"
4. Report: "Patient Maintenance opened"
```

#### 3.5 Fill Patient Maintenance (CRITICAL SEQUENCE)

**A. Patient Type - HUMAN (OCR REQUIRED - non-tabbable)**
```
1. Focus Patient Maintenance window
2. Wait 0.3s
3. VQA/OCR: Click HUMAN radio at coordinates [137, 78] (window-relative)
4. Wait 0.3s
5. NO VALIDATION - proceed immediately
```

**B. First Name**
```
1. OCR: Find "Name" label (second occurrence at x:235)
2. Click at [235, 140]
3. Type "John"
4. NO VALIDATION
```

**C. Gender - Male (OCR REQUIRED - non-tabbable)**
```
1. OCR: Find "Male" text
2. Click 15px left of text (radio button)
3. Approximate coords: [120, 243]
4. NO VALIDATION
```

**D. Address Line 1**
```
1. OCR: Find "*Address" label
2. Click at [150, 345]
3. Type "123 Main Street"
4. NO VALIDATION
```

**E. City/State (Auto-populated from Host Look Up)**
- SKIP - already filled by Alt+H
- City: Bentonville
- State: AR

**F. Allergies - No (OCR REQUIRED - non-tabbable)**
```
1. OCR region: [580, 540, 200, 30]
2. Find "No" (OCR may read as "OnNo" or "Ono")
3. Click at [679, 554]
4. NO VALIDATION
```

**G. Medical Conditions - No (OCR REQUIRED - non-tabbable)**
```
1. OCR region: [580, 605, 200, 30]
2. Find "No"
3. Click at [679, 613]
4. NO VALIDATION
```

#### 3.6 Save & Close (VALIDATION REQUIRED)
```
1. Alt+A (Save & Close)
2. Wait 1.0s
3. VALIDATE: windows_list_windows shows "Validation" dialog
4. Report: "Validation dialog appeared"
```

#### 3.7 Handle Phone Validation Dialog (CRITICAL)
```
1. Right arrow (from Yes to intermediate)
2. Right arrow (to No)
3. Enter (activate OK button)
4. Wait 1.0s
5. VALIDATE: Both "Validation" and "Patient Maintenance" windows closed
6. Report: "Patient created successfully - TESTERSON, JOHN"
```

**Success Criteria:**
- Validation dialog closed
- Patient Maintenance window closed
- Search window still open (optional - may close)
- No error dialogs

---

## WORKFLOW 4: PatientSearch

**Goal:** Search for and verify TESTERSON, JOHN exists

**Reference:** `connexus_locator_library/workflows/PatientSearch.yaml` v2.0

### Step-by-Step Execution:

#### 4.1 Open Patient Search (if not already open)
```
1. Focus "Wal*Mart Connexus"
2. Wait 0.5s
3. Ctrl+Shift+P
4. Wait 0.5s
```

#### 4.2 Fill Search Criteria (NO VALIDATION)
```
1. Type "Testerson" (Name field preselected)
2. Tab
3. Type "01021990" (DOB)
4. NO phone needed for this search
```

#### 4.3 Execute Search
```
1. Press Enter (from DOB field)
2. Wait 1.0s
```

#### 4.4 Verify Results (VALIDATION REQUIRED)
```
Method 1 - Keyboard (PREFERRED):
  1. Tab from DOB field
  2. IF focus moves to result row: SUCCESS
  3. Arrow down/up to navigate results
  4. Report: "Patient found - result row keyboard-selectable"

Method 2 - VQA (if keyboard unclear):
  1. desktop_screenshot_analyze: "Are there any patient result rows visible?"
  2. IF answer contains "yes" or "TESTERSON, JOHN": SUCCESS
  3. Report: "Patient found - TESTERSON, JOHN visible in results"

Method 3 - Fallback UIA:
  1. ui_list_elements (may fail due to known attach issues)
  2. Look for table/grid with row elements
  3. Report success if rows found
```

**Success Criteria:**
- At least one result row appears
- Result contains: TESTERSON, JOHN, 01/02/1990, BENTONVILLE, AR
- Status bar shows "1 record(s) found"

**Final Report:**
```
"✅ FULL WORKFLOW COMPLETE:
- Connexus booted
- User logged in
- Patient created: TESTERSON, JOHN (DOB: 01/02/1990)
- Patient search verified: 1 record found

All 4 workflows executed successfully."
```

---

## Timing Summary

| Workflow | Duration | Key Waits |
|----------|----------|----------|
| BootConnexus | ~5-10s | App launch |
| LoginConnexus | ~2-5s | Authentication |
| PatientCreation | ~15-20s | 0.7s (Patient Maint open), 1.0s (Save), 1.0s (Validation) |
| PatientSearch | ~2-3s | 1.0s (Search execute) |
| **TOTAL** | **~25-40s** | |

## Critical Success Points (VALIDATE ONLY HERE)

1. ✅ Connexus main window appears (Boot)
2. ✅ Login screen disappears (Login)
3. ✅ Patient Maintenance window opens (Creation - Step 3.4)
4. ✅ Validation dialog appears (Creation - Step 3.6)
5. ✅ Validation + Patient Maintenance close (Creation - Step 3.7)
6. ✅ Search result row appears (Search - Step 4.4)

## Error Recovery (If Needed)

**If Patient Maintenance Address field disabled:**
- HUMAN radio not clicked properly
- Retry: Click HUMAN at [137, 78], wait 0.5s

**If Validation dialog won't close:**
- Verify sequence: Right → Right → Enter
- NOT: Tab → Tab → Space → Tab → Enter (Tab navigation doesn't work)

**If Search returns 0 results:**
- Patient wasn't saved (check for errors during Creation)
- Retry search with just Last Name (omit DOB)

**If OCR fails on radio buttons:**
- Use VQA with grid: desktop_screenshot_analyze(use_grid=True, grid_spacing=25)
- Get coordinates from VQA response

## Speed Optimizations Applied

- ✅ No field-by-field validation during data entry
- ✅ Minimal wait times (0.2-0.3s for UI settling, 0.5-1.0s for dialogs)
- ✅ Keyboard-first (no mouse except non-tabbable radios)
- ✅ Validation only at module boundaries and popups
- ✅ Reuse open Search window when possible
- ✅ No screenshot/OCR except for required radio buttons
- ✅ No windows_get_focused_element calls during speed run (trust tab sequence)

## Agent Reporting Requirements

**Call agent_share_your_reasoning every 2-3 actions with:**
- Current workflow step
- Action just completed
- Next action planned
- Any issues encountered

Example:
```
"Workflow 3 - PatientCreation, Step 3.5B:
Completed: Clicked HUMAN radio at [137, 78]
Next: Click First Name field at [235, 140] and type 'John'
Status: On track, no issues"
```

## Final Checklist Before Starting

- [ ] Connexus is closed (for clean Boot workflow)
- [ ] YAML workflows reviewed for latest automation IDs
- [ ] Test data ready: Testerson, John, 01/02/1990, 1234567890, 72712
- [ ] OCR usage minimized (only for non-tabbable radios)
- [ ] Keyboard navigation prioritized throughout
- [ ] Validation points identified (6 critical checkpoints)
- [ ] Ready to execute back-to-back with minimal pauses

---

**EXECUTE COMMAND:**
"Run all 4 workflows sequentially: Boot → Login → Create Patient (TESTERSON, JOHN) → Search Patient. Focus on speed, keyboard-only where possible, validate at module boundaries only. Report progress every 2-3 actions."
