"""
Unit tests for LocalFsStorage.

Uses pytest's tmp_path fixture so tests never touch the real project
filesystem and clean up automatically. No network involved.
"""
from __future__ import annotations

import pytest

from core.domain.exceptions import StorageError
from infrastructure.storage.local_fs_storage import LocalFsStorage


@pytest.mark.asyncio
async def test_save_writes_file_and_returns_reference(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))

    reference = await storage.save("voice/test.mp3", b"audio-bytes", "audio/mpeg")

    assert reference.key == "voice/test.mp3"
    assert reference.size_bytes == len(b"audio-bytes")
    written_path = tmp_path / "voice" / "test.mp3"
    assert written_path.exists()
    assert written_path.read_bytes() == b"audio-bytes"
    assert reference.path == str(written_path.resolve())


@pytest.mark.asyncio
async def test_save_creates_nested_directories(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))

    await storage.save("a/b/c/file.mp3", b"data", "audio/mpeg")

    assert (tmp_path / "a" / "b" / "c" / "file.mp3").exists()


@pytest.mark.asyncio
async def test_save_raises_storage_error_on_write_failure(tmp_path):
    # Point root_dir at a location that cannot exist as a directory
    # (a file, not a directory) to force an OSError inside save().
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("i am a file, not a directory")
    storage = LocalFsStorage(root_dir=str(blocking_file))

    with pytest.raises(StorageError):
        await storage.save("voice/test.mp3", b"data", "audio/mpeg")
