# OCR Debug Prompt for Online LLM

## Problem Statement

I'm working on desktop automation for Windows Calculator and having trouble with OCR detecting individual button text. Here's the situation:

### The Issue

- **Goal:** Find and click specific calculator buttons (like "8", "CE", etc.)
- **Tool:** pytesseract/Tesseract OCR on screenshots of Windows Calculator
- **Problem:** OCR finds general text ("Calculator", "Standard") but fails to detect individual button labels reliably
- **Symptom:** When I run OCR, it finds grouped text like "7 8 9 x" or "% CE Cc @" but not individual buttons like "8" or "CE" as separate elements

### What I've Tried

1. **Upscaling 2x** with LANCZOS resampling
   - Result: Finds some text but not individual buttons

2. **Upscaling 4x** with LANCZOS resampling
   - Result: Even worse, finds less text

3. **Using `pytesseract.image_to_data()`** to get bounding boxes for each text element
   - Result: Not detecting buttons as individual elements

### Current OCR Results

**Full text OCR finds:**
```
Calculator
Standard
% CE Cc @
7 8 9 x
4 5 6 -
```

**Individual element detection finds:**
```python
['Calculator', '=', 'Standard', '5']
```

**Missing:** Individual number buttons and most calculator buttons as separate elements

### Screenshot Details

- **Window:** Windows Calculator (Standard mode)
- **Resolution:** 336x547 pixels
- **DPI Scaling:** 100% (96 DPI)
- **Screenshot:** Attached as `windows_window_direct.png`

---

## Questions

1. **What image preprocessing techniques would help OCR better detect individual calculator buttons?**

2. **Should I try:**
   - Grayscale conversion?
   - Thresholding/binarization?
   - Contrast enhancement?
   - Edge detection?
   - Color inversion?
   - Sharpening?

3. **Are there specific Tesseract PSM (Page Segmentation Mode) settings I should try?**
   - Current: Using default PSM
   - Options: PSM 6 (uniform block), PSM 11 (sparse text), PSM 8 (single word), etc.

4. **Would a different OCR approach work better for flat, modern UI button text?**
   - EasyOCR?
   - PaddleOCR?
   - Custom CV template matching?

5. **Any Python/PIL/OpenCV preprocessing steps you'd recommend before OCR?**

---

## Request

Please analyze the attached calculator screenshot (`windows_window_direct.png`) and suggest:

- **Specific preprocessing steps** with Python code examples
- **Tesseract configuration** recommendations
- **Alternative approaches** if OCR isn't the right tool
- **Why** the current approach might be failing

---

## Additional Context

- **Environment:** Windows 10/11
- **Python Libraries:** PIL/Pillow, pytesseract, pyautogui
- **Use Case:** Automated testing/RPA for calculator application
- **Coordinate system:** Already verified to be accurate (clicking works, just can't find targets)

---

## Files to Attach

1. `windows_window_direct.png` - Screenshot of Calculator window
2. `windows_debug_with_click.png` - (Optional) Shows where we're clicking vs where buttons are
