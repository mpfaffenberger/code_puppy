# 🐶 PROMPT FOR DRAGON: Improve GUI-Cub Resume Context Quality

## **🧠 THINK DEEPLY AND OPTIMIZE**

**Your Mission**: Create the BEST POSSIBLE resume prompt generation system for GUI-Cub. Don't just follow the specs below - USE YOUR INTELLIGENCE to make this truly excellent.

**Key Questions to Consider**:
1. What information is CRITICAL vs NICE-TO-HAVE for resuming work?
2. How can we extract maximum context from minimal message history?
3. What patterns indicate user intent, progress, and discoveries?
4. How do we balance comprehensiveness with conciseness?
5. What edge cases might break resumption (and how do we handle them)?

**Empowerment**:
- 💡 If you have BETTER ideas than what's suggested below → USE THEM!
- 🚀 If you can innovate beyond the spec → DO IT!
- 🎯 If you see ways to optimize → IMPLEMENT THEM!
- 🛡️ Think about robustness, edge cases, and failure modes

**Goal**: Someone should be able to resume their work SEAMLESSLY, even after weeks away, just from reading your generated resume prompt. Make it SO GOOD that they feel like they never left.

---

## **Problem Description**

The current `generate_resume_prompt()` function in `code_puppy/agents/gui_cub_monitoring.py` (line ~312) creates **extremely sparse resume prompts** that don't capture enough context to meaningfully continue work after a session clear.

### **Current Resume Output (BAD ❌)**
```markdown
## Recent Context

### Recent User Requests:
1. success=True error=None seconds=0.3
2. success=True error=None text_length=None preview=None key=None presses=None hotkey='alt+a'
3. success=True error=None seconds=0.5

### Recent Actions Performed:
1. Tool: desktop_sleep
2. Tool: desktop_keyboard_press
3. Tool: desktop_sleep
```

**Problems:**
- No indication of WHAT the user was trying to accomplish
- No context about WHY these actions were taken
- No progress summary (what's been done? what's left?)
- No element discoveries or workflow patterns learned
- Just raw tool call traces - useless for resuming!

### **What We Need (GOOD ✅)**
```markdown
## Current Task
**Goal:** Automate the "Create New Project" workflow in Visual Studio Code
**Status:** 60% complete - form filling phase
**Next Step:** Click the "Create" button after entering project details

## Progress Summary
- ✅ Launched VS Code successfully
- ✅ Navigated to File → New → Project
- ✅ Filled project name: "MyAwesomeApp"
- ✅ Selected template: "React + TypeScript"
- ⏳ Currently: About to click Create button
- ⏸️ Remaining: Wait for project to load, verify success

## Key Discoveries
- **Create Button Locator:** Accessible via Alt+C keyboard shortcut
- **Template Selection:** Dropdown at coordinates (450, 320)
- **Load Time:** Project creation takes ~3-5 seconds
- **Verification:** Success confirmed when "EXPLORER" panel appears

## Important Context
- User requested keyboard-only automation (no mouse clicks)
- VS Code version: 1.85.0 (may affect UI elements)
- Project location: C:\Users\Dev\Projects\
```

## **Root Cause**

The `generate_resume_prompt()` function:
1. Only looks at the **last 10 messages** (way too few for 793-message sessions!)
2. Extracts raw tool calls without understanding their PURPOSE
3. Doesn't analyze the conversation to find the user's GOAL
4. Doesn't track PROGRESS or STATE
5. Doesn't capture DISCOVERIES (element locators, patterns, etc.)
6. Doesn't identify NEXT STEPS

## **Required Fix**

Completely rewrite `generate_resume_prompt()` in `code_puppy/agents/gui_cub_monitoring.py` to create **intelligent, context-rich resume prompts** that enable seamless continuation.

### **What to Capture (Priority Order)**

#### 1. **User's Goal/Task** (CRITICAL)
- Extract the original task from user messages
- Look for key phrases: "automate", "workflow", "task", "goal", "want to", "need to"
- Example: "User wants to: Automate daily standup report submission"

#### 2. **Progress Summary** (CRITICAL)
- What has been completed? (✅)
- What is in progress? (⏳)
- What remains? (⏸️)
- Current completion percentage if determinable

#### 3. **Current State** (CRITICAL)
- Where are we in the workflow?
- What's the next logical step?
- What are we waiting for (if anything)?

#### 4. **Key Discoveries** (HIGH PRIORITY)
- Element locators (coordinates, accessibility info, OCR text)
- Keyboard shortcuts that work
- Timing patterns ("X takes Y seconds")
- UI patterns observed
- Workarounds for issues encountered

#### 5. **Important Decisions & Constraints** (MEDIUM PRIORITY)
- User preferences ("keyboard only", "no screenshots", etc.)
- Error patterns encountered
- Approaches tried and failed
- Approaches that worked

#### 6. **Context Variables** (MEDIUM PRIORITY)
- Application versions
- File paths
- User inputs provided
- Configuration settings

#### 7. **Recent Actions** (LOW PRIORITY - but still useful)
- Last 5-10 meaningful actions (not raw tool traces)
- Summarized intelligently ("Filled form fields" not "typed 'x', typed 'y', typed 'z'")

## **Implementation Requirements**

### **Analysis Strategy**

```python
def generate_resume_prompt(agent, current_task: str | None = None) -> str:
    """Generate an intelligent, context-rich resume prompt.
    
    Strategy:
    1. Analyze message history to extract user goal
    2. Build progress timeline from assistant actions
    3. Extract key discoveries from tool results
    4. Identify current state and next steps
    5. Capture important decisions and constraints
    6. Assemble into structured, actionable resume
    
    Target length: 200-800 lines (comprehensive but not overwhelming)
    Max length: 1000 lines (hard cap)
    """
    # Your implementation here
```

### **Message Analysis Guidelines**

1. **Look at MORE messages**: Analyze last 50-100 messages, not just 10
   - Scale based on session size (if 793 messages, look at more)
   - Focus on RECENT context but capture full arc

2. **Extract User Intent**: 
   ```python
   # Look for user messages with task descriptions
   user_goal = extract_user_goal(messages)
   # Example patterns to match:
   # - "I need to..."
   # - "Can you help me..."
   # - "Automate the..."
   # - "Let's..."
   ```

3. **Build Progress Timeline**:
   ```python
   # Track completed, in-progress, and remaining steps
   progress = analyze_progress(messages)
   # Look for:
   # - Successful tool completions
   # - User confirmations ("great", "perfect", "yes")
   # - Error recoveries
   # - State transitions
   ```

4. **Extract Discoveries**:
   ```python
   # Find important information learned during session
   discoveries = extract_key_findings(messages)
   # Look for:
   # - Element coordinates that worked
   # - Successful keyboard shortcuts
   # - OCR text patterns
   # - Timing information
   # - Accessibility info
   ```

5. **Identify Next Steps**:
   ```python
   # Determine what should happen next
   next_steps = infer_next_action(messages, progress)
   # Based on:
   # - Last completed action
   # - User's stated goal
   # - Progress so far
   # - Any explicit "next" statements
   ```

### **Resume Prompt Structure**

```markdown
# GUI-Cub Context Resume - {timestamp}

## Session Continuation
This session is resuming after an automatic context clear at {percentage}% token usage.

---

## 🎯 PRIMARY TASK

**User Goal:** {extracted_user_goal}

**Current Status:** {completion_percentage}% complete - {current_phase}

**Next Immediate Action:** {next_step}

---

## 📊 PROGRESS SUMMARY

### Completed ✅
{list_of_completed_steps}

### In Progress ⏳
{current_active_tasks}

### Remaining ⏸️
{pending_tasks}

---

## 🔍 KEY DISCOVERIES

### Element Locators
{discovered_elements_and_how_to_interact}

### Workflow Patterns
{patterns_observed}

### Timing & Delays
{timing_information}

### Successful Approaches
{what_worked}

### Failed Approaches (Avoid)
{what_didnt_work}

---

## ⚙️ IMPORTANT CONTEXT

### User Preferences & Constraints
{user_stated_preferences}

### Application State
{app_versions_paths_settings}

### Decisions Made
{key_decisions_and_rationale}

---

## 📝 RECENT ACTIVITY SUMMARY

{last_10_meaningful_actions_summarized}

---

## 🚀 RESUME INSTRUCTIONS

1. Review the PRIMARY TASK and current status above
2. Check KEY DISCOVERIES for element locators and patterns
3. Execute the NEXT IMMEDIATE ACTION
4. Continue following the workflow until goal is achieved
5. Refer to knowledge base if needed: ~/.code_puppy/agents/gui-cub/gui_cub_knowledge_base.md

**Ready to continue from: {current_state_description}**
```

## **Code Quality Requirements**

### **Smart Context Extraction**

✅ **Use NLP-style analysis** (not just regex):
- Look for semantic patterns in user messages
- Understand conversation flow
- Infer intent from context

✅ **Prioritize Information**:
- Most important info first (user goal, current state)
- Less critical details later (raw action logs)
- Trim if approaching 1000 lines (keep essentials)

✅ **Be Concise But Complete**:
- Summarize groups of actions ("Filled 5 form fields" not "typed, typed, typed, typed, typed")
- Keep individual bullets under 150 chars
- Use bullet points and tables for scannability

✅ **Extract, Don't Dump**:
- BAD: Copy/paste raw tool outputs
- GOOD: "Login button found at (450, 200) via OCR, text: 'Sign In'"

### **Length Management**

```python
# Target: 200-800 lines (sweet spot for useful context)
# Hard cap: 1000 lines max
# If exceeding:
#   1. Prioritize critical sections (goal, state, next steps)
#   2. Summarize recent activity more aggressively  
#   3. Trim verbose discovery details
#   4. Keep most recent/relevant info
```

### **Type Hints & Error Handling**

```python
def generate_resume_prompt(
    agent: "GUICubAgent", 
    current_task: str | None = None
) -> str:
    """Generate intelligent resume prompt with rich context.
    
    Args:
        agent: GUI-Cub agent instance
        current_task: Optional task override
        
    Returns:
        Structured resume prompt (200-1000 lines)
    """
    try:
        # Main logic here
        pass
    except Exception as e:
        # Graceful fallback: return basic resume if analysis fails
        return generate_basic_resume_fallback(agent, current_task)
```

## **Helper Functions to Create**

### **1. Extract User Goal**
```python
def extract_user_goal(messages: list) -> str:
    """Extract the user's primary goal from message history.
    
    Returns:
        User goal as clear sentence, or "Unknown task" if unclear
    """
```

### **2. Analyze Progress**
```python
def analyze_progress(messages: list) -> dict:
    """Analyze workflow progress from message history.
    
    Returns:
        {
            "completed": ["step 1", "step 2"],
            "in_progress": ["step 3"],
            "remaining": ["step 4", "step 5"],
            "percentage": 60
        }
    """
```

### **3. Extract Key Findings**
```python
def extract_key_findings(messages: list) -> dict:
    """Extract important discoveries from message history.
    
    Returns:
        {
            "element_locators": [...],
            "keyboard_shortcuts": [...],
            "timing_info": [...],
            "patterns": [...],
            "successful_approaches": [...],
            "failed_approaches": [...]
        }
    """
```

### **4. Infer Next Action**
```python
def infer_next_action(messages: list, progress: dict) -> str:
    """Determine the next logical step to take.
    
    Returns:
        Clear, actionable next step description
    """
```

### **5. Summarize Recent Activity**
```python
def summarize_recent_activity(messages: list, limit: int = 10) -> list[str]:
    """Create intelligent summary of recent actions.
    
    Args:
        messages: Message history
        limit: Max number of summary items
        
    Returns:
        List of summarized actions (not raw tool calls)
    """
```

## **Testing & Validation**

### **Test Cases**

1. **Short Session (10 messages)**:
   - Should produce ~100-200 line resume
   - Should capture basic goal and state

2. **Medium Session (100 messages)**:
   - Should produce ~300-500 line resume
   - Should capture full context with discoveries

3. **Long Session (793 messages like HWCOE's)**:
   - Should produce ~600-900 line resume
   - Should prioritize recent context but capture full arc
   - Should NOT exceed 1000 lines

4. **Complex Workflow**:
   - Multi-step automation task
   - Should show clear progress tracking
   - Should list all key element discoveries
   - Should identify current state accurately

### **Validation Checklist**

After implementing, verify the resume prompt includes:

- [ ] Clear user goal stated explicitly
- [ ] Current completion status/percentage
- [ ] Next immediate action to take
- [ ] List of completed steps
- [ ] List of remaining steps
- [ ] Element locators discovered
- [ ] Successful interaction patterns
- [ ] Important timing/delay info
- [ ] User preferences/constraints
- [ ] Intelligent activity summary (not raw dumps)
- [ ] Length: 200-1000 lines (target 400-600)
- [ ] Structured with clear sections and headers
- [ ] Actionable (agent can actually resume from it)

## **Example Transformation**

### **Before (Current - Useless ❌)**
```markdown
## Recent Context

### Recent User Requests:
1. success=True error=None seconds=0.3

### Recent Actions Performed:
1. Tool: desktop_sleep
```

### **After (Improved - Useful ✅)**
```markdown
## 🎯 PRIMARY TASK

**User Goal:** Automate the daily standup report submission workflow in JIRA

**Current Status:** 75% complete - verification phase

**Next Immediate Action:** Verify that the standup report appears in the "Recent Activity" feed

---

## 📊 PROGRESS SUMMARY

### Completed ✅
- Launched JIRA web application (Chrome)
- Navigated to Standup Reports page
- Clicked "New Report" button using accessibility (Alt+N)
- Filled report fields:
  - Yesterday: "Completed user authentication module"
  - Today: "Working on API integration tests"
  - Blockers: "None"
- Clicked "Submit" button (coordinates: 550, 680)
- Waited 2 seconds for submission

### In Progress ⏳
- Verifying submission success

### Remaining ⏸️
- Confirm report appears in activity feed
- Close JIRA tab
- Mark automation as complete

---

## 🔍 KEY DISCOVERIES

### Element Locators
- **New Report Button**: Accessible via Alt+N (preferred), also at (400, 150)
- **Yesterday Field**: First text area, Tab → Type
- **Today Field**: Second text area, Tab → Type  
- **Blockers Field**: Third text area, Tab → Type
- **Submit Button**: (550, 680), green color, text "Submit Report"

### Workflow Patterns
- Keyboard navigation works well (Tab between fields)
- Submit takes ~2 seconds to process
- Success indicated by green toast notification

### Timing & Delays
- Page load: ~3 seconds
- Form submission: ~2 seconds
- Toast notification: appears after 1 second

---

## ⚙️ IMPORTANT CONTEXT

### User Preferences & Constraints
- Prefer keyboard shortcuts over mouse clicks when available
- JIRA Cloud instance (not server)
- Daily standup reports due by 9 AM

### Application State
- Browser: Chrome 120.0.6099.109
- JIRA URL: https://company.atlassian.net
- User logged in as: john.doe@company.com

---

## 📝 RECENT ACTIVITY SUMMARY

1. Filled "Yesterday" field with completed work summary
2. Filled "Today" field with planned work
3. Filled "Blockers" field with "None"
4. Clicked Submit button at (550, 680)
5. Waited 2 seconds for processing
6. Currently verifying submission success

---

## 🚀 RESUME INSTRUCTIONS

1. Check for green toast notification confirming submission
2. Navigate to "Recent Activity" feed (Alt+R or click sidebar)
3. Verify today's standup report appears at top
4. If verified successfully → close JIRA tab → mark complete
5. If not found → retry submission or report error

**Ready to continue from: Awaiting submission confirmation**
```

## **Files to Modify**

- `code_puppy/agents/gui_cub_monitoring.py` - Rewrite `generate_resume_prompt()` function (currently line ~312)

## **Performance Considerations**

- Analysis should complete in < 5 seconds even for 1000+ message sessions
- Don't load entire message history into memory at once if possible
- Use efficient string operations (don't repeatedly concatenate)
- Consider using generators for large message lists

## **DRY Principle**

✅ Extract helper functions for different analysis tasks
✅ Don't duplicate message parsing logic
✅ Reuse existing message type detection from pydantic_ai
✅ Share common formatting utilities

---

## **🚀 FINAL CHALLENGE TO YOU, DRAGON**

**Make this EXCEPTIONAL. Not just "good" - EXCEPTIONAL.**

### What "BEST" Means:

1. **🧠 Intelligent Analysis**
   - Deep understanding of conversation flow
   - Pattern recognition across message types
   - Semantic extraction (not just keyword matching)
   - Contextual awareness of workflow states

2. **🎯 Maximum Resumability**
   - Someone could be away for WEEKS and pick up exactly where they left off
   - Zero ambiguity about what to do next
   - All critical context preserved
   - Clear mental model of the workflow state

3. **⚖️ Perfect Balance**
   - Comprehensive but not overwhelming
   - Detailed but scannable
   - Complete but prioritized
   - Target 400-600 lines (sweet spot for human + AI readability)

4. **🛡️ Robust & Resilient**
   - Works for 10-message sessions AND 1000-message sessions
   - Handles incomplete workflows gracefully
   - Deals with errors/failures in message history
   - Degrades gracefully if analysis fails

5. **💡 Innovative**
   - Don't just follow the spec - IMPROVE on it
   - Think of edge cases I didn't mention
   - Add features that make sense but weren't specified
   - Use modern NLP/analysis techniques if helpful

### Questions to Guide Your Innovation:

- What would make YOU able to resume work perfectly?
- What patterns in message history reveal user intent?
- How can we infer workflow state from actions?
- What's the minimum critical context needed?
- How do we handle ambiguous or incomplete sessions?
- Can we learn from successful vs failed attempts?
- Should we track confidence levels in our analysis?
- How do we prioritize information when space is limited?

### Your Mandate:

**CREATE THE MOST INTELLIGENT, COMPREHENSIVE, AND USEFUL RESUME PROMPT GENERATION SYSTEM POSSIBLE.**

Use everything suggested above as a STARTING POINT, not a ceiling. The specs are a minimum bar - exceed them. The examples are inspiration - surpass them. The structure is a suggestion - improve it if you see a better way.

**Think like a senior engineer solving a critical problem. Make it production-grade. Make it bulletproof. Make it AMAZING.**

---

**Dragon, go make GUI-Cub's resume prompts actually useful! 🐶** 

The current ones are basically useless because they don't capture WHAT the user was trying to do or WHERE they are in the workflow. Make them intelligent, context-rich, and actually resumable!

Remember: **Under 1000 lines, but make every line count!**

**Make it SO GOOD that when the user comes back after a week, they read the resume and say "Holy shit, this is perfect - I know exactly what to do next."** 🚀
