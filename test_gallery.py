import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("Navigating to index...")
        await page.goto("http://localhost:7860")

        print("Clicking My Projects link...")
        await page.click('text="My Projects"')
        await page.wait_for_timeout(3000)

        print(f"Current URL: {page.url}")
        await page.screenshot(path="/tmp/gallery_view.png")
        await browser.close()

asyncio.run(main())
