# Context Engineering & Data Compaction Tests

**Purpose:** Ensure all token-saving and context management strategies are properly tested

## Critical Gap Identified

While auditing gui-cub tests, we found comprehensive tests for **algorithms** (fuzzy matching, coordinates) but **missing tests** for:

1. **Message history compaction** - Truncation and summarization strategies
2. **Tool response compaction** - "Success-conditional compaction" in OCR, screenshots, accessibility
3. **Token estimation** - Accurate token counting for context management
4. **Protected message handling** - Recent message protection logic
5. **Huge message filtering** - Removing >50k token messages

**Impact:** These are **critical business logic** for staying within context limits. Without tests, we risk:
- Token overflow (hitting model limits)
- Lost context (over-aggressive compaction)
- Poor user experience (confusing truncation)

---

## Current State

### Existing Tests (Minimal)

#### ✅ `tests/test_compaction_strategy.py` (978 bytes)
**What it tests:**
- Config reading: `get_compaction_strategy()` returns "truncation" or "summarization"
- Default value validation
- Invalid value fallback

**What it DOESN'T test:**
- Actual truncation logic
- Actual summarization logic
- Token counting
- Protected message selection

**Verdict:** Tests config reading, not the actual compaction algorithms. ❌

---

### Missing Tests

None of these critical functions have tests:

#### ❌ `BaseAgent.truncation()` - NO TESTS
**Location:** `code_puppy/agents/base_agent.py:801`

**What it does:**
```python
def truncation(self, messages: List[ModelMessage], protected_tokens: int) -> List[ModelMessage]:
    # Always keep first message (system prompt)
    result = [messages[0]]
    num_tokens = 0
    stack = queue.LifoQueue()
    
    # Keep most recent messages up to protected_tokens
    for idx, msg in enumerate(reversed(messages[1:])):
        num_tokens += self.estimate_tokens_for_message(msg)
        if num_tokens > protected_tokens:
            break
        stack.put(msg)
    
    # Pop to restore chronological order
    while not stack.empty():
        result.append(stack.get())
    
    return self.prune_interrupted_tool_calls(result)
```

**Business logic to test:**
- Always preserves system message (index 0)
- Keeps most recent messages up to token limit
- Restores chronological order (LIFO stack usage)
- Prunes interrupted tool calls after truncation
- Edge cases: empty list, only system message, all messages fit

---

#### ❌ `BaseAgent.filter_huge_messages()` - NO TESTS
**Location:** `code_puppy/agents/base_agent.py:371`

**What it does:**
```python
def filter_huge_messages(self, messages: List[ModelMessage]) -> List[ModelMessage]:
    filtered = [m for m in messages if self.estimate_tokens_for_message(m) < 50000]
    pruned = self.prune_interrupted_tool_calls(filtered)
    return pruned
```

**Business logic to test:**
- Removes messages ≥50k tokens
- Threshold value (50k) is correct
- Preserves message order
- Prunes tool calls after filtering
- Edge cases: all messages huge, no huge messages

---

#### ❌ `BaseAgent.split_messages_for_protected_summarization()` - NO TESTS  
**Location:** `code_puppy/agents/base_agent.py:376`

**What it does:**
```python
def split_messages_for_protected_summarization(
    self, messages: List[ModelMessage]
) -> Tuple[List[ModelMessage], List[ModelMessage]]:
    # Always protect system message
    system_message = messages[0]
    protected_messages = []
    protected_token_count = estimate_tokens(system_message)
    
    # Go backwards from most recent
    for i in range(len(messages) - 1, 0, -1):
        message = messages[i]
        message_tokens = estimate_tokens(message)
        
        if protected_token_count + message_tokens > protected_tokens_limit:
            break
        
        protected_messages.append(message)
        protected_token_count += message_tokens
    
    # Reverse to restore chronological order
    protected_messages.reverse()
    protected_messages.insert(0, system_message)
    
    # Messages to summarize = everything between system and protected tail
    messages_to_summarize = messages[1:protected_start_idx]
    
    return messages_to_summarize, protected_messages
```

**Business logic to test:**
- Always protects system message (first)
- Protects most recent messages up to token limit
- Correctly splits into (to_summarize, protected)
- Maintains chronological order
- Edge cases: all messages protected, no messages protected

---

#### ❌ `BaseAgent.message_history_processor()` - NO TESTS
**Location:** `code_puppy/agents/base_agent.py:664`

**What it does:**
```python
def message_history_processor(self, ctx, messages):
    total_tokens = sum(estimate_tokens(msg) for msg in messages)
    proportion_used = total_tokens / model_max
    
    if proportion_used > compaction_threshold:
        if compaction_strategy == "truncation":
            return self.truncation(messages, protected_tokens)
        else:
            return self.summarize_messages(messages)
    
    return messages
```

**Business logic to test:**
- Triggers compaction when threshold exceeded
- Respects compaction_strategy config
- Doesn't compact when below threshold
- Handles pending tool calls (defers summarization)
- Token counting accuracy

---

### Success-Conditional Compaction (GUI-Cub Specific)

#### ❌ OCR Result Compaction - NO TESTS
**Pattern:** On success, return minimal data. On failure, return full diagnostic.

**Example from `ocr/result_types.py`:**
```python
class OCRExtractResult(BaseAutomationResult):
    # Compact fields (always included)
    found_count: int = 0
    key_elements: list[str] = []  # Top 5-10 text snippets
    summary: str = ""  # One-line summary
    average_confidence: float = 0.0
    
    # Verbose fields (only on failure)
    full_text: str = ""  # All OCR text
    text_elements: list[TextBoundingBox] = []  # All bounding boxes
    total_words: int = 0
```

**Business logic to test:**
- Success returns compact data (key_elements only)
- Failure returns full data (all text_elements)
- Token savings: success response should be ~90% smaller
- Key elements selection (top N by confidence?)

---

#### ❌ Accessibility Result Compaction - NO TESTS
**Location:** `code_puppy/tools/gui_cub/accessibility/tools.py:282`

**Pattern:** Return only actionable elements (top 20 by confidence)

```python
# Success-conditional compaction: Return filtered actionable elements
if success:
    # Return top 20 actionable elements
    actionable = [e for e in elements if e.is_actionable]
    actionable.sort(key=lambda e: e.confidence, reverse=True)
    return actionable[:20]
else:
    # Return all elements for debugging
    return elements
```

**Business logic to test:**
- Filters to actionable elements only
- Sorts by confidence (highest first)
- Limits to top 20
- Token savings vs returning all 200+ elements

---

#### ❌ Screenshot Result Compaction - NO TESTS
**Location:** `code_puppy/tools/gui_cub/screen_capture/take_screenshot.py:326`

**Pattern:** Return base64 image only on success, full diagnostic on failure

**Business logic to test:**
- Success: Returns base64 string (no metadata)
- Failure: Returns full diagnostic (resolution, format, error)
- Token savings: success response should exclude verbose metadata

---

## Test Suite Design

### New Test File: `tests/test_message_compaction.py`

**What to test:**

```python
import pytest
from code_puppy.agents.base_agent import BaseAgent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse

class TestTruncation:
    """Test message truncation logic."""
    
    def test_always_preserves_system_message(self):
        """System message (index 0) must never be truncated."""
        agent = BaseAgent(model="test")
        messages = [
            ModelRequest(parts=[{"type": "text", "content": "System prompt"}]),
            ModelRequest(parts=[{"type": "text", "content": "User message 1"}]),
            ModelRequest(parts=[{"type": "text", "content": "User message 2"}]),
        ]
        
        # Truncate to 0 tokens (extreme case)
        result = agent.truncation(messages, protected_tokens=0)
        
        assert len(result) == 1
        assert result[0] == messages[0]  # System message preserved
    
    def test_keeps_most_recent_messages_within_token_limit(self):
        """Should keep most recent messages up to protected token limit."""
        agent = BaseAgent(model="test")
        
        # Mock token estimation: each message = 100 tokens
        agent.estimate_tokens_for_message = lambda msg: 100
        
        messages = [
            ModelRequest(parts=[{"type": "text", "content": "System"}]),  # 100 tokens
            ModelRequest(parts=[{"type": "text", "content": "Old 1"}]),   # 100 tokens
            ModelRequest(parts=[{"type": "text", "content": "Old 2"}]),   # 100 tokens
            ModelRequest(parts=[{"type": "text", "content": "Recent 1"}]),# 100 tokens
            ModelRequest(parts=[{"type": "text", "content": "Recent 2"}]),# 100 tokens
        ]
        
        # Protected = 250 tokens (system + 2 most recent)
        result = agent.truncation(messages, protected_tokens=250)
        
        assert len(result) == 3  # System + 2 most recent
        assert result[0].parts[0]['content'] == "System"
        assert result[1].parts[0]['content'] == "Recent 1"
        assert result[2].parts[0]['content'] == "Recent 2"
    
    def test_maintains_chronological_order(self):
        """Messages must remain in chronological order after truncation."""
        agent = BaseAgent(model="test")
        agent.estimate_tokens_for_message = lambda msg: 50
        
        messages = [
            ModelRequest(parts=[{"type": "text", "content": "System"}]),
            ModelRequest(parts=[{"type": "text", "content": "Message 1"}]),
            ModelRequest(parts=[{"type": "text", "content": "Message 2"}]),
            ModelRequest(parts=[{"type": "text", "content": "Message 3"}]),
        ]
        
        result = agent.truncation(messages, protected_tokens=150)
        
        # Should be: System, Message 2, Message 3 (chronological)
        assert result[0].parts[0]['content'] == "System"
        assert result[1].parts[0]['content'] == "Message 2"
        assert result[2].parts[0]['content'] == "Message 3"
    
    def test_all_messages_fit_within_limit(self):
        """When all messages fit, all should be kept."""
        agent = BaseAgent(model="test")
        agent.estimate_tokens_for_message = lambda msg: 10
        
        messages = [
            ModelRequest(parts=[{"type": "text", "content": "System"}]),
            ModelRequest(parts=[{"type": "text", "content": "Message 1"}]),
            ModelRequest(parts=[{"type": "text", "content": "Message 2"}]),
        ]
        
        result = agent.truncation(messages, protected_tokens=1000)
        
        assert len(result) == 3
        assert result == messages


class TestFilterHugeMessages:
    """Test huge message filtering."""
    
    def test_removes_messages_over_50k_tokens(self):
        """Messages ≥50k tokens should be filtered out."""
        agent = BaseAgent(model="test")
        
        # Mock: first message = 60k, second = 30k, third = 40k
        token_counts = [100, 60000, 30000, 40000]
        agent.estimate_tokens_for_message = lambda msg: token_counts[messages.index(msg)]
        
        messages = [
            ModelRequest(parts=[{"type": "text", "content": "System"}]),      # 100
            ModelRequest(parts=[{"type": "text", "content": "Huge 1"}]),      # 60k
            ModelRequest(parts=[{"type": "text", "content": "Normal"}]),      # 30k
            ModelRequest(parts=[{"type": "text", "content": "Also Normal"}]), # 40k
        ]
        
        result = agent.filter_huge_messages(messages)
        
        # Should keep: System, Normal, Also Normal (all <50k)
        assert len(result) == 3
        assert result[0].parts[0]['content'] == "System"
        assert result[1].parts[0]['content'] == "Normal"
        assert result[2].parts[0]['content'] == "Also Normal"
    
    def test_preserves_order_after_filtering(self):
        """Message order must be preserved after filtering."""
        # Test implementation...
    
    def test_all_messages_under_limit(self):
        """When no messages are huge, all should be kept."""
        # Test implementation...


class TestSplitMessagesForProtectedSummarization:
    """Test protected message splitting logic."""
    
    def test_always_protects_system_message(self):
        """System message must always be in protected set."""
        agent = BaseAgent(model="test")
        agent.estimate_tokens_for_message = lambda msg: 100
        
        messages = [
            ModelRequest(parts=[{"type": "text", "content": "System"}]),
            ModelRequest(parts=[{"type": "text", "content": "Message 1"}]),
        ]
        
        to_summarize, protected = agent.split_messages_for_protected_summarization(messages)
        
        assert protected[0].parts[0]['content'] == "System"
    
    def test_protects_most_recent_messages(self):
        """Most recent messages should be protected up to token limit."""
        agent = BaseAgent(model="test")
        agent.estimate_tokens_for_message = lambda msg: 100
        
        # Mock protected token count
        with patch('code_puppy.agents.base_agent.get_protected_token_count', return_value=350):
            messages = [
                ModelRequest(parts=[{"type": "text", "content": "System"}]),    # 100
                ModelRequest(parts=[{"type": "text", "content": "Old 1"}]),     # 100
                ModelRequest(parts=[{"type": "text", "content": "Old 2"}]),     # 100
                ModelRequest(parts=[{"type": "text", "content": "Recent 1"}]),  # 100
                ModelRequest(parts=[{"type": "text", "content": "Recent 2"}]),  # 100
            ]
            
            to_summarize, protected = agent.split_messages_for_protected_summarization(messages)
            
            # Protected = System + 2 most recent (350 tokens total)
            assert len(protected) == 3
            assert protected[0].parts[0]['content'] == "System"
            assert protected[1].parts[0]['content'] == "Recent 1"
            assert protected[2].parts[0]['content'] == "Recent 2"
            
            # To summarize = Old 1, Old 2
            assert len(to_summarize) == 2
            assert to_summarize[0].parts[0]['content'] == "Old 1"
            assert to_summarize[1].parts[0]['content'] == "Old 2"
    
    def test_maintains_chronological_order(self):
        """Both sets should maintain chronological order."""
        # Test implementation...
    
    def test_all_messages_protected(self):
        """When all messages fit in protected tokens, to_summarize should be empty."""
        # Test implementation...


class TestMessageHistoryProcessor:
    """Test main message history processing logic."""
    
    def test_no_compaction_when_below_threshold(self):
        """Should return original messages when below threshold."""
        agent = BaseAgent(model="test")
        agent.get_model_context_length = lambda: 10000
        agent.estimate_tokens_for_message = lambda msg: 50
        
        # Mock threshold = 0.8 (80%)
        with patch('code_puppy.agents.base_agent.get_compaction_threshold', return_value=0.8):
            messages = [
                ModelRequest(parts=[{"type": "text", "content": f"Message {i}"}])
                for i in range(10)
            ]
            
            # Total = 500 tokens, context = 10000, usage = 5% (< 80%)
            result = agent.message_history_processor(None, messages)
            
            assert result == messages  # No compaction
    
    def test_triggers_truncation_when_above_threshold(self):
        """Should truncate when above threshold and strategy=truncation."""
        # Test implementation...
    
    def test_triggers_summarization_when_above_threshold(self):
        """Should summarize when above threshold and strategy=summarization."""
        # Test implementation...
    
    def test_defers_compaction_for_pending_tool_calls(self):
        """Should not compact when tool calls are pending."""
        # Test implementation...
```

---

### New Test File: `tests/gui_cub/test_success_conditional_compaction.py`

**What to test:**

```python
import pytest
from code_puppy.tools.gui_cub.ocr.result_types import OCRExtractResult
from code_puppy.tools.gui_cub.accessibility.element_list import compact_element_list

class TestOCRResultCompaction:
    """Test OCR result compaction logic."""
    
    def test_success_returns_compact_data(self):
        """On success, should return minimal key elements only."""
        result = OCRExtractResult(
            success=True,
            found_count=50,
            key_elements=["Submit", "Cancel", "Username", "Password"],
            summary="Login form with 50 text elements",
            average_confidence=0.92,
        )
        
        # Verify compact fields present
        assert result.found_count == 50
        assert len(result.key_elements) == 4
        assert result.summary != ""
        
        # Verify verbose fields NOT included (or empty)
        assert result.full_text == ""
        assert len(result.text_elements) == 0
    
    def test_failure_returns_full_diagnostic_data(self):
        """On failure, should return all data for debugging."""
        result = OCRExtractResult(
            success=False,
            error="OCR engine failed",
            found_count=0,
            full_text="Partial scan: Submit Can...",
            text_elements=[...],  # All detected elements
            total_words=150,
        )
        
        # Verify full diagnostic data present
        assert result.full_text != ""
        assert len(result.text_elements) > 0
        assert result.total_words > 0
    
    def test_token_savings_on_success(self):
        """Success response should be ~90% smaller than failure response."""
        # Create identical results, one success, one failure
        base_data = {...}  # 50 text elements
        
        success_result = OCRExtractResult(
            success=True,
            **base_data,
            key_elements=["Top 5 elements"],  # Compact
        )
        
        failure_result = OCRExtractResult(
            success=False,
            **base_data,
            text_elements=[all_50_elements],  # Verbose
        )
        
        success_tokens = estimate_tokens(success_result.model_dump_json())
        failure_tokens = estimate_tokens(failure_result.model_dump_json())
        
        savings = 1 - (success_tokens / failure_tokens)
        assert savings >= 0.85  # At least 85% savings


class TestAccessibilityCompaction:
    """Test accessibility element compaction."""
    
    def test_returns_top_20_actionable_elements(self):
        """Should return only top 20 actionable elements by confidence."""
        elements = [
            Element(title=f"Button {i}", actionable=True, confidence=0.9 - i*0.01)
            for i in range(50)
        ]
        
        result = compact_element_list(elements, limit=20)
        
        assert len(result) == 20
        # Should be sorted by confidence (highest first)
        assert result[0].confidence >= result[1].confidence
        assert result[1].confidence >= result[2].confidence
    
    def test_filters_non_actionable_elements(self):
        """Should exclude non-actionable elements."""
        elements = [
            Element(title="Button", actionable=True, confidence=0.9),
            Element(title="Static text", actionable=False, confidence=0.8),
            Element(title="Link", actionable=True, confidence=0.85),
        ]
        
        result = compact_element_list(elements, limit=20)
        
        assert len(result) == 2  # Only actionable
        assert all(e.actionable for e in result)
    
    def test_token_savings_200_to_20_elements(self):
        """Compacting 200 → 20 elements should save ~90% tokens."""
        # Test implementation...
```

---

## Implementation Checklist

### Phase 1: Message History Compaction Tests

- [ ] Create `tests/test_message_compaction.py`
- [ ] Test `truncation()` logic
  - [ ] System message preservation
  - [ ] Recent message protection
  - [ ] Chronological order maintenance
  - [ ] Edge cases (empty, all fit, none fit)
- [ ] Test `filter_huge_messages()` logic
  - [ ] 50k token threshold
  - [ ] Order preservation
  - [ ] Edge cases
- [ ] Test `split_messages_for_protected_summarization()` logic
  - [ ] System message in protected set
  - [ ] Recent message protection
  - [ ] Correct split point calculation
  - [ ] Edge cases
- [ ] Test `message_history_processor()` integration
  - [ ] Threshold triggering
  - [ ] Strategy selection (truncation vs summarization)
  - [ ] Pending tool call deferral
  - [ ] Token counting accuracy

### Phase 2: Success-Conditional Compaction Tests

- [ ] Create `tests/gui_cub/test_success_conditional_compaction.py`
- [ ] Test OCR result compaction
  - [ ] Success: compact data
  - [ ] Failure: full diagnostic
  - [ ] Token savings measurement
- [ ] Test accessibility element compaction
  - [ ] Top 20 filtering
  - [ ] Confidence sorting
  - [ ] Actionable filtering
  - [ ] Token savings (200 → 20)
- [ ] Test screenshot result compaction
  - [ ] Success: minimal metadata
  - [ ] Failure: full diagnostic

### Phase 3: Token Estimation Accuracy Tests

- [ ] Create `tests/test_token_estimation.py`
- [ ] Test token estimation for various message types
  - [ ] Text messages
  - [ ] Tool calls
  - [ ] Tool responses
  - [ ] Images (base64)
- [ ] Test estimation accuracy (within ±10%)
- [ ] Test edge cases (empty, very long, special characters)

---

## Success Criteria

### Coverage Goals

| Module | Current Coverage | Target Coverage |
|--------|-----------------|----------------|
| `base_agent.py` (compaction methods) | 0% | 85%+ |
| OCR result types | 0% | 80%+ |
| Accessibility compaction | 0% | 80%+ |
| Token estimation | Unknown | 90%+ |

### Quality Metrics

- [ ] All compaction edge cases tested
- [ ] Token savings verified (>80% reduction)
- [ ] No token overflow in tests
- [ ] Chronological order maintained in all cases
- [ ] System message never lost
- [ ] Protected messages never summarized prematurely

### Documentation

- [ ] Add to `TEST_REFACTOR_SUMMARY.md`
- [ ] Update `NEW_TEST_STRATEGY.md` with compaction patterns
- [ ] Document token savings measurements

---

## Why This Matters

### Context Engineering is Critical

Without proper testing:

1. **Token overflow** → Model refuses request ("context length exceeded")
2. **Lost context** → Agent forgets important information
3. **Poor compaction** → Wasted tokens on verbose responses
4. **Inconsistent behavior** → Sometimes works, sometimes fails

### Example Failure Without Tests

**Scenario:** OCR scan of calculator returns 200 buttons

**Without compaction:**
```json
{
  "text_elements": [
    {"text": "0", "x": 10, "y": 20, "width": 30, "height": 40, "confidence": 0.99},
    {"text": "1", "x": 50, "y": 20, "width": 30, "height": 40, "confidence": 0.99},
    // ... 198 more elements
  ]
}
// Result: ~15,000 tokens (!) for a simple OCR scan
```

**With compaction:**
```json
{
  "found_count": 200,
  "key_elements": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "+", "-", "="],
  "summary": "Calculator with 200 elements (digits, operators, functions)"
}
// Result: ~150 tokens (99% savings!)
```

**Impact:** Without tests, compaction might:
- Skip key elements
- Return too many elements
- Break on edge cases
- Not actually save tokens

---

## Integration with Test Refactoring

Add to `TEST_REFACTOR_SUMMARY.md`:

### Phase 3b: Context Engineering Tests (New)

**After extracting business logic (Phase 3), add:**

- Message history compaction tests (~15 tests)
- Success-conditional compaction tests (~10 tests)
- Token estimation accuracy tests (~8 tests)

**Impact:**
- ~33 new high-value tests
- Covers critical token management logic
- Prevents context overflow bugs
- Documents compaction strategies

**Total after Phase 3b:**
- Tests: ~180-230 (vs 150-200)
- Coverage: ~75% (vs 70%)
- All critical paths tested

---

## Next Steps

1. **Review** this design doc
2. **Prioritize** Phase 1 (message history) as highest priority
3. **Implement** tests alongside test refactoring effort
4. **Measure** token savings to validate compaction effectiveness
5. **Document** in main test strategy docs

---

**See also:**
- `TEST_AUDIT.md` - Overall test audit
- `NEW_TEST_STRATEGY.md` - Testing patterns
- `TEST_REFACTOR_SUMMARY.md` - Refactoring plan
