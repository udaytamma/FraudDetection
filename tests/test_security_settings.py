import pytest

from src.config.settings import Settings


def _set_required_env(monkeypatch) -> None:
    monkeypatch.setenv("API_TOKEN", "test-api")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("METRICS_TOKEN", "test-metrics")
    monkeypatch.setenv("EVIDENCE_VAULT_KEY", "test-vault-key")
    monkeypatch.setenv("EVIDENCE_HASH_KEY", "test-hash-key")


def test_production_requires_security_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    for key in [
        "API_TOKEN",
        "ADMIN_TOKEN",
        "METRICS_TOKEN",
        "EVIDENCE_VAULT_KEY",
        "EVIDENCE_HASH_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError) as excinfo:
        Settings(_env_file=None)

    message = str(excinfo.value)
    assert "API_TOKEN" in message
    assert "ADMIN_TOKEN" in message
    assert "METRICS_TOKEN" in message
    assert "EVIDENCE_VAULT_KEY" in message
    assert "EVIDENCE_HASH_KEY" in message


def test_production_allows_with_required_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _set_required_env(monkeypatch)

    settings = Settings(_env_file=None)
    assert settings.app_env == "production"
