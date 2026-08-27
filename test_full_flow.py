import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. Start on index
        print("1. Index page...")
        await page.goto("http://localhost:7860")

        # Select Anime style
        await page.select_option('#style-input', 'anime')

        # Enable storyboard
        await page.evaluate("document.getElementById('storyboard-toggle').checked = true")

        # Fill prompt and submit
        await page.fill('#prompt-input', 'A cyberpunk samurai standing in neon rain')

        print("Submitting form...")

        # Instead of capturing response, we just wait for navigation to workspace
        async with page.expect_navigation():
            await page.click('button[type="submit"]')

        print(f"2. Redirected to Workspace... URL: {page.url}")

        # Wait a bit for polling
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/full_flow_workspace.png")

        # 3. Gallery
        print("3. Checking Gallery...")
        await page.goto("http://localhost:7860/gallery")
        await page.wait_for_timeout(2000)

        # Verify job is in gallery
        await page.screenshot(path="/tmp/full_flow_gallery.png")

        print("Flow complete.")
        await browser.close()

asyncio.run(main())
