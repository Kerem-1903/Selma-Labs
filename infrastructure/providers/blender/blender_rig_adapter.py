import asyncio
import json
from pathlib import Path

from core.domain.entities.character_rig import RigSpecification
from core.domain.exceptions import BlenderExecutionError
from core.domain.ports.character_rig_port import CharacterRigPort, RigValidationReport
from infrastructure.providers.blender.blender_binary_resolver import (
    BlenderBinaryResolver,
)


class BlenderRigAdapter(CharacterRigPort):
    def __init__(
        self,
        blender_bin_path: str | None = None,
        *,
        timeout_seconds: float = 600.0,
    ) -> None:
        self.blender_bin_path = BlenderBinaryResolver.resolve(blender_bin_path)
        self.timeout_seconds = timeout_seconds
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.script_path = base_dir / "scripts" / "blender" / "rig_acting_builder.py"
        if not self.script_path.is_file():
            raise BlenderExecutionError(
                f"Blender rig script not found: {self.script_path}"
            )

    @staticmethod
    def _resolve_model_path(model_path: str) -> Path:
        resolved = Path(model_path).expanduser().resolve()
        if not resolved.is_file():
            raise BlenderExecutionError(f"Blender model not found: {resolved}")
        if resolved.suffix.lower() != ".blend":
            raise BlenderExecutionError("Rig validation requires a .blend model file.")
        return resolved

    async def _run_headless_script(self, args: list[str]) -> str:
        cmd = [
            self.blender_bin_path,
            "-b",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "-P",
            str(self.script_path),
            "--",
        ] + args

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError as error:
            process.kill()
            await process.communicate()
            raise BlenderExecutionError(
                f"Blender rig command timed out after {self.timeout_seconds:g} seconds."
            ) from error

        if process.returncode != 0:
            details = stderr.decode("utf-8", errors="replace").strip()
            raise BlenderExecutionError(f"Blender rig command failed: {details}")

        return stdout.decode("utf-8", errors="replace")

    async def validate_rig(self, model_path: str) -> RigValidationReport:
        model = self._resolve_model_path(model_path)
        stdout = await self._run_headless_script(
            ["--model", str(model), "--command", "validate"]
        )

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
            raise BlenderExecutionError(
                f"Could not parse JSON from Blender script output. Output was: {stdout}"
            )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as error:
            raise BlenderExecutionError(
                "Blender returned an invalid rig report."
            ) from error
        if not isinstance(data, dict):
            raise BlenderExecutionError("Blender rig report must be a JSON object.")

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
            available_actions=frozenset(data.get("available_actions", [])),
        )

        is_valid = data.get("is_valid") is True
        errors = tuple(str(error) for error in data.get("errors", []))

        return RigValidationReport(
            is_valid=is_valid,
            specification=spec,
            errors=errors,
        )

    async def bake_action_preview(
        self,
        model_path: str,
        action_name: str,
        output_path: str,
        fps: int = 24,
    ) -> str:
        model = self._resolve_model_path(model_path)
        if fps <= 0:
            raise BlenderExecutionError("Preview FPS must be greater than zero.")

        output = Path(output_path).expanduser().resolve()
        if output.suffix.lower() != ".mp4":
            raise BlenderExecutionError("Rig previews must use an .mp4 output path.")
        output.parent.mkdir(parents=True, exist_ok=True)
        previous_signature = (
            (output.stat().st_mtime_ns, output.stat().st_size)
            if output.exists()
            else None
        )

        await self._run_headless_script(
            [
                "--model",
                str(model),
                "--command",
                "preview",
                "--action",
                action_name,
                "--output",
                str(output),
                "--fps",
                str(fps),
            ]
        )

        if not output.is_file() or output.stat().st_size <= 0:
            raise BlenderExecutionError(f"Expected preview was not created: {output}")
        current_signature = (output.stat().st_mtime_ns, output.stat().st_size)
        if previous_signature == current_signature:
            raise BlenderExecutionError(
                f"Blender did not refresh the preview: {output}"
            )
        return str(output)
