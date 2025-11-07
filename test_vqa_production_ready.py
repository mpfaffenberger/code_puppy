#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test production VQA with real Claude 4.5 Sonnet API.

This tests the actual gui-cub VQA tooling with two-stage detection,
debug images, and all production features.
"""

import sys

if sys.platform != "darwin":
    print("[X] This script is for macOS only!")
    sys.exit(1)

from pydantic_ai import Agent

from code_puppy.tools.gui_cub.vqa_vision_click import desktop_click_element_vqa


async def test_vqa_production():
    """Test VQA with real Claude 4.5 Sonnet."""

    print("=" * 70)
    print("Production VQA Test - Spotify Minimize Button")
    print("=" * 70)
    print("\nUsing REAL Claude 4.5 Sonnet API with two-stage detection.")
    print("Debug images will be saved to: vqa_debug_output/")
    print("\nMake sure Spotify is open!\n")

    # Create agent with Claude 4.5 Sonnet
    agent = Agent(
        model="claude-4-5-sonnet-latest",
        # Add any needed configuration
    )

    # Test two-stage VQA click
    try:
        result = await desktop_click_element_vqa(
            context=agent.run_context(),  # This might need adjustment
            element_description="yellow minimize button",
            use_active_window=True,
            save_debug=True,
        )

        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(f"Success: {result.success}")
        print(f"Element found: {result.element_found}")
        if result.click_x and result.click_y:
            print(f"Clicked at: ({result.click_x}, {result.click_y})")
        if result.confidence:
            print(f"Confidence: {result.confidence:.0%}")
        if result.error:
            print(f"Error: {result.error}")

        print("\nCheck vqa_debug_output/ for debug images!")
        print("=" * 70)

    except Exception as e:
        print(f"\n[X] Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("\n⚠️  NOTE: This test requires a valid Claude 4.5 Sonnet API key.")
    print("      Configure via code-puppy settings or environment variables.\n")

    # Uncomment to run (requires API setup)
    # asyncio.run(test_vqa_production())

    print("[i] Test script created but not running (API setup required).")
    print("    Uncomment asyncio.run() line to test with real API.\n")
