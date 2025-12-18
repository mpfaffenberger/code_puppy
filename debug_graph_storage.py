"""Debug script to see what Graph Explorer stores - checking more locations.

Run this after signing into Graph Explorer to find the access token.
"""

import asyncio
from pathlib import Path
from code_puppy.config import CONFIG_DIR

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed")
    exit(1)


async def main():
    profile_path = Path(CONFIG_DIR) / "chrome_profile"

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 720},
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # Set up request interception to capture the token from API calls
        captured_token = None

        async def handle_request(request):
            nonlocal captured_token
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                captured_token = auth_header[7:]  # Remove 'Bearer ' prefix
                print(f"\n🎯 CAPTURED TOKEN FROM REQUEST TO: {request.url[:80]}...")
                print(f"   Token preview: {captured_token[:50]}...")

        page.on("request", handle_request)

        print("Navigating to Graph Explorer...")
        await page.goto(
            "https://developer.microsoft.com/en-us/graph/graph-explorer", timeout=30000
        )

        print("\nWaiting 5 seconds for page to load...")
        await asyncio.sleep(5)

        print("\n" + "=" * 60)
        print("CHECKING INDEXEDDB...")
        print("=" * 60)

        # Check IndexedDB - MSAL might store tokens there
        indexed_db_info = await page.evaluate("""
            async () => {
                const results = [];
                try {
                    const databases = await indexedDB.databases();
                    for (const db of databases) {
                        results.push(db.name);
                    }
                } catch (e) {
                    results.push('Error: ' + e.message);
                }
                return results;
            }
        """)

        print("IndexedDB databases found:")
        for db in indexed_db_info:
            print(f"  - {db}")

        print("\n" + "=" * 60)
        print("CHECKING COOKIES...")
        print("=" * 60)

        cookies = await context.cookies()
        for cookie in cookies:
            if (
                "token" in cookie["name"].lower()
                or "auth" in cookie["name"].lower()
                or "msal" in cookie["name"].lower()
            ):
                print(f"\n{cookie['name']}:")
                value = cookie["value"]
                print(f"  {value[:80]}..." if len(value) > 80 else f"  {value}")

        print("\n" + "=" * 60)
        print("TRIGGERING A GRAPH API CALL TO CAPTURE TOKEN...")
        print("=" * 60)
        print("Click 'Run query' in Graph Explorer, or make any API call...")
        print("The token will be captured from the request headers.")
        print("\nWaiting 30 seconds for you to trigger a request...")

        for i in range(30):
            await asyncio.sleep(1)
            if captured_token:
                break
            print(f"  {30 - i} seconds remaining...", end="\r")

        if captured_token:
            print("\n\n" + "=" * 60)
            print("SUCCESS! TOKEN CAPTURED:")
            print("=" * 60)
            print(f"Token length: {len(captured_token)}")
            print(f"Token preview: {captured_token[:100]}...")
            print("\nFull token saved to: /tmp/graph_token.txt")
            with open("/tmp/graph_token.txt", "w") as f:
                f.write(captured_token)
        else:
            print("\n\nNo token captured. Try clicking 'Run query' in Graph Explorer.")

        print("\n\nPress Enter to close browser...")
        input()

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
