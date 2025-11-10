# VQA Architecture Decision: Separate Agent vs Sub-Agent Invocation

**Question:** Should we use a separate pydantic-ai `Agent` instance (current) or invoke a gui-cub sub-agent for vision analysis?

**Date:** 2025-01-XX  
**Status:** Decision needed

---

## Option A: Separate pydantic-ai Agent (Current Approach) ✅

### Current Implementation

```python
# code_puppy/tools/gui_cub/vqa_desktop.py

@lru_cache(maxsize=1)
def _load_desktop_vqa_agent(model_name: str) -> Agent[None, DesktopVisualAnalysisResult]:
    """Create a cached agent instance for desktop visual analysis."""
    return Agent(
        model=model,
        instructions="You are a desktop visual analysis specialist...",
        output_type=DesktopVisualAnalysisResult,
        retries=2,
    )

def run_desktop_vqa_analysis(question: str, image_bytes: bytes) -> DesktopVisualAnalysisResult:
    agent = _get_desktop_vqa_agent()
    result = agent.run_sync([question, BinaryContent(data=image_bytes)])
    return result.output  # Returns just the structured output
```

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│ Main GUI-Cub Agent (conversation with user)                │
│                                                             │
│ Message history: [                                         │
│   "User: Click Submit",                                    │
│   "Agent: I'll take a screenshot...",                      │
│   ...                                                       │
│ ]                                                           │
│                                                             │
│ Tool call: desktop_screenshot_and_analyze(...)             │
│   ↓                                                         │
│   ┌───────────────────────────────────────────────┐       │
│   │ NEW pydantic-ai Agent instance                │       │
│   │ (created via _load_desktop_vqa_agent)         │       │
│   │                                                │       │
│   │ Message history: [                             │       │
│   │   ModelRequest([                               │       │
│   │     TextPart("Where is Submit button?"),      │       │
│   │     ImagePart(image_bytes)                     │       │
│   │   ])                                           │       │
│   │ ]                                              │       │
│   │ ↓                                              │       │
│   │ agent.run_sync() → Makes ONE model call        │       │
│   │ ↓                                              │       │
│   │ Returns: DesktopVisualAnalysisResult {         │       │
│   │   answer: "Bottom-right at (850, 650)",       │       │
│   │   confidence: 0.95,                            │       │
│   │   observations: "Blue button"                  │       │
│   │ }                                              │       │
│   └───────────────────────────────────────────────┘       │
│   ↓                                                         │
│ Returns structured output to main agent                    │
│                                                             │
│ Main agent continues with: "Found Submit at (850, 650)"    │
└─────────────────────────────────────────────────────────────┘
```

### Characteristics

**Message History:**
- ✅ **Isolated** - VQA agent has its own message history
- ✅ **Stateless** - Each call starts fresh (no memory between calls)
- ✅ **Single turn** - One question + image in, one answer out
- ✅ **No pollution** - Image never touches main agent's context

**Performance:**
- ✅ **Fast** - Direct model call, no middleware
- ✅ **Cached** - Agent instance reused (@lru_cache)
- ✅ **Lightweight** - Minimal overhead
- ✅ **Synchronous** - Simple blocking call (wrapped in thread if needed)

**Complexity:**
- ✅ **Simple** - Just create Agent, call run_sync()
- ✅ **Type-safe** - Structured output (DesktopVisualAnalysisResult)
- ✅ **Self-contained** - No external dependencies
- ✅ **Testable** - Easy to mock/test

**Token Usage:**
- ✅ **Minimal** - Only question + image in VQA context
- ✅ **No history accumulation** - Each call is independent
- ✅ **Predictable** - Same token cost every time

### Pros

1. **Perfect for stateless vision analysis** ✅
   - Each screenshot is analyzed independently
   - No memory of previous screenshots needed
   - Clean separation of concerns

2. **Minimal token overhead** ✅
   - VQA context: ~120k (image) + ~50 (question) = 120,050 tokens
   - Main context: +0 tokens (image not included)
   - No history accumulation

3. **Simple implementation** ✅
   - ~50 lines of code
   - No routing/session management
   - Direct model call

4. **Fast execution** ✅
   - No middleware overhead
   - Cached agent instance
   - Direct API call to model

5. **Type-safe structured output** ✅
   - Pydantic model validation
   - Compile-time type checking
   - Auto-retry on validation failures

### Cons

1. **No conversation context** (but this is actually a pro for vision analysis!)
   - Can't ask follow-up questions about same image
   - Each analysis is independent
   - (This is desired behavior for stateless vision tasks)

2. **Limited to single model call**
   - No multi-turn refinement
   - Can't use tools within VQA
   - (Again, not needed for vision analysis)

3. **Separate from sub-agent ecosystem**
   - Not discoverable via `list_agents()`
   - Different invocation pattern
   - (But it's an internal implementation detail, not a user-facing agent)

---

## Option B: Sub-Agent Invocation (Alternative)

### Hypothetical Implementation

```python
# Would need to create a new sub-agent definition
# code_puppy/agents/gui_cub_vqa_agent.py

def create_gui_cub_vqa_agent():
    return Agent(
        model=get_current_model(),
        instructions="You are a desktop visual analysis specialist...",
        # ... tools, result_type, etc.
    )

# In tools:
async def desktop_screenshot_and_analyze(question: str, ...) -> VQAResult:
    # Invoke via agent infrastructure
    result = await invoke_agent(
        agent_name="gui-cub-vqa",
        prompt=f"Analyze this screenshot: {question}\n[Image: base64_encoded]",
        session_id=None,  # New session each time (stateless)
    )
    return parse_vqa_result(result.response)
```

### How It Would Work

```
┌─────────────────────────────────────────────────────────────┐
│ Main GUI-Cub Agent                                          │
│                                                             │
│ Tool call: desktop_screenshot_and_analyze(...)             │
│   ↓                                                         │
│   Calls: invoke_agent("gui-cub-vqa", prompt, session_id=None)
│   ↓                                                         │
│   ┌───────────────────────────────────────────────┐       │
│   │ Agent Manager                                  │       │
│   │   ↓ load_agent("gui-cub-vqa")                 │       │
│   │   ↓ Create new session                         │       │
│   │   ↓ Initialize message history                 │       │
│   │   ↓                                            │       │
│   │   ┌─────────────────────────────────────┐     │       │
│   │   │ GUI-Cub VQA Sub-Agent                │     │       │
│   │   │                                      │     │       │
│   │   │ Session: "gui-cub-vqa-session-1"     │     │       │
│   │   │ Message history: [                   │     │       │
│   │   │   "System: You are a VQA specialist",│     │       │
│   │   │   "User: Analyze this screenshot..." │     │       │
│   │   │   + [Image data]                     │     │       │
│   │   │ ]                                    │     │       │
│   │   │ ↓                                    │     │       │
│   │   │ Agent processes with tools available │     │       │
│   │   │ ↓                                    │     │       │
│   │   │ Returns: "Button at (850, 650)"      │     │       │
│   │   └─────────────────────────────────────┘     │       │
│   │   ↓                                            │       │
│   │ Session saved to state management              │       │
│   │ (discarded if session_id=None auto-generated)  │       │
│   └───────────────────────────────────────────────┘       │
│   ↓                                                         │
│ Returns AgentInvokeOutput.response to main agent           │
│                                                             │
│ Main agent parses response and continues                   │
└─────────────────────────────────────────────────────────────┘
```

### Characteristics

**Message History:**
- ❌ **Potentially persistent** - Session could accumulate history
- ⚠️ **Stateful by default** - Requires session_id=None for stateless
- ⚠️ **Multi-turn capable** - Could ask follow-ups (not needed)
- ✅ **Isolated from main agent** - Still separate context

**Performance:**
- ❌ **Slower** - Goes through agent manager, session management
- ❌ **More overhead** - Loading, routing, state management
- ⚠️ **Session cleanup** - Need to manage session lifecycle
- ❌ **Async required** - More complex execution model

**Complexity:**
- ❌ **More complex** - Agent definition, routing, session management
- ❌ **String-based communication** - Parse prompt, parse response
- ❌ **New agent definition** - Need to create and maintain sub-agent
- ⚠️ **Less type-safe** - String responses vs structured output

**Token Usage:**
- ✅ **Isolated** - Still separate from main agent
- ⚠️ **System prompt overhead** - Sub-agent has its own system message
- ⚠️ **Potential accumulation** - If session is accidentally reused

### Pros

1. **Discoverable** ✅
   - Shows up in `list_agents()`
   - Consistent with other sub-agents
   - Could be invoked directly by users

2. **Can use tools** ✅
   - VQA agent could have its own tools
   - More powerful analysis possible
   - (But vision analysis doesn't need tools)

3. **Conversation capability** ⚠️
   - Could ask follow-up questions about same image
   - Multi-turn refinement possible
   - (Not needed for current use case)

4. **Consistent pattern** ✅
   - Same as other sub-agents
   - Familiar invocation pattern
   - Unified agent ecosystem

### Cons

1. **Unnecessary complexity** ❌
   - Need agent definition file
   - Session management overhead
   - State management not needed

2. **Performance overhead** ❌
   - Agent loading
   - Session creation/lookup
   - State serialization
   - ~100-200ms extra latency

3. **Less type-safe** ❌
   - String-based communication
   - Need to parse responses
   - No compile-time validation

4. **Token overhead** ⚠️
   - Sub-agent system prompt (~200-500 tokens)
   - Session management metadata
   - Potential history accumulation

5. **Overkill for stateless vision** ❌
   - Don't need conversation memory
   - Don't need tools
   - Don't need multi-turn capability
   - Just need: image + question → answer

---

## Comparison Table

| Aspect | Separate Agent ✅ | Sub-Agent Invocation |
|--------|-------------------|----------------------|
| **Use Case Fit** | Perfect (stateless) | Overkill |
| **Complexity** | Low (~50 LOC) | High (~200+ LOC) |
| **Performance** | Fast (direct call) | Slower (+100-200ms) |
| **Token Overhead** | Minimal (0 in main) | Higher (system prompt) |
| **Type Safety** | Excellent (Pydantic) | Poor (strings) |
| **State Management** | None needed | Unnecessary overhead |
| **Discoverability** | Internal only | In list_agents() |
| **Conversation Memory** | No (desired) | Yes (not needed) |
| **Implementation** | ✅ Done | Need to build |
| **Maintenance** | Simple | Complex |

---

## Decision Matrix

### When to Use Separate pydantic-ai Agent (Current Approach) ✅

**Use when:**
- ✅ Task is **stateless** (each call independent)
- ✅ Need **structured output** (Pydantic validation)
- ✅ Want **fast execution** (no middleware)
- ✅ Don't need conversation history
- ✅ Don't need tools within the analysis
- ✅ Simple input → output mapping

**Examples:**
- Vision analysis (current use case) ✅
- OCR processing ✅
- Image classification ✅
- Quick structured data extraction ✅

### When to Use Sub-Agent Invocation

**Use when:**
- Need **conversation memory** (multi-turn)
- Need **tools** within sub-agent
- Want **discoverability** (user-facing)
- Require **session persistence**
- Complex **multi-step reasoning**

**Examples:**
- Code review (iterative feedback)
- Research assistant (follow-up questions)
- Pair programming (ongoing conversation)
- Document analysis with tool use

---

## Recommendation: Keep Separate Agent ✅

### Verdict

**Keep the current approach** (separate pydantic-ai Agent) for vision analysis because:

1. **Perfect fit for use case** ✅
   - Vision analysis is inherently stateless
   - Each screenshot is independent
   - No conversation needed

2. **Optimal performance** ✅
   - Fastest possible execution
   - No unnecessary overhead
   - Direct model call

3. **Simplest implementation** ✅
   - Already working
   - Minimal code
   - Easy to understand

4. **Best type safety** ✅
   - Structured output guaranteed
   - Compile-time validation
   - No parsing errors

5. **Minimal token cost** ✅
   - No system prompt overhead
   - No session management
   - No history accumulation

### When to Reconsider

**Consider sub-agent invocation IF:**

1. **Need conversation about images**
   - "What else do you see in that screenshot?"
   - "Can you look more closely at the top-left?"
   - Multi-turn image analysis

2. **Need tools within VQA**
   - VQA agent needs to call other tools
   - Complex analysis pipelines
   - Tool chaining required

3. **User-facing VQA agent**
   - Users want to chat directly with VQA agent
   - Need discoverability via list_agents()
   - Standalone VQA service

**Current reality:** None of these apply. Vision analysis is:
- Single-turn: "Where is X?" → "At (x, y)"
- Stateless: Each screenshot independent
- Internal: Tool for main agent, not user-facing

---

## Implementation Recommendations

### Keep Current Architecture ✅

```python
# Current (GOOD):
async def desktop_screenshot_and_analyze(
    question: str,
    include_image: bool = False,
    ...
) -> VQAResult:
    # 1. Capture screenshot
    image = capture_screen(...)
    
    # 2. Analyze via separate Agent (stateless, fast)
    vqa_agent = _get_desktop_vqa_agent()  # Cached
    analysis = vqa_agent.run_sync([
        question,
        BinaryContent(data=image)
    ])
    
    # 3. Return structured result (no image)
    return VQAResult(
        answer=analysis.answer,
        confidence=analysis.confidence,
        screenshot_path=save_to_disk(image),
        image_base64=base64 if include_image else None,
    )
```

### Enhance Current Approach

**Add these improvements:**

1. **Make image optional in result** (Priority 1)
   ```python
   include_image: bool = False  # Don't bloat main context
   ```

2. **Add debug mode for troubleshooting**
   ```python
   debug: bool = False  # Include image + VQA raw response
   ```

3. **Track VQA token usage**
   ```python
   # Log VQA tokens separately from main agent
   vqa_tokens = estimate_tokens(question + image_encoding)
   emit_info(f"VQA used {vqa_tokens} tokens (isolated context)")
   ```

4. **Support multiple VQA models**
   ```python
   # Already implemented via get_vqa_model_name()
   # Can use cheap vision model (gpt-4o-mini) for VQA
   # While main agent uses smarter model (o1-mini)
   ```

---

## Hybrid Approach (Future Consideration)

### If We Ever Need Conversational Vision

**Scenario:** User wants multi-turn image analysis

```python
# User interaction:
User: "Take a screenshot and tell me what you see"
Agent: [Uses current stateless VQA] "I see a form with Name and Email fields"

User: "Look more closely at the top-left corner"
Agent: [Needs to reference same screenshot!]
```

**Solution:** Hybrid approach

```python
async def desktop_screenshot_analyze_conversational(
    question: str,
    session_id: str,  # Conversation ID
    include_previous_screenshots: bool = False,
) -> VQAResult:
    # Use sub-agent invocation for multi-turn
    result = await invoke_agent(
        agent_name="gui-cub-vqa-conversational",
        prompt=question,
        session_id=session_id,  # Maintain conversation
    )
    return result

# Meanwhile, keep stateless version for automation:
async def desktop_screenshot_analyze(
    question: str,
) -> VQAResult:
    # Current approach - stateless, fast
    return run_desktop_vqa_analysis(question, image)
```

**When to use each:**
- `desktop_screenshot_analyze()`: Automation (99% of use cases) ✅
- `desktop_screenshot_analyze_conversational()`: Human exploration (1%)

---

## Conclusion

**Answer to your question:**

> "Would I want a separate VQA agent and not just a sub gui-cub?"

**YES! Keep the separate pydantic-ai Agent** for these reasons:

1. **Vision analysis is stateless** - perfect fit for isolated Agent
2. **Performance matters** - direct call is faster
3. **Type safety matters** - structured output is safer
4. **Simplicity matters** - already working, minimal code
5. **Token efficiency matters** - no system prompt overhead

**The current architecture is perfect for the use case.** 🎯

**Only switch to sub-agent invocation if:**
- Need conversation about images (multi-turn)
- Need tools within VQA agent
- Want user-facing VQA service

None of these apply to desktop automation vision analysis.

---

## Debug Access: Main Agent's Escape Hatch

### The Critical Requirement

**User feedback:** "It's important that the base gui-cub agent can still access the entire OCR engine functionality for debugging if it's busted."

**Absolutely right!** While delegation saves tokens, the main agent MUST be able to get full data when needed.

### Current Implementation (OCR) ✅

**Already supports debug access:**

```python
@agent.tool
def desktop_extract_text(
    context: RunContext,
    _internal: bool = False,  # Internal use - skip compaction
    ...
) -> OCRExtractResult:
    result = extract_text_from_image(image)
    
    # Compaction skipped when _internal=True
    if result.success and not _internal:
        return _compact_ocr_extract_result(result)  # 10 elements
    
    return result  # ALL 150 elements with coordinates
```

### Debug Workflow

**Normal (95% of cases):**
```python
result = desktop_extract_text()  # Compacted (~200 tokens)
# Agent: "I see Submit, Cancel, Username"
```

**Debug (5% of cases):**
```python
result = desktop_extract_text(_internal=True)  # Full data (~8k tokens)
# Agent: "I need to see ALL text elements to debug why Submit wasn't found"
# Returns: All 150 elements with bounding boxes, confidence scores, etc.
```

### Recommended: Add Debug Mode to VQA

```python
async def desktop_screenshot_and_analyze(
    question: str,
    include_image: bool = False,      # Include image in result
    debug_mode: bool = False,         # Include image + raw VQA data
    ...
) -> VQAResult:
    vqa_result = vqa_agent.run_sync([question, image])
    
    if debug_mode:
        # FULL debugging info
        return VQAResult(
            answer=vqa_result.output.answer,
            confidence=vqa_result.output.confidence,
            observations=vqa_result.output.observations,
            # Debug extras:
            image_base64=base64_encode(image),        # Full screenshot
            raw_vqa_messages=vqa_result.messages,     # VQA conversation
            vqa_token_usage=vqa_result.usage,         # Token breakdown
            model_used=vqa_model_name,                # Which model
            screenshot_path=screenshot_path,
        )
    
    # Normal mode (default)
    return VQAResult(
        answer=vqa_result.output.answer,
        confidence=vqa_result.output.confidence,
        screenshot_path=screenshot_path,
        image_base64=base64 if include_image else None,
    )
```

### Agent Escalation Pattern

**Smart debugging:**

```python
# LEVEL 1: Try compacted (fast, cheap)
result = desktop_screenshot_and_analyze("Where is Submit?")
# ~300 tokens

if result.confidence > 0.9:
    # High confidence - use it
    click(parse_coords(result.answer))
else:
    # LEVEL 2: Low confidence - try full OCR data
    ocr = desktop_extract_text(_internal=True)  # Get ALL elements
    # ~8,000 tokens
    
    submit = [e for e in ocr.text_elements if "submit" in e.text.lower()]
    if submit:
        # Found via full OCR
        click(submit[0].center_x, submit[0].center_y)
    else:
        # LEVEL 3: Complete failure - enable debug mode
        debug = desktop_screenshot_and_analyze(
            "Where is Submit?",
            debug_mode=True,  # Get EVERYTHING
        )
        # ~120,800 tokens
        
        # Agent can now:
        # - See the screenshot image
        # - Review VQA's raw reasoning
        # - Check if image quality is poor
        # - Share findings with user
        
        share_your_reasoning(
            f"Vision analysis failing. Debug shows: {debug.raw_vqa_messages}."
            f"Image quality may be poor. Trying accessibility API instead."
        )
```

### Token Cost Analysis

**Scenario: 100 vision operations, 5% need debugging**

```
Without Debug Access (Always embed images):
100 operations × 120,300 tokens = 12,030,000 tokens

With Debug Access (Smart delegation):
95 normal operations × 300 tokens = 28,500 tokens
4 full OCR operations × 8,000 tokens = 32,000 tokens
1 debug operation × 120,800 tokens = 120,800 tokens
TOTAL: 181,300 tokens

Savings: 98.5% (181k vs 12M tokens)
```

**Key insight:** Even with debug access, delegation is massively more efficient because:
- Most operations succeed with compacted data
- Debug mode used rarely (1-5% of cases)
- Full data available when needed

### Debug Access Levels

| Level | Mode | Tokens | When |
|-------|------|--------|------|
| **1. Compacted** | Default | 200-300 | 95% of calls |
| **2. Full Data** | `_internal=True` | 8,000 | Compacted insufficient |
| **3. Debug Mode** | `debug_mode=True` | 120,800 | Vision completely failing |

**Agent decides escalation based on:**
- Confidence scores (< 0.7 → escalate)
- Task success (failed → escalate)
- Repeated failures (3+ → debug mode)

---

## Related Decisions

- Use `include_image=False` by default to keep images out of main context ✅
- Use `_internal=True` for full OCR data when needed ✅
- Use `debug_mode=True` for complete vision debugging ✅
- Save screenshots to disk for manual review ✅
- Return structured analysis (not raw text) ✅
- Cache VQA agent instance for performance ✅
- Support configurable VQA model (already done) ✅
- **Main agent retains full debug access when needed** ✅
