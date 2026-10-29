"""Layer-boundary tests: the dependency rules from ADR-003 and the phase scope, as code.

They read the source files with ``ast`` and check imports, so a forbidden dependency fails the
build instead of surviving as a convention.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "wazi"

# Things that are deliberately out of scope until their phase.
OUT_OF_SCOPE = {
    "langgraph",
    "langchain",
    "langchain_core",
    "langchain_community",
    "groq",
    "openai",
    "anthropic",
    "google",
    "qdrant_client",
    "sentence_transformers",
    "fastembed",
    "docling",
    "redis",
    "celery",
    "archagenticrag",
    "ai_companion",  # Ava
}

# unit (package directory or top-level module) -> wazi units it may import (itself is allowed)
ALLOWED_WAZI_IMPORTS: dict[str, set[str]] = {
    "configuration": set(),
    "security": set(),
    "messaging": set(),
    "idempotency": set(),
    "ports": {"messaging"},
    "dispatch": {"messaging"},
    "responder": {"messaging"},
    "safe_logging": set(),
    "outbound": {"messaging", "ports"},
    "worker": {"idempotency", "messaging", "ports", "safe_logging"},
    "webhook": {
        "configuration",
        "security",
        "messaging",
        "idempotency",
        "dispatch",
        "safe_logging",
    },
    # The composition root may import everything; nothing may import it.
    "bootstrap": {
        "configuration",
        "idempotency",
        "outbound",
        "ports",
        "responder",
        "webhook",
        "worker",
    },
}

# third-party HTTP stacks: which unit may import which
FRAMEWORK_OWNERS = {"fastapi": {"webhook", "bootstrap"}, "starlette": {"webhook"}, "uvicorn": set()}
HTTP_CLIENT_OWNERS = {"httpx": {"outbound"}}


def unit_files(unit: str) -> list[Path]:
    package = SRC / unit
    if package.is_dir():
        return sorted(package.rglob("*.py"))
    return [SRC / f"{unit}.py"]


def imports_of(path: Path) -> set[str]:
    """Absolute module names imported by a file."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def wazi_target(module: str) -> str | None:
    """'wazi.security.signature' -> 'security'; 'wazi.dispatch' -> 'dispatch'."""
    parts = module.split(".")
    return parts[1] if parts[0] == "wazi" and len(parts) > 1 else None


def test_every_source_unit_is_covered_by_the_rules():
    units = {p.name for p in SRC.iterdir() if p.is_dir() and p.name != "__pycache__"}
    units |= {p.stem for p in SRC.glob("*.py") if p.stem != "__init__"}
    assert units == set(ALLOWED_WAZI_IMPORTS), "add new modules/packages to ALLOWED_WAZI_IMPORTS"


@pytest.mark.parametrize("unit", sorted(ALLOWED_WAZI_IMPORTS))
def test_unit_only_imports_allowed_wazi_units(unit):
    allowed = ALLOWED_WAZI_IMPORTS[unit] | {unit}
    for path in unit_files(unit):
        for module in imports_of(path):
            target = wazi_target(module)
            if target is not None:
                assert target in allowed, f"{path.name} in '{unit}' imports wazi.{target}"


def test_nothing_imports_the_composition_root():
    for unit in ALLOWED_WAZI_IMPORTS:
        for path in unit_files(unit):
            for module in imports_of(path):
                assert wazi_target(module) != "bootstrap" or unit == "bootstrap"


@pytest.mark.parametrize("unit", sorted(ALLOWED_WAZI_IMPORTS))
def test_http_frameworks_and_clients_are_confined_to_their_owner_units(unit):
    for path in unit_files(unit):
        roots = {m.split(".")[0] for m in imports_of(path)}
        for name, owners in {**FRAMEWORK_OWNERS, **HTTP_CLIENT_OWNERS}.items():
            if name in roots:
                assert unit in owners, f"{path.name} in '{unit}' imports {name}"


def test_nothing_out_of_scope_is_imported_anywhere():
    for path in SRC.rglob("*.py"):
        roots = {m.split(".")[0] for m in imports_of(path)}
        assert not (roots & OUT_OF_SCOPE), f"{path} imports {roots & OUT_OF_SCOPE}"


def test_webhook_package_contains_no_business_logic_modules():
    # The HTTP layer is a single wiring module plus its package file.
    assert {p.name for p in unit_files("webhook")} == {"__init__.py", "app.py"}


def test_no_print_statements_in_application_code():
    # Ava printed its bearer token with print(). Application code must use logging only.
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "print", f"print() in {path}"


_SECRET_LITERALS = [
    re.compile(r"EAA[A-Za-z0-9]{20,}"),  # Meta access-token shape
    re.compile(r"""Bearer\s+[A-Za-z0-9_\-\.]{16,}"""),  # a literal bearer token
    # name = "literal"; environment-variable NAMES such as "WAZI_..." are fine, values are not
    re.compile(
        r"""(?i)(api_key|password|secret|token)\s*=\s*["'](?!WAZI_[A-Z_]+["'])[^"']{8,}["']"""
    ),
]


def test_no_hardcoded_secret_like_literals():
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in _SECRET_LITERALS:
            assert not pattern.search(text), f"secret-like literal in {path}"


def test_access_token_is_only_read_where_expected():
    # The token should flow: Settings -> bootstrap -> WhatsAppCloudClient and nowhere else.
    users = {
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "access_token" in p.read_text(encoding="utf-8")
    }
    assert users == {
        "configuration/settings.py",
        "bootstrap.py",
        "outbound/client.py",
    }
