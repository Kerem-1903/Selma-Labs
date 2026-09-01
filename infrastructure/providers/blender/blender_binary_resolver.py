import os
import shutil
import sys
from pathlib import Path
from typing import Optional


class BlenderNotFoundError(Exception):
    def __init__(self, message: str = "Blender executable not found."):
        self.message = (
            f"{message}\n"
            "Please ensure Blender (4.x or 5.x) is installed.\n"
            "If it is not in your PATH, you can set the BLENDER_BIN_PATH "
            "environment variable to point to the blender executable."
        )
        super().__init__(self.message)


class BlenderBinaryResolver:
    @staticmethod
    def resolve(blender_bin_path: Optional[str] = None) -> str:
        """
        Locates the Blender executable. Checks in the following order:
        1. Explicit `blender_bin_path` passed via settings/env.
        2. System PATH.
        3. Common Windows installation directories (C:\Program Files\Blender Foundation\Blender*\blender.exe).
        """
        if blender_bin_path and blender_bin_path.strip():
            blender_path = Path(blender_bin_path).expanduser().resolve()
            if blender_path.is_file() and os.access(blender_path, os.X_OK):
                return str(blender_path)
            # On windows, it might just be the path without .exe, check that too
            if sys.platform == "win32" and not blender_path.name.lower().endswith(".exe"):
                blender_path_exe = blender_path.with_name(f"{blender_path.name}.exe")
                if blender_path_exe.is_file() and os.access(blender_path_exe, os.X_OK):
                    return str(blender_path_exe)

        blender_executable = "blender"
        if sys.platform == "win32":
            blender_executable = "blender.exe"

        # Check system PATH
        path_blender = shutil.which(blender_executable)
        if path_blender:
            return path_blender

        # Check common Windows directories
        if sys.platform == "win32":
            program_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
            blender_foundation = Path(program_files) / "Blender Foundation"
            if blender_foundation.is_dir():
                # We sort the directories in reverse order so we get the newest version first
                for blender_dir in sorted(blender_foundation.glob("Blender*"), reverse=True):
                    candidate = blender_dir / blender_executable
                    if candidate.is_file() and os.access(candidate, os.X_OK):
                        return str(candidate)

        raise BlenderNotFoundError()
