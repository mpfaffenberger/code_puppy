# GUI-Cub: Connexus Patient Creation & Drop-Off Workflow

## ⚡ SPEED OPTIMIZED WORKFLOW (Starting from Logged-In State)

**Prerequisites:** Connexus must be logged in and showing the main window with menu bar (File, Search, WorkQueue, Tools, Reports, Help)

**Execution Priority:** Speed and efficiency. Minimize wait times, trust keyboard input, verify only when critical.

**Speed Guidelines:**
- Use minimum safe wait times (0.1-0.2s between actions)
- Skip redundant OCR verifications (trust UIA field values)
- Only verify at critical checkpoints (patient created, order accepted)
- Execute actions rapidly - Connexus can handle fast input
- Keep only blocking waits: host lookup (5s)

**Speed Targets:**
- Phase 1 (Patient Creation): 20 seconds  
- Phase 2 (Drop-Off RX): 15 seconds
- **Total: ~35 seconds**

## Workflow Overview

1. **Create New Patient** - Dakota Test22
2. **Drop-Off RX** - Search for Dakota Test22 and initiate new prescription order

## CRITICAL RULES - READ FIRST

### Focus Management (MANDATORY)

**WARNING:** Connexus runs fullscreen and loses focus during navigation. You MUST:

```python
# PATTERN: Focus once per module/dialog, refocus BEFORE navigation actions
windows_focus_window(window_title="Connexus")
desktop_sleep(0.2)  # Reduced from 0.5s

# Fill multiple fields WITHOUT refocusing
desktop_keyboard_type("username")
desktop_keyboard_press("tab")
desktop_keyboard_type("password")

# Refocus BEFORE pressing Enter/Accept (navigation action)
windows_focus_window(window_title="Connexus")
desktop_sleep(0.2)
desktop_keyboard_press("enter")  # This navigates to new module
```

### Timing Requirements (SPEED OPTIMIZED)

- **Host lookup:** Wait 5 seconds (auto-runs after zip entry)
- **Popup appearance:** Wait 0.5-1.0 seconds AFTER triggering action (CRITICAL - dialogs need render time)
- **Popup interaction:** Wait 0.5s after closing popup before next action
- **Default step wait:** 0.1-0.2 seconds between actions (FAST)
- **Focus settle:** 0.2 seconds (reduced from 0.5s)
- **Tab navigation:** 0.3-0.5 seconds (CRITICAL for phone field - needs longer settle time)
- **Field input completion:** 0.3 seconds after typing (ensure input registers)

### Automation Strategy

**Priority order:**
1. **Keyboard shortcuts** (Alt+P, Alt+A, Ctrl+D, Ctrl+Shift+P)
2. **UI Automation** (automation_ids: btnScan, cmbPriority, txtFirstName)
3. **Keyboard typing** (for dropdowns where automation_id not accessible)
4. **OCR** (ONLY for radio buttons: HUMAN, Male, Allergies No, Medical Conditions No)

---

## Phase 1: Create New Patient - Dakota Test22

### Objective
Create a new patient record with unique details.

### Patient Data

```yaml
patient:
  first_name: "Dakota"
  last_name: "Test22"
  dob: "01011995"  # MMDDYYYY
  phone: "5015554321"  # 10 digits
  zip: "72712"  # Bentonville, AR (auto-populates city/state)
  gender: "Male"
  address: "789 Test Lane"
```

### Steps

#### 1.1: Verify Connexus Main Window Ready

1. **Check Main Window**
   ```python
   # Verify window title: "Wal*Mart Connexus"
   # Verify menu bar: File, Search, WorkQueue, Tools, Reports, Help
   windows_focus_window(window_title="Wal*Mart Connexus")
   desktop_sleep(0.2)
   ```

#### 1.2: Open Patient Search

2. **Focus Connexus Main Window**
   ```python
   windows_focus_window(window_title="Wal*Mart Connexus")
   desktop_sleep(0.2)
   ```

3. **Open Search Dialog**
   ```python
   desktop_keyboard_hotkey(["ctrl", "shift", "p"])
   desktop_sleep(0.3)
   ```

#### 1.3: Fill Search Fields (Name field is pre-focused)

**CRITICAL:** Do NOT call `desktop_focus_window` after Search opens! Name field is pre-selected.

4. **Enter Last Name (immediately, no Tab needed)**
   ```python
   desktop_keyboard_type("Test22")
   desktop_sleep(0.2)
   ```

5. **Tab to DOB Field**
   ```python
   desktop_keyboard_press("tab")
   desktop_sleep(0.3)  # Increased from 0.1s - ensure field focus settles
   ```

6. **Enter Date of Birth**
   ```python
   desktop_keyboard_type("01011995")
   desktop_sleep(0.3)  # Increased from 0.2s - ensure input completes
   ```

7. **Tab to Phone Field**
   ```python
   desktop_keyboard_press("tab")
   desktop_sleep(0.5)  # CRITICAL: Increased from 0.1s to 0.5s - phone field needs more time to receive focus
   ```

8. **Clear Phone Field and Enter Phone Number**
   ```python
   # CRITICAL FIX: Clear any residual text before typing
   desktop_keyboard_hotkey(["ctrl", "a"])  # Select all
   desktop_sleep(0.1)
   desktop_keyboard_type("5015554321")
   desktop_sleep(0.3)  # Increased from 0.2s - ensure phone input completes
   ```

9. **Press Alt+O (Operation key)**
   ```python
   desktop_keyboard_hotkey(["alt", "o"])
   desktop_sleep(0.2)
   ```

10. **Tab to Zip Field (3 tabs)**
    ```python
    desktop_keyboard_press("tab", presses=3)
    desktop_sleep(0.2)
    ```

11. **Enter Zip Code**
    ```python
    desktop_keyboard_type("72712")
    desktop_sleep(0.1)
    ```

12. **Host Look Up (Auto-runs)**
    ```python
    desktop_keyboard_hotkey(["alt", "h"])
    desktop_sleep(5)  # Cannot reduce - host query time
    # CRITICAL: Wait for Host Lookup confirmation dialog to appear
    desktop_sleep(1.0)  # Wait for popup to render and become interactive
    ```
    - **Success:** City="Bentonville", State="AR" auto-populate

13. **Confirm Host Lookup (Press OK)**
    ```python
    desktop_keyboard_press("enter")  # Press OK button
    desktop_sleep(0.5)  # Wait for dialog to close
    ```

#### 1.4: Open Patient Maintenance

14. **Click New Button (Alt+N shortcut)**
    ```python
    # Focus Search window and press Alt+N to open Patient Maintenance
    windows_focus_window(window_title="Search")
    desktop_sleep(0.2)
    desktop_keyboard_hotkey(["alt", "n"])
    desktop_sleep(1.0)  # CRITICAL: Wait for Patient Maintenance window to fully load
    ```

#### 1.5: Fill Patient Maintenance Form

**CRITICAL FIRST STEP:** Click HUMAN radio button BEFORE filling any other fields!

15. **Select Patient Type: HUMAN**
    ```python
    # Click HUMAN radio button at top left of form
    # Coordinates from connexus_locator_library (verified working)
    desktop_mouse_click(x=140, y=79)
    desktop_sleep(0.2)
    ```

16. **Enter First Name**
    ```python
    # Click First Name field using locator library coordinates
    desktop_mouse_click(x=235, y=140)
    desktop_sleep(0.2)
    desktop_keyboard_type("Dakota")
    desktop_sleep(0.2)
    ```

17. **Select Gender: Male**
    ```python
    # Click Male radio button using locator library coordinates
    desktop_mouse_click(x=120, y=243)
    desktop_sleep(0.2)
    ```

18. **Enter Address Line 1**
    ```python
    # Click Address field using locator library coordinates
    desktop_mouse_click(x=150, y=345)
    desktop_sleep(0.2)
    desktop_keyboard_type("789 Test Lane")
    desktop_sleep(0.2)
    ```

19. **Skip City/State Verification** (auto-populated, speed optimization)

20. **Select Allergies: No**
    ```python
    # Click No radio button for Allergies using locator library coordinates
    desktop_mouse_click(x=679, y=554)
    desktop_sleep(0.2)
    ```

21. **Select Medical Conditions: No**
    ```python
    # Click No radio button for Medical Conditions using locator library coordinates
    desktop_mouse_click(x=679, y=613)
    desktop_sleep(0.2)
    ```

#### 1.6: Save Patient

22. **Save Patient (Alt+A)**
    ```python
    desktop_keyboard_hotkey(["alt", "a"])
    desktop_sleep(1.0)  # Wait for validation dialog to appear
    ```

23. **Handle Phone Validation Dialog**
    ```python
    # CRITICAL: Wait for phone validation popup to fully render
    desktop_sleep(0.5)  # Additional wait for popup to become interactive
    # Select "No" with arrow keys (2 presses needed: Yes → intermediate → No)
    desktop_keyboard_press("right", presses=2)
    desktop_sleep(0.1)
    desktop_keyboard_press("enter")
    desktop_sleep(0.5)  # Wait for dialog to close
    ```

24. **Close Search Window**
    ```python
    # Close the Search window to return to main screen
    desktop_keyboard_press("escape")
    desktop_sleep(0.3)
    ```

### Success Indicators
- ✅ Patient created in database
- ✅ Validation dialog closed
- ✅ Search window closed
- ✅ Patient searchable by Last Name (Test22)

---

## Phase 2: Drop-Off New RX with Dakota Test22

### Objective
Search for newly created patient and initiate new prescription order.

### Configuration

- **Search Query:** `test22` (case-insensitive)
- **Bag Number:** Random 4-digit (e.g., 9876)
- **RX Origin:** `ORIGINAL RX`
- **Priority:** `In-Store`
- **Ready By:** Today (default)

### Steps

#### 2.1: Open Drop-Off Screen

1. **Open Drop-Off**
   ```python
   desktop_keyboard_hotkey(["ctrl", "d"])
   desktop_sleep(0.5)
   ```

#### 2.2: Search for Patient

2. **Enter Search Query (Lastname, Firstname format)**
   ```python
   # Use "Lastname, Firstname" format for precise matching
   desktop_keyboard_type("Test22, Dakota")
   desktop_sleep(0.2)
   ```

3. **Open Search**
   ```python
   desktop_keyboard_press("enter")
   desktop_sleep(0.5)
   ```

4. **Select First Result**
   ```python
   # First result should be correct with lastname, firstname search
   desktop_keyboard_press("enter")
   desktop_sleep(0.5)
   ```
   
   **Alternative: If Multiple Results (Optional)**
   ```python
   # If search returns multiple patients, add DOB to narrow down:
   # Clear search field and re-search with: "Test22, Dakota 01/01/1995"
   # Then press Enter twice to select first result
   ```

#### 2.3: Handle Validation Dialog

5. **Patient Not Present (bypass)**
   ```python
   # CRITICAL: Wait for "Patient Not Present" validation dialog to appear
   desktop_sleep(1.0)  # Wait for popup to render
   desktop_keyboard_hotkey(["alt", "p"])
   desktop_sleep(0.5)  # Wait for dialog to close
   ```

#### 2.4: Scan New RX

6. **Click Scan New RX**
   ```python
   ui_click_element(automation_id="btnScan", window_title="Connexus")
   desktop_sleep(0.5)
   ```

7. **Enter Bag Number (with retry for duplicates)**
   ```python
   import random
   max_retries = 5
   
   for attempt in range(max_retries):
       bag_number = str(random.randint(1000, 9999))
       desktop_keyboard_type(bag_number)
       desktop_sleep(0.2)
       desktop_keyboard_press("enter")
       desktop_sleep(1.0)  # CRITICAL: Wait for barcode verification dialog OR duplicate dialog
       
       windows_list = ui_list_windows()
       if "Duplicate" in str(windows_list):
           desktop_keyboard_press("escape")
           desktop_sleep(0.5)  # Wait for duplicate dialog to close
           continue
       else:
           break
   ```

8. **Confirm Verify Barcode**
   ```python
   # Barcode verification dialog should already be visible from step 7
   desktop_keyboard_press("enter")
   desktop_sleep(0.5)  # Wait for dialog to close
   ```

#### 2.5: Set RX Origin Type

9. **Select ORIGINAL RX**
   ```python
   desktop_keyboard_type("ORIGINAL RX")
   desktop_sleep(0.3)
   ```

10. **Accept RX Origin**
    ```python
    desktop_keyboard_hotkey(["alt", "a"])
    desktop_sleep(1.0)  # CRITICAL: Wait for RX Origin dialog to close and next screen to load
    ```

#### 2.6: Set Priority and Ready By Date

11. **Click Priority Dropdown**
    ```python
    # Find and click Priority field using OCR
    result = desktop_find_text("Priority", use_active_window=True)
    if result.found:
        desktop_mouse_click(x=result.best_match.center_x + 70, y=result.best_match.center_y)
    desktop_sleep(0.2)
    ```

12. **Type Priority Value**
    ```python
    desktop_keyboard_hotkey(["ctrl", "a"])
    desktop_keyboard_type("In-Store")
    desktop_keyboard_press("tab")
    desktop_sleep(0.2)
    ```

13. **Navigate to Ready By Date Field**
    ```python
    # Tab to Ready By date field
    desktop_keyboard_press("tab", presses=2)
    desktop_sleep(0.2)
    ```

14. **Set Ready By Date to Today**
    ```python
    # CRITICAL: Ready By date is REQUIRED for "Today" priority
    # Press down arrow to open calendar, then Enter to select today
    desktop_keyboard_press("down")
    desktop_sleep(0.2)
    desktop_keyboard_press("enter")
    desktop_sleep(0.3)
    ```
    
    **Note:** The Ready By date must be set BEFORE accepting the order with Alt+A, otherwise an "Entry Error" will appear.

#### 2.8: Accept Order

15. **Accept to Proceed to Input**
    ```python
    desktop_keyboard_hotkey(["alt", "a"])
    desktop_sleep(0.5)
    ```

### Success Indicators
- ✅ Drop-Off screen opened
- ✅ Patient Dakota Test22 found and selected
- ✅ Bag number entered (no duplicate error)
- ✅ RX Origin Type set to ORIGINAL RX
- ✅ Priority set to In-Store
- ✅ Order accepted, proceeded to Input screen

---

## Timing Summary (SPEED OPTIMIZED)

| Phase | Action | Wait Time |
|-------|--------|----------|
| Patient | Search dialog | 0.3s |
| Patient | Host lookup | 5s (cannot reduce) |
| Patient | New patient form | 0.5s |
| Patient | Save | 0.5s |
| Drop-Off | Open screen | 0.5s |
| Drop-Off | Search | 0.5s |
| Drop-Off | Scan New RX | 0.5s |
| Drop-Off | Bag verification | 0.5s |
| Drop-Off | RX Origin accept | 0.5s |
| Drop-Off | Final accept | 0.5s |

**Total estimated time:** 35-40 seconds (speed optimized)

---

## Notes for GUI-Cub

- **SPEED IS PRIORITY** - Use minimum safe wait times (0.1-0.2s)
- **POPUP CRITICAL RULE** - ALWAYS wait 0.5-1.0s AFTER triggering action BEFORE interacting with popup
- **PHONE FIELD FIX** - Use Ctrl+A before typing phone to clear residual text, wait 0.5s after tab
- **Trust keyboard input** - Skip redundant verifications
- **ALWAYS focus window before keyboard actions** (windows_focus_window)
- **NEVER focus terminal/shell apps** - focus Connexus only
- **Refocus before navigation actions** (Enter, Alt+A that change screens)
- **Use automation_ids when available** (btnScan, cmbPriority, txtFirstName)
- **Fall back to keyboard typing** when automation_id not accessible
- **OCR only for radio buttons** (HUMAN, Male, Allergies, Medical Conditions)
- **Report back at phases only** (agent_share_your_reasoning at Patient/DropOff completion)
- **Log only failures** to knowledge base (speed optimization)

**This is a WORKFLOW RUNNING MODE task** - execute autonomously with phase-level progress updates only.

**Execute immediately without asking for patient details - use Dakota Test22 as specified above.**

---

**End of Prompt**
