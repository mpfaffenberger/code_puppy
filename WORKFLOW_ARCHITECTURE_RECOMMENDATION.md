# GUI-Cub Workflow Architecture - Recommendation

## 🎯 Core Problem Statement

**Current State:**
- `gui_cub_execute_workflow` treats YAML as **rigid automation scripts**
- Workflows execute step-by-step mechanically (step 1 → step 2 → step 3)
- Agent has NO decision-making power during workflow execution
- WorkflowExecutor bypasses agent intelligence

**Desired State:**
- YAML workflows are **guidance and recommendations**, not automation scripts
- Agent reads workflow YAML and **intelligently decides** how to accomplish goals
- Agent can adapt when steps don't work as expected
- Agent uses tools based on YAML suggestions but makes its own decisions

---

## 🔍 Comparison: qa-kitten vs gui-cub

### qa-kitten (Correct Pattern) ✅

```python
# qa-kitten workflow tools
browser_read_workflow(name="login_flow")  # Returns markdown GUIDANCE
# Agent receives the content and interprets it
# Agent decides which browser_* tools to call
# Workflow is DOCUMENTATION, not AUTOMATION
```

**qa-kitten workflow file (Markdown):**
```markdown
# Login to GitHub Workflow

## Goal
Authenticate user to GitHub

## Suggested Steps
1. Navigate to github.com
2. Find and click "Sign in" button (usually top-right)
3. Type username in username field
4. Type password in password field
5. Click "Sign in" button

## Tips
- Use semantic locators (find_by_role) preferred
- Password field might have autocomplete
- May encounter 2FA - handle gracefully
```

**How qa-kitten uses it:**
1. Agent reads workflow with `browser_read_workflow("login_flow")`
2. Agent sees "Navigate to github.com" → decides to call `browser_navigate()`
3. Agent sees "Find Sign in button" → decides to call `browser_find_by_role(role='button', name='Sign in')`
4. **Agent makes ALL tool decisions based on GUIDANCE**

### gui-cub (Current - Incorrect Pattern) ❌

```python
# gui-cub workflow executor
gui_cub_execute_workflow(name="login_flow", parameters={...})
# WorkflowExecutor takes over completely
# Agent has NO involvement in execution
# YAML rigidly defines every tool call
```

**gui-cub workflow file (YAML):**
```yaml
name: "Login Flow"
steps:
  - action: focus_window  # ❌ Hardcoded action
    app: "Chrome"
  - action: type          # ❌ Rigid sequence
    text: "username"
  - action: press         # ❌ No agent intelligence
    key: "tab"
```

**How gui-cub currently uses it:**
1. Agent calls `gui_cub_execute_workflow("login_flow")`
2. WorkflowExecutor reads YAML and executes steps mechanically
3. Step 1: Call `tools.focus_window("Chrome")`
4. Step 2: Call `tools.keyboard_type("username")`
5. **WorkflowExecutor makes ALL decisions, agent is bypassed**

---

## 🏗️ Recommended Architecture

### Option 1: Follow qa-kitten Pattern (RECOMMENDED) 🏆

**Change workflow format from YAML to Markdown** (or keep YAML as structured guidance)

#### Markdown Format (Preferred):
```markdown
# Login to Application

## Goal
Authenticate user to the application

## Context
- Application: Desktop app (TextEdit, Chrome, etc.)
- Credentials: Usually from environment variables
- May require window focus first

## Recommended Approach

1. **Focus the application window**
   - Tool suggestion: `focus_window(app="AppName")`
   - Alternative: Use `ui_find_element` to locate window

2. **Locate username field**
   - Try OCR: `desktop_find_text("Username")`
   - Try UI automation: `ui_find_element(title="Username")`
   - VQA fallback: `desktop_vqa_click_two_stage(description="username input field")`

3. **Enter username**
   - Type text: `desktop_keyboard_type(text=username)`
   - Verify with screenshot if needed

4. **Locate password field**
   - Similar strategy to username
   - Use tab key if fields are adjacent: `desktop_keyboard_press("tab")`

5. **Enter password**
   - Type password from secure storage
   - Avoid logging sensitive data

6. **Submit form**
   - Click submit button: `desktop_click_element_smart(text="Login")`
   - Or press Enter: `desktop_keyboard_press("enter")`

## Common Issues & Solutions

- **Window not focused:** Call `focus_window()` first
- **Fields not found:** Take screenshot with `desktop_screenshot` to analyze
- **Click fails:** Use multi-strategy `desktop_click_element_smart`
- **Credentials not available:** Check environment variables

## Success Criteria

- User is logged in (verify with screenshot or UI state)
- No error messages visible
- Dashboard/home screen is displayed
```

**Agent behavior with this format:**

```python
# User: "Run the login workflow for Chrome"

# Agent thinks:
# 1. Read the workflow guidance
result = gui_cub_read_workflow("login")
content = result["content"]

# 2. Interpret guidance and make decisions
# "Focus the application window" → I'll call focus_window
focus_window("Chrome")

# 3. "Locate username field" → Let me try OCR first
ocr_result = desktop_find_text("Username")
if ocr_result["found"]:
    # Click the field
    desktop_mouse_click(x=ocr_result["x"], y=ocr_result["y"])
else:
    # Try UI automation fallback
    ui_result = ui_find_element(title="Username")
    ui_click_element(title="Username")

# Agent is IN CONTROL, making intelligent decisions
```

#### YAML Format (Alternative - Structured Guidance):
```yaml
name: "Login Workflow"
description: "Authenticate user to application"

goal: "Successfully log in to the application"

context:
  application: "Desktop application (configurable)"
  credentials_source: "Environment variables or parameters"
  
recommended_steps:
  - step: "Focus application window"
    goal: "Bring target window to foreground"
    suggested_tools:
      - tool: "focus_window"
        parameters:
          app: "{{app_name}}"
    alternatives:
      - "Use ui_find_element to locate and activate window"
      - "Use VQA to identify window visually"
  
  - step: "Locate and click username field"
    goal: "Position cursor in username input"
    suggested_tools:
      - tool: "desktop_find_text"
        parameters:
          search_text: "Username"
      - tool: "ui_find_element"
        parameters:
          title: "Username"
    strategies:
      - "Try OCR text recognition first (fast, reliable)"
      - "Fall back to UI automation if OCR fails"
      - "Use VQA as last resort for complex UIs"
  
  - step: "Enter username"
    goal: "Type username into field"
    suggested_tools:
      - tool: "desktop_keyboard_type"
        parameters:
          text: "{{username}}"
    tips:
      - "Verify field is focused before typing"
      - "Use environment variables for credentials"

common_issues:
  - issue: "Window not focused"
    solution: "Call focus_window() before interacting"
  - issue: "Fields not visible"
    solution: "Take screenshot to analyze UI state"

success_criteria:
  - "No error messages visible"
  - "Dashboard or home screen displayed"
  - "Username visible in UI (if applicable)"
```

**Agent behavior with structured YAML:**

```python
# User: "Run the login workflow"

# Agent reads workflow
result = gui_cub_read_workflow("login")
workflow = result["parsed"]  # Parsed YAML dict

# Agent interprets the GOAL
goal = workflow["goal"]  # "Successfully log in to the application"

# Agent reviews recommended_steps as GUIDANCE
for step_guide in workflow["recommended_steps"]:
    step_goal = step_guide["goal"]
    suggested_tools = step_guide["suggested_tools"]
    
    # Agent DECIDES which approach to use based on suggestions
    # Agent can try alternatives if first approach fails
    # Agent adapts based on current state
    
# Agent remains in FULL CONTROL
```

---

## 🔄 Migration Path

### Phase 1: Deprecate `gui_cub_execute_workflow` ⚠️

**Current state:**
- Tool exists: `gui_cub_execute_workflow(name, parameters)`
- Executes workflows mechanically via WorkflowExecutor
- Bypasses agent intelligence

**Recommendation:**
1. Mark `gui_cub_execute_workflow` as **deprecated**
2. Add warning in tool docstring
3. Update system prompt to discourage usage
4. Keep tool functional for backward compatibility (for now)

**Updated tool docstring:**
```python
@agent.tool
async def gui_cub_execute_workflow(...) -> Dict[str, Any]:
    """⚠️ DEPRECATED - Use gui_cub_read_workflow instead.
    
    This tool executes workflows mechanically without agent intelligence.
    For better results, use gui_cub_read_workflow to read workflow guidance
    and make intelligent decisions about which tools to call.
    
    This tool remains available for legacy workflows but is discouraged.
    """
```

### Phase 2: Update System Prompt 📝

**Add to gui-cub system prompt:**

```python
## Workflow Philosophy 🎯

**Workflows are GUIDANCE, not automation scripts!**

When working with workflows:

1. **ALWAYS start by reading workflows** - Use gui_cub_read_workflow("workflow_name")
2. **Interpret, don't execute** - Workflows suggest approaches, YOU decide which tools to use
3. **Adapt based on context** - Use your intelligence to handle variations
4. **Learn from patterns** - Workflows document proven strategies

### How to Use Workflows:

**❌ DON'T DO THIS:**
```python
# Mechanical execution (old pattern)
gui_cub_execute_workflow("login")  # Agent loses control
```

**✅ DO THIS INSTEAD:**
```python
# Read guidance and interpret intelligently
workflow = gui_cub_read_workflow("login")
content = workflow["content"]

# Review the recommended steps
# Decide which tools to use based on current context
# Adapt if something doesn't work
# Use your full intelligence to accomplish the goal
```

### Workflow Best Practices:

1. **Check existing workflows first**: `gui_cub_list_workflows()`
2. **Read relevant workflows**: `gui_cub_read_workflow(name)`
3. **Interpret guidance intelligently**: Don't blindly follow steps
4. **Adapt to reality**: Use screenshots and verification to adapt
5. **Document success**: Save new patterns with `gui_cub_save_workflow()`

**Workflows should contain:**
- Goals and objectives (WHAT to accomplish)
- Recommended approaches (SUGGESTIONS, not commands)
- Common issues and solutions
- Success criteria
- Tips and alternatives

**Workflows should NOT contain:**
- Rigid step-by-step commands that must be followed exactly
- Hard dependencies on specific tool sequences
- No room for agent decision-making
```

### Phase 3: Convert Existing Workflows 🔄

**Find existing YAML workflows:**
```bash
find ~/.code_puppy/agents/gui_cub/workflows -name "*.yaml"
```

**Conversion strategy:**

1. **Keep YAML files** (backward compatibility)
2. **Add Markdown equivalents** with rich guidance
3. **Update structure** to emphasize goals over rigid steps

**Example conversion:**

**Before (Rigid YAML):**
```yaml
name: "Open Calculator"
steps:
  - action: hotkey
    keys: ["cmd", "space"]
  - action: type
    text: "Calculator"
  - action: press
    key: "enter"
```

**After (Guidance YAML):**
```yaml
name: "Open Calculator"
goal: "Launch the Calculator application"

recommended_approach:
  description: "Use Spotlight search on macOS to quickly launch Calculator"
  
suggested_steps:
  - step: "Open Spotlight"
    tool_suggestions:
      - desktop_keyboard_hotkey: ["cmd", "space"]
    alternatives:
      - "Click Spotlight icon in menu bar"
      - "Use Alfred or other launcher if available"
  
  - step: "Search for Calculator"
    tool_suggestions:
      - desktop_keyboard_type: "Calculator"
    tips:
      - "Application name is case-insensitive"
      - "Spotlight will auto-suggest after a few characters"
  
  - step: "Launch application"
    tool_suggestions:
      - desktop_keyboard_press: "enter"
    alternatives:
      - "Click on Calculator suggestion in results"
      - "Use arrow keys + enter if multiple results"

platform_notes:
  macos: "Use Spotlight (cmd+space)"
  windows: "Use Start menu (win key) or Run dialog (win+r)"
  linux: "Use application launcher or terminal"

success_criteria:
  - "Calculator window is visible and focused"
  - "Can interact with Calculator interface"
```

**Or Markdown (Preferred):**
```markdown
# Open Calculator Application

## Goal
Launch the Calculator application on macOS

## Recommended Approach

Use Spotlight search for quick, reliable application launching.

### Steps:

1. **Open Spotlight**
   - Tool: `desktop_keyboard_hotkey(["cmd", "space"])`
   - Alternative: Click Spotlight icon in menu bar
   - Alternative: Use Alfred if installed

2. **Search for Calculator**
   - Tool: `desktop_keyboard_type("Calculator")`
   - Note: Case-insensitive, auto-suggests after few chars

3. **Launch application**
   - Tool: `desktop_keyboard_press("enter")`
   - Alternative: Click Calculator in results
   - Alternative: Arrow keys + Enter if multiple results

## Platform Variations

- **macOS:** Spotlight (cmd+space)
- **Windows:** Start menu (win key) or Run dialog (win+r)
- **Linux:** Application launcher or terminal

## Success Criteria

- Calculator window is visible
- Window has focus
- Can interact with Calculator interface
```

### Phase 4: Remove WorkflowExecutor (Future) 🗑️

**Long-term goal:**
1. All workflows converted to guidance format
2. `gui_cub_execute_workflow` fully deprecated
3. Remove `workflow_executor.py` and related code
4. Keep `ToolRegistry` for potential future use

**Timeline:** 3-6 months after Phase 3 completion

---

## 📋 Implementation Checklist

### Immediate Actions (Week 1):
- [ ] Add deprecation warning to `gui_cub_execute_workflow`
- [ ] Update gui-cub system prompt with workflow philosophy
- [ ] Create template for guidance-style workflows (Markdown)
- [ ] Create template for structured guidance (YAML)
- [ ] Document new workflow pattern in README

### Short-term (Month 1):
- [ ] Convert 3-5 existing workflows to guidance format
- [ ] Test agent behavior with new workflow style
- [ ] Gather feedback on Markdown vs YAML preference
- [ ] Update workflow examples in documentation
- [ ] Create migration guide for users

### Medium-term (Month 2-3):
- [ ] Convert all remaining workflows to guidance format
- [ ] Update all code examples and documentation
- [ ] Add workflow best practices to system prompt
- [ ] Create "workflow design guide" for users
- [ ] Monitor agent performance with new pattern

### Long-term (Month 6+):
- [ ] Deprecate `gui_cub_execute_workflow` completely
- [ ] Remove WorkflowExecutor code
- [ ] Clean up related infrastructure
- [ ] Final documentation update

---

## 💡 Key Insights

### Why This Matters:

1. **Agent Intelligence** 🧠
   - Current: Agent is bypassed during workflow execution
   - New: Agent uses full intelligence to interpret guidance

2. **Adaptability** 🔄
   - Current: Workflows fail if exact steps don't work
   - New: Agent adapts based on actual UI state

3. **Context Awareness** 👁️
   - Current: Workflows are context-blind
   - New: Agent considers current situation

4. **Maintainability** 🛠️
   - Current: Rigid workflows break with UI changes
   - New: Guidance remains valid even if UI changes

5. **Learning** 📚
   - Current: Workflows are isolated automation
   - New: Workflows are knowledge base for agent

### User Experience:

**Current UX:**
```
User: "Run the login workflow"
→ gui_cub_execute_workflow("login") 
→ Mechanical step execution
→ Success or failure (no adaptation)
```

**New UX:**
```
User: "Run the login workflow"
→ Agent reads workflow guidance
→ Agent plans approach based on guidance + current state
→ Agent executes with intelligence and adaptation
→ Agent handles unexpected situations
→ Higher success rate, better user experience
```

---

## 🎓 Conclusion

The refactor we just completed (ToolRegistry) is still valuable for:
- Clean architecture
- Testability
- Single source of truth for tool functions

**However**, the bigger architectural issue is:
- **Workflows should be GUIDANCE, not AUTOMATION**
- **Agent should INTERPRET workflows, not EXECUTE them mechanically**
- **Follow the qa-kitten pattern for intelligent workflow usage**

### Recommendation:

**Immediate action:** Update system prompt and deprecate `gui_cub_execute_workflow`

**Format preference:** Start with **Markdown** (more readable, flexible) and evaluate

**Timeline:** Begin Phase 1 immediately, Phase 2-3 over next 2 months

**Success metric:** Agent uses workflows as guidance 100% of the time, mechanical execution 0%

---

**Created by:** Doc 🐶 (Code Puppy)
**Date:** 2024
**Status:** Recommendation for review and implementation
