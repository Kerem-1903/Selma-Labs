import pytest
from core.domain.exceptions import BlenderNotFoundError, EngineException, SelmaError

def test_blender_not_found_error_inheritance():
    error = BlenderNotFoundError()
    assert isinstance(error, EngineException)
    assert isinstance(error, SelmaError)
    assert isinstance(error, Exception)

def test_blender_not_found_error_message():
    error = BlenderNotFoundError("Custom message.")
    assert "Custom message." in str(error)
    assert "environment variable" in str(error)
