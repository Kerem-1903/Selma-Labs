import re

with open("infrastructure/providers/video/comfyui_video_provider.py", "r") as f:
    code = f.read()

injection = """        for node_id, node_data in workflow.items():
            if node_data.get("class_type") == "CLIPTextEncode":
                # Check for negative prompt (usually node 7 or containing negative words in defaults, but for safety we just inject positive)
                # To handle styles, we append style modifiers if the workflow file name implies it.
                style_modifier = ""
                if "anime" in self.workflow_path:
                    style_modifier = ", masterpiece anime style, studio ghibli, makoto shinkai, vibrant colors, detailed line art"
                elif "3d" in self.workflow_path:
                    style_modifier = ", unreal engine 5 render, octane render, pixar style, 3d animation, volumetric lighting"
                elif "cyberpunk" in self.workflow_path:
                    style_modifier = ", cyberpunk 2077 style, neon lighting, futuristic, dark sci-fi, dystopian city"

                final_prompt = prompt + style_modifier

                # Only inject into the first CLIPTextEncode (assuming it's positive) or if it has an empty text field
                if not found_node or node_data["inputs"].get("text", "") == "":
                    node_data["inputs"]["text"] = final_prompt
                    found_node = True
                    break"""

old_code = """        for node_id, node_data in workflow.items():
            if node_data.get("class_type") == "CLIPTextEncode":
                # Inject the prompt
                node_data["inputs"]["text"] = prompt
                found_node = True
                break # We just update the first text encoder we find for this example"""

code = code.replace(old_code, injection)

with open("infrastructure/providers/video/comfyui_video_provider.py", "w") as f:
    f.write(code)
