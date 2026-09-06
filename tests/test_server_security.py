import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from pathlib import Path
import json

# server.py'ı import etmeden önce çevresel değişkenleri ayarla
os.environ["SELMA_ALLOW_PUBLISH"] = "false"
from server import app

client = TestClient(app)

def test_api_publish_disabled_by_default():
    response = client.post("/api/publish/dummy_id", data={"platform": "youtube"})
    assert response.status_code == 403
    assert "Publishing is disabled" in response.json()["error"]

def test_api_publish_invalid_platform():
    os.environ["SELMA_ALLOW_PUBLISH"] = "true"
    response = client.post("/api/publish/dummy_id", data={"platform": "invalid_platform"})
    assert response.status_code == 400
    assert "Invalid platform" in response.json()["error"]
    os.environ["SELMA_ALLOW_PUBLISH"] = "false"

def test_api_publish_path_traversal():
    os.environ["SELMA_ALLOW_PUBLISH"] = "true"

    # Need to mock the repository to return a valid job id but with a bad path
    class MockRun:
        def has_completed_stage(self, stage):
            return True
        def get_stage_artifact(self, stage):
            return {"file_path": "../../../etc/passwd"}

    with patch("server.LocalJsonRunRepository.get_by_id", return_value=MockRun()):
        response = client.post("/api/publish/dummy_id", data={"platform": "youtube"})
        assert response.status_code == 500
        assert "error_id" in response.json()
        assert "An internal error occurred" in response.json()["error"]

    os.environ["SELMA_ALLOW_PUBLISH"] = "false"

def test_generate_invalid_provider():
    response = client.post("/api/generate", data={
        "prompt": "test",
        "script_provider": "hacked_provider"
    })
    assert response.status_code == 400
    assert "Invalid script provider" in response.json()["error"]

def test_generate_large_file(tmp_path):
    # Create a 20MB file
    large_file = tmp_path / "large.jpg"
    large_file.write_bytes(b"0" * (20 * 1024 * 1024))

    with open(large_file, "rb") as f:
        response = client.post(
            "/api/generate",
            data={"prompt": "test"},
            files={"image": ("large.jpg", f, "image/jpeg")}
        )

    assert response.status_code == 400
    assert "too large" in response.json()["error"]

def test_generate_invalid_mime(tmp_path):
    text_file = tmp_path / "test.txt"
    text_file.write_text("hello")

    with open(text_file, "rb") as f:
        response = client.post(
            "/api/generate",
            data={"prompt": "test"},
            files={"image": ("test.txt", f, "text/plain")}
        )

    assert response.status_code == 400
    assert "Invalid file type" in response.json()["error"]

def test_vision_invalid_mime(tmp_path):
    text_file = tmp_path / "test.txt"
    text_file.write_text("hello")

    with open(text_file, "rb") as f:
        response = client.post(
            "/api/vision/analyze",
            files={"image": ("test.txt", f, "text/plain")}
        )

    assert response.status_code == 400
    assert "Invalid file type" in response.json()["error"]
