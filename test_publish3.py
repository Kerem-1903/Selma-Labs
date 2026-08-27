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
        # Auto accept is needed for alerts

        async def accept_dialog(dialog):
            print(f"Alert received: {dialog.message()}")
            await dialog.accept()

        page.on("dialog", accept_dialog)

        print("Clicking publish to TikTok...")
        # Since function is defined inside DOMContentLoaded we can't call it directly from window. Let's click the button.
        await page.evaluate("document.querySelectorAll('button')[2].click()") # The first few buttons are timeline controls, so let's find the correct button.

        await page.wait_for_timeout(3000)
        await browser.close()

asyncio.run(main())
