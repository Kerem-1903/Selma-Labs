import re

with open("web/templates/workspace.html", "r") as f:
    code = f.read()

# Add a function to handle publish API calls
js_injection = """
        // Publish handlers
        async function publishVideo(platform) {
            const runId = window.location.pathname.split('/').pop();
            const btn = event.currentTarget;
            const originalHTML = btn.innerHTML;

            btn.innerHTML = `<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Publishing...`;
            btn.disabled = true;

            try {
                const formData = new FormData();
                formData.append('platform', platform);

                const response = await fetch(`/api/publish/${runId}`, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                if(response.ok) {
                    alert(`Successfully published to ${platform}! ID: ${data.platform_id}`);
                } else {
                    alert(`Failed to publish: ${data.error}`);
                }
            } catch(e) {
                alert(`Error: ${e.message}`);
            } finally {
                btn.innerHTML = originalHTML;
                btn.disabled = false;
            }
        }
"""

code = code.replace(
    "function fetchStatus() {",
    js_injection + "\n        function fetchStatus() {"
)

# Update onclick handlers
code = code.replace("onclick=\"alert('Publishing to YouTube...')\"", "onclick=\"publishVideo('youtube')\"")
code = code.replace("onclick=\"alert('Publishing to TikTok...')\"", "onclick=\"publishVideo('tiktok')\"")
code = code.replace("onclick=\"alert('Publishing to Instagram Reels...')\"", "onclick=\"publishVideo('instagram_reels')\"")

with open("web/templates/workspace.html", "w") as f:
    f.write(code)
