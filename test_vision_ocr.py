#!/usr/bin/env python3
"""Test Vision Framework OCR on saved screenshots."""

import sys
from pathlib import Path

from PIL import Image

from code_puppy.tools.gui_cub.ocr_providers.vision_provider import VisionOCRProvider

if len(sys.argv) < 2:
    print("Usage: python test_vision_ocr.py <image_path>")
    sys.exit(1)

image_path = Path(sys.argv[1])
if not image_path.exists():
    print(f"Error: {image_path} not found")
    sys.exit(1)

print(f"Testing Vision OCR on: {image_path}")
print(f"Image size: {image_path.stat().st_size} bytes")

# Load image
image = Image.open(image_path)
print(f"Image dimensions: {image.size}")
print(f"Image mode: {image.mode}")

# Test Vision provider
provider = VisionOCRProvider()
print(f"\nVision available: {provider.is_available()}")

if not provider.is_available():
    print("Vision Framework not available!")
    sys.exit(1)

print("\nRunning OCR...")
result = provider.extract_text(image, language="en")

print(f"\nResults:")
print(f"  Success: {result.success}")
print(f"  Provider: {result.provider}")
print(f"  Words found: {len(result.words)}")
print(f"  Error: {result.error}")
print(f"\nFull text:")
print("="*60)
print(result.full_text)
print("="*60)

if result.words:
    print(f"\nFirst 10 words:")
    for i, word in enumerate(result.words[:10]):
        print(f"  {i+1}. '{word.text}' (confidence: {word.confidence:.2f})")
