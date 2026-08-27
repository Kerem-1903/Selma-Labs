import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Get run id
        resp = await page.request.get("http://localhost:7860/api/gallery")
        data = await resp.json()
        run_id = data["runs"][0]["run_id"]

        await page.goto(f"http://localhost:7860/workspace/{run_id}")
        await page.wait_for_timeout(2000)

        page.on("dialog", lambda dialog: print(f"Alert received: {dialog.message()}"))
        page.on("dialog", lambda dialog: dialog.accept())

        print("Clicking publish to TikTok...")
        # TikTok button is the second button in that list
        await page.evaluate("document.querySelectorAll('button[onclick*=\"publishVideo\"]')[1].click()")

        await page.wait_for_timeout(3000)
        await browser.close()

asyncio.run(main())
