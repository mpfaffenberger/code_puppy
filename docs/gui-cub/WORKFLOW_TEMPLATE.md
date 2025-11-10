# [Workflow Name] - GUI-Cub Guidance Template

> **Purpose:** This template helps you create workflow guidance documents for GUI-Cub.
> **Format:** Markdown (preferred) for maximum readability and flexibility
> **Philosophy:** Workflows are GUIDANCE for the agent, NOT rigid automation scripts

---

# [Task Name]

## Goal

[Clear, concise statement of what this workflow accomplishes]

Example: "Authenticate user to the Gmail web interface"

## Context

[Background information, prerequisites, and assumptions]

- **Application:** [Name of application/website]
- **Platform:** [macOS/Windows/Linux or "Cross-platform"]
- **Prerequisites:** [What needs to be set up first]
- **Credentials:** [Where credentials come from - env vars, parameters, etc.]
- **Typical Use Case:** [When would someone use this workflow]

Example:
```markdown
- Application: Gmail (web browser)
- Platform: Cross-platform
- Prerequisites: Browser must be initialized
- Credentials: From environment variables GMAIL_USER and GMAIL_PASS
- Typical Use Case: Automated email checking or sending
```

## Recommended Approach

[High-level strategy and suggested steps]

### Strategy Overview

[1-2 sentences describing the overall approach]

Example: "Use Spotlight to quickly launch Calculator, then use keyboard shortcuts for all operations to avoid unreliable mouse clicks."

### Suggested Steps

[Numbered steps with tool suggestions and alternatives]

#### 1. [Step Name]

**Goal:** [What this step accomplishes]

**Suggested Tools:**
- Primary: `tool_name(param1="value", param2="value")`
- Alternative: `other_tool(...)` if primary approach fails
- Fallback: `last_resort_tool(...)` as last option

**Tips:**
- [Helpful hint about this step]
- [Common mistake to avoid]
- [Platform-specific consideration]

**Example:**
```python
# Primary approach
desktop_focus_window("Calculator")

# Alternative if focus_window fails
ui_find_element(title="Calculator")
ui_click_element(title="Calculator")
```

#### 2. [Next Step Name]

[Repeat pattern for each step]

---

### Complete Example:

```markdown
#### 1. Focus Target Window

**Goal:** Bring Calculator to foreground

**Suggested Tools:**
- Primary: `desktop_focus_window(app="Calculator")`
- Alternative: `ui_focus_window(title="Calculator")`

**Tips:**
- ALWAYS focus window BEFORE screenshots or keyboard input
- Window name may vary by platform
- Verify with screenshot after focusing

#### 2. Enter Calculation

**Goal:** Type the mathematical expression

**Suggested Tools:**
- Primary: `desktop_keyboard_type(text="5+5")`
- Alternative: Click number buttons using `ui_click_element()`

**Tips:**
- Keyboard typing is faster and more reliable
- Verify calculator is focused first
- Use standard operators: +, -, *, /
```

## Common Issues & Solutions

[Document known problems and how to solve them]

### Issue: [Problem Description]

**Symptoms:**
- [How you know this issue is occurring]
- [Error messages or behaviors]

**Solution:**
- [Step-by-step fix]
- [Alternative approaches]

**Prevention:**
- [How to avoid this issue]

**Example:**
```markdown
### Issue: Window Not Focused

**Symptoms:**
- Keyboard input goes to wrong application
- Screenshots show incorrect window
- Click coordinates are off

**Solution:**
1. Call `desktop_focus_window(app_name)` explicitly
2. Take screenshot to verify correct window
3. Retry the operation

**Prevention:**
- ALWAYS call focus_window before ANY interaction
- Include focus_window in every workflow step
```

## Platform-Specific Notes

[Document differences across operating systems]

### macOS
- [macOS-specific considerations]
- [Tool recommendations for macOS]
- [Keyboard shortcut variations]

### Windows
- [Windows-specific considerations]
- [Tool recommendations for Windows]
- [UI automation specifics]

### Linux
- [Linux-specific considerations]
- [Tool recommendations for Linux]
- [Desktop environment variations]

**Example:**
```markdown
### macOS
- Use Spotlight: `desktop_keyboard_hotkey(["cmd", "space"])`
- Calculator path: /Applications/Calculator.app
- Accessibility API available via macos_automation tools

### Windows
- Use Start Menu: `desktop_keyboard_press("win")`
- Calculator: calc.exe
- Use windows_automation tools for UI interaction
```

## Success Criteria

[How to verify the workflow succeeded]

- [ ] [Specific condition that indicates success]
- [ ] [Another verification point]
- [ ] [Final confirmation]

**Example:**
```markdown
- [ ] Calculator window is visible and has focus
- [ ] Result is displayed correctly in calculator
- [ ] No error messages or dialogs
- [ ] Window remains in foreground
```

## Alternative Strategies

[Other approaches that might work]

### Strategy 2: [Alternative Name]

**When to use:** [Conditions where this approach is better]

**Steps:**
1. [Different approach]
2. [Alternative steps]

**Pros:**
- [Advantage 1]
- [Advantage 2]

**Cons:**
- [Disadvantage 1]
- [Disadvantage 2]

## Related Workflows

[Links to similar or related workflow documents]

- [Workflow Name] - [Brief description of relationship]
- [Another Workflow] - [Why it's related]

## Tool Reference

[Quick reference for key tools used in this workflow]

### Primary Tools

**`desktop_focus_window(app)`**
- Purpose: Bring window to foreground
- When: ALWAYS before interactions
- Platform: Cross-platform

**`desktop_keyboard_type(text)`**
- Purpose: Type text via keyboard
- When: Preferred over clicking UI elements
- Platform: Cross-platform

[Add more tools as needed]

## Troubleshooting Checklist

[Quick diagnostic steps when workflow doesn't work]

1. [ ] Is the target application installed and accessible?
2. [ ] Did you focus the window before interacting?
3. [ ] Are credentials available (if needed)?
4. [ ] Take a screenshot - does the UI match expectations?
5. [ ] Try alternative tools if primary approach fails
6. [ ] Check platform-specific notes
7. [ ] Review common issues section

## Metadata

**Created:** [Date]
**Last Updated:** [Date]
**Tested On:**
- macOS: [Version or "Not tested"]
- Windows: [Version or "Not tested"]
- Linux: [Distribution or "Not tested"]

**Success Rate:** [High/Medium/Low or percentage if known]
**Estimated Time:** [Typical execution time]
**Complexity:** [Simple/Moderate/Complex]

---

## Template Usage Notes

**When creating a new workflow:**
1. Copy this template
2. Replace all [bracketed placeholders] with actual content
3. Remove sections that don't apply
4. Add sections if needed for your specific use case
5. Focus on GUIDANCE and SUGGESTIONS, not rigid commands
6. Include multiple alternatives and strategies
7. Document common issues you encountered

**Remember:**
- Workflows guide the agent, they don't replace its intelligence
- Include WHY, not just WHAT
- Suggest tools, don't mandate them
- Document alternatives for when things don't work
- Think "cookbook" not "robot script"

**Good workflow = Helpful guide for an intelligent agent**
**Bad workflow = Rigid step-by-step automation script**
