# Resume: VQA Bounding Box Real-World Testing

## 🎯 Current Status

We've implemented a **bounding box VQA approach** for precise UI element detection, but haven't tested it with **real Claude 4.5 Sonnet API calls** yet.

### ✅ What's Complete:

1. **VQA Module (`code_puppy/tools/gui_cub/vqa_vision_click.py`):**
   - ✅ Uses bounding box detection (not direct points)
   - ✅ VQABoundingBox model (x, y, width, height)
   - ✅ VQAElementLocation with bbox field
   - ✅ `center_x` / `center_y` properties (calculated from bbox)
   - ✅ Updated prompt requesting bbox instead of point
   - ✅ Coordinate scaling for downscaling/upscaling
   - ✅ Two-stage coarse-to-fine approach

2. **Test Script (`test_vqa_coarse_to_fine.py`):**
   - ✅ Simulates two-stage VQA (coarse → fine)
   - ✅ Stage 1: Full window crop → approximate location
   - ✅ Stage 2: ±100px fine crop → precise center
   - ✅ Window boundary clipping (no background capture)
   - ✅ Bounding box visualization (blue=Stage1, red=Stage2)
   - ✅ Generates 5 debug images
   - ⚠️ **Uses SIMULATED responses** (not real API)

3. **Documentation:**
   - ✅ `FINE_CROP_VQA_BRAINSTORM.md` - 10 ideas for improving accuracy
   - ✅ `brainstorm.md` - External LLM recommendations (bbox ranked #1)
   - ✅ Expected performance: 93% success, 2.1px error with bbox

---

## ⚠️ Critical Issue Discovered

**User observation:**
> "The small yellow button is almost exactly between the two colored crosshair/boxes."

**What this means:**
- Our **simulated VQA coordinates** might be inaccurate
- Stage 1 (blue) and Stage 2 (red) are both slightly off from actual button
- Real button appears to be between the two detection markers

**Simulated coordinates used:**
```python
# Stage 1 (coarse):
coarse_bbox = (38, 14, 12, 12)  # in window crop
coarse_center = (44, 20)

# Stage 2 (fine):
fine_bbox = (124, 108, 12, 12)  # in fine crop  
fine_center = (130, 114)
```

**These were based on manual grid search, NOT real VQA!**

---

## 🚀 Next Steps: Real VQA Testing

### Option 1: Create Real VQA Test Script

Create `test_vqa_real_api.py` that:
1. Captures Spotify window
2. Crops to title bar region
3. **Actually calls Claude 4.5 Sonnet** via pydantic-ai
4. Gets real bbox coordinates
5. Compares against ground truth
6. Measures actual accuracy

**Pros:**
- Full control over test
- Can measure accuracy precisely
- Can compare simulated vs real
- Generates detailed debug output

**Cons:**
- Need to set up pydantic-ai context
- Uses API credits
- Need ground truth coordinates

### Option 2: Use Existing GUI-Cub Tools

The VQA module is already integrated into code-puppy:
- Import and use `vqa_find_element_in_crop()` directly
- Pass real PIL Image crops
- Get real VQA responses
- Simpler integration

**Pros:**
- Already implemented and tested
- Uses production code
- Simpler setup

**Cons:**
- Less control over test flow
- Harder to measure accuracy metrics

### Option 3: Manual Testing via Code-Puppy

Just ask code-puppy agent to:
```
Use VQA to click the yellow minimize button on Spotify.
Show me the bounding box detection and coordinates.
```

**Pros:**
- Fastest to test
- Uses real VQA immediately

**Cons:**
- No systematic accuracy measurement
- Hard to compare results

---

## 📋 Recommended Approach

**Create `test_vqa_real_api.py` with these features:**

1. **Ground Truth Setup:**
   - Manually mark actual button center (e.g., via screenshot annotation)
   - Or use accessibility API to get precise bounds
   - Store as reference coordinates

2. **Two-Stage Real VQA:**
   ```python
   # Stage 1: Coarse detection on full window
   stage1_result = await vqa_find_element_in_crop(
       window_crop,
       "yellow minimize button",
       context
   )
   
   # Stage 2: Fine detection on ±100px crop
   fine_crop = crop_around(stage1_result.center, radius=100)
   stage2_result = await vqa_find_element_in_crop(
       fine_crop,
       "yellow minimize button",
       context
   )
   ```

3. **Accuracy Measurement:**
   - Calculate pixel error: `distance(detected_center, ground_truth)`
   - Log bbox dimensions: `(width, height)`
   - Track confidence scores
   - Success rate: error ≤ 2px?

4. **Comparison:**
   - Simulated coordinates vs Real VQA coordinates
   - Stage 1 accuracy vs Stage 2 accuracy
   - Bbox approach vs (hypothetical) direct point

5. **Visualization:**
   - Draw ground truth (green)
   - Draw Stage 1 detection (blue)
   - Draw Stage 2 detection (red)
   - Show error distances

---

## 🧪 Test Cases to Run

1. **Spotify minimize button** (current test)
   - 12px yellow circle
   - Top-left of window
   - Challenging due to edge position

2. **Spotify close button**
   - 12px red circle
   - Even more edge-case (leftmost)

3. **Spotify zoom button**
   - 12px green circle
   - Rightmost button

4. **Different window positions**
   - Centered on screen
   - Near edge (current)
   - Maximized

5. **Different themes**
   - Light mode
   - Dark mode

---

## 📊 Success Criteria

**For bbox approach to be validated:**

- ✅ Mean error < 3px (better than simulated 3.4px direct point)
- ✅ Success rate > 90% (error ≤ 2px)
- ✅ Stage 2 more accurate than Stage 1
- ✅ Confidence scores > 0.85
- ✅ Bbox dimensions reasonable (10-14px for 12px button)

**If these fail:**
- Try two-pass zoom refinement (Stage 2b)
- Add coordinate anchoring (reference red/green buttons)
- Adjust downscaling strategy
- Try different prompt formulations

---

## 🔧 Implementation Skeleton

```python
#!/usr/bin/env python3
"""Real VQA testing with Claude 4.5 Sonnet API."""

import asyncio
from pathlib import Path
import pyautogui
from PIL import Image, ImageDraw
from pydantic_ai import Agent

from code_puppy.tools.gui_cub.vqa_vision_click import (
    vqa_find_element_in_crop,
    crop_to_region,
)
from code_puppy.tools.gui_cub.platform import get_screen_scale_factor

# Ground truth (manually verified button center)
GROUND_TRUTH_X = 850  # Replace with actual
GROUND_TRUTH_Y = 380  # Replace with actual

async def test_real_vqa():
    """Test VQA with real Claude 4.5 Sonnet API."""
    
    # 1. Set up agent with vision model
    agent = Agent(
        model="claude-4-5-sonnet-latest",
        # ... configuration
    )
    
    # 2. Capture and crop window
    screenshot = pyautogui.screenshot()
    window_crop, offset = crop_to_region(
        screenshot,
        region=(window_x, window_y, window_w, window_h),
        scale_factor=get_screen_scale_factor()
    )
    
    # 3. Stage 1: Coarse VQA
    stage1_result = await vqa_find_element_in_crop(
        window_crop,
        "yellow minimize button",
        agent.run_context()  # How to get context?
    )
    
    print(f"Stage 1 BBox: {stage1_result.bbox}")
    print(f"Stage 1 Center: ({stage1_result.center_x}, {stage1_result.center_y})")
    
    # 4. Stage 2: Fine crop and VQA
    # ... crop ±100px around stage1 center
    # ... call vqa_find_element_in_crop again
    
    # 5. Calculate accuracy
    error_x = abs(final_x - GROUND_TRUTH_X)
    error_y = abs(final_y - GROUND_TRUTH_Y)
    error_distance = (error_x**2 + error_y**2) ** 0.5
    
    print(f"\nAccuracy:")
    print(f"  Error: {error_distance:.2f}px")
    print(f"  Success: {error_distance <= 2.0}")
    
    # 6. Visualize
    # ... draw ground truth, stage1, stage2 on image
    
if __name__ == "__main__":
    asyncio.run(test_real_vqa())
```

---

## 🎯 Key Questions to Answer

1. **How accurate is Claude 4.5 Sonnet with bbox approach?**
   - Is it really 93% success / 2.1px error?
   - Or is that optimistic?

2. **Are our simulated coordinates close?**
   - Were (44, 20) and (130, 114) good guesses?
   - How far off are they?

3. **Does bbox actually improve accuracy?**
   - Need to test direct point approach too
   - Compare variance

4. **Is two-stage better than single-stage?**
   - Does Stage 2 refine Stage 1?
   - Or is the ±100px crop too aggressive?

5. **What's the optimal crop size?**
   - ±100px? ±150px? ±50px?
   - Trade-off: larger crop = more context, smaller crop = more precision

---

## 📝 Files to Reference

- `code_puppy/tools/gui_cub/vqa_vision_click.py` - VQA implementation
- `test_vqa_coarse_to_fine.py` - Simulated test (current)
- `brainstorm.md` - External LLM recommendations
- `FINE_CROP_VQA_BRAINSTORM.md` - Detailed ideas for improvement

---

## 🚦 Action Items for Next Session

**Priority 1: Real VQA Testing**
1. Create `test_vqa_real_api.py`
2. Set up pydantic-ai Agent with Claude 4.5 Sonnet
3. Get ground truth coordinates (manual or accessibility API)
4. Run real VQA on Spotify minimize button
5. Measure actual accuracy
6. Compare simulated vs real coordinates

**Priority 2: If Accuracy Issues**
1. Implement two-pass zoom refinement
2. Add coordinate anchoring (red/green button references)
3. Try different crop sizes
4. Experiment with prompt variations

**Priority 3: Validation**
1. Test on multiple buttons (red, yellow, green)
2. Test different window positions
3. Test different themes (light/dark)
4. Calculate statistical metrics (mean, std dev, percentiles)

---

## 💬 Resume Prompt

**Copy this when resuming:**

```
I was working on VQA-based UI element detection using bounding boxes.

We implemented the bbox approach in vqa_vision_click.py and created a 
test script (test_vqa_coarse_to_fine.py) with SIMULATED VQA responses.

The user noticed the actual yellow minimize button is between the two 
detection markers (Stage 1 blue and Stage 2 red), suggesting our 
simulated coordinates are inaccurate.

NEXT STEP: Create a real VQA test script that uses actual Claude 4.5 
Sonnet API calls to measure real-world accuracy.

See RESUME_VQA_TESTING.md for full context and implementation plan.

Ready to create test_vqa_real_api.py with real VQA calls!
```

---

## 🏆 Expected Outcome

**After real VQA testing, we'll know:**

1. Actual bbox accuracy with Claude 4.5 Sonnet
2. Whether simulated coordinates were close
3. If bbox approach beats direct point (30% improvement claim)
4. Whether two-stage refinement helps
5. What optimizations are needed

**Then we can:**
- Document real performance metrics
- Optimize based on actual results (not assumptions)
- Confidently recommend bbox approach
- Integrate into production GUI-Cub tools

---

**Current state: Ready to test with real API calls!** 🚀

**Commits ready to push: 19**

**Next commit will be: `test_vqa_real_api.py` with actual Claude 4.5 Sonnet testing**