from core.domain.exceptions import (
    BlenderNotFoundError,
    EngineException,
    RigValidationError,
    SelmaError,
)


def test_blender_not_found_error_inheritance():
    error = BlenderNotFoundError()
    assert isinstance(error, EngineException)
    assert isinstance(error, SelmaError)
    assert isinstance(error, Exception)


def test_blender_not_found_error_message():
    error = BlenderNotFoundError("Custom message.")
    assert "Custom message." in str(error)
    assert "environment variable" in str(error)


def test_rig_validation_error_is_an_engine_exception():
    assert isinstance(RigValidationError("invalid rig"), EngineException)
