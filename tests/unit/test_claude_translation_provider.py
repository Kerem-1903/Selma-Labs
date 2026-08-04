import pytest
from core.domain.exceptions import ProviderAuthError
from infrastructure.providers.translation.claude_translation_provider import ClaudeTranslationProvider


def test_provider_requires_api_key():
    with pytest.raises(ProviderAuthError, match="API key is required"):
        ClaudeTranslationProvider(api_key="")


def test_provider_identity():
    provider = ClaudeTranslationProvider(api_key="key", model_name="test-model")
    assert provider.provider_identity == "anthropic:test-model"
