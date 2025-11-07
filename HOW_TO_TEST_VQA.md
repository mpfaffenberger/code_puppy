# How to Test Two-Stage VQA with Code-Puppy

## 🎯 Quick Start

The two-stage VQA tool is now registered and ready to use!

---

## 📬 **Prompt for Code-Puppy:**

### **Option 1: Natural Language (Simplest)**

Just ask:

```
Click the yellow minimize button on Spotify
```

**That's it!** The agent will automatically use the two-stage VQA with debug images.

Or be more explicit:

```
Use VQA to click the yellow minimize button on Spotify
```

### **Option 2: Specific Tool Call**

If you want control over debug images:

```
Use desktop_vqa_click_two_stage to click the yellow minimize button on Spotify.
Set save_debug to False if you don't want debug images.
```

Or:

```
Find and click the yellow minimize button on Spotify
```

(Uses `desktop_find_and_click` which is now an alias for two-stage VQA)

---

## 🚀 **Step-by-Step Test Instructions:**

### **1. Make Sure Spotify is Running**
```bash
# Open Spotify if not already running
open -a Spotify
```

### **2. Start Code-Puppy**
You're already here! 😄

### **3. Just ask!**

Paste this simple prompt:

```
Click the yellow minimize button on Spotify
```

**OR** for more details:

```
Use VQA to click the yellow minimize button on Spotify. 
Show me:
1. Whether the click was successful
2. The coordinates clicked
3. The confidence scores
4. Where the debug images were saved
```

---

## 💾 **What Will Happen:**

1. **Stage 1 (Coarse):**
   - Captures Spotify window
   - Runs VQA on full window (1600x1200px)
   - Gets approximate button location (~70% confidence)
   - Saves: `1_stage1_coarse_crop.png`

2. **Stage 2 (Fine):**
   - Crops ±100px around Stage 1 result
   - Runs VQA on small focused crop (200-400px)
   - Gets precise center (~95% confidence)
   - Saves: `2_stage2_fine_crop.png`

3. **Click:**
   - Converts coordinates to screen space
   - Clicks the button!
   - Saves: `3_visualization_both_stages.png`

4. **Debug Images:**
   - All saved to: `vqa_debug_output/`
   - Timestamped filenames
   - Includes full screenshot, crops, visualization

---

## 📊 **Expected Output:**

```json
{
  "success": true,
  "element_found": true,
  "click_x": 850,
  "click_y": 427,
  "confidence": 0.95,
  "error": null
}
```

**Debug Images:**
- `vqa_debug_output/20231106_143022_0_full_screenshot.png`
- `vqa_debug_output/20231106_143022_1_stage1_coarse_crop.png`
- `vqa_debug_output/20231106_143022_2_stage2_fine_crop.png`
- `vqa_debug_output/20231106_143022_3_visualization_both_stages.png`

**Visualization Shows:**
- 🔵 Blue box + crosshair = Stage 1 (coarse detection)
- 🔴 Red box + crosshair + dot = Stage 2 (fine detection, FINAL)

---

## ✅ **Success Criteria:**

The test is successful if:
1. ✅ `success: true`
2. ✅ `element_found: true`
3. ✅ Confidence > 90%
4. ✅ Spotify window minimizes
5. ✅ Debug images saved to `vqa_debug_output/`
6. ✅ Visualization shows both stages

---

## 🔍 **Troubleshooting:**

### **If VQA Fails to Find Element:**

Check the debug images:
1. `1_stage1_coarse_crop.png` - Is the button visible?
2. `2_stage2_fine_crop.png` - Is it in the fine crop?
3. `3_visualization_both_stages.png` - Where did VQA think it was?

### **If Coordinates are Off:**

Look at visualization:
- Are blue and red boxes both near the actual button?
- Is Stage 2 (red) more accurate than Stage 1 (blue)?
- Are bboxes the right size (~12x12 for window buttons)?

### **If Model Not Found:**

Make sure Claude 4.5 Sonnet is configured:
```bash
# Check available models
/models

# Select Claude 4.5 Sonnet
/model claude-4-5-sonnet
```

---

## 📝 **Alternative Test Prompts:**

### **Test Different Buttons:**

```
Use two-stage VQA to click the red close button on Spotify
```

```
Use two-stage VQA to click the green zoom button on Spotify
```

### **Test Without Debug Images:**

```
Click the yellow minimize button using desktop_vqa_click_two_stage 
but set save_debug to False
```

### **Test on Different App:**

```
Use two-stage VQA to click the minimize button on Safari
```

---

## 🏆 **What We're Testing:**

1. **Accuracy:** Does it click within ±2px of true center?
2. **Reliability:** Does it succeed 93%+ of the time?
3. **Confidence:** Does Stage 2 give ~95% confidence?
4. **Performance:** Does Stage 2 improve over Stage 1?
5. **Debug Images:** Are visualizations helpful for debugging?

---

## 🚀 **Ready to Test!**

**Copy this entire prompt:**

```
I want to test the new two-stage VQA implementation.

Please use desktop_vqa_click_two_stage to click the yellow minimize 
button on Spotify with debug images enabled.

After the click, show me:
1. Full result dictionary
2. Both stage confidence scores
3. Final click coordinates
4. Whether Spotify minimized
5. Where debug images were saved
6. Analysis of the visualization image

Make sure Spotify is the active window first!
```

---

**That's it! The tool is fully integrated and ready to use!** 🎉