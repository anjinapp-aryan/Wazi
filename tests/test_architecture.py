"""Layer-boundary tests: the dependency rules from ADR-003 and the Phase 4 scope, as code.

They read the source files with ``ast`` and check imports, so a forbidden dependency fails the
build instead of surviving as a convention.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "wazi"

HTTP_FRAMEWORKS = {"fastapi", "starlette", "uvicorn", "httpx"}
# Things that are deliberately out of scope in Phase 4.
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

# package -> wazi sub-packages it may import (itself always allowed)
ALLOWED_WAZI_IMPORTS: dict[str, set[str]] = {
    "configuration": set(),
    "security": set(),
    "messaging": set(),
    "idempotency": set(),
    "webhook": {
        "configuration",
        "security",
        "messaging",
        "idempotency",
        "dispatch",
        "safe_logging",
    },
}
NO_HTTP_FRAMEWORK = {"configuration", "security", "messaging", "idempotency"}


def imports_of(path: Path) -> set[str]:
    """Absolute module names imported by a file."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def package_files(package: str) -> list[Path]:
    return sorted((SRC / package).rglob("*.py"))


def wazi_target(module: str) -> str | None:
    """'wazi.security.signature' -> 'security'; 'wazi.dispatch' -> 'dispatch'."""
    parts = module.split(".")
    return parts[1] if parts[0] == "wazi" and len(parts) > 1 else None


@pytest.mark.parametrize("package", sorted(ALLOWED_WAZI_IMPORTS))
def test_package_only_imports_allowed_wazi_packages(package):
    allowed = ALLOWED_WAZI_IMPORTS[package] | {package}
    for path in package_files(package):
        for module in imports_of(path):
            target = wazi_target(module)
            if target is not None:
                assert target in allowed, f"{path.name} in '{package}' imports wazi.{target}"


@pytest.mark.parametrize("package", sorted(NO_HTTP_FRAMEWORK))
def test_non_http_layers_do_not_import_an_http_framework(package):
    for path in package_files(package):
        roots = {m.split(".")[0] for m in imports_of(path)}
        assert not (roots & HTTP_FRAMEWORKS), f"{path.name} imports {roots & HTTP_FRAMEWORKS}"


def test_dispatch_depends_only_on_messaging():
    targets = {wazi_target(m) for m in imports_of(SRC / "dispatch.py")} - {None}
    assert targets == {"messaging"}


def test_nothing_out_of_scope_is_imported_anywhere():
    for path in SRC.rglob("*.py"):
        roots = {m.split(".")[0] for m in imports_of(path)}
        assert not (roots & OUT_OF_SCOPE), f"{path} imports {roots & OUT_OF_SCOPE}"


def test_webhook_package_contains_no_business_logic_modules():
    # The HTTP layer is a single wiring module plus its package file.
    assert {p.name for p in package_files("webhook")} == {"__init__.py", "app.py"}


def test_no_print_statements_in_application_code():
    # Ava printed its bearer token with print(). Application code must use logging only.
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "print", f"print() in {path}"


def test_no_hardcoded_secret_like_literals():
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for marker in ("bearer ", "eaa", "api_key =", "password ="):
            assert marker not in text, f"{marker!r} found in {path}"
