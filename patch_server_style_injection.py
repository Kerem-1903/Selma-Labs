import re

with open("server.py", "r") as f:
    code = f.read()

injection = """        if voice_provider:
            request_settings.voice_provider = voice_provider
            if voice_file_path and voice_provider == "local_xtts":
                # Assuming setting property or handle logic here
                pass

        style_map = {
            "cinematic": "assets/comfyui_workflow.json",
            "anime": "assets/comfyui_anime_workflow.json",
            "3d": "assets/comfyui_3d_workflow.json",
            "cyberpunk": "assets/comfyui_cyberpunk_workflow.json"
        }
        if style in style_map:
            request_settings.comfyui_workflow_path = style_map[style]
"""

old_code = """        if voice_provider:
            request_settings.voice_provider = voice_provider
            if voice_file_path and voice_provider == "local_xtts":
                # Assuming setting property or handle logic here
                pass"""

code = code.replace(old_code, injection)

with open("server.py", "w") as f:
    f.write(code)
