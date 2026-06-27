#!/usr/bin/env python3
"""Automated configuration validation for the SUPERVOID LibreChat deployment.

Validates the committed deployment artefacts WITHOUT needing Docker:
  * librechat.yaml — the SUPERVOID Brain custom endpoint + MCP server shape;
  * docker-compose.librechat.yml — pinned images, private networking;
  * .env.librechat (optional, via --env-file) — required secrets are set and not
    left as placeholders.

Exit code 0 = all checks pass; non-zero = at least one failure. Designed to be
called both as a pre-deploy step and from the test suite (``validate_all``).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import yaml

BRAIN_DIR = Path(__file__).resolve().parent.parent
LIBRECHAT_YAML = BRAIN_DIR / "librechat.yaml"
COMPOSE_YAML = BRAIN_DIR / "docker-compose.librechat.yml"
ENV_EXAMPLE = BRAIN_DIR / ".env.librechat.example"

REQUIRED_SECRETS = [
    "JWT_SECRET", "JWT_REFRESH_SECRET", "CREDS_KEY", "CREDS_IV",
    "MEILI_MASTER_KEY", "MCP_SERVICE_TOKEN",
]
USER_HEADERS = [
    "X-SUPERVOID-User-Id", "X-SUPERVOID-User-Email",
    "X-SUPERVOID-User-Role", "X-SUPERVOID-Request-Id",
]


def _load_yaml(path: Path, errors: list) -> Optional[dict]:
    if not path.exists():
        errors.append(f"missing file: {path}")
        return None
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        errors.append(f"invalid YAML in {path.name}: {exc}")
        return None


def _check_librechat_yaml(errors: list) -> None:
    cfg = _load_yaml(LIBRECHAT_YAML, errors)
    if cfg is None:
        return
    if not cfg.get("version"):
        errors.append("librechat.yaml: missing 'version'.")
    # registration disabled (no social logins block; registration via env flag)
    reg = cfg.get("registration") or {}
    if reg.get("socialLogins", []) != []:
        errors.append("librechat.yaml: registration.socialLogins should be empty.")

    custom = (cfg.get("endpoints") or {}).get("custom") or []
    brain = next((e for e in custom if e.get("name") == "SUPERVOID Brain"), None)
    if brain is None:
        errors.append("librechat.yaml: no custom endpoint named 'SUPERVOID Brain'.")
    else:
        if brain.get("apiKey") != "user_provided":
            errors.append("librechat.yaml: SUPERVOID Brain apiKey must be 'user_provided'.")
        base = brain.get("baseURL", "")
        if not base.endswith("/brain/v1"):
            errors.append("librechat.yaml: SUPERVOID Brain baseURL must end with '/brain/v1'.")
        models = (brain.get("models") or {}).get("default") or []
        if not models:
            errors.append("librechat.yaml: SUPERVOID Brain models.default must list the served alias(es).")
        if brain.get("titleConvo") is not True:
            errors.append("librechat.yaml: titleConvo must be true (titles via the Brain).")
        if not isinstance(brain.get("dropParams", []), list):
            errors.append("librechat.yaml: dropParams must be a list (drop only after testing).")

    mcp = (cfg.get("mcpServers") or {}).get("supervoid")
    if mcp is None:
        errors.append("librechat.yaml: missing mcpServers.supervoid.")
    else:
        if mcp.get("type") != "streamable-http":
            errors.append("librechat.yaml: MCP server type must be 'streamable-http'.")
        if not mcp.get("url"):
            errors.append("librechat.yaml: MCP server url is required.")
        headers = mcp.get("headers") or {}
        for h in USER_HEADERS:
            if h not in headers:
                errors.append(f"librechat.yaml: MCP headers missing dynamic '{h}'.")
        if mcp.get("serverInstructions") is not True:
            errors.append("librechat.yaml: MCP serverInstructions must be true.")
        if not mcp.get("initTimeout") or not mcp.get("timeout"):
            errors.append("librechat.yaml: MCP initTimeout and timeout must be set.")


def _check_compose(errors: list) -> None:
    cfg = _load_yaml(COMPOSE_YAML, errors)
    if cfg is None:
        return
    services = cfg.get("services") or {}
    for name in ("librechat", "mongodb", "meilisearch"):
        if name not in services:
            errors.append(f"compose: missing required service '{name}'.")
    # images pinned (no ':latest', and a tag present)
    for name, svc in services.items():
        image = svc.get("image", "")
        ref = image.split(":-")[-1].rstrip("}") if ":-" in image else image  # ${X:-pin}
        if ref.endswith(":latest"):
            errors.append(f"compose: service '{name}' uses ':latest' (pin a release).")
        if ":" not in ref.split("@")[0]:
            errors.append(f"compose: service '{name}' image is not pinned to a tag/digest.")
    # mongo + meili must NOT publish host ports
    for name in ("mongodb", "meilisearch"):
        if services.get(name, {}).get("ports"):
            errors.append(f"compose: service '{name}' must not publish host ports (internal only).")
    # librechat must bind to loopback (never 0.0.0.0)
    lc_ports = services.get("librechat", {}).get("ports", [])
    joined = " ".join(str(p) for p in lc_ports)
    if "0.0.0.0" in joined:
        errors.append("compose: librechat must not bind 0.0.0.0 (loopback only, behind the proxy).")
    if "LIBRECHAT_BIND_ADDR" not in joined and "127.0.0.1" not in joined:
        errors.append("compose: librechat port binding should use LIBRECHAT_BIND_ADDR / 127.0.0.1.")
    # the internal network must be marked internal
    nets = cfg.get("networks") or {}
    internal = nets.get("librechat-internal") or {}
    if internal.get("internal") is not True:
        errors.append("compose: 'librechat-internal' network must be marked internal: true.")


def _parse_env(path: Path) -> dict:
    out: dict = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _check_env_example(errors: list) -> None:
    if not ENV_EXAMPLE.exists():
        errors.append(f"missing {ENV_EXAMPLE.name}")
        return
    env = _parse_env(ENV_EXAMPLE)
    for key in REQUIRED_SECRETS:
        if key not in env:
            errors.append(f".env.librechat.example: missing key '{key}'.")


def _check_env_file(path: Path, errors: list) -> None:
    if not path.exists():
        errors.append(f"env file not found: {path}")
        return
    env = _parse_env(path)
    for key in REQUIRED_SECRETS:
        val = env.get(key, "")
        if not val:
            errors.append(f"env: '{key}' is not set.")
        elif "CHANGE_ME" in val or len(val) < 16:
            errors.append(f"env: '{key}' is a placeholder / too weak (use a strong secret).")
    if env.get("LIBRECHAT_ALLOW_REGISTRATION", "false").lower() == "true":
        errors.append("env: LIBRECHAT_ALLOW_REGISTRATION=true — disable after admin provisioning.")
    if env.get("LIBRECHAT_BIND_ADDR", "127.0.0.1") == "0.0.0.0":
        errors.append("env: LIBRECHAT_BIND_ADDR must not be 0.0.0.0 (keep behind the proxy).")


def validate_all(*, env_file: Optional[Path] = None) -> list[str]:
    errors: list[str] = []
    _check_librechat_yaml(errors)
    _check_compose(errors)
    _check_env_example(errors)
    if env_file is not None:
        _check_env_file(env_file, errors)
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate the LibreChat deployment config.")
    parser.add_argument("--env-file", type=Path, default=None,
                        help="Also validate a concrete .env.librechat (secrets set, not placeholders).")
    args = parser.parse_args(argv)
    errors = validate_all(env_file=args.env_file)
    if errors:
        print("FAIL — LibreChat configuration validation:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASS — LibreChat configuration is valid.")
    if args.env_file is None:
        print("  (run with --env-file .env.librechat to also validate secrets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
