import torch
from nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

class ControlNetCombine:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controlnet_1": ("CONTROL_NET",),
                "controlnet_2": ("CONTROL_NET",),
                "method": (['stack', 'add'],),
            }
        }

    RETURN_TYPES = ("CONTROL_NET",)
    FUNCTION = "combine"
    CATEGORY = "controlnet"

    def combine(self, controlnet_1, controlnet_2, method):
        """Combine two ControlNet conditioning tensors.
        * stack – concatenate along channel dimension (default for OpenPose+Depth)
        * add – element‑wise addition (useful for subtle blending)
        """
        if method == "stack":
            out = torch.cat([controlnet_1, controlnet_2], dim=1)
        else:
            out = controlnet_1 + controlnet_2
        return (out,)

# Register node with ComfyUI
NODE_CLASS_MAPPINGS["ControlNetCombine"] = ControlNetCombine
NODE_DISPLAY_NAME_MAPPINGS["ControlNetCombine"] = "ControlNet Combine (OpenPose+Depth/Lineart)"
