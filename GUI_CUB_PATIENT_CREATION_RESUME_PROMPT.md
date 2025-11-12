# GUI Cub Resume Prompt - Connexus New Patient Workflow (Windows)

## Context
- App: Connexus (Wal*Mart Connexus)
- Workflow: New Patient creation (Patient Maintenance)
- Current status: Completed a functional run using Keyboard + OCR
- Next goal: Resume and harden workflow with new element value/focus tools

## Preconditions
- Connexus running and logged in
- Main window title: "Wal*Mart Connexus" (or "Connexus")
- Starting point: Patient Search dialog OR Patient Maintenance, depending on test phase

## Hotkeys & Actions
- Open Patient Search: Ctrl+Shift+P
- Host Look Up: Alt+H (after Zip entered)
- New… (open Patient Maintenance): Alt+N
- Save & Close (Accept): Alt+A (enabled when required fields are filled)

## Patient Maintenance - Required Fields (Minimum for HUMAN)
1. Patient Type: HUMAN
   - Current method: OCR - find "Human" text, click radio to the left
   - Planned: UIA locator + value verification
2. Gender: Male (radio group)
3. Address Line 1: 123 Main Street
4. City: Bentonville
5. State: AR
6. Allergies: No
7. Medical Conditions: No

## Validation Prompt
- "Patient Phone Number has not been entered. Do you want to add?" → Select No

## Known Issues to Address
- Patient Type (HUMAN) radio has no tab index → add a robust locator fallback
- UIA windows_list_elements attaches inconsistently → use process-based attach
- Verify field values post-typing using new tools:
  - windows_get_focused_element(pid, window_title)
  - windows_get_element_value(pid, window_title, control_type="Edit", name="Field Label")

## Resume Steps
1. Focus Connexus
2. Navigate to Patient Search → fill fields → Alt+H → Alt+N
3. On Patient Maintenance:
   - Select HUMAN (OCR radio click)
   - Fill Gender, Address, City, State
   - Set Allergies = No, Medical Conditions = No
   - Alt+A to Save & Close; handle phone prompt (No)
4. Verify save success (TBD: add positive cue)

## Logging & KB Updates
- Append timings, success indicators, and element locators to:
  - ~/.code_puppy/agents/gui-cub/connexus_knowledge_base.md
  - GUI_CUB_CONNEXUS_WORKFLOWS_KB.md
- Store workflow YAML at:
  - connexus_locator_library/workflows/PatientCreation.yaml

## Next Enhancements
- Replace OCR clicks with UIA fuzzy locators
- Implement mnemonics for Search Now (if available)
- Add robust verification after each field entry using new get_element_value
