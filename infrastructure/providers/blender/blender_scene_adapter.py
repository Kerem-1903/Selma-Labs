import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict

from core.domain.ports.blender_scene_renderer_port import BlenderSceneRendererPort
from core.domain.value_objects.blender_render_manifest import BlenderRenderManifest
from infrastructure.providers.blender.blender_binary_resolver import BlenderBinaryResolver

logger = logging.getLogger(__name__)


class BlenderSceneAdapter(BlenderSceneRendererPort):
    def __init__(self, blender_bin_path: str = ""):
        if not blender_bin_path:
            blender_bin_path = os.environ.get("BLENDER_BIN_PATH", "")
        self.blender_bin = BlenderBinaryResolver.resolve(blender_bin_path)

    async def render_turntable(
        self, model_path: str, output_dir: str, resolution_profile: str
    ) -> BlenderRenderManifest:
        """
        Executes a headless blender subprocess to render a turntable animation.
        """
        model_path_obj = Path(model_path).resolve()
        output_dir_obj = Path(output_dir).resolve()
        output_dir_obj.mkdir(parents=True, exist_ok=True)

        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "blender" / "lookdev_turntable.py"
        ).resolve()

        if not script_path.exists():
            raise FileNotFoundError(f"Blender script not found at {script_path}")

        render_id = f"render_{uuid.uuid4().hex[:8]}"

        cmd = [
            self.blender_bin,
            "-b",  # Headless mode
            "-P",
            str(script_path),
            "--",  # Arguments for the script follow
            "--model",
            str(model_path_obj),
            "--output-dir",
            str(output_dir_obj),
            "--quality",
            resolution_profile,
            "--render-id",
            render_id,
        ]

        logger.info(f"Executing Blender turntable render: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=600.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise TimeoutError("Blender turntable rendering timed out after 600s")

        if process.returncode != 0:
            stderr_str = stderr_data.decode("utf-8") if stderr_data else "Unknown error"
            stdout_str = stdout_data.decode("utf-8") if stdout_data else ""
            raise RuntimeError(f"Blender render failed (code {process.returncode}):\n{stderr_str}\n{stdout_str}")

        # The python script should have created a JSON manifest in the output directory
        manifest_path = output_dir_obj / f"{render_id}_manifest.json"
        if not manifest_path.exists():
            raise RuntimeError(f"Render completed but manifest was not found at {manifest_path}")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            return BlenderRenderManifest.from_dict(manifest_data)
        except Exception as e:
            raise RuntimeError(f"Failed to parse blender render manifest: {e}")

    async def run_benchmark(self, model_path: str) -> Dict[str, Any]:
        """
        Executes a headless blender subprocess to run benchmark tests.
        """
        model_path_obj = Path(model_path).resolve()

        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "blender" / "benchmark_runner.py"
        ).resolve()

        if not script_path.exists():
            raise FileNotFoundError(f"Blender script not found at {script_path}")

        cmd = [
            self.blender_bin,
            "-b",
            "-P",
            str(script_path),
            "--",
            "--model",
            str(model_path_obj),
        ]

        logger.info(f"Executing Blender benchmark: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=900.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise TimeoutError("Blender benchmark timed out after 900s")

        if process.returncode != 0:
            stderr_str = stderr_data.decode("utf-8") if stderr_data else "Unknown error"
            stdout_str = stdout_data.decode("utf-8") if stdout_data else ""
            raise RuntimeError(f"Blender benchmark failed (code {process.returncode}):\n{stderr_str}\n{stdout_str}")

        stdout_str = stdout_data.decode("utf-8")

        # We need to parse the benchmark results from stdout
        # The script should print a special JSON string, e.g., "---BENCHMARK_RESULT_START---{...}---BENCHMARK_RESULT_END---"
        start_marker = "---BENCHMARK_RESULT_START---"
        end_marker = "---BENCHMARK_RESULT_END---"

        start_idx = stdout_str.find(start_marker)
        end_idx = stdout_str.find(end_marker)

        if start_idx == -1 or end_idx == -1:
             raise RuntimeError(f"Could not find benchmark JSON in stdout. Stdout:\n{stdout_str}")

        json_str = stdout_str[start_idx + len(start_marker):end_idx].strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse benchmark JSON: {e}\nJSON string: {json_str}")
