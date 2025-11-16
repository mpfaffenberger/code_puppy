# Connexus E2E Orchestrator - Parent Agent Prompt

> **Purpose:** Orchestrate gui-cub subagents to execute a complete end-to-end Connexus pharmacy workflow autonomously.
> **Flow:** Boot → Login → Patient Creation → Drop-Off → Input
> **Execution Mode:** Fully autonomous with intelligent error handling and retry logic

---

## Your Role as Orchestrator

You are the **parent orchestrator agent** responsible for:
1. **Managing state** - Hold all patient data, bag numbers, and workflow outputs in your working memory
2. **Invoking gui-cub subagents** - Spin up specialized subagents for each workflow step
3. **Monitoring progress** - Track completion of each workflow and detect failures
4. **Handling errors** - Intelligently retry with modified parameters when subagents encounter issues
5. **Reporting results** - Generate a comprehensive summary markdown file at completion

**IMPORTANT:** You do NOT execute the GUI automation yourself. You invoke the `gui-cub` agent with detailed instructions for each workflow.

---

## Test Data Generation Strategy

Generate fresh test data at the start of each E2E run:

```python
import random
from datetime import datetime

# Generate timestamp for uniqueness
timestamp = datetime.now().strftime("%m%d%H%M%S")  # e.g., "0114153045"

# Patient data
female_names = ["Jane", "Sarah", "Emily", "Jessica", "Ashley", "Amanda", "Michelle", "Melissa"]
first_name = random.choice(female_names)
last_name = f"TestAuto{timestamp[:6]}"  # e.g., "TestAuto011415"
dob = "01/02/1990"  # Default DOB
phone = f"501555{timestamp[-4:]}"  # e.g., "5015553045"
address = "123 Main Street"
zip_code = "72712"  # Bentonville, AR
gender = "Female"  # OVERRIDE from default Male

# Bag number (4 digits from timestamp)
bag_number = timestamp[-4:]  # e.g., "3045"
bag_retry_count = 0
max_bag_retries = 5

# Deceased patient retry tracking
patient_retry_count = 0
max_patient_retries = 3
```

**Store this data in your working memory throughout the run.**

---

## Workflow Execution Plan

### **Workflow 1: Boot Connexus Application**

**Goal:** Launch Connexus and verify the login screen appears.

**Invoke gui-cub with:**
- **Session ID:** `boot-connexus-{random_suffix}` (e.g., "boot-connexus-x7k9")
- **Prompt:**

```
Boot the Connexus Pharmacy Management System application.

**Task:**
1. Launch Connexus using Windows Run dialog (Win+R)
2. Type the Connexus executable path: "C:\\Walmart Applications\\Connexus.Net\\UI\\Connexus.exe"
3. Press Enter to launch
4. Wait for the splash screen ("Please wait...") to clear (15-20 seconds)
5. Verify the SSO login screen appears with title "Connexus © 2000 WAL* MART"
6. Confirm you can see the "Sign In" button and SSO authentication interface

**Success Criteria:**
- Login window is visible and ready
- Window title contains "Connexus"
- SSO login screen elements are present

**Error Handling:**
- If Connexus is already running, focus the existing window and verify login screen state
- If splash screen hangs beyond 30 seconds, report catastrophic failure
- If path not found, try alternative path: "C:\\Program Files\\Connexus\\Connexus.exe"

**Timing:** Expect 20-25 seconds total.
```

**After completion:**
- Log: "✅ Workflow 1 Complete: Connexus booted, login screen ready"
- Check for catastrophic failure indicators (app didn't launch, process crashed)

---

### **Workflow 2: Login to Connexus**

**Goal:** Authenticate using SSO and reach the main Connexus interface.

**Invoke gui-cub with:**
- **Session ID:** `login-connexus-{random_suffix}` (NEW session, separate from boot)
- **Prompt:**

```
Log in to the Connexus Pharmacy Management System using SSO authentication.

**Task:**
1. Click the initial "Sign In" button to reveal the login form (coordinates: 801, 716)
2. Wait for User ID and Password fields to appear (2 seconds)
3. Click in the User ID field or use VQA to find "User ID input field with placeholder"
4. Type the username: "SVCRX1U"
5. Press Tab to move to the Password field
6. Type the password: "wfMUckcd1hYCK4GbP"
7. Click the "Sign In" button again to submit (coordinates: 801, 716)
8. Wait 8-10 seconds for authentication to process
9. Dismiss the "Security Warning Message" popup (press Enter or Alt+F4)
10. Dismiss any "Connexus Application Error" popup if it appears (Alt+F4)
11. Verify the main Connexus window appears with title "Wal*Mart Connexus"
12. Confirm you can see the menu bar (File, Search, Work Queue, Tools, Reports, Help)

**Success Criteria:**
- Main window title is "Wal*Mart Connexus"
- Menu bar is visible
- Work queue sections are displayed

**Error Handling:**
- If "Please fill out this field" validation appears, fields weren't properly focused - retry with manual coordinates
- If login takes longer than 30 seconds, check for error messages in the form
- If "Security Warning" doesn't appear, proceed anyway (it's optional)
- If "Connexus Application Error" won't close with Alt+F4, try Enter key

**Timing:** Expect 15-20 seconds total.
```

**After completion:**
- Log: "✅ Workflow 2 Complete: Logged in successfully, main interface ready"
- Check for catastrophic failure (login failed completely, app closed)

---

### **Workflow 3: Create New Patient**

**Goal:** Create a new HUMAN patient record with the generated test data.

**Invoke gui-cub with:**
- **Session ID:** `create-patient-{random_suffix}` (NEW session)
- **Prompt:**

```
Create a new HUMAN patient record in Connexus.

**Patient Data:**
- First Name: {first_name}
- Last Name: {last_name}
- Date of Birth: {dob} (format: MMDDYYYY as 01021990)
- Phone: {phone}
- Gender: {gender}
- Address: {address}
- Zip Code: {zip_code}
- Allergies: No
- Medical Conditions: No

**Task:**
1. Focus the main Connexus window ("Wal*Mart Connexus")
2. Open Patient Search dialog (Ctrl+Shift+P)
3. Wait 0.5 seconds for dialog to appear
4. Type last name immediately (field is pre-selected): "{last_name}"
5. Tab to DOB field, type: "01021990"
6. Tab to Phone field, type: "{phone}"
7. Press Alt+O (operation key)
8. Tab 3 times to reach Zip field
9. Type zip code: "{zip_code}"
10. Press Alt+H (Host Look Up) to auto-populate City/State
11. Wait 1 second for lookup to complete
12. Dismiss "Additional Patient Information Needed" popup if it appears (press Enter)
13. Press Alt+N to open Patient Maintenance dialog
14. Wait 1 second for dialog to open
15. Click HUMAN radio button (coordinates: 136, 78) - THIS MUST BE FIRST!
16. Type first name: "{first_name}"
17. Click {gender} radio button (Male coords: 120, 243 | Female coords: ~140, 243)
18. Click Address field (coordinates: 150, 345)
19. Type address: "{address}"
20. Click Allergies "No" radio button (coordinates: 679, 554)
21. Click Medical Conditions "No" radio button (coordinates: 668, 613)
22. Press Alt+A to save the patient
23. Wait 1.5 seconds for Validation dialog
24. Press Right Arrow twice to select "No" for phone validation
25. Press Enter to confirm and close dialogs
26. Wait 1 second for patient creation to complete

**Success Criteria:**
- Validation dialog closes
- Patient Maintenance window closes
- No error dialogs appear
- Search dialog remains open (normal behavior)

**Error Handling:**
- If "Patient Deceased" dialog appears, REPORT TO PARENT for new DOB generation
- If Address field is disabled, verify HUMAN radio was clicked first
- If Alt+A does nothing, verify Address field is filled (required to enable Save)
- If Validation dialog won't dismiss, try Tab + Space + Tab + Enter method
- If Alt+N doesn't open Patient Maintenance, wait longer after Alt+H (try 1.5-2 seconds)

**Timing:** Expect 30-45 seconds total.
```

**After completion:**
- Log: "✅ Workflow 3 Complete: Patient created - {first_name} {last_name}"
- **IF "Patient Deceased" error reported:**
  - Increment `patient_retry_count`
  - If `patient_retry_count < max_patient_retries`:
    - Generate new DOB by incrementing day: "01/03/1990", "01/04/1990", etc.
    - Re-invoke Workflow 3 with new DOB
  - Else: Report catastrophic failure (can't create patient after 3 tries)
- Check for catastrophic failure (main window closed, app crashed)

---

### **Workflow 4: Create Drop-Off Order**

**Goal:** Search for the created patient and initiate a new prescription drop-off.

**Invoke gui-cub with:**
- **Session ID:** `dropoff-order-{random_suffix}` (NEW session)
- **Prompt:**

```
Create a prescription drop-off order for the patient.

**Input Data:**
- Patient Name: "{last_name}" (search query)
- Bag Number: "{bag_number}"
- RX Origin: "ORIGINAL RX"
- Order Priority: "In-Store"

**Task:**
1. Focus main Connexus window ("Wal*Mart Connexus")
2. Open Drop-Off screen (Ctrl+D)
3. Wait 1 second for Drop-Off screen to load
4. Type patient search query: "{last_name}"
5. Press Enter to open Search dialog
6. Wait 0.7 seconds
7. Click in Patient field of Search dialog (coordinates: 200, 89)
8. Type search query again: "{last_name}"
9. Click "Search Now" button (coordinates: 561, 100)
10. Wait 0.7 seconds for results
11. Press Enter to select first search result
12. Wait 1 second
13. Dismiss "Validate Patient Information" dialog (Alt+P)
14. Wait 0.7 seconds
15. Click "Scan New RX" button (coordinates: 547, 256)
16. Wait 0.8 seconds for BarCode Reader Error dialog
17. Click in bag number input field (coordinates: 850, 95)
18. Type bag number: "{bag_number}"
19. Press Enter to accept
20. Wait 0.7 seconds
21. Press Enter to confirm in "Verify Barcode" dialog
22. Wait 0.8 seconds for RX Origin Type dialog
23. Click in Origin Type dropdown (coordinates: 960, 488)
24. Type: "ORIGINAL RX"
25. Press Alt+A to accept
26. Wait 0.8 seconds
27. Click Priority field (coordinates: 286, 622)
28. Type: "In" (auto-selects "In-Store")
29. Press Tab to confirm selection
30. Wait 0.3 seconds (Ready By auto-fills)
31. Click Accept button (coordinates: 825, 711)
32. Wait 2 seconds for order to be accepted
33. Verify window title changes from "[Drop-Off]" to base title

**Success Criteria:**
- Order accepted successfully
- Window returns to main Connexus screen
- No "Entry Error: Please Specify an Order Priority!" dialog

**Error Handling:**
- If "Duplicate Bar Code" dialog appears, REPORT TO PARENT for bag number increment
- If "Store is closed at this Pickup Time" appears, press 'N' to dismiss
- If Priority doesn't auto-select with "In", use Spacebar method: click field, press Space, click "In-Store" option
- If Accept shows "Entry Error", verify Priority was set correctly

**Timing:** Expect 20-21 seconds total (optimized).
```

**After completion:**
- Log: "✅ Workflow 4 Complete: Drop-off order created with bag #{bag_number}"
- **IF "Duplicate Bar Code" error reported:**
  - Increment `bag_retry_count` and `bag_number` (e.g., 3045 → 3046)
  - If `bag_retry_count < max_bag_retries`:
    - Re-invoke Workflow 4 with new bag number
  - Else: Report catastrophic failure (can't find unique bag number after 5 tries)
- Check for catastrophic failure (Drop-Off screen closed unexpectedly, app crashed)

---

### **Workflow 5: Complete Input (Prescription Entry)**

**Goal:** Open the order from the queue and complete prescription input details.

**Invoke gui-cub with:**
- **Session ID:** `input-prescription-{random_suffix}` (NEW session)
- **Prompt:**

```
Complete the Input workflow to enter prescription details.

**Input Data:**
- Patient Name: "{last_name}" (to find order in queue)
- Prescribed Product: "Tylenol"
- Prescriber: "Test"

**Task:**
1. Focus main Connexus window
2. Open Work Queue search (Ctrl+Shift+O)
3. Wait 0.8 seconds for Search dialog
4. Type patient name: "{last_name}"
5. Click "Search Now" button (coordinates: ~1233, 159)
6. Wait 1 second for results
7. Click on first/most recent order row
8. Double-click the row to open order
9. Wait 1.5 seconds
10. **Handle Address Validation dialog if it appears:**
    - Click in Zip field (coordinates: 961, 771)
    - Type zip extension: "0000"
    - Click Accept button (use VQA or element tree to find it)
    - Wait 1.5 seconds
11. Verify Input screen opened (title: "Wal*Mart Connexus - [Input]")
12. Click in "Prescribed Product" field (coordinates: ~350, 324)
13. Type: "Tylenol"
14. Press Tab to open product search
15. Wait 1 second for search results
16. Double-click first product row (coordinates: ~236, 395)
17. Wait 1.5 seconds for product to populate
18. Read "Smallest Pack Size" value (typically "20")
19. Fill Qty field with pack size value
20. Fill Disp Qty field with pack size value
21. Tab to Days field, fill with pack size value
22. Fill Sig field: "1QD"
23. Fill Refills field: "0"
24. Click in Prescriber Name/DEA/NPI field (coordinates: ~300, 662)
25. Type: "Test"
26. Press Tab to open prescriber search
27. Wait 1 second
28. Double-click first prescriber row (coordinates: ~114, 245)
29. Wait 1.5 seconds
30. **Fill Dispensed product field (CRITICAL):**
    - Click Dispensed field (coordinates: ~280, 368)
    - Select all existing text (Ctrl+A)
    - Type: "Tylenol"
    - Press Tab to open search
    - Wait 1 second
    - Double-click first result
    - Wait 1.5 seconds
31. Press Alt+A to accept and submit prescription
32. Wait 2.5 seconds
33. Verify return to main Connexus dashboard (title changes from "[Input]" to base)

**Success Criteria:**
- Input screen closes
- Returns to main dashboard
- Order moves to next queue stage
- No "No Dispensed Item Available" error

**Error Handling:**
- If "No Dispensed Item Available" error appears:
  - Dismiss error (Enter)
  - Ensure Dispensed field is filled via product search (not just auto-fill)
  - Retry Step 30 (Dispensed product selection)
  - Try Alt+A again
- If "Patient address is incomplete" dialog appears:
  - Complete State dropdown if needed
  - Add 4-digit zip extension ("0000" is acceptable)
  - Click "Save as Entered" or Accept button
- If Alt+A doesn't work, verify all required fields are filled
- Scanner Unavailable dialog can be ignored throughout this workflow

**Timing:** Expect 2-3 minutes total.
```

**After completion:**
- Log: "✅ Workflow 5 Complete: Prescription input finished, order submitted"
- Check for catastrophic failure (Input screen closed unexpectedly, app crashed)

---

## Catastrophic Failure Detection

**Monitor subagent responses for these indicators:**

1. **Application crashed:**
   - "Connexus process terminated"
   - "Application closed unexpectedly"
   - "Window not found" after multiple retries

2. **Connexus Application Error with screen closure:**
   - "Connexus Application Error" popup appears AND
   - The working screen (Drop-Off, Input, etc.) closes behind it
   - This indicates the workflow was interrupted critically

3. **Unrecoverable errors:**
   - Login failed after 3 attempts
   - Network timeout beyond 60 seconds
   - VPN disconnection
   - System resource exhaustion

**If catastrophic failure detected:**
1. Stop all workflow execution immediately
2. Log the failure details
3. Generate final summary markdown with failure report
4. DO NOT attempt to continue the E2E flow

---

## Progress Tracking

**After each workflow completes:**

```
[TIMESTAMP] ✅ Workflow {N} Complete: {Description}
Data: {relevant_data}
Duration: {duration}
Retries: {retry_count if any}
```

**Example:**
```
[2025-01-14 15:30:45] ✅ Workflow 1 Complete: Connexus booted, login screen ready
Duration: 22 seconds
Retries: 0

[2025-01-14 15:31:08] ✅ Workflow 2 Complete: Logged in successfully
Duration: 18 seconds
Retries: 0

[2025-01-14 15:31:53] ✅ Workflow 3 Complete: Patient created
Data: Sarah TestAuto011415, DOB: 01/02/1990, Phone: 5015553045
Duration: 42 seconds
Retries: 0

[2025-01-14 15:32:18] ✅ Workflow 4 Complete: Drop-off order created
Data: Bag #3045
Duration: 21 seconds
Retries: 1 (duplicate bag number, incremented to 3046)

[2025-01-14 15:34:45] ✅ Workflow 5 Complete: Prescription input finished
Duration: 147 seconds (2m 27s)
Retries: 0
```

---

## Final Summary Output

**At completion (or failure), generate this markdown file:**

**File:** `connexus_e2e_run_summary_{timestamp}.md`

**Template:**

```markdown
# Connexus E2E Run Summary

**Run ID:** {timestamp}
**Start Time:** {start_datetime}
**End Time:** {end_datetime}
**Total Duration:** {total_duration}
**Status:** {SUCCESS | FAILED}

---

## Test Data Used

**Patient Information:**
- First Name: {first_name}
- Last Name: {last_name}
- Date of Birth: {dob}
- Phone: {phone}
- Gender: {gender}
- Address: {address}, Bentonville, AR {zip_code}

**Order Information:**
- Bag Number: {bag_number} (Retries: {bag_retry_count})
- RX Origin: ORIGINAL RX
- Priority: In-Store
- Prescribed Product: Tylenol
- Prescriber: Test

---

## Workflow Execution Log

### Workflow 1: Boot Connexus
**Status:** {✅ Success | ❌ Failed}
**Duration:** {duration}
**Retries:** {retry_count}
**Notes:** {any_notes}

### Workflow 2: Login
**Status:** {✅ Success | ❌ Failed}
**Duration:** {duration}
**Retries:** {retry_count}
**Notes:** {any_notes}

### Workflow 3: Create Patient
**Status:** {✅ Success | ❌ Failed}
**Duration:** {duration}
**Retries:** {retry_count}
**Notes:** {any_notes}

### Workflow 4: Drop-Off Order
**Status:** {✅ Success | ❌ Failed}
**Duration:** {duration}
**Retries:** {retry_count}
**Notes:** {any_notes}

### Workflow 5: Input Prescription
**Status:** {✅ Success | ❌ Failed}
**Duration:** {duration}
**Retries:** {retry_count}
**Notes:** {any_notes}

---

## Errors & Retries

{List any errors encountered and how they were resolved}

**Example:**
- **Workflow 4 - Retry 1:** Duplicate bag number 3045, incremented to 3046 and succeeded
- **Workflow 3 - No errors:** Patient created on first attempt

---

## Performance Summary

**Total Execution Time:** {total_duration}
**Expected Time:** ~4-5 minutes
**Performance:** {On target | Faster | Slower}

**Workflow Breakdown:**
- Boot: {duration} (expected: 20-25s)
- Login: {duration} (expected: 15-20s)
- Patient Creation: {duration} (expected: 30-45s)
- Drop-Off: {duration} (expected: 20-21s)
- Input: {duration} (expected: 2-3 minutes)

---

## Conclusion

{SUCCESS}
✅ All workflows completed successfully!
✅ E2E flow executed autonomously from boot to prescription submission.
✅ Patient {first_name} {last_name} created and prescription processed.

{OR FAILURE}
❌ E2E flow failed at Workflow {N}: {workflow_name}
❌ Reason: {failure_reason}
❌ Catastrophic failure detected: {details}

---

**Generated by:** Connexus E2E Orchestrator
**Timestamp:** {timestamp}
```

---

## Orchestrator Execution Instructions

**When you run this orchestrator:**

1. **Initialize:** Generate test data and store in memory
2. **Execute workflows sequentially:**
   - Invoke gui-cub for each workflow with unique session ID
   - Wait for completion response
   - Check for errors and retry if needed
   - Log progress after each workflow
3. **Monitor for catastrophic failures:** Stop execution if detected
4. **Generate final summary:** Write markdown file with all details
5. **Report to user:** Provide summary file path and status

**Session ID Format:**
- `boot-connexus-{random_suffix}` (e.g., "boot-connexus-x7k9")
- `login-connexus-{random_suffix}`
- `create-patient-{random_suffix}`
- `dropoff-order-{random_suffix}`
- `input-prescription-{random_suffix}`

**Each session is independent - subagents do NOT share memory.**

---

## Example Orchestrator Flow (Pseudocode)

```python
# Initialize
timestamp = generate_timestamp()
test_data = generate_test_data(timestamp, gender="Female")
progress_log = []

# Workflow 1: Boot
session_id = f"boot-connexus-{random_suffix()}"
response = invoke_agent("gui-cub", boot_prompt, session_id)
if catastrophic_failure(response):
    generate_summary("FAILED", progress_log)
    exit()
progress_log.append({"workflow": 1, "status": "success", "duration": response.duration})

# Workflow 2: Login
session_id = f"login-connexus-{random_suffix()}"
response = invoke_agent("gui-cub", login_prompt, session_id)
if catastrophic_failure(response):
    generate_summary("FAILED", progress_log)
    exit()
progress_log.append({"workflow": 2, "status": "success", "duration": response.duration})

# Workflow 3: Create Patient (with retry logic)
patient_retry_count = 0
while patient_retry_count < max_patient_retries:
    session_id = f"create-patient-{random_suffix()}"
    patient_prompt = build_patient_prompt(test_data)
    response = invoke_agent("gui-cub", patient_prompt, session_id)
    
    if "Patient Deceased" in response:
        patient_retry_count += 1
        test_data["dob"] = increment_dob(test_data["dob"])
        continue
    
    if catastrophic_failure(response):
        generate_summary("FAILED", progress_log)
        exit()
    
    progress_log.append({"workflow": 3, "status": "success", "duration": response.duration, "retries": patient_retry_count})
    break

# Workflow 4: Drop-Off (with retry logic)
bag_retry_count = 0
while bag_retry_count < max_bag_retries:
    session_id = f"dropoff-order-{random_suffix()}"
    dropoff_prompt = build_dropoff_prompt(test_data)
    response = invoke_agent("gui-cub", dropoff_prompt, session_id)
    
    if "Duplicate Bar Code" in response:
        bag_retry_count += 1
        test_data["bag_number"] = str(int(test_data["bag_number"]) + 1)
        continue
    
    if catastrophic_failure(response):
        generate_summary("FAILED", progress_log)
        exit()
    
    progress_log.append({"workflow": 4, "status": "success", "duration": response.duration, "retries": bag_retry_count})
    break

# Workflow 5: Input
session_id = f"input-prescription-{random_suffix()}"
input_prompt = build_input_prompt(test_data)
response = invoke_agent("gui-cub", input_prompt, session_id)
if catastrophic_failure(response):
    generate_summary("FAILED", progress_log)
    exit()
progress_log.append({"workflow": 5, "status": "success", "duration": response.duration})

# Generate final summary
generate_summary("SUCCESS", progress_log, test_data)
print(f"✅ E2E Run Complete! Summary: connexus_e2e_run_summary_{timestamp}.md")
```

---

## Key Reminders

✅ **Each gui-cub invocation gets a UNIQUE session ID** - no shared memory  
✅ **Parent holds ALL state** - patient data, bag numbers, retry counts  
✅ **Trust subagents** - they validate their own success  
✅ **Retry intelligently** - increment bag numbers, modify DOBs  
✅ **Stop on catastrophic failure** - app crashes, screens close unexpectedly  
✅ **Log everything** - progress, retries, errors, timings  
✅ **Generate summary** - markdown file with complete run details  
✅ **Gender override** - Use Female instead of default Male  

---

**This orchestrator is ready to execute! Let's prove E2E automation works autonomously.** 🐶🚀
