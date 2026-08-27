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

        async def accept_dialog(dialog):
            print(f"Alert received: {dialog.message()}")
            await dialog.accept()

        page.on("dialog", accept_dialog)

        print(f"Testing direct API endpoint for run {run_id}")

        # Directly test the API via POST to /api/publish/{job_id}
        resp = await page.request.post(
            f"http://localhost:7860/api/publish/{run_id}",
            form={"platform": "tiktok"}
        )
        data = await resp.json()
        print(f"API Response: {data}")

        await browser.close()

asyncio.run(main())
