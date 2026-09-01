import asyncio
import json
import os
from pathlib import Path

from core.domain.entities.character_rig import RigSpecification
from core.domain.exceptions import BlenderExecutionError
from core.domain.ports.blender_rig_port import BlenderRigPort, RigValidationReport
from infrastructure.providers.blender.blender_binary_resolver import BlenderBinaryResolver


class BlenderRigAdapter(BlenderRigPort):
    def __init__(self, blender_bin_path: str | None = None) -> None:
        self.blender_bin_path = BlenderBinaryResolver.resolve(blender_bin_path)
        # Calculate script path once
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.script_path = base_dir / "scripts" / "blender" / "rig_acting_builder.py"

    async def _run_headless_script(self, script_path: str, args: list[str]) -> str:
        cmd = [
            self.blender_bin_path,
            "-b",
            "-P",
            script_path,
            "--"
        ] + args

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise BlenderExecutionError(f"Blender script failed: {stderr.decode('utf-8')}")

        return stdout.decode('utf-8')

    async def validate_rig(self, model_path: str) -> RigValidationReport:
        stdout = await self._run_headless_script(str(self.script_path), ["--model", model_path, "--command", "validate"])

        # Parse JSON output from the script, looking for the ###JSON_START### and ###JSON_END### markers
        json_str = ""
        in_json = False
        for line in stdout.splitlines():
            if "###JSON_START###" in line:
                in_json = True
                continue
            if "###JSON_END###" in line:
                in_json = False
                continue
            if in_json:
                json_str += line

        if not json_str:
            raise BlenderExecutionError(f"Could not parse JSON from Blender script output. Output was: {stdout}")

        data = json.loads(json_str)

        spec = RigSpecification(
            has_ik_arm_l=data.get("has_ik_arm_l", False),
            has_ik_arm_r=data.get("has_ik_arm_r", False),
            has_ik_leg_l=data.get("has_ik_leg_l", False),
            has_ik_leg_r=data.get("has_ik_leg_r", False),
            has_fk_arm_l=data.get("has_fk_arm_l", False),
            has_fk_arm_r=data.get("has_fk_arm_r", False),
            has_fk_leg_l=data.get("has_fk_leg_l", False),
            has_fk_leg_r=data.get("has_fk_leg_r", False),
            has_secondary_hair=data.get("has_secondary_hair", False),
            has_secondary_jacket=data.get("has_secondary_jacket", False),
            shape_keys=frozenset(data.get("shape_keys", [])),
            available_actions=frozenset(data.get("available_actions", []))
        )

        is_valid = data.get("is_valid", False)
        errors = data.get("errors", [])

        return RigValidationReport(
            is_valid=is_valid,
            specification=spec,
            errors=errors
        )

    async def bake_action_preview(self, model_path: str, action_name: str, output_path: str, fps: int = 24) -> str:
        await self._run_headless_script(str(self.script_path), ["--model", model_path, "--command", "preview", "--action", action_name, "--output", output_path, "--fps", str(fps)])

        # Verify the output file was created
        if not os.path.exists(output_path):
            # Blender might have appended an extension or frame numbers. Let's just return the directory or a guessed file
            path_obj = Path(output_path)
            # Find the actual output if it's named slightly differently
            matches = list(path_obj.parent.glob(f"{path_obj.stem}*"))
            if matches:
                return str(matches[0])
            raise BlenderExecutionError(f"Expected output file not found at {output_path}")

        return output_path
