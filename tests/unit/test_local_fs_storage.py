"""
Unit tests for LocalFsStorage.

Uses pytest's tmp_path fixture so tests never touch the real project
filesystem and clean up automatically. No network involved.
"""
from __future__ import annotations

from pathlib import Path

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
async def test_load_and_exists_resolve_portable_storage_key(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))
    key = "characters/akira/references/front/reference.png"

    assert await storage.exists(key) is False
    await storage.save(key, b"image-bytes", "image/png")

    assert await storage.exists(key) is True
    assert await storage.load(key) == b"image-bytes"


@pytest.mark.asyncio
async def test_load_missing_key_raises_storage_error(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))

    with pytest.raises(StorageError, match="Failed to read asset"):
        await storage.load("characters/akira/missing.png")


@pytest.mark.asyncio
async def test_save_raises_storage_error_on_write_failure(tmp_path):
    # Point root_dir at a location that cannot exist as a directory
    # (a file, not a directory) to force an OSError inside save().
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("i am a file, not a directory")
    storage = LocalFsStorage(root_dir=str(blocking_file))

    with pytest.raises(StorageError):
        await storage.save("voice/test.mp3", b"data", "audio/mpeg")


@pytest.mark.asyncio
async def test_save_stream_writes_chunks_without_buffering_contract(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))

    async def chunks():
        yield b"video-"
        yield b"bytes"

    reference = await storage.save_stream("video/test.mp4", chunks(), "video/mp4")

    assert reference.size_bytes == 11
    assert (tmp_path / "video" / "test.mp4").read_bytes() == b"video-bytes"


@pytest.mark.asyncio
async def test_save_rejects_keys_outside_the_storage_root(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path / "root"))

    with pytest.raises(StorageError, match="inside"):
        await storage.save("../escape.mp4", b"data", "video/mp4")


@pytest.mark.asyncio
async def test_save_materializes_windows_safe_path_for_object_store_key(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))
    key = "video/fake:video_source-p-AI software-1.mp4"

    reference = await storage.save(key, b"video", "video/mp4")

    path = tmp_path / "video"
    files = list(path.iterdir())
    assert reference.key == key
    assert len(files) == 1
    assert ":" not in files[0].name
    assert files[0].read_bytes() == b"video"
    assert reference.path == str(files[0].resolve())


@pytest.mark.asyncio
async def test_normalized_storage_keys_do_not_collapse_to_same_file(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))

    left = await storage.save("video/a:b.mp4", b"left", "video/mp4")
    right = await storage.save("video/a?b.mp4", b"right", "video/mp4")

    assert left.path != right.path
    assert Path(left.path).read_bytes() == b"left"
    assert Path(right.path).read_bytes() == b"right"


@pytest.mark.asyncio
async def test_save_escapes_windows_reserved_filename(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))

    reference = await storage.save("video/CON.mp4", b"video", "video/mp4")

    assert Path(reference.path).name.startswith("_CON-")
    assert Path(reference.path).is_file()


@pytest.mark.asyncio
async def test_normalized_filename_stays_within_portable_component_limit(tmp_path):
    storage = LocalFsStorage(root_dir=str(tmp_path))
    key = f"video/{'x' * 150}:clip.mp4"

    reference = await storage.save(key, b"video", "video/mp4")

    assert len(Path(reference.path).name) <= storage._MAX_COMPONENT_LENGTH
