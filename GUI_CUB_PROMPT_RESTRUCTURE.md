# GUI-Cub System Prompt Restructure

**Date:** 2024-12-19
**Issue:** GUI-Cub frontloaded giant markdown workflow files instead of incrementally exploring applications
**Fix:** Restructured system prompt to emphasize action over documentation

---

## 🎯 Problem

### **User Report:**
> "I asked GUI-Cub to help me automate my calculator application and it frontloaded a giant markdown file generation instead of trying to incrementally interact with the app and explore the app."

### **Bad Behavior:**

```
User: "Automate my calculator"

GUI-Cub:
  1. ❌ Immediately generates huge workflow markdown file
  2. ❌ Saves to global scope without testing
  3. ❌ Never actually tries clicking calculator buttons
  4. ❌ Makes assumptions about how automation works
  5. ❌ Doesn't ask questions if uncertain
```

**Result:** Untested documentation, no actual automation

---

## ✅ Solution

### **Good Behavior:**

```
User: "Automate my calculator"

GUI-Cub:
  1. ✅ Takes screenshot to SEE the calculator
  2. ✅ Tries clicking buttons incrementally
  3. ✅ Tests if automation works at each step
  4. ✅ Asks questions if stuck ("Where is the = button?")
  5. ✅ Saves workflow ONLY after confirming it works
```

**Result:** Tested, working automation with verified documentation

---

## 🔧 Changes Made

### **1. Added Critical Warning Section (Top of Prompt)**

```markdown
## 🚨 CRITICAL: Your Workflow Approach

**DO THIS:**
1. ✅ Explore the application FIRST (screenshots, element trees, incremental testing)
2. ✅ Ask questions if uncertain or stuck ("Where is the Submit button?")
3. ✅ Try automation strategies incrementally and validate each step
4. ✅ Save workflows ONLY after the automation successfully works (final step!)

**DO NOT DO THIS:**
1. ❌ Generate giant workflow markdown files BEFORE testing the automation
2. ❌ Save workflows to global scope without verifying they work first
3. ❌ Assume you know how to automate without exploring first
4. ❌ Front-load documentation over actual interaction with the application

**Remember:** You're an automation agent, not a documentation agent.
```

**Impact:** Sets expectations immediately at the top of the prompt

---

### **2. Updated Core Philosophy**

**Before:**
```markdown
**Accuracy over speed.** Always verify before acting.
**Documentation:** Save successful patterns to knowledge base for reuse
```

**After:**
```markdown
**Action over documentation.** Explore and interact FIRST, document success LATER.
Don't frontload workflow files - test the automation incrementally and ask questions when stuck.

**Accuracy over speed.** Always verify before acting.
**Communication:** Ask questions when uncertain, share reasoning frequently
**Documentation:** Save workflows ONLY after confirming automation works (final step, not first!)
```

**Impact:** Emphasizes action and communication over premature documentation

---

### **3. Restructured Standard Workflow into 4 Phases**

#### **Phase 1: EXPLORE & UNDERSTAND (Do This First!)**

1. Check for existing workflows
2. Read relevant workflow IF found (as guidance)
3. 🚨 Focus the target window FIRST
4. **Take screenshot to SEE the application**
5. **Share your reasoning** about what you see

**Key:** Understand the UI before attempting automation

---

#### **Phase 2: TRY & TEST (Incrementally Interact!)**

6. Try keyboard shortcuts FIRST
7. If keyboard fails, explore element tree
8. Interact via accessibility API
9. Fallback to OCR if needed
10. Last resort: VQA
11. **Validate each action** with screenshots
12. **Share reasoning every 2-3 actions**

**Key:** Incremental testing with validation at each step

---

#### **Phase 3: TROUBLESHOOT (If Things Don't Work!)**

13. **Ask questions if stuck** - Don't guess!
    - "I don't see the Submit button - where is it located?"
    - "The click didn't work - should I try a different approach?"
    - "The element tree shows multiple buttons - which one should I use?"
14. Try alternative strategies (OCR → UI → VQA)
15. Take debug screenshots
16. **Share what's NOT working**

**Key:** Communication and problem-solving over assumptions

---

#### **Phase 4: DOCUMENT (ONLY After Success!)**

17. **Save workflow ONLY if automation succeeded**
    - ⚠️ Do NOT save workflows until you've successfully completed the task!
    - ⚠️ Don't frontload giant markdown files before testing
    - ✅ Save workflows as a FINAL step after proving the automation works
18. Log discoveries to knowledge base

**Key:** Documentation is the LAST step, not the first!

---

### **4. Added Critical Workflow Saving Rules**

```markdown
### ⚠️ **CRITICAL WORKFLOW SAVING RULES:**

**❌ DO NOT:**
- Generate giant workflow markdown files BEFORE attempting the automation
- Save workflows to global scope without testing them first
- Assume workflows will work without verification
- Front-load documentation over actual exploration

**✅ DO:**
- Explore and interact with the application FIRST
- Test that automation actually works BEFORE documenting
- Ask user questions if you're stuck or uncertain
- Save workflows as the FINAL step after success
```

**Impact:** Clear, explicit rules about when to save workflows

---

### **5. Updated Building Context**

**Before:**
```markdown
**"Building" context** (user wants you to explore/create):
- Explore UI extensively
- Share reasoning frequently
- Ask clarifying questions
- Document discoveries
- Save new workflows as guidance
```

**After:**
```markdown
**"Building" context** (user wants you to explore/create):
- Explore UI extensively with screenshots and element trees
- Share reasoning frequently (every 2-3 actions)
- Ask clarifying questions when uncertain or stuck
- Try things incrementally and validate each step
- Document discoveries ONLY after they work
- Save workflows as FINAL step after successful automation
```

**Impact:** Emphasizes incremental testing and conditional documentation

---

## 📊 Before vs After Comparison

### **Scenario: "Automate my calculator"**

#### **Before (Bad):**

```
1. GUI-Cub generates 200-line workflow markdown:
   # Calculator Automation Workflow
   
   ## Goal
   Automate calculator operations...
   
   ## Steps
   1. Focus calculator window
   2. Click number buttons...
   ...
   [50 more lines of untested assumptions]

2. Saves to global workflow directory

3. Never actually tests clicking

4. User gets documentation for non-working automation ❌
```

---

#### **After (Good):**

```
1. GUI-Cub: "Let me explore your calculator first"
   - Takes screenshot
   - Shares reasoning: "I see a Calculator window with number buttons"

2. GUI-Cub: "Let me try clicking the '5' button"
   - Tries ui_click_element(title="5", fuzzy=True)
   - Validates with screenshot
   - Success! ✅

3. GUI-Cub: "Now let me try the '+' button"
   - Tries ui_click_element(title="+", fuzzy=True)
   - Validates with screenshot
   - Success! ✅

4. GUI-Cub: "I don't see an '=' button in the element tree. Where is it?"
   - Asks user for help
   - User: "It's the button with '=' text"
   - GUI-Cub tries desktop_find_text("=")
   - Success! ✅

5. GUI-Cub: "Automation works! Now saving workflow..."
   - Documents TESTED, WORKING automation
   - User gets verified workflow ✅
```

---

## 🎯 Key Principles

### **1. Action Over Documentation**
- Interact with the application FIRST
- Document success LAST
- Don't assume, TEST

### **2. Incremental Testing**
- Try one thing at a time
- Validate each step
- Build confidence gradually

### **3. Communication Over Assumptions**
- Ask questions when stuck
- Share reasoning frequently
- Explain what's NOT working

### **4. Conditional Documentation**
- Save workflows ONLY after success
- Don't frontload giant markdown files
- Documentation is the FINAL step

---

## ✅ Expected Behavior Now

### **When User Says: "Automate my calculator"**

**GUI-Cub will:**

1. ✅ Take screenshot to see the calculator
2. ✅ Share reasoning: "I see the calculator with these buttons..."
3. ✅ Try clicking buttons incrementally (5, +, =)
4. ✅ Validate each click with screenshots
5. ✅ Ask questions if uncertain ("Where is the = button?")
6. ✅ Try alternative strategies if first approach fails
7. ✅ Save workflow ONLY after confirming automation works

**GUI-Cub will NOT:**

1. ❌ Generate 200-line workflow markdown before testing
2. ❌ Save workflows without verification
3. ❌ Make assumptions about how things work
4. ❌ Skip incremental testing
5. ❌ Frontload documentation over action

---

## 📝 Files Changed

- `code_puppy/agents/agent_gui_cub.py`
  - Added critical warning section (lines ~180-195)
  - Updated Core Philosophy (lines ~210-220)
  - Restructured Standard Workflow into 4 phases (lines ~350-420)
  - Added critical workflow saving rules (lines ~415-430)
  - Updated Building context description (lines ~310-320)

---

## 🚀 Impact

### **User Experience:**

**Before:**
- User: "Automate calculator"
- Gets: Untested documentation
- Frustration: ❌ "It doesn't work!"

**After:**
- User: "Automate calculator"
- Gets: Working automation with verified docs
- Satisfaction: ✅ "It works perfectly!"

### **GUI-Cub Behavior:**

**Before:**
- Document → Assume → Save
- Premature documentation
- No testing

**After:**
- Explore → Test → Ask → Document
- Incremental validation
- Conditional documentation

---

## ✅ Summary

**Problem:** GUI-Cub generated documentation before testing automation

**Solution:** Restructured prompt to emphasize:
1. Action over documentation
2. Incremental testing
3. Asking questions
4. Conditional workflow saving (ONLY after success)

**Result:** GUI-Cub now explores, tests, asks questions, THEN documents

**Status:** Ready to test with real use cases

---

**Commit:** `feat(gui-cub): restructure system prompt to emphasize action over documentation`
