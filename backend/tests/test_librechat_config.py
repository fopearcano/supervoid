"""Automated validation of the committed LibreChat deployment configuration.

Keeps the deployment artefacts honest in CI: librechat.yaml exposes only the
governed SUPERVOID Brain endpoint + MCP server, the compose pins images and keeps
the data services private, and the env example declares every required secret.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_VALIDATOR = _REPO / "deploy" / "brain" / "scripts" / "validate_librechat_config.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_librechat_config", _VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_validator_module_present():
    assert _VALIDATOR.exists(), "the LibreChat config validator must be committed"


def test_committed_config_is_valid():
    mod = _load_validator()
    errors = mod.validate_all()
    assert errors == [], "LibreChat config validation failed:\n" + "\n".join(errors)


def test_placeholder_env_is_rejected():
    """The secret-strength check must FAIL on the example's CHANGE_ME placeholders
    (proving the validation actually guards secrets, not just structure)."""
    mod = _load_validator()
    example = _REPO / "deploy" / "brain" / ".env.librechat.example"
    errors = mod.validate_all(env_file=example)
    assert any("placeholder" in e or "too weak" in e for e in errors)


def test_artifacts_exist():
    base = _REPO / "deploy" / "brain"
    for name in ("docker-compose.librechat.yml", "librechat.yaml",
                 ".env.librechat.example", "nginx/librechat.conf"):
        assert (base / name).exists(), f"missing deployment artefact: {name}"
