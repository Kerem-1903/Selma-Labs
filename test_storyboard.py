import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("http://localhost:7860")

        # Check Storyboard toggle using evaluate (since it's sr-only)
        await page.evaluate("document.getElementById('storyboard-toggle').checked = true")

        # Check if the toggle is checked
        val = await page.evaluate("document.getElementById('storyboard-toggle').checked")
        print(f"Storyboard mode checked: {val}")

        await page.screenshot(path="/tmp/storyboard_toggle.png")
        await browser.close()

asyncio.run(main())
