import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from infrastructure.providers.blender.blender_binary_resolver import BlenderBinaryResolver, BlenderNotFoundError

def test_resolve_from_bin_path_valid():
    with mock.patch("pathlib.Path.is_file", return_value=True), \
         mock.patch("os.access", return_value=True):
        path = BlenderBinaryResolver.resolve("/custom/path/blender")
        assert "/custom/path/blender" in path

def test_resolve_from_path():
    with mock.patch("shutil.which", return_value="/usr/bin/blender"):
        path = BlenderBinaryResolver.resolve(None)
        assert path == "/usr/bin/blender"

@pytest.mark.skipif(sys.platform != "win32", reason="Windows specific test")
def test_resolve_windows_program_files():
    with mock.patch("shutil.which", return_value=None), \
         mock.patch("pathlib.Path.is_dir", return_value=True), \
         mock.patch("pathlib.Path.glob", return_value=[Path("C:/Program Files/Blender Foundation/Blender 4.2")]), \
         mock.patch("pathlib.Path.is_file", return_value=True), \
         mock.patch("os.access", return_value=True):

         path = BlenderBinaryResolver.resolve(None)
         assert "Blender 4.2\\blender.exe" in path

def test_resolve_not_found():
    with mock.patch("shutil.which", return_value=None):
        with pytest.raises(BlenderNotFoundError):
            BlenderBinaryResolver.resolve(None)
