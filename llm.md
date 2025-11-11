Apple’s Vision Framework confidence scores appear low but are normal for that engine. Confidence values (≈0.3–0.6) reflect a conservative, non-linear internal scale rather than true probability. For UI text the model is trained mainly on document fonts and lighting, so Vision under-reports confidence even when recognition is perfect.

### Expected confidence ranges

| Text type                 | Typical Vision confidence | Practical accuracy |
| ------------------------- | ------------------------- | ------------------ |
| Clean UI fonts (12–16 pt) | 0.35–0.55                 | 95–100 %           |
| Document scans / print    | 0.6–0.9                   | 95–100 %           |
| Noisy / photos            | 0.2–0.5                   | variable           |

### Interpretation

* The field `VNRecognizedTextObservation.confidence` is a relative internal score, not a calibrated probability.
* Scale is roughly logistic: values cluster near 0.5 even for correct text.
* 0.5 ≈ “good match,” not 50 % certainty.
* Scores < 0.3 usually indicate uncertain segmentation or mixed characters.

### Comparisons

| Engine                          | Reported confidence meaning         | Typical clean-text range |
| ------------------------------- | ----------------------------------- | ------------------------ |
| **Apple Vision**                | Relative internal likelihood        | 0.3–0.8                  |
| **Tesseract 5**                 | Log-probability normalized to 0–100 | 80–99                    |
| **Google Vision API**           | Calibrated softmax prob.            | 0.8–1.0                  |
| **Azure Vision / AWS Textract** | Calibrated linear prob.             | 0.9–1.0                  |

Thus Vision scores appear lower because others rescale to “percent confidence,” while Vision keeps model-space values.

### Why UI text scores low

* **Small size:** < 18 pt reduces glyph stroke count.
* **Retina anti-aliasing:** sub-pixel blending softens edges.
* **Training bias:** models built on documents, not macOS UI snapshots.
* **Color or shadows:** minor penalties from background variance.

### Recommendations

1. Treat anything ≥ 0.3 as valid if the text visually aligns.
2. Use consensus: accept lines whose text parses or matches expected tokens rather than relying on confidence alone.
3. For automation, threshold at ≈ 0.25–0.3 and validate via string match or bounding-box geometry.
4. If needed, resample to 1× logical pixels and use the Accurate recognition level; do not sharpen post-resize.
5. Keep `usesLanguageCorrection=True`; it slightly raises confidence on dictionary words.

### Best practice summary

* **Do not equate Vision confidence with probability.**
* **Trust correctness, not the number.** Use confidence only to filter clear garbage (≤ 0.2).
* **50 % confidence is typical and acceptable** for clean UI captures.
