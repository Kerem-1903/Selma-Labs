import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # We need a run ID to test workspace timeline. Get one from API
        resp = await page.request.get("http://localhost:7860/api/gallery")
        data = await resp.json()
        if not data.get("runs"):
            print("No runs found to test workspace")
            return

        run_id = data["runs"][0]["run_id"]

        print(f"Navigating to workspace for run {run_id}...")
        await page.goto(f"http://localhost:7860/workspace/{run_id}")
        await page.wait_for_timeout(3000) # wait for mocks to render

        # Take screenshot of workspace with timeline
        await page.screenshot(path="/tmp/timeline_view.png")
        print("Workspace loaded.")

        await browser.close()

asyncio.run(main())
