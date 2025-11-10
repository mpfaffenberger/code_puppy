# GUI-Cub System Prompt Comprehensive Audit

**Date:** 2024-12-19
**Purpose:** Identify contradictions, structural issues, and optimize prompt effectiveness
**Goal:** Build the best possible system prompt

---

## 📊 Prompt Statistics

**Total Length:** ~6,100 tokens (~23,000 characters)
**Sections:** 15 major sections
**Structure:** Introduction → Critical Rules → Details → Examples

---

## ✅ What's GOOD (Keep These)

### **1. Strong Opening**
- Bear cub personality (engaging, memorable)
- OS context immediately (macOS/Windows specific guidance)
- Critical workflow approach upfront (🚨 section)

### **2. Clear Hierarchy**
- Emoji markers for sections
- Critical rules marked with 🚨
- DO/DON'T lists with ✅/❌

### **3. Examples Throughout**
- Code examples for workflows
- Markdown templates
- Common patterns section

### **4. Action-Oriented**
- "DO THIS" vs "DO NOT DO THIS"
- Specific tool usage examples
- Clear phase-based workflow

---

## 🔴 CRITICAL ISSUES (Must Fix)

### **Issue 1: YAML Template Artifact in Middle of Prompt**

**Location:** Lines ~570-590

```yaml
  - name: timeout
    type: number
    description: "Max wait time in seconds"
    default: 5

outputs:
  - name: patient_name
    description: "Patient's full name"
  - name: date_of_birth
    description: "DOB"
  - name: screenshot
    description: "Verification screenshot"

steps:
  - action: type
    text: "${patient_id}"
  
  - action: press
    key: "enter"
```

**Problem:** This looks like leftover YAML workflow template code that got mixed into the system prompt!

**Impact:** Confusing, wastes tokens, looks like a bug

**Fix:** REMOVE this entire section - it's not part of the prompt narrative

---

### **Issue 2: Redundant "Workflow Philosophy" Sections**

**Locations:**
1. **Lines ~216-305:** "Workflow Philosophy" (detailed)
2. **Lines ~495-520:** "Workflow Management" (similar content)
3. **Lines ~520-565:** "Saving Workflows - Best Practices" (overlaps again)

**Redundancy Examples:**

**Section 1 says:**
```
Workflows are GUIDANCE, not automation scripts!
Always check existing workflows first
```

**Section 2 says:**
```
ALWAYS check existing workflows before starting new tasks!
Workflow Library - Save, reuse, and learn from documented patterns
```

**Section 3 says:**
```
When to save: After successfully completing multi-step automation
Naming conventions: Use descriptive names
What to include: Step-by-step tool usage
```

**Problem:** Same concepts repeated 3 times with slight variations

**Impact:** Wastes ~1000 tokens, dilutes key messages

**Fix:** Consolidate into ONE comprehensive "Workflow Management" section

---

### **Issue 3: "Standard Workflow" Repeats Critical Rules**

**Critical Rules section (Lines ~334-347) says:**
```
🚨 ALWAYS focus the target window FIRST
- Before screenshots
- Before mouse clicks
- Before keyboard input
```

**Standard Workflow Phase 1 (Lines ~358-365) says:**
```
3. 🚨 CRITICAL: Focus the target window FIRST
   - Why: Screenshots, mouse clicks, keyboard input go to wrong app
   - When: Before EVERY screenshot, click, keyboard action
   - Example: desktop_focus_window("Calculator")
```

**Problem:** Same rule explained twice with near-identical text

**Impact:** Wastes ~150 tokens

**Fix:** Keep detailed version in Standard Workflow, remove from Critical Rules

---

### **Issue 4: "User Context Adaptation" Duplicates "Building vs Running"**

**Workflow Philosophy section (Lines ~295-316) says:**
```
**"Building" context:**
- Explore UI extensively
- Share reasoning frequently
- Ask clarifying questions
- Document discoveries ONLY after they work

**"Running" context:**
- Read existing workflows
- Execute efficiently
- Adapt when steps don't work
```

**User Context Adaptation section (Lines ~471-493) says:**
```
**"Building" Context:**
- When creating new workflows, exploring UI
- Frequent communication via agent_share_your_reasoning
- Ask clarifying questions when elements ambiguous
- Verbose reporting

**"Running" Context:**
- Read existing workflows
- Execute efficiently but ADAPT
- Report completion status
```

**Problem:** Same concept explained twice with 80% overlap

**Impact:** Wastes ~300 tokens

**Fix:** Merge into ONE section in Standard Workflow

---

## ⚠️ STRUCTURAL ISSUES (Should Fix)

### **Issue 5: Poor Information Architecture**

**Current Order:**
1. Introduction
2. 🚨 CRITICAL: Workflow Approach
3. Philosophy
4. Specializations
5. Core Philosophy
6. Workflow Philosophy (← should be near Standard Workflow!)
7. Critical Rules (← should be earlier!)
8. Standard Workflow (← should be earlier!)
9. Tool Strategy
10. User Context Adaptation (← redundant!)
11. Workflow Management (← redundant!)
12. Knowledge Base
13. Platform Support
14. Common Patterns
15. Screenshot Strategy

**Problem:** Critical information scattered throughout
- Critical Rules at line ~334 (should be earlier)
- Standard Workflow at line ~354 (should be earlier)
- Workflow concepts repeated in 3 places

**Impact:** Agent might miss critical info buried in middle

**Optimal Order (Prompt Engineering Best Practices):**
1. ✅ Introduction (who you are)
2. ✅ 🚨 CRITICAL RULES (most important - focus window, security, etc.)
3. ✅ STANDARD WORKFLOW (how to approach tasks - 4 phases)
4. ✅ TOOL STRATEGY (priority tiers)
5. ✅ WORKFLOW MANAGEMENT (consolidated - check first, save last)
6. ✅ PLATFORM SUPPORT (macOS/Windows specifics)
7. ✅ COMMON PATTERNS (examples)
8. ✅ KNOWLEDGE BASE (supplementary)
9. ✅ SCREENSHOT STRATEGY (technical details)

**Fix:** Restructure to put critical info first, details last

---

### **Issue 6: "Core Philosophy" Too Buried**

**Location:** Lines ~208-215 (after Workflow Approach and before Workflow Philosophy)

**Content:**
```
Action over documentation.
Accuracy over speed.
Tool Priority: Keyboard → Accessibility → OCR → VQA
```

**Problem:** This is CRITICAL but buried on line 208

**Impact:** Agent might not internalize these core principles

**Fix:** Move to top (lines 10-20) OR merge into Critical Rules

---

### **Issue 7: Specializations List Not Actionable**

**Location:** Lines ~202-206

```
🎯 **Desktop Automation** - workflows on macOS and Windows
⌨️ **Keyboard-First Interaction** - Tab navigation, shortcuts
🔍 **Smart Element Discovery** - Accessibility APIs with fuzzy matching
📋 **Workflow Management** - YAML-based automation and knowledge base
```

**Problem:** This is just a list - not actionable guidance

**Impact:** Wastes ~100 tokens on descriptive fluff

**Fix:** Remove or merge into introduction

---

### **Issue 8: "Workflow Format" Section Too Long**

**Location:** Lines ~265-294 (~350 tokens)

**Content:**
- Explanation of Markdown format
- Full example login workflow
- Explanation of YAML format

**Problem:** Example workflow is too long and detailed for system prompt

**Impact:** Wastes ~200 tokens showing how to format (not critical)

**Fix:** 
- Keep ONE sentence: "Preferred format: Markdown (like qa-kitten)"
- Move detailed examples to documentation
- Agent can learn format from reading existing workflows

---

## 🟡 MINOR ISSUES (Nice to Fix)

### **Issue 9: Phase 4 Has Both "When to Save" Lists**

**Location:** Lines ~386-422

**Content:**
```
**When to save workflows:**
- ✅ After successfully completing complex multi-step automation
- ✅ When you discover reliable pattern
...

**What to include in saved workflows:**
✅ **DO Include:**
- Step-by-step tool usage
...

❌ **DON'T Include:**
- Untested assumptions
...

### ⚠️ **CRITICAL WORKFLOW SAVING RULES:**

**❌ DO NOT:**
- Generate giant workflow markdown files BEFORE attempting
...

**✅ DO:**
- Explore and interact FIRST
...
```

**Problem:** "Critical Workflow Saving Rules" at end just repeats what was already said

**Impact:** Redundant (wastes ~100 tokens)

**Fix:** Remove "Critical Workflow Saving Rules" section - already covered

---

### **Issue 10: "Common Patterns" Should Have More Context**

**Location:** Lines ~630-680

**Content:**
```python
# Form filling (keyboard-first):
desktop_focus_window("Settings")
desktop_keyboard_press("tab")
...
```

**Problem:** Code examples lack explanation of WHEN to use each pattern

**Impact:** Examples are useful but could be more pedagogical

**Fix:** Add 1-2 sentences before each pattern explaining the use case

---

### **Issue 11: "Knowledge Base" Section Too Technical**

**Location:** Lines ~615-628

**Content:**
```
Location: ~/.code_puppy/agents/gui-cub/gui_cub_knowledge_base.md
Quality over quantity - KB auto-prunes at 1000 lines (FIFO)
Use searchable tags for easy retrieval
```

**Problem:** File paths and FIFO implementation details aren't useful for agent

**Impact:** Wastes ~50 tokens on technical trivia

**Fix:** Simplify to: "Document discoveries with append_to_knowledge_base. Use tags for searchability."

---

## 📉 REDUNDANCY ANALYSIS

### **Workflow Concepts (Repeated 3x)**

| Concept | Location 1 | Location 2 | Location 3 |
|---------|-----------|-----------|------------|
| Check workflows first | Workflow Philosophy | Standard Workflow Phase 1 | Workflow Management |
| Workflows are guidance | Workflow Philosophy | User Context | Workflow Management |
| When to save | Phase 4 | Saving Workflows | Critical Rules |
| What to include | Phase 4 | Saving Workflows | - |

**Total waste:** ~800 tokens

---

### **Focus Window (Repeated 3x)**

| Location | Lines | Content |
|----------|-------|----------|
| Critical Rules | ~334 | "ALWAYS focus window FIRST" |
| Standard Workflow Phase 1 | ~360 | "CRITICAL: Focus window FIRST (with examples)" |
| Common Patterns | ~633 | "# CRITICAL: Focus window FIRST" (in code) |

**Total waste:** ~150 tokens

**Fix:** Keep detailed version in Phase 1, brief mention in Critical Rules

---

### **Building vs Running Context (Repeated 2x)**

| Location | Lines | Tokens |
|----------|-------|--------|
| Workflow Philosophy | ~295 | ~150 |
| User Context Adaptation | ~471 | ~250 |

**Total waste:** ~200 tokens (80% overlap)

**Fix:** Keep ONE version in Standard Workflow intro

---

## 📊 TOTAL WASTE ESTIMATE

| Issue | Wasted Tokens |
|-------|---------------|
| YAML template artifact | ~300 |
| Workflow redundancy | ~800 |
| Focus window repetition | ~150 |
| Building/Running duplication | ~200 |
| Specializations fluff | ~100 |
| Long workflow format examples | ~200 |
| Redundant saving rules | ~100 |
| Knowledge base technical details | ~50 |
| **TOTAL WASTE** | **~1,900 tokens** |

**Current:** ~6,100 tokens  
**Optimized:** ~4,200 tokens (31% reduction)  
**Benefit:** More focused, less redundant, better agent attention

---

## 🎯 RECOMMENDED STRUCTURE

### **New Optimal Order:**

```
1. INTRODUCTION (100 tokens)
   - Bear cub personality
   - OS context (macOS/Windows)
   - Your mission

2. 🚨 CRITICAL RULES (300 tokens)
   - ALWAYS focus window first (with examples)
   - NEVER use OCR/VQA on terminals (security)
   - Tool priority: Keyboard → Accessibility → OCR → VQA
   - Action over documentation
   - Workflows are guidance, not scripts

3. STANDARD WORKFLOW - 4 Phases (800 tokens)
   Phase 1: EXPLORE
   - Check workflows first
   - Focus window
   - Take screenshot
   - Share reasoning
   
   Phase 2: TRY & TEST
   - Keyboard first
   - Then accessibility
   - Then OCR
   - VQA last resort
   
   Phase 3: TROUBLESHOOT
   - Ask questions
   - Try alternatives
   - Debug screenshots
   
   Phase 4: DOCUMENT
   - Save ONLY after success
   - What to include
   - What NOT to include

4. TOOL STRATEGY - Priority Tiers (400 tokens)
   - Tier 1: Keyboard (preferred)
   - Tier 2: Accessibility API
   - Tier 3: OCR with offsets
   - Tier 4: VQA (last resort)

5. WORKFLOW MANAGEMENT (400 tokens) [CONSOLIDATED]
   - Check workflows first (saves time!)
   - Workflows are guidance
   - When to save (4 triggers)
   - What to include (DO/DON'T)
   - Naming conventions
   - How to update workflows

6. PLATFORM SUPPORT (200 tokens)
   - macOS: Accessibility API
   - Windows: UI Automation
   - Cross-platform: ui_automation tools

7. COMMON PATTERNS (600 tokens)
   - Form filling (keyboard-first)
   - Element tree exploration
   - Tier fallback pattern
   - Smart click pattern
   - With use case explanations

8. KNOWLEDGE BASE (100 tokens)
   - append_to_knowledge_base for discoveries
   - Use tags for searchability

9. SCREENSHOT STRATEGY (200 tokens)
   - Tier 1: Explicit coordinates
   - Tier 2: Active window (default)
   - Tier 3: Full screen (fallback)
```

**Total:** ~3,100 tokens (50% reduction from current 6,100!)

---

## ✅ SPECIFIC RECOMMENDATIONS

### **Priority 1: CRITICAL (Must Do)**

1. **REMOVE YAML template artifact** (lines ~570-590)
   - Effort: 2 minutes
   - Impact: Removes confusion

2. **CONSOLIDATE workflow sections** (3 sections → 1 section)
   - Effort: 30 minutes
   - Impact: Saves ~800 tokens, clearer structure

3. **RESTRUCTURE order** (critical info first)
   - Effort: 1 hour
   - Impact: Better agent comprehension

---

### **Priority 2: HIGH (Should Do)**

4. **Remove redundant "Focus window" mentions**
   - Effort: 10 minutes
   - Impact: Saves ~150 tokens

5. **Merge Building/Running context** (2 sections → 1)
   - Effort: 15 minutes
   - Impact: Saves ~200 tokens

6. **Simplify "Specializations" section**
   - Effort: 5 minutes
   - Impact: Saves ~100 tokens

7. **Remove long workflow format examples**
   - Effort: 5 minutes
   - Impact: Saves ~200 tokens

---

### **Priority 3: MEDIUM (Nice to Have)**

8. **Remove redundant "Critical Workflow Saving Rules"**
   - Effort: 5 minutes
   - Impact: Saves ~100 tokens

9. **Add context to Common Patterns**
   - Effort: 15 minutes
   - Impact: Better examples

10. **Simplify Knowledge Base section**
    - Effort: 5 minutes
    - Impact: Saves ~50 tokens

---

## 📊 EXPECTED OUTCOMES

### **After Implementing All Recommendations:**

**Token Reduction:**
- Current: ~6,100 tokens
- After: ~4,200 tokens
- **Savings: ~1,900 tokens (31%)**

**Structural Improvements:**
- ✅ Critical rules at top (better attention)
- ✅ No contradictions
- ✅ No redundancy
- ✅ Clear hierarchy
- ✅ Logical flow

**Agent Benefits:**
- ✅ Faster processing (fewer tokens)
- ✅ Better comprehension (critical info first)
- ✅ Less confusion (no contradictions)
- ✅ More focused (no fluff)

---

## 📝 IMPLEMENTATION CHECKLIST

### **Phase 1: Critical Fixes (30 minutes)**
- [ ] Remove YAML template artifact (lines ~570-590)
- [ ] Consolidate 3 workflow sections into 1
- [ ] Move Critical Rules earlier (after introduction)

### **Phase 2: Structure (1 hour)**
- [ ] Reorder sections (critical first, details last)
- [ ] Remove redundant focus window mentions
- [ ] Merge Building/Running context sections

### **Phase 3: Polish (30 minutes)**
- [ ] Simplify Specializations
- [ ] Remove long workflow examples
- [ ] Remove redundant saving rules
- [ ] Simplify Knowledge Base section
- [ ] Add context to Common Patterns

### **Phase 4: Validate (15 minutes)**
- [ ] Read through entire prompt
- [ ] Check for remaining contradictions
- [ ] Verify token count reduction
- [ ] Test with real use case

**Total Effort:** ~2.5 hours
**Impact:** HIGH (31% token reduction, much clearer structure)

---

## ✅ SUMMARY

### **Critical Issues Found:**
1. 🔴 YAML template artifact (300 tokens)
2. 🔴 Workflow concepts repeated 3x (800 tokens)
3. 🔴 Poor information architecture (critical info buried)
4. 🔴 Focus window repeated 3x (150 tokens)
5. 🔴 Building/Running context repeated 2x (200 tokens)

### **Total Waste:** ~1,900 tokens (31% of prompt)

### **Recommended Approach:**
1. Remove artifacts and redundancy
2. Restructure: critical first, details last
3. Consolidate workflow sections
4. Simplify examples

### **Expected Result:**
- Clearer, more focused prompt
- 31% token reduction
- Better agent comprehension
- No contradictions

---

**Status:** Comprehensive audit complete  
**Priority:** HIGH (significant improvements needed)  
**Effort:** ~2.5 hours implementation  
**Impact:** Much better prompt quality
