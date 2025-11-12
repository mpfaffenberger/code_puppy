# GUI-Cub: Connexus Complete Workflow - Boot → Login → Create Patient → Drop-Off RX

## ⚡ SPEED OPTIMIZED WORKFLOW

**Execution Priority:** Speed and efficiency. Minimize wait times, trust keyboard input, verify only when critical.

**Speed Guidelines:**
- Use minimum safe wait times (0.1-0.2s between actions)
- Skip redundant OCR verifications (trust UIA field values)
- Only verify at critical checkpoints (login success, patient created, order accepted)
- Execute actions rapidly - Connexus can handle fast input
- Keep only blocking waits: app launch (12s), login (50s), host lookup (5s)

**Speed Targets:**
- Phase 1 (Boot): 15 seconds
- Phase 2 (Login): 60 seconds (50s login wait + 10s popups)
- Phase 3 (Patient): 20 seconds  
- Phase 4 (Drop-Off): 15 seconds
- **Total: ~2 minutes**

## Workflow Overview

1. **Boot Connexus** - Launch application via Win+R
2. **Login** - Authenticate as HOMEOFFICE user with credentials
3. **Create New Patient** - Dakota Test22
4. **Drop-Off RX** - Search for Dakota Test22 and initiate new prescription order

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

- **App launch:** Wait 12 seconds (minimum)
- **Login submit:** Wait 50 seconds (HOMEOFFICE users - cannot reduce)
- **Host lookup:** Wait 5 seconds (auto-runs after zip entry)
- **Popups:** Check every 1 second, up to 5 retries
- **Default step wait:** 0.1-0.2 seconds between actions (FAST)
- **Focus settle:** 0.2 seconds (reduced from 0.5s)
- **Tab navigation:** 0.1 seconds (reduced from 0.3s)

### Automation Strategy

**Priority order:**
1. **Keyboard shortcuts** (Alt+P, Alt+A, Ctrl+D, Ctrl+Shift+P)
2. **UI Automation** (automation_ids: btnScan, cmbPriority, txtFirstName)
3. **Keyboard typing** (for dropdowns where automation_id not accessible)
4. **OCR** (ONLY for radio buttons: HUMAN, Male, Allergies No, Medical Conditions No)

---

## Phase 1: Boot Connexus Application

### Objective
Launch Connexus.exe and wait for login screen to appear.

### Steps

1. **Open Run Dialog**
   ```python
   desktop_keyboard_hotkey(["win", "r"])
   desktop_sleep(0.5)
   ```

2. **Type Connexus Path**
   ```python
   desktop_keyboard_type("C:\\Walmart Applications\\Connexus.Net\\UI\\Connexus.exe")
   desktop_sleep(0.2)
   ```

3. **Launch Application**
   ```python
   desktop_keyboard_press("enter")
   desktop_sleep(12)  # Minimum wait for splash screen
   ```

4. **Poll for Login Screen (Adaptive Wait)**
   - Poll every 2 seconds, max 20 seconds total
   - Success criteria: Login window visible (title contains "Connex" or "Login")
   - Verify elements: Password field (name="Password"), Accept button (name="Accept")

5. **Verify Login Screen Ready**
   ```python
   # Use ui_list_elements to check for:
   # - Password field (control_type="Edit", name="Password")
   # - Accept button (control_type="Button", name="Accept")
   ```

### Success Indicators
- ✅ Login window visible and responsive
- ✅ Username field ready for input
- ✅ No error dialogs present

---

## Phase 2: Login to Connexus

### Objective
Authenticate as HOMEOFFICE user and clear post-login popups.

### Configuration

**Credentials:**
- Username: `SVCRX1U`
- Password: `wfMUckcd1hYCK4GbP`
- Login Type: `HOMEOFFICE`
- Store: `5504`

### Steps

1. **Focus Connexus Window**
   ```python
   windows_focus_window(window_title="Connex")  # Partial match
   desktop_sleep(0.2)
   ```

2. **Enter Username**
   ```python
   desktop_keyboard_type("SVCRX1U")
   desktop_sleep(0.2)
   ```

3. **Tab to Password Field**
   ```python
   desktop_keyboard_press("tab")
   desktop_sleep(0.1)
   ```

4. **Enter Password**
   ```python
   desktop_keyboard_type("wfMUckcd1hYCK4GbP")
   desktop_sleep(0.2)
   ```

5. **Navigate to HomeOffice Checkbox**
   ```python
   # Tab 1: Password → Change Store No.
   # Tab 2: Change Store No. → HomeOffice User
   desktop_keyboard_press("tab")
   desktop_sleep(0.1)
   desktop_keyboard_press("tab")
   desktop_sleep(0.1)
   ```

6. **Check HomeOffice User Checkbox**
   ```python
   desktop_keyboard_press("space")
   desktop_sleep(0.2)
   ```

7. **Navigate to Accept Button**
   ```python
   # Tab 1: HomeOffice User → Cancel
   # Tab 2: Cancel → Accept
   windows_focus_window(window_title="Connexus")
   desktop_sleep(0.2)
   desktop_keyboard_press("tab")
   desktop_sleep(0.1)
   
   windows_focus_window(window_title="Connexus")
   desktop_sleep(0.2)
   desktop_keyboard_press("tab")
   desktop_sleep(0.1)
   ```

8. **Submit Login (REFOCUS BEFORE NAVIGATION)**
   ```python
   # CRITICAL: Refocus before Enter (navigation action)
   windows_focus_window(window_title="Connexus")
   desktop_sleep(0.2)
   desktop_keyboard_press("enter")
   desktop_sleep(50)  # Login takes ~50 seconds (cannot reduce)
   ```

9. **Wait for Security Popup**
   - Poll every 2 seconds for "Security Warning Message" window
   - Appears within ~5 seconds of login submit

10. **Dismiss Security Popup**
    ```python
    windows_focus_window(window_title="Security Warning")
    desktop_sleep(0.2)
    desktop_keyboard_press("enter")
    desktop_sleep(2)
    ```

11. **Clear Remaining Popups (Retry Loop - FAST)**
    ```python
    # Max 5 retries, check every 1 second (FAST)
    for attempt in range(1, 6):
        # Check for Warning! dialogs via ui_list_windows
        # If "Warning" in window titles:
        windows_focus_window(window_title="Warning")
        desktop_sleep(0.2)
        desktop_keyboard_press("enter")
        desktop_sleep(1)
        # Else: break (no more popups)
    ```

12. **Verify Login Success**
    - Check for menu bar: File, Search, WorkQueue, Tools, Reports, Help
    - Verify window title: "Wal*Mart Connexus"

### Success Indicators
- ✅ Main window visible and responsive
- ✅ All post-login popups cleared
- ✅ Menu bar accessible

---

## Phase 3: Create New Patient - Dakota Test22

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

#### 3.1: Open Patient Search

1. **Focus Connexus Main Window**
   ```python
   windows_focus_window(window_title="Wal*Mart Connexus")
   desktop_sleep(0.2)
   ```

2. **Open Search Dialog**
   ```python
   desktop_keyboard_hotkey(["ctrl", "shift", "p"])
   desktop_sleep(0.3)
   ```

#### 3.2: Fill Search Fields (Name field is pre-focused)

**CRITICAL:** Do NOT call `desktop_focus_window` after Search opens! Name field is pre-selected.

3. **Enter Last Name (immediately, no Tab needed)**
   ```python
   desktop_keyboard_type("Test22")
   desktop_sleep(0.2)
   ```

4. **Tab to DOB Field**
   ```python
   desktop_keyboard_press("tab")
   desktop_sleep(0.1)
   ```

5. **Enter Date of Birth**
   ```python
   desktop_keyboard_type("01011995")
   desktop_sleep(0.2)
   ```

6. **Tab to Phone Field**
   ```python
   desktop_keyboard_press("tab")
   desktop_sleep(0.1)
   ```

7. **Enter Phone Number**
   ```python
   desktop_keyboard_type("5015554321")
   desktop_sleep(0.2)
   ```

8. **Press Alt+O (Operation key)**
   ```python
   desktop_keyboard_hotkey(["alt", "o"])
   desktop_sleep(0.2)
   ```

9. **Tab to Zip Field (3 tabs)**
   ```python
   desktop_keyboard_press("tab", presses=3)
   desktop_sleep(0.2)
   ```

10. **Enter Zip Code**
    ```python
    desktop_keyboard_type("72712")
    desktop_sleep(0.1)
    ```

11. **Host Look Up (Auto-runs)**
    ```python
    desktop_keyboard_hotkey(["alt", "h"])
    desktop_sleep(5)  # Cannot reduce - host query time
    ```
    - **Success:** City="Bentonville", State="AR" auto-populate

#### 3.3: Open Patient Maintenance

12. **Click New Button**
    ```python
    desktop_keyboard_hotkey(["alt", "n"])
    desktop_sleep(0.5)
    ```

#### 3.4: Fill Patient Maintenance Form

**CRITICAL FIRST STEP:** Click HUMAN radio button BEFORE filling any other fields!

13. **Select Patient Type: HUMAN**
    ```python
    result = desktop_find_text(search_text="HUMAN", use_active_window=True)
    if result.found:
        radio_x = result.best_match.center_x - 20
        radio_y = result.best_match.center_y
        desktop_mouse_click(x=radio_x, y=radio_y)
        desktop_sleep(0.2)
    ```

14. **Enter First Name**
    ```python
    ui_click_element(automation_id="txtFirstName", window_title="Patient Maintenance")
    desktop_sleep(0.1)
    desktop_keyboard_type("Dakota")
    desktop_sleep(0.1)
    ```

15. **Select Gender: Male**
    ```python
    result = desktop_find_text(search_text="Male", use_active_window=True)
    if result.found:
        radio_x = result.best_match.center_x - 15
        radio_y = result.best_match.center_y
        desktop_mouse_click(x=radio_x, y=radio_y)
        desktop_sleep(0.1)
    ```

16. **Enter Address Line 1**
    ```python
    ui_click_element(automation_id="txtAddressLine1", window_title="Patient Maintenance")
    desktop_sleep(0.1)
    desktop_keyboard_type("789 Test Lane")
    desktop_sleep(0.1)
    ```

17. **Skip City/State Verification** (auto-populated, speed optimization)

18. **Select Allergies: No**
    ```python
    result = desktop_find_text(
        search_text="No",
        use_active_window=True,
        x=580, y=540, width=200, height=30
    )
    if result.found:
        desktop_mouse_click(x=result.best_match.center_x, y=result.best_match.center_y)
        desktop_sleep(0.1)
    ```

19. **Select Medical Conditions: No**
    ```python
    result = desktop_find_text(
        search_text="No",
        use_active_window=True,
        x=580, y=605, width=200, height=30
    )
    if result.found:
        desktop_mouse_click(x=result.best_match.center_x, y=result.best_match.center_y)
        desktop_sleep(0.1)
    ```

#### 3.5: Save Patient

20. **Save Patient (Alt+A)**
    ```python
    desktop_keyboard_hotkey(["alt", "a"])
    desktop_sleep(1.0)
    ```

21. **Handle Phone Validation Dialog**
    ```python
    # Select "No" with arrow keys
    desktop_keyboard_press("right")  # Yes → intermediate
    desktop_keyboard_press("right")  # intermediate → No
    desktop_sleep(0.1)
    desktop_keyboard_press("enter")
    desktop_sleep(0.5)
    ```

### Success Indicators
- ✅ Patient created in database
- ✅ Validation dialog closed
- ✅ Patient searchable by Last Name (Test22)

---

## Phase 4: Drop-Off New RX with Dakota Test22

### Objective
Search for newly created patient and initiate new prescription order.

### Configuration

- **Search Query:** `test22` (case-insensitive)
- **Bag Number:** Random 4-digit (e.g., 9876)
- **RX Origin:** `ORIGINAL RX`
- **Priority:** `In-Store`
- **Ready By:** Today (default)

### Steps

#### 4.1: Open Drop-Off Screen

1. **Open Drop-Off**
   ```python
   desktop_keyboard_hotkey(["ctrl", "d"])
   desktop_sleep(0.5)
   ```

#### 4.2: Search for Patient

2. **Enter Search Query**
   ```python
   desktop_keyboard_type("test22")
   desktop_sleep(0.2)
   ```

3. **Open Search**
   ```python
   desktop_keyboard_press("enter")
   desktop_sleep(0.5)
   ```

4. **Select First Result**
   ```python
   desktop_keyboard_press("enter")
   desktop_sleep(0.5)
   ```

#### 4.3: Handle Validation Dialog

5. **Patient Not Present (bypass)**
   ```python
   desktop_keyboard_hotkey(["alt", "p"])
   desktop_sleep(0.5)
   ```

#### 4.4: Scan New RX

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
       desktop_sleep(0.5)
       
       windows_list = ui_list_windows()
       if "Duplicate" in str(windows_list):
           desktop_keyboard_press("escape")
           desktop_sleep(0.3)
           continue
       else:
           break
   ```

8. **Confirm Verify Barcode**
   ```python
   desktop_keyboard_press("enter")
   desktop_sleep(0.5)
   ```

#### 4.5: Set RX Origin Type

9. **Select ORIGINAL RX**
   ```python
   desktop_keyboard_type("ORIGINAL RX")
   desktop_sleep(0.3)
   ```

10. **Accept RX Origin**
    ```python
    desktop_keyboard_hotkey(["alt", "a"])
    desktop_sleep(0.5)
    ```

#### 4.6: Set Priority

11. **Click Priority Dropdown**
    ```python
    ui_click_element(automation_id="cmbPriority", window_title="Connexus")
    desktop_sleep(0.2)
    ```

12. **Type Priority Value**
    ```python
    desktop_keyboard_hotkey(["ctrl", "a"])
    desktop_keyboard_type("In-Store")
    desktop_keyboard_press("tab")
    desktop_sleep(0.2)
    ```

#### 4.7: Set Ready By Date

13. **Navigate to Ready By**
    ```python
    desktop_keyboard_press("tab", presses=2)
    desktop_sleep(0.2)
    ```

14. **Select Date**
    ```python
    desktop_keyboard_press("down")
    desktop_sleep(0.2)
    desktop_keyboard_press("enter")
    desktop_sleep(0.3)
    ```

#### 4.8: Accept Order

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
| Boot | App launch | 12s |
| Boot | Login screen poll | 2s intervals |
| Login | Tab navigation | 0.1s per tab |
| Login | Submit login | 50s (cannot reduce) |
| Login | Security popup | 2s |
| Login | Clear popups | 1s intervals, 5 retries |
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

**Total estimated time:** 2-3 minutes (speed optimized)

---

## Notes for GUI-Cub

- **SPEED IS PRIORITY** - Use minimum safe wait times (0.1-0.2s)
- **Trust keyboard input** - Skip redundant verifications
- **ALWAYS focus window before keyboard actions** (windows_focus_window)
- **NEVER focus terminal/shell apps** - focus Connexus only
- **Refocus before navigation actions** (Enter, Alt+A that change screens)
- **Use automation_ids when available** (btnScan, cmbPriority, txtFirstName)
- **Fall back to keyboard typing** when automation_id not accessible
- **OCR only for radio buttons** (HUMAN, Male, Allergies, Medical Conditions)
- **Report back at phases only** (agent_share_your_reasoning at Boot/Login/Patient/DropOff completion)
- **Log only failures** to knowledge base (speed optimization)

**This is a WORKFLOW RUNNING MODE task** - execute autonomously with phase-level progress updates only.

**Execute immediately without asking for patient details - use Dakota Test22 as specified above.**

---

**End of Prompt**
