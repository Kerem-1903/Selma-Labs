import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("http://localhost:7860")

        # Using correct textarea id
        await page.fill('#prompt-input', "Mariana Çukuru'nun derinliklerindeki gizemli canlılar")
        await page.click('button:has-text("Generate")')
        await page.wait_for_timeout(3000) # Wait for redirect
        print(page.url)
        await page.screenshot(path="/tmp/workspace_view_actual.png")
        await browser.close()

asyncio.run(main())
