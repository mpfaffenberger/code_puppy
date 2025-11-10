# GUI-Cub Context & Data Engineering Audit

**Date:** 2025-01-XX  
**Purpose:** Audit current context/data engineering practices and provide actionable recommendations

## Executive Summary

**Current State:** GUI-Cub implements **success-conditional compaction** for tool responses, achieving ~85-95% token savings on successful operations.

**Strengths:**
- ✅ OCR results compacted (200+ elements → 10 key elements)
- ✅ Accessibility trees compacted (200+ → 20 actionable)
- ✅ Smart relevance scoring for element selection
- ✅ Consistent compaction pattern across tools

**Gaps:**
- ⚠️ No compaction for screenshots (large base64 images)
- ⚠️ Inconsistent key element selection (hardcoded limits)
- ⚠️ No token budget awareness (doesn't adapt to context usage)
- ⚠️ Missing progressive detail levels
- ⚠️ No structured summarization format

**Opportunity:** Additional **30-50% token savings** possible with recommended improvements.

---

## Current Implementation Analysis

### 1. OCR Result Compaction ✅ (Good)

**Location:** `code_puppy/tools/gui_cub/ocr/extraction.py:_compact_ocr_extract_result`

**Current Strategy:**
```python
def _compact_ocr_extract_result(full_result: OCRExtractResult) -> OCRExtractResult:
    # Extract high-confidence, meaningful text (top 10)
    key_elements = [
        elem.text
        for elem in sorted(full_result.text_elements, key=lambda e: e.confidence, reverse=True)[:10]
        if elem.confidence > 0.7 and len(elem.text.strip()) > 2
    ]
    
    summary = _generate_ocr_summary(full_result.text_elements)
    
    return OCRExtractResult(
        success=True,
        found_count=len(full_result.text_elements),
        key_elements=key_elements,  # Only top 10
        summary=summary,
        average_confidence=full_result.average_confidence,
        # Stripped fields:
        full_text="",
        text_elements=[],  # All 200+ elements removed
    )
```

**Metrics:**
- **Full result:** ~8,000-15,000 tokens (200+ elements with bounding boxes)
- **Compact result:** ~150-300 tokens (summary + 10 key elements)
- **Savings:** ~95% 🎉

**Strengths:**
- ✅ Excellent token savings
- ✅ Confidence-based filtering
- ✅ Meaningfulness check (length > 2)
- ✅ Clear success/failure distinction

**Weaknesses:**
- ⚠️ Hardcoded limit (10 elements) - should be context-aware
- ⚠️ Confidence threshold (0.7) not configurable
- ⚠️ Summary generation logic unclear
- ⚠️ No coordinate preservation (loses spatial info)

---

### 2. Accessibility Tree Compaction ✅ (Good)

**Location:** `code_puppy/tools/gui_cub/accessibility/element_list.py:_compact_element_list_result`

**Current Strategy:**
```python
def _compact_element_list_result(
    full_result: ElementListResult, max_elements: int = 20
) -> ElementListResult:
    # Filter to actionable elements only
    actionable_roles = {
        "AXButton", "AXTextField", "AXMenuItem", ...
    }
    
    # Calculate relevance score
    actionable_with_scores = []
    for elem in full_result.elements:
        if elem.role in actionable_roles:
            relevance = _calculate_element_relevance(elem)
            
            # Compact structure - essential fields only
            compact_elem = {
                "role": elem.role,
                "title": elem.title,
                "x": elem.center_x,
                "y": elem.center_y,
                "relevance": round(relevance, 2),
            }
            actionable_with_scores.append((relevance, compact_elem))
    
    # Sort by relevance, limit to top 20
    actionable_with_scores.sort(reverse=True)
    return actionable[:max_elements]
```

**Metrics:**
- **Full result:** ~10,000-20,000 tokens (200+ elements, full tree)
- **Compact result:** ~400-800 tokens (20 actionable elements)
- **Savings:** ~96% 🎉

**Strengths:**
- ✅ Relevance scoring (not just random selection)
- ✅ Role-based filtering (actionable only)
- ✅ Coordinate preservation (x, y included)
- ✅ Configurable limit (max_elements parameter)

**Weaknesses:**
- ⚠️ Relevance algorithm not documented
- ⚠️ Default limit (20) may be too high for tight budgets
- ⚠️ No hierarchy preservation (loses parent-child relationships)
- ⚠️ Strips descriptions/labels (might be important)

---

### 3. Screenshot Handling ❌ (Needs Work)

**Location:** `code_puppy/tools/gui_cub/screen_capture/take_screenshot.py`

**Current Strategy:**
```python
# Returns full base64 image regardless of context
return ScreenshotResult(
    success=True,
    image_base64=base64_string,  # LARGE! (50k-200k tokens)
    width=1920,
    height=1080,
    format="PNG",
)
```

**Metrics:**
- **Result size:** 50,000-200,000 tokens (depending on resolution)
- **Compaction:** 0% (no compaction applied) ❌

**Problems:**
- ❌ Massive token usage (can consume 20% of context in one call)
- ❌ No thumbnail option for quick checks
- ❌ No region cropping guidance
- ❌ Format not optimized (PNG vs JPEG)

**Opportunity:** **Huge savings potential** (~80-90% with smart strategies)

---

## Token Usage Breakdown

### Typical GUI-Cub Workflow

```
Agent workflow: Click "Submit" button in calculator

1. desktop_list_accessible_elements()
   - Full tree: ~15,000 tokens
   - Compacted: ~600 tokens
   - Savings: 96% ✅

2. desktop_screenshot()
   - Full image: ~120,000 tokens
   - Compacted: ~120,000 tokens (no compaction!)
   - Savings: 0% ❌

3. desktop_ocr_extract_text()
   - Full OCR: ~8,000 tokens
   - Compacted: ~200 tokens
   - Savings: 97.5% ✅

4. desktop_click(x=500, y=300)
   - Result: ~50 tokens
   - Already minimal ✅

TOTAL WORKFLOW TOKENS:
- Without compaction: ~143,000 tokens (would overflow most models!)
- With current compaction: ~120,850 tokens (still very high)
- With recommended improvements: ~5,000-10,000 tokens (85-93% savings)
```

**Key insight:** Screenshots dominate token usage, yet have no compaction.

---

## Recommendations

### Priority 1: Critical (Implement Immediately)

#### 1.1 Screenshot Compaction Strategy 🔥

**Problem:** Screenshots consume 50k-200k tokens with no compaction.

**Solution:** Multi-tier screenshot strategy

```python
class ScreenshotTier(Enum):
    NONE = "none"          # No image (just metadata)
    THUMBNAIL = "thumb"    # 200x150 px (~2k tokens)
    CROPPED = "crop"       # Region only (~5-10k tokens)
    FULL = "full"          # Full res (~50-200k tokens)

def desktop_screenshot(
    context: RunContext,
    tier: ScreenshotTier = ScreenshotTier.THUMBNAIL,  # Default: thumbnail
    region: tuple[int, int, int, int] | None = None,
    format: str = "JPEG",  # JPEG is 60% smaller than PNG for screenshots
    quality: int = 85,     # Good visual quality, smaller size
) -> ScreenshotResult:
    if tier == ScreenshotTier.NONE:
        return ScreenshotResult(
            success=True,
            width=screen_width,
            height=screen_height,
            summary="Screenshot available, use tier='thumb' to view",
            # No image data
        )
    
    if tier == ScreenshotTier.THUMBNAIL:
        # Downscale to 200x150
        thumb = image.resize((200, 150), Image.LANCZOS)
        base64_thumb = encode_base64(thumb)
        return ScreenshotResult(
            success=True,
            image_base64=base64_thumb,  # ~2k tokens
            width=200,
            height=150,
            tier="thumbnail",
            summary="Thumbnail preview, use tier='full' for details",
        )
    
    # ... CROPPED and FULL tiers
```

**Token savings:**
- None tier: ~100 tokens (vs 120k) = **99.9% savings**
- Thumbnail tier: ~2,000 tokens (vs 120k) = **98.3% savings**
- Cropped tier: ~5,000-10,000 tokens (vs 120k) = **92-96% savings**

**Recommended defaults:**
- First screenshot in workflow: `THUMBNAIL` (quick preview)
- Follow-up for details: `CROPPED` (region of interest)
- Only if truly needed: `FULL`

**Implementation:**
- [ ] Add `ScreenshotTier` enum
- [ ] Implement thumbnail generation
- [ ] Default to `THUMBNAIL` tier
- [ ] Update tool documentation
- [ ] Add examples to agent prompt

---

#### 1.2 Context-Aware Element Limits 🎯

**Problem:** Hardcoded limits (10 OCR elements, 20 accessibility elements) don't adapt to available context.

**Solution:** Dynamic limits based on token budget

```python
def _calculate_element_budget(
    current_tokens: int,
    max_tokens: int,
    compaction_threshold: float = 0.8,
) -> int:
    """
    Calculate how many elements we can afford to return.
    
    Strategy:
    - If context usage < 50%: Return up to 20 elements (generous)
    - If context usage 50-80%: Return up to 10 elements (moderate)
    - If context usage > 80%: Return up to 5 elements (aggressive)
    """
    usage = current_tokens / max_tokens
    
    if usage < 0.5:
        return 20  # Plenty of room
    elif usage < compaction_threshold:
        return 10  # Getting tight
    else:
        return 5   # Very tight, minimal elements only

def _compact_ocr_extract_result(
    full_result: OCRExtractResult,
    context_tokens: int | None = None,  # NEW: pass current context
    max_tokens: int | None = None,
) -> OCRExtractResult:
    # Calculate dynamic limit
    if context_tokens and max_tokens:
        max_elements = _calculate_element_budget(context_tokens, max_tokens)
    else:
        max_elements = 10  # Fallback to default
    
    key_elements = [
        elem.text
        for elem in sorted(full_result.text_elements, key=lambda e: e.confidence, reverse=True)[:max_elements]
        if elem.confidence > 0.7 and len(elem.text.strip()) > 2
    ]
    # ...
```

**Token savings:**
- Low context usage: Same as current (20 elements)
- High context usage: **50% fewer elements** (5 vs 10)
- Prevents overflow: Adapts to remaining budget

**Implementation:**
- [ ] Add `_calculate_element_budget()` helper
- [ ] Pass context tokens to compaction functions
- [ ] Update OCR compaction
- [ ] Update accessibility compaction
- [ ] Add tests for budget calculation

---

#### 1.3 Structured Summarization Format 📋

**Problem:** Summaries are freeform strings, inconsistent across tools.

**Solution:** Standardized summary structure

```python
class CompactSummary(BaseModel):
    """Standardized summary format for all compacted results."""
    
    # Core info (always present)
    tool: str                    # "ocr_extract", "accessibility_tree", etc.
    success: bool
    found_count: int            # Total elements found
    returned_count: int         # Elements returned after compaction
    
    # Quick overview
    one_line: str               # "Found 150 text elements, showing top 10"
    top_items: list[str]        # ["Submit", "Cancel", "Username", ...]
    
    # Context awareness
    compaction_ratio: float     # 0.05 = 95% reduction
    tokens_saved: int | None    # Estimated tokens saved
    
    # Detail retrieval hint
    detail_hint: str | None     # "Use _internal=True for full data"

# Example usage:
return OCRExtractResult(
    success=True,
    summary=CompactSummary(
        tool="ocr_extract",
        success=True,
        found_count=150,
        returned_count=10,
        one_line="Found 150 text elements (avg confidence: 0.89), showing top 10",
        top_items=["Submit", "Cancel", "Username", "Password", "Login"],
        compaction_ratio=0.067,  # 93.3% reduction
        tokens_saved=7850,
        detail_hint="Use _internal=True for all 150 elements",
    ).model_dump(),
    key_elements=[...],
)
```

**Benefits:**
- ✅ Consistent format across all tools
- ✅ Agent can easily understand compaction happened
- ✅ Clear path to get more details if needed
- ✅ Self-documenting (tokens_saved, compaction_ratio)

**Implementation:**
- [ ] Create `CompactSummary` model
- [ ] Update all compaction functions to use it
- [ ] Add to result types
- [ ] Update agent prompt to explain format

---

### Priority 2: Important (Implement Soon)

#### 2.1 Progressive Detail Levels 📊

**Problem:** Binary choice (full data vs compact) - no middle ground.

**Solution:** Multiple detail levels

```python
class DetailLevel(Enum):
    MINIMAL = 1    # Count + summary only (~50 tokens)
    COMPACT = 2    # Top 5-10 items (~200 tokens) [DEFAULT]
    MODERATE = 3   # Top 20-30 items (~500 tokens)
    FULL = 4       # All data (~10,000+ tokens)

def desktop_ocr_extract_text(
    context: RunContext,
    detail_level: DetailLevel = DetailLevel.COMPACT,
    ...
) -> OCRExtractResult:
    # Perform OCR
    full_result = extract_text_from_image(image)
    
    if detail_level == DetailLevel.MINIMAL:
        return OCRExtractResult(
            success=True,
            found_count=len(full_result.text_elements),
            summary=f"Found {len(full_result.text_elements)} text elements",
            average_confidence=full_result.average_confidence,
            # No key_elements, no full data
        )
    
    elif detail_level == DetailLevel.COMPACT:
        # Current behavior (top 10)
        return _compact_ocr_extract_result(full_result, max_elements=10)
    
    elif detail_level == DetailLevel.MODERATE:
        # More details (top 30)
        return _compact_ocr_extract_result(full_result, max_elements=30)
    
    else:  # FULL
        return full_result
```

**Use cases:**
- `MINIMAL`: "Are there any text elements?" (yes/no + count)
- `COMPACT`: "What are the main UI elements?" (default, best balance)
- `MODERATE`: "Show me more options" (when compact isn't enough)
- `FULL`: "I need coordinates for all elements" (debugging, rare)

**Token comparison:**
| Level | Tokens | Use Case |
|-------|--------|----------|
| MINIMAL | ~50 | Quick check |
| COMPACT | ~200 | Default (current) |
| MODERATE | ~500 | More context needed |
| FULL | ~8,000 | Debugging/special cases |

**Implementation:**
- [ ] Add `DetailLevel` enum
- [ ] Update OCR tools
- [ ] Update accessibility tools
- [ ] Update agent prompt with examples
- [ ] Add tests for each level

---

#### 2.2 Smart Coordinate Preservation 🎯

**Problem:** OCR compaction strips bounding boxes, losing spatial information.

**Solution:** Include coordinates for top elements

```python
class CompactTextElement(BaseModel):
    """Minimal text element with coordinates."""
    text: str
    x: int          # Center X (not full bbox)
    y: int          # Center Y
    confidence: float
    # Removed: width, height, full bbox (saves ~50% per element)

def _compact_ocr_extract_result(
    full_result: OCRExtractResult,
    max_elements: int = 10,
    include_coords: bool = True,  # NEW: option to include coordinates
) -> OCRExtractResult:
    if include_coords:
        # Return compact elements WITH coordinates
        key_elements_with_coords = [
            CompactTextElement(
                text=elem.text,
                x=elem.center_x,
                y=elem.center_y,
                confidence=elem.confidence,
            )
            for elem in sorted(full_result.text_elements, key=lambda e: e.confidence, reverse=True)[:max_elements]
            if elem.confidence > 0.7
        ]
        
        return OCRExtractResult(
            success=True,
            key_elements_with_coords=key_elements_with_coords,  # NEW field
            # ...
        )
    else:
        # Current behavior (text only)
        key_elements = [elem.text for elem in ...]
        return OCRExtractResult(key_elements=key_elements, ...)
```

**Benefits:**
- ✅ Agent can click on found text elements
- ✅ Still saves tokens (center point vs full bbox)
- ✅ Backward compatible (include_coords=False for text-only)

**Token comparison:**
- Text only: `["Submit", "Cancel"]` → ~20 tokens
- With coords: `[{"text": "Submit", "x": 500, "y": 300}, ...]` → ~60 tokens
- Full bbox: `[{"text": "Submit", "x": 480, "y": 280, "width": 80, "height": 40}, ...]` → ~100 tokens

**Savings:** 40% vs full bbox, while retaining clickability!

**Implementation:**
- [ ] Add `CompactTextElement` model
- [ ] Add `include_coords` parameter
- [ ] Update OCR result types
- [ ] Default to `include_coords=True` for clickable elements
- [ ] Add tests

---

#### 2.3 Relevance Score Transparency 🔍

**Problem:** Element relevance calculation is opaque.

**Solution:** Document and expose relevance algorithm

```python
def _calculate_element_relevance(
    elem: dict,
    common_actions: list[str] = ["submit", "ok", "cancel", "close", "save", "open"],
) -> float:
    """
    Calculate element relevance score (0.0-1.0).
    
    Scoring factors:
    - +0.4: Matches common action words (submit, ok, etc.)
    - +0.3: Is a button or primary control
    - +0.2: Has short, meaningful title (3-20 chars)
    - +0.1: Near top-left (common UI pattern)
    
    Returns:
        Relevance score (0.0 = irrelevant, 1.0 = highly relevant)
    """
    score = 0.0
    title = (elem.get("title") or "").lower()
    role = elem.get("role") or elem.get("type") or ""
    
    # Factor 1: Common action words (+0.4)
    if any(action in title for action in common_actions):
        score += 0.4
    
    # Factor 2: Primary control type (+0.3)
    if role in {"AXButton", "Button", "AXMenuItem", "MenuItem"}:
        score += 0.3
    
    # Factor 3: Meaningful title length (+0.2)
    if 3 <= len(title) <= 20:
        score += 0.2
    
    # Factor 4: Position (top-left area) (+0.1)
    x = elem.get("x") or elem.get("center_x") or 0
    y = elem.get("y") or elem.get("center_y") or 0
    if x < 800 and y < 600:  # Top-left quadrant (rough)
        score += 0.1
    
    return min(score, 1.0)  # Cap at 1.0
```

**Benefits:**
- ✅ Transparent (agent can understand why elements ranked)
- ✅ Tunable (adjust weights for different apps)
- ✅ Testable (clear scoring logic)
- ✅ Documented (in code and agent prompt)

**Implementation:**
- [ ] Document existing `_calculate_element_relevance()`
- [ ] Add inline comments explaining scoring
- [ ] Expose relevance score in compacted results
- [ ] Add tests for each scoring factor
- [ ] Consider making weights configurable

---

### Priority 3: Nice to Have (Future Enhancements)

#### 3.1 Hierarchical Element Grouping 🌳

**Problem:** Flat element lists lose parent-child relationships.

**Solution:** Preserve minimal hierarchy

```python
class ElementGroup(BaseModel):
    """Grouped elements by container/window."""
    container: str              # "Calculator", "Menu Bar", etc.
    elements: list[dict]        # Elements in this container
    count: int

# Compact result with grouping:
return ElementListResult(
    success=True,
    groups=[
        ElementGroup(container="Calculator", elements=[...], count=15),
        ElementGroup(container="Menu Bar", elements=[...], count=5),
    ],
    total_elements=200,
    returned_elements=20,
)
```

**Benefits:**
- Better context (know which window elements belong to)
- Clearer structure
- Easier for agent to understand UI layout

**Token cost:** +5-10% vs flat list (worth it for clarity)

---

#### 3.2 Incremental Detail Retrieval 🔄

**Problem:** Agent must decide detail level upfront.

**Solution:** Support follow-up queries for more detail

```python
# First call: Get compact summary
result1 = desktop_ocr_extract_text(
    detail_level=DetailLevel.MINIMAL
)
# Returns: "Found 150 elements"

# Agent realizes it needs more details
result2 = desktop_ocr_get_details(
    session_id=result1.session_id,  # Reference previous scan
    start_index=0,
    count=20,  # Get first 20 elements
)
# Returns: Top 20 elements without re-scanning
```

**Benefits:**
- No re-scanning (cache previous OCR result)
- Progressive disclosure (start small, request more as needed)
- Token efficient (only fetch what's needed)

**Challenges:**
- Requires session/cache management
- Adds complexity
- May not be worth it for initial implementation

---

#### 3.3 Format-Specific Optimization 🖼️

**Problem:** PNG format is inefficient for screenshots.

**Solution:** Use JPEG for photos, PNG for diagrams

```python
def desktop_screenshot(
    format: str = "auto",  # Auto-detect best format
    quality: int = 85,
) -> ScreenshotResult:
    if format == "auto":
        # Analyze image content
        if _is_photographic(image):
            format = "JPEG"  # Better compression
        else:
            format = "PNG"   # Better for UI/text
    
    # Encode with chosen format
    base64_image = encode_image(image, format, quality)
    # ...
```

**Token savings:**
- JPEG (quality=85): ~60% smaller than PNG for screenshots
- PNG: Better for diagrams/text (lossless)

---

## Implementation Roadmap

### Phase 1: Critical Fixes (Week 1-2)

**Goal:** Achieve 85-90% token savings across all tools

- [ ] **1.1 Screenshot Compaction**
  - [ ] Add `ScreenshotTier` enum
  - [ ] Implement thumbnail generation
  - [ ] Default to THUMBNAIL tier
  - [ ] Update documentation
  - **Expected impact:** 90-95% screenshot token reduction

- [ ] **1.2 Context-Aware Limits**
  - [ ] Add `_calculate_element_budget()` helper
  - [ ] Pass context tokens to compaction functions
  - [ ] Update all tools
  - **Expected impact:** 20-50% additional savings in tight contexts

- [ ] **1.3 Structured Summaries**
  - [ ] Create `CompactSummary` model
  - [ ] Update all compaction functions
  - [ ] Update agent prompts
  - **Expected impact:** Better agent understanding, clearer debugging

**Success metrics:**
- Typical workflow: 120k tokens → 5-10k tokens
- Screenshot calls: 120k tokens → 2k tokens (thumbnail)
- Context overflow rate: -90%

---

### Phase 2: Important Enhancements (Week 3-4)

**Goal:** Progressive detail levels and better spatial awareness

- [ ] **2.1 Progressive Detail Levels**
  - [ ] Add `DetailLevel` enum
  - [ ] Implement MINIMAL/COMPACT/MODERATE/FULL levels
  - [ ] Update all tools
  - **Expected impact:** Finer-grained control, 30-70% savings vs current compact

- [ ] **2.2 Smart Coordinate Preservation**
  - [ ] Add `CompactTextElement` model
  - [ ] Include center coordinates in OCR results
  - [ ] Update accessibility results
  - **Expected impact:** Clickable elements without full bbox overhead

- [ ] **2.3 Relevance Score Transparency**
  - [ ] Document `_calculate_element_relevance()`
  - [ ] Expose scores in results
  - [ ] Add tests
  - **Expected impact:** Better agent decisions, debuggability

**Success metrics:**
- Agent can choose appropriate detail level
- OCR elements are clickable
- Relevance scoring is testable and clear

---

### Phase 3: Future Enhancements (Month 2+)

**Goal:** Advanced features for power users

- [ ] **3.1 Hierarchical Grouping**
- [ ] **3.2 Incremental Detail Retrieval**
- [ ] **3.3 Format-Specific Optimization**

---

## Metrics & Validation

### Before Implementation

```
Typical GUI-Cub workflow (5 tool calls):

1. List accessible elements: ~600 tokens (compacted from 15k) ✅
2. Screenshot: ~120,000 tokens (no compaction) ❌
3. OCR extract: ~200 tokens (compacted from 8k) ✅
4. Find element: ~100 tokens (compacted) ✅
5. Click: ~50 tokens ✅

TOTAL: ~120,950 tokens
LIMITATIONS:
- Cannot use gpt-4-turbo (128k context) for complex workflows
- Risk context overflow
- Expensive (high token costs)
```

### After Priority 1 (Critical Fixes)

```
Same workflow with improvements:

1. List accessible elements: ~300 tokens (context-aware limit) ✅✅
2. Screenshot (THUMBNAIL): ~2,000 tokens (tier=thumb) ✅✅
3. OCR extract: ~150 tokens (context-aware) ✅✅
4. Find element: ~80 tokens ✅
5. Click: ~50 tokens ✅

TOTAL: ~2,580 tokens
SAVINGS: 97.9% 🎉

BENEFITS:
- Can use smaller models (gpt-4o-mini, claude-haiku)
- 10-20x more room for conversation
- Lower costs (~20x cheaper)
- Faster responses
```

### After Priority 2 (Important Enhancements)

```
Advanced workflow with progressive detail:

1. List elements (MINIMAL): ~50 tokens
   → "Found 200 elements"
2. Screenshot (THUMBNAIL): ~2,000 tokens
   → Agent: "I see buttons in top-left"
3. List elements (COMPACT, top-left region): ~200 tokens
   → Agent: "Found Submit button at (500, 300)"
4. Click: ~50 tokens

TOTAL: ~2,300 tokens
SAVINGS: 98.1% 🚀

BENEFITS:
- Start with minimal info, progressively request more
- Optimal token usage (only what's needed)
- Clear spatial awareness (coordinates preserved)
```

---

## Testing Requirements

See also: `CONTEXT_ENGINEERING_TESTS.md`

### New Tests Required

1. **Screenshot Compaction Tests** (~10 tests)
   - [ ] Thumbnail generation
   - [ ] Region cropping
   - [ ] Format optimization (JPEG vs PNG)
   - [ ] Token measurement (verify 95%+ savings)

2. **Context-Aware Budget Tests** (~8 tests)
   - [ ] Budget calculation (50%, 80%, 95% usage)
   - [ ] Dynamic element limits
   - [ ] Fallback to defaults when context unknown

3. **Progressive Detail Tests** (~12 tests)
   - [ ] Each detail level (MINIMAL/COMPACT/MODERATE/FULL)
   - [ ] Token measurements
   - [ ] Correctness at each level

4. **Coordinate Preservation Tests** (~6 tests)
   - [ ] Center point accuracy
   - [ ] Clickability
   - [ ] Token savings vs full bbox

**Total new tests:** ~36 tests

---

## Related Documents

- `CONTEXT_ENGINEERING_TESTS.md` - Test design for compaction logic
- `TEST_REFACTOR_SUMMARY.md` - Overall test refactoring plan
- `NEW_TEST_STRATEGY.md` - Testing philosophy

---

## Conclusion

**Current state:** Excellent compaction for OCR/accessibility (~95% savings), but **screenshots are a massive token sink** with no compaction.

**Opportunity:** Implementing Priority 1 recommendations achieves **~98% total token savings** for typical workflows.

**ROI:** 
- Implementation effort: 2-3 weeks
- Token savings: 10-20x reduction
- Cost savings: ~20x cheaper per workflow
- Context headroom: 10-20x more conversation history

**Recommendation:** Prioritize **1.1 Screenshot Compaction** (biggest impact) and **1.2 Context-Aware Limits** (prevents overflow) immediately.
