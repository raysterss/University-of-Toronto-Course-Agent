"""Tests for src/model.py — model abstraction layer."""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest

from src.model import BaseModelInterface, MockModel, TencentTokenHubModel


# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------

def test_base_interface_instantiable():
    """BaseModelInterface can be instantiated."""
    base = BaseModelInterface()
    assert base is not None


def test_base_interface_raises_not_implemented():
    """Calling generate_response on the base raises NotImplementedError."""
    base = BaseModelInterface()
    with pytest.raises(NotImplementedError):
        base.generate_response([{"role": "user", "content": "Hello"}])


# ---------------------------------------------------------------------------
# MockModel
# ---------------------------------------------------------------------------

def test_mock_model_returns_response():
    """MockModel.generate_response returns a non-empty string."""
    model = MockModel()
    messages = [{"role": "user", "content": "Recommend AI courses"}]
    response = model.generate_response(messages)
    assert isinstance(response, str)
    assert len(response) > 0


def test_mock_model_deterministic():
    """Same input produces the same output every time."""
    model = MockModel()
    messages = [{"role": "user", "content": "Hello"}]
    first = model.generate_response(messages)
    second = model.generate_response(messages)
    assert first == second


# ---------------------------------------------------------------------------
# Design check — no external dependencies
# ---------------------------------------------------------------------------

def test_no_external_api_dependency():
    """MockModel does not import or call any external API."""
    model = MockModel()
    # Should work without network, API keys, or environment variables
    response = model.generate_response([])
    assert response == "Mock model response"


# ---------------------------------------------------------------------------
# Polymorphism check
# ---------------------------------------------------------------------------

def test_mock_model_is_base_model():
    """MockModel is a subclass of BaseModelInterface."""
    model = MockModel()
    assert isinstance(model, BaseModelInterface)


# ---------------------------------------------------------------------------
# TencentTokenHubModel — environment variable validation
# ---------------------------------------------------------------------------


class TestTokenHubEnvVars:
    """Tests that do NOT call the real API."""

    def test_missing_api_key_raises(self, monkeypatch):
        """Missing TOKENHUB_API_KEY raises ValueError."""
        monkeypatch.delenv("TOKENHUB_API_KEY", raising=False)
        monkeypatch.setenv("TOKENHUB_BASE_URL", "https://example.com")
        monkeypatch.setenv("TOKENHUB_MODEL", "test-model")
        with pytest.raises(ValueError, match="TOKENHUB_API_KEY"):
            TencentTokenHubModel()

    def test_missing_base_url_raises(self, monkeypatch):
        """Missing TOKENHUB_BASE_URL raises ValueError."""
        monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
        monkeypatch.delenv("TOKENHUB_BASE_URL", raising=False)
        monkeypatch.setenv("TOKENHUB_MODEL", "test-model")
        with pytest.raises(ValueError, match="TOKENHUB_BASE_URL"):
            TencentTokenHubModel()

    def test_missing_model_raises(self, monkeypatch):
        """Missing TOKENHUB_MODEL raises ValueError."""
        monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
        monkeypatch.setenv("TOKENHUB_BASE_URL", "https://example.com")
        monkeypatch.delenv("TOKENHUB_MODEL", raising=False)
        with pytest.raises(ValueError, match="TOKENHUB_MODEL"):
            TencentTokenHubModel()

    def test_initializes_with_all_env_vars(self, monkeypatch):
        """Model initialises when all three env vars are present."""
        monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
        monkeypatch.setenv("TOKENHUB_BASE_URL", "https://example.com")
        monkeypatch.setenv("TOKENHUB_MODEL", "test-model")
        model = TencentTokenHubModel()
        assert model is not None

    def test_stores_attributes(self, monkeypatch):
        """Initialised model stores api_key, base_url, and model_name."""
        monkeypatch.setenv("TOKENHUB_API_KEY", "my-key")
        monkeypatch.setenv("TOKENHUB_BASE_URL", "https://tokenhub.example.com")
        monkeypatch.setenv("TOKENHUB_MODEL", "deepseek-chat")
        model = TencentTokenHubModel()
        assert model.api_key == "my-key"
        assert model.base_url == "https://tokenhub.example.com"
        assert model.model_name == "deepseek-chat"


# ---------------------------------------------------------------------------
# Polymorphism check for TokenHub
# ---------------------------------------------------------------------------

def test_tokenhub_model_is_base_model(monkeypatch):
    """TencentTokenHubModel is a subclass of BaseModelInterface."""
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    monkeypatch.setenv("TOKENHUB_BASE_URL", "https://example.com")
    monkeypatch.setenv("TOKENHUB_MODEL", "test-model")
    model = TencentTokenHubModel()
    assert isinstance(model, BaseModelInterface)
