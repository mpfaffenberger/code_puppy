# Accessibility Diagnostic Tool 🔍

**Purpose:** Debug and diagnose why accessibility/element tree tools aren't returning good labels/info.

---

## Quick Start

```bash
# Show statistics about element quality
python scripts/debug_accessibility.py --stats

# Compare accessibility vs OCR (highly recommended!)
python scripts/debug_accessibility.py --compare-ocr

# Interactive browser mode
python scripts/debug_accessibility.py -i

# Test compaction impact
python scripts/debug_accessibility.py --test-compaction
```

---

## What It Does

This script runs **outside the agent** to help diagnose accessibility API issues:

### 1. **Element Quality Analysis**
Analyzes accessibility elements to understand:
- How many have good titles vs empty/useless titles
- Interactive vs static element ratio
- Role distribution
- Average title length
- Overall data quality

```bash
python scripts/debug_accessibility.py --stats
```

**Output:**
```json
{
  "total": 150,
  "with_title": 80,
  "empty_title": 70,
  "good_title": 45,
  "useless_title": 35,
  "interactive_elements": 20,
  "static_elements": 130,
  "by_role": {
    "AXButton": 8,
    "AXTextField": 4,
    "AXStaticText": 95
  }
}
```

### 2. **Compare with OCR** (Most Useful!)
Compares what accessibility sees vs what OCR sees:

```bash
python scripts/debug_accessibility.py --compare-ocr
```

**This reveals:**
- ✅ Text found by both (good accessibility data)
- 👁️ Text OCR found but accessibility missed (missing labels)
- 📱 Text accessibility found but OCR missed (aria-labels, hidden text)

**Example Output:**
```
📊 Results:
   Accessibility elements: 150
   OCR text elements: 89
   OCR total words: 234

🔍 Overlap Analysis:
   Both found: 12 texts
   OCR only: 77 texts
   Accessibility only: 8 texts

💡 Assessment:
   ⚠️  Accessibility is missing a lot of visible text!
   ➜  Consider: OCR might be better for text-heavy UIs
```

### 3. **Test Compaction Impact**
See what gets filtered out during compaction:

```bash
python scripts/debug_accessibility.py --test-compaction
```

**Shows:**
- Full tree statistics
- Compacted tree statistics
- What was filtered out
- Sample of filtered elements

### 4. **Interactive Browser**
Explore elements interactively:

```bash
python scripts/debug_accessibility.py -i
```

**Commands:**
- `list` - List all elements
- `list axbutton` - List only buttons
- `show 5` - Show detailed info for element #5
- `stats` - Show statistics
- `compare` - Compare with OCR
- `refresh` - Refresh element tree
- `quit` - Exit

---

## Advanced Usage

### Show Full Element Tree
```bash
python scripts/debug_accessibility.py --full-tree
```

### Filter by Role
```bash
python scripts/debug_accessibility.py --role AXButton --stats
```

### Save to File for Analysis
```bash
python scripts/debug_accessibility.py --stats --output analysis.json
```

### Focus Specific App (macOS)
```bash
python scripts/debug_accessibility.py --app Safari --stats
```

---

## Interpreting Results

### Good Accessibility Data ✅
```json
{
  "total": 150,
  "good_title": 120,     // 80% have good titles
  "empty_title": 30,
  "interactive_elements": 85
}
```
**Action:** Accessibility API is working well! Use it.

---

### Poor Accessibility Data ❌
```json
{
  "total": 150,
  "good_title": 15,      // Only 10% have good titles
  "empty_title": 135,
  "interactive_elements": 8
}
```
**Action:** Accessibility API is unreliable. Prefer OCR or VQA.

---

### Marginal Accessibility Data ⚠️
```json
{
  "total": 150,
  "good_title": 60,      // 40% have good titles
  "empty_title": 90,
  "interactive_elements": 35
}
```
**Action:** Use accessibility for interactive elements, OCR for text.

---

## Common Issues

### Issue: "Most elements have empty titles"

**Diagnosis:**
```bash
python scripts/debug_accessibility.py --compare-ocr
```

If OCR finds lots of text that accessibility doesn't:
- **Problem:** App doesn't use proper accessibility labels
- **Solution:** Prefer OCR or VQA for this app

---

### Issue: "Interactive elements count is low"

**Diagnosis:**
```bash
python scripts/debug_accessibility.py --full-tree | grep -i button
```

If you see buttons in UI but script doesn't find them:
- **Problem:** Wrong window focused OR custom controls
- **Solution:** Check window focus, try OCR for custom controls

---

### Issue: "Compaction filters out important elements"

**Diagnosis:**
```bash
python scripts/debug_accessibility.py --test-compaction
```

If important elements are in "filtered out" list:
- **Problem:** Relevance scoring is too aggressive
- **Solution:** Adjust element scoring in `element_list.py`

---

## Debugging Workflow

### Step 1: Get Baseline
```bash
python scripts/debug_accessibility.py --stats
```

**Questions:**
- Total elements found?
- What % have good titles?
- Interactive vs static ratio?

---

### Step 2: Compare with OCR
```bash
python scripts/debug_accessibility.py --compare-ocr
```

**Questions:**
- Is OCR finding more text?
- Is overlap high or low?
- What's the recommendation?

---

### Step 3: Inspect Specific Elements
```bash
python scripts/debug_accessibility.py -i
> list axbutton
> show 0
> show 1
```

**Questions:**
- Do button titles match what you see on screen?
- Are coordinates accurate?
- Are labels meaningful?

---

### Step 4: Test Compaction
```bash
python scripts/debug_accessibility.py --test-compaction
```

**Questions:**
- Are good elements being filtered?
- Is relevance scoring working?
- Should we adjust compaction?

---

### Step 5: Save for Analysis
```bash
python scripts/debug_accessibility.py --full-tree --output debug.json
```

Share `debug.json` with team for detailed analysis.

---

## Platform Differences

### macOS (atomacos)
- Uses `AX*` roles (e.g., `AXButton`)
- Generally good accessibility support
- Works well with native apps
- May struggle with Electron/web apps

### Windows (UIAutomation)
- Uses generic names (e.g., `Button`, `Edit`)
- Support varies by framework
- WPF/UWP: Excellent
- Win32: Variable
- Electron: Often poor

---

## Next Steps After Diagnosis

### If Accessibility is Good ✅
- Keep using accessibility-first approach
- OCR/VQA as fallback only

### If Accessibility is Poor ❌
- Switch to OCR-first for text elements
- Use VQA for visual elements
- Only use accessibility for very specific cases

### If Accessibility is Marginal ⚠️
- Use accessibility for interactive elements (buttons, fields)
- Use OCR for reading text content
- Use VQA for complex visual tasks

---

## Example Session

```bash
$ python scripts/debug_accessibility.py --compare-ocr

================================================================================
  GUI-Cub Accessibility Diagnostic Tool
================================================================================

Platform: macOS
Time: 2025-01-10 14:30:00

--------------------------------------------------------------------------------
  Comparing Accessibility vs OCR
--------------------------------------------------------------------------------

📱 Fetching accessibility elements...
✅ Found 150 elements

👁️  Running OCR...
✅ Extracted 234 words

📊 Results:
   Accessibility elements: 150
   OCR text elements: 89
   OCR total words: 234

📝 Text Content:
   Accessibility unique titles: 18
   OCR unique texts: 82

🔍 Overlap Analysis:
   Both found: 12 texts
   OCR only: 70 texts
   Accessibility only: 6 texts

👁️  OCR found but accessibility missed (sample):
      'submit'
      'username'
      'password'
      'sign in'
      'forgot password?'
      ...

💡 Assessment:
   ⚠️  Accessibility is missing a lot of visible text!
   ➜  Consider: OCR might be better for text-heavy UIs
   ❌ Very low overlap - accessibility labels may be poor quality
   ➜  Recommendation: Prefer OCR or VQA for this application
```

---

## Tips

1. **Run on different apps** to see quality variance
2. **Use `--compare-ocr`** as first diagnostic step
3. **Interactive mode** is great for exploration
4. **Save output** for comparing across sessions
5. **Test after app updates** (accessibility can change)

---

## Troubleshooting

### "No elements found"
- Check if correct window is focused
- Try `--app <name>` to target specific app
- macOS: Grant accessibility permissions

### "OCR comparison fails"
- Install dependencies: `uv pip install pyautogui pillow`
- Make sure window is visible (not minimized)

### "Script crashes"
- Check Python version (3.11+)
- Verify gui-cub is calibrated
- Check platform support (macOS/Windows only)
