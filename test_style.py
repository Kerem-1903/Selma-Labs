import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("http://localhost:7860")

        # Select Anime style
        await page.select_option('#style-input', 'anime')

        # Check if the style input has the value 'anime'
        val = await page.evaluate("document.getElementById('style-input').value")
        print(f"Selected style: {val}")

        await page.screenshot(path="/tmp/style_selector.png")
        await browser.close()

asyncio.run(main())
