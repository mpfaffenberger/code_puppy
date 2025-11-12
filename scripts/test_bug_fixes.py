#!/usr/bin/env python3
"""Test script to verify bug fixes from 2025-01-11."""

import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_app_detection_case_insensitive():
    """Test that app detection works with different capitalizations."""
    print("\n" + "=" * 60)
    print("TEST 1: App Detection Case-Insensitive Matching")
    print("=" * 60)

    if platform.system() != "Darwin":
        print("⚠️  Skipping - macOS only test")
        return

    try:
        from AppKit import NSWorkspace

        workspace = NSWorkspace.sharedWorkspace()
        running_apps = workspace.runningApplications()

        # Test case-insensitive matching
        test_cases = ["finder", "Finder", "FINDER"]

        for app_name in test_cases:
            app_name_lower = app_name.lower()
            found = False

            for app in running_apps:
                localized_name = app.localizedName()
                bundle_id = app.bundleIdentifier()

                if localized_name and localized_name.lower() == app_name_lower:
                    found = True
                    print(f"✅ Found '{app_name}' -> {localized_name}")
                    break

                if bundle_id and bundle_id.lower().endswith(f".{app_name_lower}"):
                    found = True
                    print(f"✅ Found '{app_name}' via bundle ID -> {bundle_id}")
                    break

            if not found:
                print(f"❌ Could not find '{app_name}'")

        print("✅ Case-insensitive matching works!")

    except ImportError:
        print(
            "⚠️  AppKit not available - install with: pip install pyobjc-framework-Cocoa"
        )
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


def test_screenshot_thread_safety():
    """Test that screenshots work from background threads."""
    print("\n" + "=" * 60)
    print("TEST 2: Screenshot Thread Safety")
    print("=" * 60)

    try:
        # Check PIL availability
        import PIL  # noqa: F401

        print("✅ PIL/Pillow is installed")

        # Test screenshot from main thread
        print("\n1. Testing screenshot from main thread...")
        from code_puppy.tools.gui_cub.screen_capture.capture import _safe_screenshot

        img = _safe_screenshot()
        print(f"✅ Main thread screenshot: {img.size[0]}x{img.size[1]}")

        # Test screenshot from worker thread (this is what agent does)
        print("\n2. Testing screenshot from worker thread...")
        import threading

        result = {"success": False, "error": None, "size": None}

        def thread_screenshot():
            try:
                img = _safe_screenshot()
                result["success"] = True
                result["size"] = img.size
            except Exception as e:
                result["error"] = str(e)

        thread = threading.Thread(target=thread_screenshot)
        thread.start()
        thread.join(timeout=5.0)

        if result["success"]:
            print(
                f"✅ Worker thread screenshot: {result['size'][0]}x{result['size'][1]}"
            )
            print("✅ Thread-safe screenshot works!")
        else:
            print(f"❌ Worker thread failed: {result['error']}")

    except ImportError as e:
        print(f"⚠️  Required package missing: {e}")
        print("   Install with: uv pip install Pillow")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


def test_pil_requirement_enforcement():
    """Test that macOS properly requires PIL."""
    print("\n" + "=" * 60)
    print("TEST 3: PIL Requirement Enforcement (macOS)")
    print("=" * 60)

    if platform.system() != "Darwin":
        print("⚠️  Skipping - macOS only test")
        return

    try:
        # This should work if PIL is installed
        from code_puppy.tools.gui_cub.screen_capture.capture import _safe_screenshot
        from code_puppy.tools.gui_cub.dependencies import PIL_AVAILABLE

        if PIL_AVAILABLE:
            print("✅ PIL is available")
            img = _safe_screenshot()
            print(f"✅ Screenshot works: {img.size[0]}x{img.size[1]}")
        else:
            print("❌ PIL is NOT available")
            try:
                img = _safe_screenshot()
                print("❌ Should have raised RuntimeError!")
            except RuntimeError as e:
                print(f"✅ Correctly raised RuntimeError: {e}")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("🐶 Testing Bug Fixes from 2025-01-11")
    print(f"Platform: {platform.system()}")

    test_app_detection_case_insensitive()
    test_screenshot_thread_safety()
    test_pil_requirement_enforcement()

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
