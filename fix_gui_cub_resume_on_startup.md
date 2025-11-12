# 🐶 PROMPT FOR DRAGON: Fix GUI-Cub Session Resume on Startup

## **Problem Description**

GUI-Cub's autonomous context management (`auto_save_and_resume` at 85% token usage) successfully:
1. ✅ Saves session snapshots to `~/.code_puppy/agents/gui-cub/sessions/session_YYYYMMDD_HHMMSS.md`
2. ✅ Generates and saves resume prompt to `~/.code_puppy/agents/gui-cub/resume_prompt.md`
3. ✅ Clears message history to free up tokens
4. ✅ Loads the resume prompt back into memory immediately after clearing

**BUT** when GUI-Cub is **restarted fresh** (e.g., user exits and comes back later), it does NOT automatically load the saved `resume_prompt.md` file. This means the context is lost on restart, which defeats the purpose of saving it!

## **Root Cause**

In `code_puppy/agents/agent_gui_cub.py`, the `__init__` method (line 17-22) initializes the agent but **never checks for existing resume prompts** to restore from:

```python
def __init__(self):
    """Initialize GUI-Cub agent with token monitoring."""
    super().__init__()
    # TIER 4: Proactive token monitoring
    self.token_monitor = TokenMonitor(context_limit=128000)
    self._last_token_check = 0
    # ❌ MISSING: Check for and load resume_prompt.md if it exists!
```

## **Required Fix**

Add startup resume logic to the `__init__` method that:

1. **Checks if `resume_prompt.md` exists** in `~/.code_puppy/agents/gui-cub/`
2. **If it exists**, read its content and append it as the first message to the agent's message history
3. **Display a clear notification** to the user that the session was auto-resumed from the saved state
4. **Handle errors gracefully** - if the file doesn't exist or can't be read, just start fresh (don't crash)

## **Implementation Details**

**Location**: `code_puppy/agents/agent_gui_cub.py`, in the `__init__` method

**Suggested approach**:
```python
def __init__(self):
    """Initialize GUI-Cub agent with token monitoring."""
    super().__init__()
    # TIER 4: Proactive token monitoring
    self.token_monitor = TokenMonitor(context_limit=128000)
    self._last_token_check = 0
    
    # TIER 4.5: Auto-resume from saved session if available
    self._try_resume_from_saved_session()

def _try_resume_from_saved_session(self):
    """Try to load and resume from saved resume_prompt.md if it exists."""
    from pathlib import Path
    from pydantic_ai.messages import ModelRequest, TextPart
    from .gui_cub_monitoring import get_gui_cub_base_dir
    from rich.console import Console
    
    console = Console()
    
    try:
        base_dir = get_gui_cub_base_dir()
        resume_path = base_dir / "resume_prompt.md"
        
        if resume_path.exists():
            # Read the saved resume prompt
            with open(resume_path, "r", encoding="utf-8") as f:
                resume_content = f.read()
            
            # Append it as the first message in history
            resume_message = ModelRequest([TextPart(resume_content)])
            self.append_to_message_history(resume_message)
            
            # Notify the user
            console.print(
                "\n[bold green]✅ SESSION RESUMED FROM SAVED STATE[/bold green]\n"
                "[dim]Loaded context from: ~/.code_puppy/agents/gui-cub/resume_prompt.md[/dim]\n"
            )
            
            # Update token count
            token_count = sum(
                self.estimate_tokens_for_message(msg) 
                for msg in self.get_message_history()
            )
            self.token_monitor.update(token_count)
            
    except Exception as e:
        # Silently fail - just start fresh if resume fails
        # Don't spam user with errors on every startup
        pass
```

## **Key Requirements**

1. ✅ **Reuse existing helper**: Use `get_gui_cub_base_dir()` from `gui_cub_monitoring.py` to get the correct path (already cross-platform)
2. ✅ **Use proper message format**: Use `ModelRequest([TextPart(content)])` to match pydantic_ai message structure
3. ✅ **Silent fallback**: If resume file doesn't exist or fails to load, just start fresh (don't crash or spam errors)
4. ✅ **User notification**: Print a clear message when session is auto-resumed so user knows what happened
5. ✅ **Update token count**: After loading resume, update the token monitor with the new token count

## **Testing Instructions**

After implementing the fix, test it like this:

1. **Start GUI-Cub** and let it hit the 85% threshold (or manually trigger `auto_save_and_resume`)
2. **Verify files were created**:
   - `~/.code_puppy/agents/gui-cub/resume_prompt.md` should exist
   - `~/.code_puppy/agents/gui-cub/sessions/session_YYYYMMDD_HHMMSS.md` should exist
3. **Exit GUI-Cub completely** (close the session)
4. **Restart GUI-Cub**
5. **Expected behavior**:
   - Should print: `✅ SESSION RESUMED FROM SAVED STATE`
   - Should show loaded context from resume_prompt.md
   - Token count should reflect the loaded resume content
6. **Test fresh start**: Delete `resume_prompt.md` and restart GUI-Cub
   - Should start fresh without errors

## **Files to Modify**

- `code_puppy/agents/agent_gui_cub.py` - Add `_try_resume_from_saved_session()` method and call it from `__init__`

## **DRY Principle Check**

✅ Reuse `get_gui_cub_base_dir()` from `gui_cub_monitoring.py` (don't duplicate path logic)  
✅ Reuse `ModelRequest` and `TextPart` from pydantic_ai (match existing message format)  
✅ Reuse agent's existing `append_to_message_history()` method  
✅ Reuse agent's existing `estimate_tokens_for_message()` method  

## **Code Quality Requirements**

- Keep new method under 50 lines (simple and focused)
- Type hints on everything
- Cross-platform path handling (already handled by `get_gui_cub_base_dir()`)
- Graceful error handling (silent fail, don't crash)
- Clear user messaging (let them know when resume happens)

---

**Dragon, go fix this! 🐶** Make GUI-Cub properly resume sessions on startup by loading the saved `resume_prompt.md` file. The user is frustrated because their context got wiped when it should have been restored. Let's make this seamless!
