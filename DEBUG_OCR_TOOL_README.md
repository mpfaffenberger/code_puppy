# OCR Debugging Visualization Tool

Standalone script to debug OCR detection on Retina displays. Captures screenshots, runs OCR, and outputs annotated images with bounding boxes and confidence scores.

## Quick Start

### Test on Calculator

```bash
python debug_ocr_visualization.py --window "Calculator"
```

### Test on TextEdit

```bash
python debug_ocr_visualization.py --window "TextEdit"
```

### Test on Active Window

```bash
python debug_ocr_visualization.py
```

### Test Full Screen

```bash
python debug_ocr_visualization.py --fullscreen
```

## What It Does

1. **Captures screenshot** - Full screen or specific window
2. **Normalizes for OCR** - Applies blur, downscale, grayscale, contrast
3. **Runs OCR** - Uses Vision Framework with our settings
4. **Draws bounding boxes** - Color-coded by confidence:
   - 🟢 **Green** = High confidence (>70%)
   - 🟠 **Orange** = Medium confidence (50-70%)
   - 🔴 **Red** = Low confidence (<50%)
5. **Saves outputs** - Multiple images and detailed results

## Output Files

All files saved to current directory:

### `debug_ocr_original_2x.png`
Original Retina screenshot at 2x resolution (e.g., 1202x982 pixels)

### `debug_ocr_normalized_1x.png`
**This is what OCR actually sees!**
- Downscaled to 1x (e.g., 601x491 pixels)
- Grayscale
- Contrast enhanced
- Blurred to remove sub-pixel artifacts

### `debug_ocr_annotated.png`
Original image with:
- Bounding boxes around detected text
- Confidence percentages
- Color-coded by confidence level

### `debug_ocr_results.txt`
Detailed text output:
- Full extracted text
- Per-element details (text, confidence, position, size)
- Easy to grep and analyze

## Example Output

```
================================================================================
OCR DEBUGGING VISUALIZATION TOOL
================================================================================

Screen scale factor: 2.0x
Retina display detected - images will be normalized 2.0x → 1x for OCR

Focusing window: 'Calculator'...
✅ Focused window

Getting active window bounds...
✅ Window bounds (logical): (100, 100, 500, 400)
   Window title: Calculator

Capture region (physical): (200, 200, 1000, 800)

📸 Capturing screenshot...
✅ Captured: 1000x800 pixels

🔬 Preparing image for OCR (blur, downscale, grayscale, contrast)...
✅ Normalized: 500x400 pixels (L)

🔍 Running OCR...
✅ OCR complete!

Found 12 text elements
Average confidence: 0.87 (87%)

================================================================================
OCR RESULTS: 12 text elements found
================================================================================

[ 1] '7'
     Confidence: 92% (HIGH)
     Position: (120, 150) - Logical coords
     Size: 40x40
     Physical box: (240, 300, 80, 80)

[ 2] '8'
     Confidence: 94% (HIGH)
     Position: (180, 150) - Logical coords
     Size: 40x40
     Physical box: (360, 300, 80, 80)

...

================================================================================
SAVING DEBUG OUTPUT
================================================================================

✅ Saved original 2x image: debug_ocr_original_2x.png
   Dimensions: 1000x800
✅ Saved normalized 1x image: debug_ocr_normalized_1x.png
   Dimensions: 500x400
✅ Saved annotated image: debug_ocr_annotated.png
✅ Saved text results: debug_ocr_results.txt

================================================================================
SUMMARY
================================================================================

Total text elements: 12
Average confidence: 87%

Confidence breakdown:
  HIGH (>70%): 11 elements
  MED (50-70%): 1 elements
  LOW (<50%): 0 elements

================================================================================
Check the output images to verify:
  1. Are text regions detected correctly? (annotated image)
  2. Are bounding boxes in the right place? (annotated image)
  3. What does the normalized image look like? (1x image)
  4. What are the actual confidence scores? (results.txt)
================================================================================
```

## What to Look For

### ✅ Good Signs:

1. **High confidence (>80%)** - OCR is working well
2. **Bounding boxes align with text** - Coordinates are correct
3. **Normalized image is clean** - Grayscale, good contrast, no artifacts
4. **All visible text detected** - OCR isn't missing anything

### ⚠️ Warning Signs:

1. **Low confidence (<50%)** - OCR is struggling
2. **Bounding boxes offset** - Coordinate conversion issue
3. **Normalized image is blurry** - Too much blur (adjust radius)
4. **Missing text** - OCR not detecting some elements

### 🔴 Red Flags:

1. **Very low confidence (<30%)** - Something is very wrong
2. **Boxes completely wrong** - Scale factor detection broken
3. **Normalized image is black/white** - Contrast issue
4. **No text detected** - OCR engine failure

## Debugging Tips

### If confidence is still low after normalization:

1. **Check normalized image** - Does it look clean?
   - If too blurry: Reduce blur radius in `prepare_ocr_image()`
   - If too noisy: Increase blur radius
   - If poor contrast: Check autocontrast is working

2. **Compare 2x vs 1x** - Is downscaling helping?
   - Open both images side-by-side
   - 1x should look clearer for OCR

3. **Check text size** - Is text too small?
   - Text <12pt may have low confidence
   - Try on larger UI elements (buttons, titles)

### If coordinates are wrong:

1. **Check scale factor** - Should be 2.0 on Retina
2. **Verify bounding box color** - Green boxes = high confidence
3. **Look at physical vs logical** - Output shows both

### If OCR finds nothing:

1. **Check window capture** - Is the right window captured?
2. **Verify OCR engine** - Vision Framework available?
3. **Test with simple text** - Try Calculator (big numbers)

## Command-Line Options

```
usage: debug_ocr_visualization.py [-h] [--window WINDOW] [--fullscreen]

Debug OCR by capturing screenshots and visualizing detection boxes

optional arguments:
  -h, --help            show this help message and exit
  --window WINDOW, -w WINDOW
                        Window title to capture (e.g., 'Calculator', 'TextEdit')
  --fullscreen, -f      Capture full screen instead of window
```

## Integration with Code-Puppy Agent

The agent can run this script for you:

```
Run the OCR debug script on Calculator
```

The agent will:
1. Execute `python debug_ocr_visualization.py --window "Calculator"`
2. Show you the console output
3. Tell you where to find the output images
4. Help interpret the results

## Troubleshooting

### Script fails with import error:

```bash
# Make sure you're in the code-puppy directory
cd /path/to/code-puppy
python debug_ocr_visualization.py
```

### Permission denied:

```bash
chmod +x debug_ocr_visualization.py
./debug_ocr_visualization.py
```

### No window found:

- Try `--fullscreen` to test full screen capture
- Use partial window title: `--window "Calc"` instead of `--window "Calculator"`
- Make sure window is visible (not minimized)

## Example Test Sequence

```bash
# Test 1: Calculator (simple, large text)
python debug_ocr_visualization.py --window "Calculator"
# Expected: 90%+ confidence on button numbers

# Test 2: TextEdit (varied text sizes)
python debug_ocr_visualization.py --window "TextEdit"
# Expected: 80-90% confidence on UI labels

# Test 3: Full screen (complex)
python debug_ocr_visualization.py --fullscreen
# Expected: Varies, lots of text detected
```

## Before/After Comparison

### Before Fix (passing 2x directly to OCR):
- Average confidence: 30-50%
- Red/orange boxes everywhere
- OCR struggles with Retina text

### After Fix (normalized to 1x):
- Average confidence: 80-95%
- Mostly green boxes
- OCR handles text confidently

## Related Files

- `code_puppy/tools/gui_cub/ocr/extraction.py` - OCR extraction logic
- `code_puppy/tools/gui_cub/ocr_providers/vision_provider.py` - Vision Framework
- `OCR_RETINA_NORMALIZATION_FIX.md` - Implementation documentation
- `llm.md` - Expert recommendations
