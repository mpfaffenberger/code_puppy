# Native OCR Development Plan

## 🔄 Updates (v2)

**Key Changes from v1:**
1. ✅ **All OCR is synchronous** - No async/await complexity
   - WinRT uses `asyncio.run()` wrapper for synchronous interface
   - Vision Framework is already synchronous
   - Simple blocking calls throughout

2. ✅ **Quiet startup warnings** - Tesseract is now optional fallback
   - **OLD:** Big yellow warning on startup if Tesseract missing
   - **NEW:** Small info message: "Tesseract not installed (optional fallback)"
   - **Show warnings ONLY when:**
     - Native OCR fails
     - Tesseract fallback is needed
     - Tesseract is missing
     - Then offer to install interactively

3. ✅ **Interactive installation offer** - When OCR fallback fails
   - Prompt user: Install now / Show instructions / Skip
   - No admin nagging on startup
   - Smart installation at point of need

---

## Executive Summary

Migrate GUI-Cub's OCR system from Tesseract-only to **native platform OCR APIs with Tesseract fallback**.

### Target Architecture:
- **Windows**: WinRT OCR (Windows.Media.Ocr) → Tesseract fallback
- **macOS**: Apple Vision Framework (VNRecognizeTextRequest) → Tesseract fallback  
- **Linux**: Tesseract only (no native OCR API)

### Benefits:
- ✅ **Faster** - Native APIs are 2-5x faster than Tesseract
- ✅ **No dependencies** - No need to install Tesseract on Windows/macOS
- ✅ **Better accuracy** - OS-native OCR is optimized for each platform
- ✅ **HiDPI native** - Apple Vision and WinRT handle Retina/scaling automatically
- ✅ **Smaller install** - No 200MB Tesseract download on Windows
- ✅ **Quieter startup** - No big yellow warnings if Tesseract missing (it's just a fallback)
- ✅ **Synchronous** - No async complexity, simple blocking calls

---

## Phase 1: Architecture & Design

### 1.1 OCR Provider Interface

Create an abstract provider interface that all OCR backends implement:

```python
# code_puppy/tools/gui_cub/ocr_providers/base.py

from abc import ABC, abstractmethod
from PIL import Image
from typing import List, Optional
from pydantic import BaseModel

class OCRWord(BaseModel):
    """Single word/text element from OCR."""
    text: str
    confidence: float  # 0.0 to 1.0
    bbox: tuple[int, int, int, int]  # (x, y, width, height)
    
class OCRResult(BaseModel):
    """Result from OCR operation."""
    success: bool
    words: List[OCRWord]
    full_text: str
    provider: str  # "winrt", "vision", "tesseract"
    error: Optional[str] = None

class OCRProvider(ABC):
    """Abstract base class for OCR providers."""
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this OCR provider is available on this system."""
        pass
    
    @abstractmethod
    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Extract text from an image."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get provider name for logging."""
        pass
```

### 1.2 Provider Implementations

Create separate provider modules:

```
code_puppy/tools/gui_cub/ocr_providers/
├── __init__.py          # Provider registry and factory
├── base.py              # Abstract interface
├── winrt_provider.py    # Windows WinRT OCR
├── vision_provider.py   # macOS Vision Framework
├── tesseract_provider.py # Tesseract fallback
└── provider_chain.py    # Chain-of-responsibility pattern
```

### 1.3 Provider Chain (Fallback Logic)

```python
# code_puppy/tools/gui_cub/ocr_providers/provider_chain.py

class OCRProviderChain:
    """Chain of OCR providers with automatic fallback."""
    
    def __init__(self, providers: List[OCRProvider]):
        self.providers = [p for p in providers if p.is_available()]
    
    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Try providers in order until one succeeds."""
        errors = []
        
        for provider in self.providers:
            try:
                result = provider.extract_text(image, language)
                if result.success:
                    return result
                errors.append(f"{provider.get_name()}: {result.error}")
            except Exception as e:
                errors.append(f"{provider.get_name()}: {str(e)}")
        
        # All providers failed
        return OCRResult(
            success=False,
            words=[],
            full_text="",
            provider="none",
            error=f"All OCR providers failed: {'; '.join(errors)}"
        )
```

---

## Phase 2: Windows WinRT OCR Implementation

### 2.1 Dependencies

```toml
# pyproject.toml additions:
[project.optional-dependencies]
gui-cub = [
    # ... existing deps ...
    "winrt-Windows.Media.Ocr; sys_platform == 'win32'",
    "winrt-Windows.Graphics.Imaging; sys_platform == 'win32'",
    "winrt-Windows.Storage.Streams; sys_platform == 'win32'",
]
```

### 2.2 WinRT Provider Implementation

```python
# code_puppy/tools/gui_cub/ocr_providers/winrt_provider.py

from PIL import Image
import io
from typing import List

try:
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.graphics.imaging import BitmapDecoder, SoftwareBitmap
    from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False

from .base import OCRProvider, OCRResult, OCRWord

class WinRTOCRProvider(OCRProvider):
    """Windows Runtime OCR provider using Windows.Media.Ocr."""
    
    def __init__(self):
        self._engine = None
        if WINRT_AVAILABLE:
            try:
                # Try to get OCR engine for current display language
                self._engine = OcrEngine.try_create_from_user_profile_languages()
            except:
                pass
    
    def is_available(self) -> bool:
        """Check if WinRT OCR is available (Windows 10+)."""
        return WINRT_AVAILABLE and self._engine is not None
    
    def get_name(self) -> str:
        return "WinRT OCR"
    
    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Extract text using WinRT OCR (synchronous wrapper).
        
        Steps:
        1. Convert PIL Image to bytes
        2. Load into InMemoryRandomAccessStream
        3. Create BitmapDecoder
        4. Get SoftwareBitmap
        5. Run OCR engine (wrapped in asyncio.run())
        6. Parse results
        """
        import asyncio
        
        try:
            # Convert PIL Image to PNG bytes
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            # WinRT OCR is async, but we wrap it for synchronous use
            async def _do_ocr():
                # Create WinRT stream
                stream = InMemoryRandomAccessStream()
                writer = DataWriter(stream.get_output_stream_at(0))
                writer.write_bytes(img_bytes.read())
                await writer.store_async()
                await writer.flush_async()
                
                # Decode to SoftwareBitmap
                decoder = await BitmapDecoder.create_async(stream)
                bitmap = await decoder.get_software_bitmap_async()
                
                # Run OCR
                return await self._engine.recognize_async(bitmap)
            
            # Run async code synchronously
            result = asyncio.run(_do_ocr())
            
            # Parse results
            words = []
            for line in result.lines:
                for word in line.words:
                    # WinRT returns bounding box as (x, y, width, height)
                    bbox = (
                        int(word.bounding_rect.x),
                        int(word.bounding_rect.y),
                        int(word.bounding_rect.width),
                        int(word.bounding_rect.height)
                    )
                    words.append(OCRWord(
                        text=word.text,
                        confidence=1.0,  # WinRT doesn't provide confidence
                        bbox=bbox
                    ))
            
            full_text = result.text
            
            return OCRResult(
                success=True,
                words=words,
                full_text=full_text,
                provider="winrt"
            )
            
        except Exception as e:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="winrt",
                error=str(e)
            )
```

### 2.3 Testing Strategy

**Test files:**
- `tests/gui_cub/ocr_providers/test_winrt_provider.py`

**Test cases:**
1. Availability detection on Windows 10+
2. Simple text extraction (Hello World)
3. Multi-line text
4. Numbers and special characters
5. Low contrast text
6. HiDPI/scaled screenshots
7. Performance benchmarking vs Tesseract

---

## Phase 3: macOS Vision Framework Implementation

### 3.1 Dependencies

```toml
# pyproject.toml additions:
[project.optional-dependencies]
gui-cub = [
    # ... existing deps ...
    "pyobjc-framework-Vision; sys_platform == 'darwin'",
    "pyobjc-framework-Quartz; sys_platform == 'darwin'",
]
```

### 3.2 Vision Provider Implementation

```python
# code_puppy/tools/gui_cub/ocr_providers/vision_provider.py

from PIL import Image
import io
from typing import List

try:
    import Vision
    import Quartz
    from Foundation import NSURL, NSData
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

from .base import OCRProvider, OCRResult, OCRWord

class VisionOCRProvider(OCRProvider):
    """macOS Vision Framework OCR provider using VNRecognizeTextRequest."""
    
    def is_available(self) -> bool:
        """Check if Vision framework is available (macOS 10.15+)."""
        if not VISION_AVAILABLE:
            return False
        
        # Check macOS version >= 10.15 (Vision OCR introduced)
        import platform
        version = platform.mac_ver()[0]
        major, minor = map(int, version.split('.')[:2])
        return major >= 10 and minor >= 15
    
    def get_name(self) -> str:
        return "Apple Vision"
    
    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Extract text using Vision framework.
        
        Steps:
        1. Convert PIL Image to CGImage
        2. Create VNImageRequestHandler
        3. Create VNRecognizeTextRequest with fast recognition
        4. Perform request
        5. Parse observations
        """
        try:
            # Convert PIL Image to PNG bytes
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_data = NSData.dataWithBytes_length_(
                img_bytes.getvalue(),
                len(img_bytes.getvalue())
            )
            
            # Create CGImage from data
            image_source = Quartz.CGImageSourceCreateWithData(img_data, None)
            cg_image = Quartz.CGImageSourceCreateImageAtIndex(image_source, 0, None)
            
            # Create Vision request
            request = Vision.VNRecognizeTextRequest.alloc().init()
            
            # Set recognition level (fast vs accurate)
            # VNRequestTextRecognitionLevelFast = 0
            # VNRequestTextRecognitionLevelAccurate = 1
            request.setRecognitionLevel_(0)  # Fast for desktop automation
            
            # Set language if needed
            if language and language != "en":
                request.setRecognitionLanguages_([language])
            
            # Create request handler
            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
                cg_image, {}
            )
            
            # Perform OCR
            success = handler.performRequests_error_([request], None)
            
            if not success:
                return OCRResult(
                    success=False,
                    words=[],
                    full_text="",
                    provider="vision",
                    error="Vision request failed"
                )
            
            # Parse results
            words = []
            full_text_lines = []
            
            observations = request.results()
            for observation in observations:
                text = observation.text()
                confidence = observation.confidence()
                
                # Get bounding box (normalized 0.0-1.0)
                bbox_norm = observation.boundingBox()
                
                # Convert to pixel coordinates
                # Note: Vision uses bottom-left origin, need to flip Y
                img_width, img_height = image.size
                x = int(bbox_norm.origin.x * img_width)
                y = int((1.0 - bbox_norm.origin.y - bbox_norm.size.height) * img_height)
                width = int(bbox_norm.size.width * img_width)
                height = int(bbox_norm.size.height * img_height)
                
                words.append(OCRWord(
                    text=text,
                    confidence=confidence,
                    bbox=(x, y, width, height)
                ))
                full_text_lines.append(text)
            
            full_text = '\n'.join(full_text_lines)
            
            return OCRResult(
                success=True,
                words=words,
                full_text=full_text,
                provider="vision"
            )
            
        except Exception as e:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="vision",
                error=str(e)
            )
```

### 3.3 Retina/HiDPI Handling

**Key advantage:** Vision framework automatically handles Retina coordinates!

- Vision returns **normalized coordinates** (0.0 to 1.0)
- We multiply by image pixel dimensions
- No need for manual backingScaleFactor conversion
- Works correctly on Retina and non-Retina displays

### 3.4 Testing Strategy

**Test files:**
- `tests/gui_cub/ocr_providers/test_vision_provider.py`

**Test cases:**
1. Availability detection on macOS 10.15+
2. Simple text extraction
3. Retina screenshot (2x scale factor)
4. Non-Retina screenshot (1x scale factor)
5. Multi-line text
6. Performance benchmarking vs Tesseract
7. Coordinate accuracy (verify bounding boxes)

---

## Phase 4: Tesseract Fallback Provider

### 4.1 Refactor Existing Tesseract Code

```python
# code_puppy/tools/gui_cub/ocr_providers/tesseract_provider.py

from PIL import Image
from typing import List

try:
    import pytesseract
    from pytesseract import Output
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from .base import OCRProvider, OCRResult, OCRWord

class TesseractOCRProvider(OCRProvider):
    """Tesseract OCR provider (cross-platform fallback)."""
    
    def is_available(self) -> bool:
        """Check if Tesseract is installed."""
        if not TESSERACT_AVAILABLE:
            return False
        
        try:
            pytesseract.get_tesseract_version()
            return True
        except:
            return False
    
    def get_name(self) -> str:
        return "Tesseract"
    
    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Extract text using Tesseract."""
        try:
            # Map language codes
            lang_map = {
                "en": "eng",
                "es": "spa",
                "fr": "fra",
                # ... etc
            }
            tesseract_lang = lang_map.get(language, "eng")
            
            # Run OCR
            data = pytesseract.image_to_data(
                image,
                lang=tesseract_lang,
                output_type=Output.DICT
            )
            
            # Parse results
            words = []
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                if not text:
                    continue
                
                words.append(OCRWord(
                    text=text,
                    confidence=data['conf'][i] / 100.0,  # Convert to 0.0-1.0
                    bbox=(
                        data['left'][i],
                        data['top'][i],
                        data['width'][i],
                        data['height'][i]
                    )
                ))
            
            full_text = pytesseract.image_to_string(image, lang=tesseract_lang)
            
            return OCRResult(
                success=True,
                words=words,
                full_text=full_text,
                provider="tesseract"
            )
            
        except Exception as e:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="tesseract",
                error=str(e)
            )
```

---

## Phase 5: Provider Factory & Integration

### 5.1 Provider Factory

```python
# code_puppy/tools/gui_cub/ocr_providers/__init__.py

from .base import OCRProvider, OCRResult, OCRWord
from .provider_chain import OCRProviderChain
from .winrt_provider import WinRTOCRProvider
from .vision_provider import VisionOCRProvider
from .tesseract_provider import TesseractOCRProvider

from code_puppy.tools.gui_cub.platform import IS_WINDOWS, IS_MACOS, IS_LINUX

def get_default_ocr_chain() -> OCRProviderChain:
    """Get platform-specific OCR provider chain.
    
    Windows: WinRT → Tesseract
    macOS: Vision → Tesseract
    Linux: Tesseract only
    """
    providers = []
    
    if IS_WINDOWS:
        providers.append(WinRTOCRProvider())
    elif IS_MACOS:
        providers.append(VisionOCRProvider())
    
    # Tesseract fallback for all platforms
    providers.append(TesseractOCRProvider())
    
    return OCRProviderChain(providers)

# Singleton instance
_default_chain = None

def get_ocr_provider() -> OCRProviderChain:
    """Get singleton OCR provider chain."""
    global _default_chain
    if _default_chain is None:
        _default_chain = get_default_ocr_chain()
    return _default_chain
```

### 5.2 Update ocr_tools.py

```python
# code_puppy/tools/gui_cub/ocr_tools.py

# Add at top:
from .ocr_providers import get_ocr_provider, OCRResult as ProviderOCRResult

# Update desktop_extract_text:
def desktop_extract_text(
    ctx: RunContext[AgentDeps],
    region: list[int] | None = None,
    language: str = "eng",
) -> OCRExtractResult:
    """Extract text from screen region using native OCR (with Tesseract fallback).
    
    Platform-specific OCR:
    - Windows: WinRT OCR → Tesseract fallback
    - macOS: Apple Vision → Tesseract fallback
    - Linux: Tesseract only
    """
    # ... existing screenshot capture code ...
    
    # NEW: Use provider chain instead of direct pytesseract
    ocr_chain = get_ocr_provider()
    result = ocr_chain.extract_text(screenshot, language=language)
    
    if not result.success:
        return OCRExtractResult(
            success=False,
            error=f"OCR failed: {result.error}"
        )
    
    # Convert provider result to OCRExtractResult
    text_elements = [
        TextBoundingBox(
            text=word.text,
            confidence=word.confidence,
            x=word.bbox[0],
            y=word.bbox[1],
            width=word.bbox[2],
            height=word.bbox[3],
            center_x=word.bbox[0] + word.bbox[2] // 2,
            center_y=word.bbox[1] + word.bbox[3] // 2
        )
        for word in result.words
    ]
    
    return OCRExtractResult(
        success=True,
        found_count=len(text_elements),
        text_elements=text_elements,
        full_text=result.full_text,
        summary=f"Extracted {len(text_elements)} words using {result.provider}"
    )
```

---

## Phase 6: Update Warning/Calibration System

### 6.1 New Warning Strategy

**OLD Behavior (aggressive):**
```python
# On startup, if Tesseract missing:
emit_warning(
    """[yellow]
    ⚠️  TESSERACT OCR NOT INSTALLED
    
    OCR tools require pytesseract and tesseract-ocr.
    Install with:
      • macOS: brew install tesseract
      • Windows: choco install tesseract
      • Linux: apt-get install tesseract-ocr
    
    Or run: /calibrate to auto-install
    [/yellow]"""
)
```

**NEW Behavior (quiet):**
```python
# On startup, if Tesseract missing:
emit_info(
    "Tesseract OCR not installed (optional fallback for native OCR)",
    message_group="startup"
)

# Only show big warning when NEEDED:
# When native OCR fails and user tries to use OCR:
emit_warning(
    """[yellow]
    ⚠️  Native OCR unavailable, Tesseract fallback needed but not installed.
    
    Would you like to:
      1. Install Tesseract now (requires admin on Windows)
      2. See installation instructions
      3. Skip OCR operation
    
    Type /install_tesseract or /tesseract_help
    [/yellow]""",
    message_group="ocr_fallback_needed"
)
```

### 6.2 Update calibration.py

```python
# code_puppy/tools/gui_cub/calibration.py

def check_tesseract_availability(quiet: bool = False) -> dict:
    """Check if Tesseract is available.
    
    Args:
        quiet: If True, suppress warnings (for startup check)
    
    Returns:
        dict with 'available', 'version', 'path'
    """
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        return {
            'available': True,
            'version': str(version),
            'path': pytesseract.pytesseract.tesseract_cmd
        }
    except Exception:
        if quiet:
            # Just log, don't show big warning
            emit_info(
                "Tesseract OCR not installed (optional fallback)",
                message_group="startup_check"
            )
        else:
            # Show big warning with installation options
            emit_warning(
                "Tesseract not available. Run /install_tesseract for installation.",
                message_group="ocr_needed"
            )
        
        return {
            'available': False,
            'version': None,
            'path': None
        }

def offer_tesseract_installation(group_id: str) -> bool:
    """Offer to install Tesseract when OCR fallback is needed.
    
    Returns:
        True if user wants to install, False to skip
    """
    from rich.console import Console
    from rich.prompt import Confirm
    
    console = Console()
    
    console.print(
        "[yellow]⚠️  Native OCR failed, Tesseract fallback needed but not installed.[/yellow]"
    )
    console.print()
    console.print("Options:")
    console.print("  1. Install Tesseract now (may require admin privileges)")
    console.print("  2. Show manual installation instructions")
    console.print("  3. Skip OCR operation")
    console.print()
    
    choice = console.input("Choose [1/2/3]: ").strip()
    
    if choice == "1":
        # Attempt installation
        success = auto_install_tesseract(group_id)
        return success
    elif choice == "2":
        # Show installation instructions
        show_tesseract_install_instructions()
        return False
    else:
        # Skip
        emit_info("Skipping OCR operation", message_group=group_id)
        return False

def show_tesseract_install_instructions():
    """Print platform-specific Tesseract installation instructions."""
    from rich.console import Console
    from code_puppy.tools.gui_cub.platform import IS_WINDOWS, IS_MACOS, IS_LINUX
    
    console = Console()
    console.print("\n[bold]Tesseract OCR Installation Instructions[/bold]\n")
    
    if IS_WINDOWS:
        console.print("[cyan]Windows:[/cyan]")
        console.print("  • Using Chocolatey: [green]choco install tesseract[/green]")
        console.print("  • Manual download: https://github.com/UB-Mannheim/tesseract/wiki")
        console.print("  • GUI-Cub can install portable version: [green]/calibrate[/green]")
    elif IS_MACOS:
        console.print("[cyan]macOS:[/cyan]")
        console.print("  • Using Homebrew: [green]brew install tesseract[/green]")
        console.print("  • Using MacPorts: [green]sudo port install tesseract[/green]")
    elif IS_LINUX:
        console.print("[cyan]Linux:[/cyan]")
        console.print("  • Ubuntu/Debian: [green]sudo apt-get install tesseract-ocr[/green]")
        console.print("  • Fedora: [green]sudo dnf install tesseract[/green]")
        console.print("  • Arch: [green]sudo pacman -S tesseract[/green]")
    
    console.print("\n[dim]After installation, restart GUI-Cub.[/dim]\n")
```

### 6.3 Update config_manager.py Startup Checks

```python
# code_puppy/tools/gui_cub/config_manager.py

def check_capabilities_on_startup():
    """Check capabilities on startup with QUIET mode for Tesseract."""
    capabilities = {}
    
    # ... other capability checks (pyautogui, etc.) ...
    
    # Tesseract check (QUIET mode)
    tesseract_info = check_tesseract_availability(quiet=True)
    capabilities['tesseract'] = tesseract_info['available']
    
    # Only show info message, not big warning
    if not tesseract_info['available']:
        emit_info(
            "ℹ️  Tesseract OCR not installed (native OCR will be used, Tesseract is optional fallback)",
            message_group="startup"
        )
    
    return capabilities
```

### 6.4 Update OCR Provider Chain to Offer Installation

```python
# code_puppy/tools/gui_cub/ocr_providers/provider_chain.py

class OCRProviderChain:
    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Try providers in order until one succeeds."""
        errors = []
        
        for provider in self.providers:
            try:
                result = provider.extract_text(image, language)
                if result.success:
                    return result
                errors.append(f"{provider.get_name()}: {result.error}")
            except Exception as e:
                errors.append(f"{provider.get_name()}: {str(e)}")
        
        # All providers failed
        # Check if Tesseract was in the chain but unavailable
        from .tesseract_provider import TesseractOCRProvider
        has_tesseract_provider = any(
            isinstance(p, TesseractOCRProvider) for p in self.providers
        )
        
        if has_tesseract_provider:
            # Tesseract was in fallback chain but failed
            # Offer installation if not already installed
            tesseract_info = check_tesseract_availability(quiet=True)
            if not tesseract_info['available']:
                # Offer to install now
                group_id = generate_group_id()
                emit_warning(
                    "Native OCR failed and Tesseract fallback is not installed.",
                    message_group=group_id
                )
                
                # Offer installation (interactive)
                installed = offer_tesseract_installation(group_id)
                if installed:
                    # Retry with newly installed Tesseract
                    return self.extract_text(image, language)
        
        return OCRResult(
            success=False,
            words=[],
            full_text="",
            provider="none",
            error=f"All OCR providers failed: {'; '.join(errors)}"
        )
```

---

## Phase 7: Configuration & User Control

### 7.1 Config Options

```yaml
# ~/.code_puppy/agents/gui_cub/config.yaml

ocr:
  # Provider preference order
  provider_order:
    - native  # Use platform-native OCR first
    - tesseract  # Fallback to Tesseract
  
  # Force specific provider (for testing)
  force_provider: null  # "winrt" | "vision" | "tesseract" | null
  
  # Performance tuning
  native:
    # macOS Vision recognition level
    vision_recognition_level: fast  # "fast" | "accurate"
    
    # WinRT language preference
    winrt_language: "en-US"
  
  tesseract:
    # Tesseract-specific options
    language: eng
    psm: 3  # Page segmentation mode
```

### 7.2 Runtime Provider Selection

```python
# Allow users to force a specific provider:

def get_ocr_provider(force_provider: str | None = None) -> OCRProviderChain:
    """Get OCR provider chain with optional override."""
    if force_provider:
        providers = []
        if force_provider == "winrt":
            providers.append(WinRTOCRProvider())
        elif force_provider == "vision":
            providers.append(VisionOCRProvider())
        elif force_provider == "tesseract":
            providers.append(TesseractOCRProvider())
        return OCRProviderChain(providers)
    
    # Default platform-specific chain
    return get_default_ocr_chain()
```

---

## Phase 8: Testing & Benchmarking

### 8.1 Unit Tests

**Test files:**
```
tests/gui_cub/ocr_providers/
├── test_base.py
├── test_winrt_provider.py
├── test_vision_provider.py
├── test_tesseract_provider.py
├── test_provider_chain.py
└── test_integration.py
```

**Test images:**
```
tests/fixtures/ocr_test_images/
├── simple_text.png           # "Hello World"
├── multiline_text.png        # Paragraph
├── numbers.png               # "123456"
├── low_contrast.png          # Gray text on gray background
├── retina_2x.png             # macOS Retina screenshot
├── windows_150percent.png    # Windows 150% DPI
└── calculator_display.png    # Real app screenshot
```

### 8.2 Performance Benchmarks

```python
# tests/gui_cub/ocr_providers/benchmark.py

import time
from PIL import Image

def benchmark_provider(provider, test_images):
    """Benchmark OCR provider speed and accuracy."""
    results = []
    
    for img_path, expected_text in test_images:
        img = Image.open(img_path)
        
        start = time.perf_counter()
        result = provider.extract_text(img)
        duration = time.perf_counter() - start
        
        accuracy = calculate_accuracy(result.full_text, expected_text)
        
        results.append({
            'image': img_path.name,
            'duration_ms': duration * 1000,
            'accuracy': accuracy,
            'word_count': len(result.words)
        })
    
    return results

# Expected results (rough estimates):
# WinRT: ~50-100ms per image
# Vision: ~50-150ms per image
# Tesseract: ~200-500ms per image
```

### 8.3 Integration Tests

```python
# tests/gui_cub/ocr_providers/test_integration.py

def test_provider_chain_fallback():
    """Test that provider chain falls back correctly."""
    # Mock native provider to fail
    # Verify Tesseract is called
    pass

def test_calculator_ocr():
    """Real-world test: Read calculator display."""
    # Open calculator
    # Type "1234567890"
    # Screenshot
    # OCR should read "1234567890"
    pass
```

---

## Phase 9: Migration & Deployment

### 9.1 Migration Plan

**Step 1: Parallel deployment**
- Keep existing Tesseract code working
- Add new provider system alongside
- Use feature flag to enable/disable

**Step 2: Gradual rollout**
- Week 1: Internal testing only
- Week 2: Opt-in beta (config flag)
- Week 3: Default for new installs
- Week 4: Default for all users

**Step 3: Deprecation**
- Remove direct pytesseract calls
- Keep Tesseract as fallback provider

### 9.2 Backwards Compatibility

```python
# Maintain existing API:

# OLD (still works):
result = desktop_extract_text(ctx, region=[0, 0, 800, 600])

# NEW (same API, different backend):
result = desktop_extract_text(ctx, region=[0, 0, 800, 600])
# Now uses WinRT/Vision first, Tesseract fallback
```

### 9.3 Documentation Updates

**Files to update:**
- `README.md` - Add native OCR features
- `INSTALL.md` - Update installation (Tesseract optional)
- `docs/OCR.md` - Document provider system
- `CHANGELOG.md` - Add migration notes

---

## Phase 10: Performance Monitoring

### 10.1 Telemetry

```python
# Track which provider is used:

class OCRProviderChain:
    def extract_text(self, image, language="en"):
        for provider in self.providers:
            result = provider.extract_text(image, language)
            if result.success:
                # Log which provider succeeded
                emit_info(
                    f"OCR success using {provider.get_name()}",
                    message_group="ocr_telemetry"
                )
                return result
```

### 10.2 Metrics to Track

- **Provider usage**: % using native vs Tesseract
- **Performance**: Average OCR time by provider
- **Accuracy**: User corrections/retries (indirect measure)
- **Fallback rate**: How often native OCR fails

---

## Implementation Timeline (8 weeks)

### Sprint 1 (Week 1): Foundation
- [ ] Create provider interface (`base.py`) - **synchronous only**
- [ ] Create provider chain (`provider_chain.py`)
- [ ] Create Tesseract provider (`tesseract_provider.py`)
- [ ] Unit tests for base system

### Sprint 2 (Week 2): Windows Implementation
- [ ] Implement WinRT provider (`winrt_provider.py`) - **synchronous with asyncio.run() wrapper**
- [ ] Add winrt dependencies to pyproject.toml
- [ ] Unit tests for WinRT provider
- [ ] Benchmark WinRT vs Tesseract

### Sprint 3 (Week 3): macOS Implementation
- [ ] Implement Vision provider (`vision_provider.py`) - **synchronous**
- [ ] Add PyObjC dependencies to pyproject.toml
- [ ] Unit tests for Vision provider
- [ ] Test Retina coordinate handling
- [ ] Benchmark Vision vs Tesseract

### Sprint 4 (Week 4): Integration
- [ ] Update `ocr_tools.py` to use provider chain
- [ ] Integration tests

### Sprint 5 (Week 5): Warning System Update ⭐ **NEW**
- [ ] Update `calibration.py` with `check_tesseract_availability(quiet=True)`
- [ ] Add `offer_tesseract_installation()` function (interactive prompt)
- [ ] Add `show_tesseract_install_instructions()` helper
- [ ] Update `config_manager.py` startup checks (quiet mode)
- [ ] Update provider chain to offer installation on fallback failure
- [ ] Test interactive installation flow
- [ ] Remove big yellow warnings from startup

### Sprint 6 (Week 6): Configuration & Testing
- [ ] Add configuration options
- [ ] Documentation updates

### Sprint 7 (Week 7): Polish & Testing
- [ ] Real-world testing on Windows
- [ ] Real-world testing on macOS
- [ ] Test quiet startup (no big warnings)
- [ ] Test installation offer flow
- [ ] Performance tuning
- [ ] Bug fixes

### Sprint 8 (Week 8): Deployment
- [ ] Beta release
- [ ] User feedback collection
- [ ] Final adjustments
- [ ] Stable release

### Risk 1: Native API Unavailability
**Risk:** WinRT/Vision not available on older OS versions  
**Mitigation:** Tesseract fallback always available

### Risk 2: Coordinate System Differences
**Risk:** Different coordinate systems between providers  
**Mitigation:** Normalize all to same format (PIL coordinates)

### Risk 3: Performance Regression
**Risk:** Native OCR slower than expected  
**Mitigation:** Benchmark first, keep Tesseract if faster

### Risk 4: Accuracy Differences
**Risk:** Native OCR less accurate than Tesseract  
**Mitigation:** Add accuracy tests, allow user override

### Risk 5: Dependency Bloat
**Risk:** WinRT/PyObjC packages too large  
**Mitigation:** Optional dependencies, lazy imports

---

## Success Metrics

### Performance:
- ✅ **50% faster OCR** on Windows (WinRT vs Tesseract)
- ✅ **40% faster OCR** on macOS (Vision vs Tesseract)
- ✅ **90%+ success rate** with native providers (10% fallback)

### User Experience:
- ✅ **No manual Tesseract install** required on Windows/macOS
- ✅ **Smaller install size** (no 200MB Tesseract download)
- ✅ **Same or better accuracy** vs Tesseract

### Code Quality:
- ✅ **>90% test coverage** for OCR providers
- ✅ **Zero breaking changes** to existing API
- ✅ **Clear documentation** for provider system

---

## Future Enhancements

### Phase 11 (Future):
1. **Linux native OCR** - Explore Tesseract alternatives (easyocr, keras-ocr)
2. **Cloud OCR providers** - Google Vision API, Azure Computer Vision (optional)
3. **GPU acceleration** - CUDA/Metal for faster OCR
4. **Language packs** - Auto-download language models
5. **OCR caching** - Cache results for repeated screenshots
6. **Confidence thresholds** - Skip low-confidence results

---

## Questions for Discussion

1. ✅ **~~Async vs Sync?~~** ANSWERED: Synchronous only (use asyncio.run() wrapper for WinRT)
2. ✅ **~~Startup warnings?~~** ANSWERED: Quiet startup, show warnings only when fallback needed
3. **Provider priority config?** Let users configure provider order?
4. **Telemetry opt-in?** Track provider usage stats?
5. **Multi-language support?** Auto-detect language or require user input?
6. **Confidence filtering?** Skip words below confidence threshold?
7. **Installation automation level?** How aggressive should auto-install be?

---

**Status:** Planning Phase  
**Owner:** TBD  
**Target Release:** GUI-Cub v2.0  
**Dependencies:** None (additive feature)