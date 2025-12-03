# GUI-Cub FAQ & Quick Reference

This document provides canned responses for common questions about GUI-Cub.
The `gui_cub_faq` tool uses this content to provide helpful, consistent answers.

---

## What can you do?

**Response:**

Im GUI-Cub 🐻, your desktop automation companion! Heres what I can do:

### Core Capabilities
- **Automate any desktop app** - Click buttons, fill forms, navigate menus
- **Visual understanding** - I can see your screen via screenshots and OCR
- **Smart element detection** - Find UI elements by text, role, or accessibility labels
- **Keyboard & mouse control** - Type text, use shortcuts, click anywhere
- **Window management** - Focus, minimize, maximize, and arrange windows
- **Workflow learning** - I remember successful automation patterns for reuse

### Interaction Methods (in order of preference)
1. **Keyboard shortcuts** - Fastest and most reliable
2. **Accessibility API** - Click elements by their semantic meaning
3. **OCR text search** - Find and click visible text
4. **Visual Q&A** - Last resort for purely visual elements

### Platform Support
- **macOS**: Full support with native automation APIs
- **Windows**: Full support with UI Automation framework
- **Linux**: Basic support (keyboard/mouse only)

### Example Tasks
- Open Calculator and compute 15% of 847
- Find all PDFs in Downloads and rename them by date
- Fill out this web form with my saved info
- Take a screenshot of the error message
- Navigate to Settings > Privacy > Location Services

---

## How does this agent work?

**Response:**

GUI-Cub works by combining several technologies to see and interact with your desktop:

### The Vision Layer
1. **Screenshots** - Capture whats on screen (like taking a photo)
2. **OCR** - Extract text from screenshots (reading the "photo")
3. **VQA** - Ask questions about whats visible (Where is the Submit button?)

### The Interaction Layer
1. **Accessibility API** - Query the systems UI element tree
2. **Mouse control** - Move cursor and click at precise coordinates
3. **Keyboard control** - Type text and trigger shortcuts
4. **Window management** - Focus, resize, and position windows

### The Intelligence Layer
1. **Tier system** - I try fast methods first, expensive ones last
2. **Workflows** - I save successful automation patterns for reuse
3. **Knowledge base** - I remember what worked and what didnt
4. **Calibration** - I adapt to your screens resolution and scaling

### Workflow
```
1. Check for existing workflows (reuse knowledge)
2. Focus the target window
3. Take a screenshot to understand the current state
4. Explore UI elements via accessibility tree
5. Execute actions using the tier system
6. Verify each action succeeded
7. Save workflow if I learned something new
```

---

## What are workflows?

**Response:**

Workflows are saved automation patterns that I can reuse:

### What Gets Saved
- Step-by-step instructions for a task
- Which interaction tier worked best
- App-specific quirks and timing requirements
- What failed (so I dont repeat mistakes)

### Where They Live
```
~/.code_puppy/gui_cub/workflows/
├── calculator_basic_math.yaml
├── chrome_new_incognito.yaml
└── vscode_open_terminal.yaml
```

### How I Use Them
1. Before ANY task, I check `gui_cub_list_workflows()`
2. If a relevant workflow exists, I read it for guidance
3. I adapt the workflow to current conditions (not rigid scripts)
4. If I learn something new, I update or create a workflow

### Commands
- `gui_cub_list_workflows()` - See all saved workflows
- `gui_cub_read_workflow(name)` - Read a specific workflow
- `gui_cub_save_workflow(name, content)` - Save a new workflow

---

## What is the tier system?

**Response:**

The tier system is my strategy for interacting with UI elements efficiently:

### Interaction Tiers (Fastest → Most Expensive)
| Tier | Method | Speed | When to Use |
| ---- | ----------------- | ----------------- | ---------------------------------------- |
| 1️⃣ | **Keyboard** | ~50 tokens | Shortcuts, Tab, Enter - ALWAYS try first |
| 2️⃣ | **Accessibility** | ~100-500 tokens | Click by element name/role - reliable |
| 3️⃣ | **OCR** | ~500-2000 tokens | Find visible text - fallback |
| 4️⃣ | **VQA** | ~1000-3000 tokens | Visual-only elements - LAST RESORT |

### Why This Matters
- **Token efficiency** - Lower tiers save API costs
- **Speed** - Keyboard is instant, VQA takes seconds
- **Reliability** - Accessibility API is ±1px accurate, OCR can drift

### Example
```
Task: Click Save button
1. Try Ctrl+S (Tier 1) ✓ Done in 50 tokens!
If fails...
2. Find Save via accessibility tree (Tier 2)
If fails...
3. OCR for Save text (Tier 3)
If fails...
4. VQA: Where is the Save button? (Tier 4)
```

---

## What is calibration?

**Response:**

Calibration ensures I click in the right place on YOUR screen:

### Why Its Needed
- Different displays have different resolutions (1080p, 4K, Retina)
- OS scaling affects coordinate systems (100%, 125%, 200%)
- macOS Retina displays use logical vs physical pixels

### What Gets Calibrated
1. **Screen resolution** - Actual pixel dimensions
2. **Scaling factor** - System DPI/scaling setting
3. **Coordinate mapping** - How to translate between coordinate systems

### When It Happens
- **Automatically** on first GUI-Cub use
- **Manually** via `desktop_grid_calibration()` if clicks are off

### Stored Config
```
~/.code_puppy/gui_cub/config.yaml
```

---

## Why do you check workflows first?

**Response:**

I check workflows FIRST because:
1. **Efficiency** - Why rediscover what I already know?
2. **Reliability** - Saved workflows have been tested
3. **Speed** - Reusing patterns is faster than exploring
4. **Learning** - Workflows capture app-specific quirks

### The Rule
> Before ANY task, call `gui_cub_list_workflows()` - NO EXCEPTIONS

Even for simple tasks like "open calculator" - I check first. There might be:
- A known timing issue
- A preferred interaction tier
- A keyboard shortcut I learned before

---

## What can you NOT do?

**Response:**

Heres what I **cannot** do (important boundaries!):

### Hard Limits
- ❌ **OCR terminals** - Security risk (contains secrets/passwords)
- ❌ **CAPTCHAs** - By design, these block automation
- ❌ **DRM-protected content** - Cant screenshot some video players
- ❌ **Games with anti-cheat** - Blocked by detection systems
- ❌ **Invisible/background windows** - Need focused, visible UI

### Soft Limits
- ⚠️ **Dynamic UIs** - Rapidly changing content is hard to track
- ⚠️ **Custom UI frameworks** - Non-standard accessibility may fail
- ⚠️ **Very small text** - OCR struggles below ~8pt font
- ⚠️ **Low contrast UIs** - Hard to detect element boundaries

### Platform Gaps
- **Linux** - No native UI automation (keyboard/mouse only)
- **Remote desktops** - May have latency/resolution issues
- **VMs** - Coordinate mapping can be tricky

---

## How do I get started?

**Response:**

Getting started is easy! Just tell me what you want to automate:

### Quick Start
1. Switch to GUI-Cub: `/agent gui-cub`
2. Tell me what to do: "Open Calculator and add 5 + 3"
3. Ill handle calibration, exploration, and execution

### Tips for Best Results
- **Be specific** - Click the blue Submit button > Submit
- **Name the app** - In Chrome, open a new tab > Open a tab
- **State your goal** - I want to end up with a PDF helps me plan

### First-Time Setup
- Calibration runs automatically on first use
- Grant accessibility permissions when prompted
    - macOS: System Preferences > Privacy > Accessibility
    - Windows: Usually works out of the box

---

## What platforms do you support?

**Response:**

### Full Support
🟢 **macOS** (10.14+)
- Native AppleScript integration
- Full Accessibility API support
- Dock and menu bar automation
- `mac_launch_app()` for reliable app launching

**Windows** (10/11)
- UI Automation framework
- Taskbar and system tray access
- PowerShell integration
- `windows_automation` tools

### Basic Support
🟡 **Linux**
- Screenshot capture
- OCR text extraction
- Keyboard input (via xdotool if available)
- Mouse control (via xdotool if available)
- ❌ No native accessibility API support

### Not Supported
🔴
- ChromeOS
- Mobile devices (iOS, Android)
- Headless/server environments

---

## How do I report bugs or issues?

**Response:**

If something goes wrong:

### Quick Fixes
1. **Clicks are off?** Run `desktop_grid_calibration()`
2. **Cant find element?** Try deeper search: `windows_search_elements(query, max_depth=25)`
3. **App not responding?** Check if window is focused: `desktop_focus_window(app)`

### Debugging Tools
- `save_debug_screenshot()` - Capture current state with annotations
- `desktop_click_debugging()` - Analyze why a click failed
- `gui_cub_debug()` - View current configuration and state

### Reporting
1. Describe what you were trying to do
2. Share the error message (if any)
3. Include a debug screenshot if relevant
4. Mention your OS and screen resolution

---

## Whats the knowledge base?

**Response:**

The knowledge base is my persistent memory across sessions:

### What It Stores
- Discoveries about apps and their quirks
- What interaction methods worked/failed
- Timing requirements and delays
- Links to related workflows

### Location
```
~/.code_puppy/gui_cub/gui_cub_knowledge_base.md
```

### How I Use It
- Checked when exploring new apps
- Referenced when troubleshooting
- Updated when I learn something new

### Example Entry
```markdown
## 2025-12-03 | Calculator app automation
**Discovery:** Requires 0.3s delay between button clicks
**What worked:** Accessibility API with AXButton elements
**What failed:** OCR unreliable for small number buttons
**Tags:** #calculator #accessibility #timing
```

---

## METADATA
_This file is used by the `gui_cub_faq` tool to provide canned responses._
_Last updated: 2025-12-03_
_Maintainer: Code Puppy Team_
