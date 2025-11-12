# Resume: Connexus Workflow Modernization

**Session Date:** 2025-01-15  
**Status:** In Progress - Login Workflow Next  
**Agent:** GUI-Cub (Desktop Automation)

---

## 📋 CONTEXT

We are modernizing old YAML-based Connexus automation workflows into modern GUI-Cub Markdown guidance format.

**Directory:** `connexus_locator_library/`

**Old Workflows (6 total):**
- ✅ BootConnexus.yaml - COMPLETED & MODERNIZED
- ❌ LoginConnexus.yaml - IN PROGRESS (next)
- ❌ PatientSearch.yaml - NOT STARTED
- ❌ PatientCreation.yaml - NOT STARTED
- ❌ DropOff.yaml - NOT STARTED
- Reference: OrderIntake.yaml (element locator library)

---

## ✅ COMPLETED WORK

### 1. Boot Connexus Workflow ✅
- **Saved to:** `~/.code_puppy/agents/gui_cub/workflows/boot_connexus.md`
- **Test Date:** 2025-01-15
- **Status:** ✅ Tested and working
- **Method:** Win+R → Type path → Enter → Wait 20s → Verify login screen

**Key Discovery:**
- ⚠️ **CRITICAL:** Login screen has COMPLETELY CHANGED from old YAML
- **Old:** Traditional username/password fields with Accept button
- **New:** Modern SSO (Single Sign-On) authentication screen
- **Elements visible:** "Sign In" button, Country/Region selector, Location: Homeoffice

### 2. Login Connexus Workflow ✅
- **Saved to:** `~/.code_puppy/agents/gui_cub/workflows/login_connexus.md`
- **Test Date:** 2025-01-15
- **Status:** ✅ Tested and working
- **Credentials Used:** SVCRX1U / wfMUckcd1hYCK4GbP
- **Login Time:** ~15-20 seconds (vs 50+ seconds in old YAML)

**Key Discoveries:**
- **Embedded Chrome browser** for SSO authentication (Chrome_WidgetWin_0)
- Click "Sign In" → Reveals User ID/Password fields
- Fields require **OCR/VQA** (no accessibility tree)
- Tab navigation works between fields
- Popup sequence: Security Warning → (optional) Application Error
- Alt+F4 most reliable for closing error dialogs
- Main window title: "Wal*Mart Connexus"

**What Changed from Old YAML:**
- ❌ No more native WinForms controls (txtUserName, txtPassword, chkHOUser)
- ❌ No more "Accept" button (now "Sign In")
- ❌ No more HomeOffice checkbox (pre-set in Location dropdown)
- ✅ Faster login (15-20s vs 50s)
- ✅ Modern web-based SSO interface
- ⚠️ Requires VQA/OCR instead of UI Automation

### 3. Patient Creation Workflow ✅
- **Saved to:** `~/.code_puppy/agents/gui_cub/workflows/patient_creation.md`
- **Test Date:** 2025-01-15
- **Status:** ✅ Tested and working
- **Patient Created:** John Testerson, DOB 01/02/1990
- **Total Time:** ~30-45 seconds
- **Comprehensive Field Inventory:** General Information tab fully documented

**Key Discoveries:**
- **CRITICAL:** HUMAN patient type MUST be selected FIRST (enables Address field)
- **Search dialog focus:** Type immediately after Ctrl+Shift+P (don't change focus!)
- **Validation dialog:** "No" radio has no tab index - use Right Arrow x2
- **Alt+N disabled** until Host Lookup (Alt+H) completes (~0.6-1.0s wait)
- **Address field required** to enable Save button (Alt+A)
- **Radio buttons:** No automation_ids - use OCR + manual coordinates
- **windows_get_focused_element(pid)** works for field verification

**Field Inventory Captured:**
- 9 major sections documented on General Information tab
- 50+ individual fields cataloged with automation_ids (where available)
- Radio button coordinates tested and confirmed
- 4 additional tabs identified (Profile/Other, Allergy/Medical Conditions, Clinical Services, Personal Representative)

**What Changed from Old YAML:**
- ✅ Same keyboard-first approach still works
- ✅ automation_ids still accessible via windows_get_focused_element(pid)
- ⚠️ Radio buttons still require OCR/manual coordinates (no UI Automation)
- ✅ Validation dialog handling unchanged (arrow keys work)
- ✅ Host Lookup still auto-populates City/State from Zip

---

## 🎯 CURRENT STATE

**Connexus Status:** LOGGED IN and main application ready
- Window title: "Wal*Mart Connexus"
- Successfully authenticated via SSO
- PID: 21748
- User: SVCRX1U
- Ready for patient workflow testing

---

## 🚀 NEXT TASK

Workflows remaining to modernize:
1. **Patient Search** - PatientSearch.yaml
2. **Drop-Off** - DropOff.yaml

Or explore additional tabs in Patient Creation:
- Profile/Other tab
- Allergy/Medical Conditions tab (detailed)
- Clinical Services tab
- Personal Representative Information tab

---

## 🛠️ APPROACH

Follow the same pattern we used for Boot Connexus:
1. Read old YAML for reference: `connexus_locator_library/workflows/LoginConnexus.yaml`
2. Test the actual login flow interactively (ask user for credentials if needed)
3. Document what works, what doesn't, and what changed
4. Save workflow AFTER confirming it works
5. Use modern Markdown guidance format (goals, strategies, alternatives)

---

## 💡 KEY PRINCIPLES

- ✅ Document AFTER testing, not before
- ✅ Include what worked AND what didn't work
- ✅ Use Markdown format (readable guidance, not rigid scripts)
- ✅ Tool priority: Keyboard → Accessibility → OCR → VQA
- ✅ Focus on WHAT and WHY, not just HOW
- ✅ Multiple strategies with intelligent adaptation

---

## ✅ ANSWERED QUESTION

**What happens when you click "Sign In" on the SSO login screen?**

**Answer:** The SSO screen reveals username/password fields IN THE SAME WINDOW using an embedded Chrome browser!

**Technical Details:**
- Embedded Chromium browser (Chrome_WidgetWin_0 control)
- User ID field with placeholder "e.g. wm5p4rk"
- Password field (masked input)
- HTML5 form validation
- No accessibility tree for form fields (requires OCR/VQA)
- Authentication completes in ~15-20 seconds
- Popups: Security Warning Message → (optional) Connexus Application Error

---

## 📁 FILES TO REFERENCE

- Old login YAML: `connexus_locator_library/workflows/LoginConnexus.yaml`
- Element library: `connexus_locator_library/reference/OrderIntake.yaml`
- Completed workflow: `~/.code_puppy/agents/gui_cub/workflows/boot_connexus.md`

---

## 💻 COMMANDS TO START

```python
# Check if Connexus still open
ui_list_windows()

# If not, re-launch using boot_connexus workflow
# (see ~/.code_puppy/agents/gui_cub/workflows/boot_connexus.md)

# Focus login window
windows_focus_window(window_title="Connexus")

# Read old login YAML for reference
read_file("connexus_locator_library/workflows/LoginConnexus.yaml")

# Proceed with testing login flow
```

---

## 📊 PROGRESS TRACKER

| Workflow | Old YAML | Status | Modern Markdown | Tested |
|----------|----------|--------|----------------|--------|
| Boot Connexus | BootConnexus.yaml | ✅ Complete | boot_connexus.md | ✅ Yes |
| Login Connexus | LoginConnexus.yaml | ✅ Complete | login_connexus.md | ✅ Yes |
| Patient Creation | PatientCreation.yaml | ✅ Complete | patient_creation.md | ✅ Yes |
| Patient Search | PatientSearch.yaml | ❌ Not Started | - | ❌ No |
| Drop-Off | DropOff.yaml | ❌ Not Started | - | ❌ No |

---

## 🐻 RESUMPTION INSTRUCTIONS

**To resume from this exact point:**

1. **Load this file** to understand context
2. **Check Connexus state:** Is login screen still open?
3. **If closed:** Re-launch using boot_connexus workflow
4. **Answer open question:** What happens when clicking "Sign In"?
5. **Proceed with login workflow modernization**
6. **Update this file** as you complete each workflow

---

**Let's continue modernizing the Login Connexus workflow! 🐻**