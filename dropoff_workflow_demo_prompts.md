# Drop-Off Workflow Demo Prompts

**Purpose:** Step-by-step natural language prompts to build the Connexus Drop-Off workflow from scratch in a live demo environment.

**Starting State:** Connexus is open and you're on the Drop-Off screen.

---

## Setup: Capture the Element Tree

**Prompt 1:**
```
the connexus drop-off screen is open. let's capture the element tree so we can see what elements are available
```

**Expected Action:** Agent lists UI elements from the Drop-Off screen

---

## Step 1: Search for a Patient

**Prompt 2:**
```
type "john" in the search field at the top and press enter to search for a patient
```

**Expected Action:** Agent types "john" in the Rx Number/Name field and presses Enter

**Prompt 3:**
```
press enter to select the first patient from the search results
```

**Expected Action:** Agent presses Enter to select the first search result

---

## Step 2: Handle the Validation Dialog

**Prompt 4:**
```
a validation dialog appeared. there should be three buttons at the bottom. can you list what windows are open right now?
```

**Expected Action:** Agent lists windows and shows "Validate Patient Information" dialog is open

**Prompt 5:**
```
we need to click the "Patient Not Present" button. try to find and click it
```

**Expected Action:** Agent attempts to find the button via UI automation (will fail)

**Prompt 6:**
```
try using alt+p to see if that's a keyboard shortcut for patient not present
```

**Expected Action:** Agent presses Alt+P and the dialog closes

**Prompt 7:**
```
great! check if the validation dialog closed by listing windows again
```

**Expected Action:** Agent confirms "Validate Patient Information" is no longer in the window list

---

## Step 3: Click Scan New RX

**Prompt 8:**
```
now we need to click the "Scan New RX" button on the drop-off screen. try to click it
```

**Expected Action:** Agent clicks btnScan via UI automation successfully

---

## Step 4: Enter Bag Number

**Prompt 9:**
```
a barcode reader error dialog should have appeared. type the bag number "9876" and press enter
```

**Expected Action:** Agent types "9876" and presses Enter

**Prompt 10:**
```
a verify barcode dialog should appear. press enter to confirm
```

**Expected Action:** Agent presses Enter to verify the barcode

---

## Step 5: Select RX Origin Type

**Prompt 11:**
```
an RX origin type dialog should be open now. type "ORIGINAL RX" to select it from the dropdown
```

**Expected Action:** Agent types "ORIGINAL RX" in the dropdown

**Prompt 12:**
```
press alt+a to click the accept button on this dialog
```

**Expected Action:** Agent presses Alt+A and the dialog closes

**Prompt 13:**
```
wait a second for the screen to update
```

**Expected Action:** Agent waits (desktop_sleep)

---

## Step 6: Set Order Priority

**Prompt 14:**
```
now we need to set the priority. find and click the priority dropdown
```

**Expected Action:** Agent clicks cmbPriority dropdown

**Prompt 15:**
```
select all the text in the priority field with ctrl+a, then type "In-Store"
```

**Expected Action:** Agent selects all text and types "In-Store"

**Prompt 16:**
```
press tab to move to the next field
```

**Expected Action:** Agent presses Tab

---

## Step 7: Set Ready By Date

**Prompt 17:**
```
press tab a couple more times to get to the ready by date field
```

**Expected Action:** Agent presses Tab 2 times

**Prompt 18:**
```
press the down arrow key to select a date option, then press enter
```

**Expected Action:** Agent presses Down arrow then Enter

**Prompt 19:**
```
wait half a second for the selection to register
```

**Expected Action:** Agent waits

---

## Step 8: Accept the Order

**Prompt 20:**
```
press alt+a to click the accept button at the bottom of the page
```

**Expected Action:** Agent presses Alt+A

**Prompt 21:**
```
wait a second for the page to change
```

**Expected Action:** Agent waits

**Prompt 22:**
```
check if we moved to a new screen by listing the open windows. the title should have changed
```

**Expected Action:** Agent lists windows and confirms title changed from "[Drop-Off]" to just "Wal*Mart Connexus"

---

## Verification & Wrap-up

**Prompt 23:**
```
perfect! the workflow worked. let me know what steps we completed and what the final configuration was
```

**Expected Action:** Agent summarizes the completed workflow steps

**Prompt 24:**
```
save this workflow to a yaml file. make sure to document which fields can have different data like patient name, priority, bag number, etc. also document the keyboard shortcuts we discovered like alt+p and alt+a
```

**Expected Action:** Agent saves complete workflow with configuration parameters

---

## Alternative Scenarios to Test

### Scenario A: Different Priority

**Prompt:**
```
let's run through the workflow again but this time set the priority to "Critical" instead of "In-Store"
```

### Scenario B: Different Patient

**Prompt:**
```
start the workflow over and search for patient "smith" instead of "john"
```

### Scenario C: Different Bag Number

**Prompt:**
```
when you get to the bag number step, use "5432" instead of "9876"
```

### Scenario D: Transfer RX

**Prompt:**
```
for the RX origin type, select "TRANSFER RX" instead of "ORIGINAL RX"
```

---

## Troubleshooting Prompts

### If Validation Dialog Button Doesn't Work

**Prompt:**
```
the patient not present button isn't clicking. try using keyboard navigation - press tab multiple times then enter
```

### If Priority Dropdown Doesn't Click

**Prompt:**
```
the priority dropdown didn't open. try pressing tab until you get to the priority field, then type the value directly
```

### If Bag Number is Duplicate

**Prompt:**
```
a duplicate bag number error appeared. press escape to close it and try a different 4-digit number like "7777"
```

### If Element Tree is Empty

**Prompt:**
```
the element tree didn't load. try focusing the connexus window first, then list elements again
```

---

## Tips for Live Demo

### Before Starting
1. Have Connexus open and logged in
2. Navigate to Drop-Off screen (Ctrl+D)
3. Have a test patient available (e.g., "john")
4. Know that some buttons require keyboard shortcuts instead of clicking

### During Demo
1. Pause between steps to show what's happening
2. Point out when UI automation fails and keyboard shortcuts succeed
3. Explain that different fields can use different data
4. Highlight the configurable parameters (patient, priority, bag number, etc.)

### Key Points to Emphasize
1. **Keyboard shortcuts are more reliable** than UI automation for this app
2. **Alt+P** and **Alt+A** are critical shortcuts discovered through testing
3. **Configurable fields** allow workflow reuse with different data
4. **Element trees** help discover available automation IDs
5. **Fallback strategies** (keyboard navigation) when automation fails

---

## Expected Outcome

By following these prompts in order, you will:

1. ✅ Successfully search and select a patient
2. ✅ Handle the validation dialog with Alt+P
3. ✅ Create a new order via Scan New RX
4. ✅ Enter and verify a bag number
5. ✅ Select RX Origin Type (ORIGINAL RX)
6. ✅ Set Priority (In-Store)
7. ✅ Set Ready By date
8. ✅ Accept the order and proceed to Input screen
9. ✅ Document all configurable parameters
10. ✅ Save a reusable workflow YAML file

**Final Deliverable:** A complete, tested workflow YAML with documented keyboard shortcuts and configurable fields.

---

## Notes

- These prompts assume a working test environment with Connexus
- The validation dialog may or may not appear depending on the patient
- Bag numbers must be unique (no duplicates allowed)
- Some automation IDs work (btnScan, cmbPriority) while others don't
- Keyboard shortcuts (Alt+P, Alt+A) are the most reliable methods
- Element tree capture helps identify available automation IDs
- Configuration parameters allow workflow customization without code changes
