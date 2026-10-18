# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Wazi is a **learning project** building a WhatsApp AI agent step by step. The mentor/owner is the human user; work is organised in gated phases (0-10, listed in `docs/PROJECT_CONSTITUTION.md` §14). Execute only the phase you are asked to, report evidence, then stop. Never start the next phase on your own.

Current state: Phases 0-4 done. Code exists only for the secure webhook ingress (Phase 4). There is no agent, LLM, Qdrant, RAG, LangGraph, memory, tools, outbound WhatsApp client or deployment yet.

Project rules that shape every change (full text in `docs/PROJECT_CONSTITUTION.md`):
- **REUSE → ADAPT → COMPOSE → BUILD.** Run a short reuse/licence check before writing anything significant, and justify any new dependency.
- Do not claim a test passed unless it was run; do not invent numbers or repo statistics. Label unverified things as unverified.
- Phase deliverables are documents in `docs/` (`PHASE_*.md`, `REUSE_AUDIT.md`, `adr/`). Keep them accurate to what exists.

## Commands

Environment is `uv` with a project-local `.venv` (Python >=3.12). On this Windows machine call tools through the venv:

```bash
uv sync                          # install from uv.lock (add --extra serve for uvicorn)
.venv/Scripts/python -m pytest -q                      # all tests (147, offline, ~0.3 s)
.venv/Scripts/python -m pytest tests/test_signature.py::test_valid_signature_accepted   # one test
.venv/Scripts/python -m pytest -k handshake            # by keyword
.venv/Scripts/python -m ruff check .                   # lint
.venv/Scripts/python -m ruff format --check .          # format check (drop --check to apply)
```

Optional local server (loopback only; use made-up values, never real secrets):

```bash
WAZI_WHATSAPP_VERIFY_TOKEN=x WAZI_WHATSAPP_APP_SECRET=y \
  .venv/Scripts/python -m uvicorn --factory wazi.webhook:create_app --host 127.0.0.1 --port 8099 --no-access-log
```

No type checker is configured. There is no CI.

## Architecture (the part spanning several files)

Request path for `POST /webhook`, wired in `src/wazi/webhook/app.py` and deliberately in this order:

```
raw bytes (size-limited stream) -> signature gate -> strict UTF-8 JSON -> envelope validation
  -> normalise -> idempotency claim -> dispatcher -> fast 200 ACK
```

- **Signature is verified on the original bytes before any parsing** (`security/signature.py`: HMAC-SHA256, header `X-Hub-Signature-256: sha256=<hex>`, constant-time, fails closed). Never verify re-serialised JSON.
- **Status codes encode Meta's retry policy**: Meta retries any non-200, so final outcomes (accepted, duplicate, unsupported type, status receipts) return 200. 4xx only for things retrying cannot fix; 5xx only when a retry could succeed (dispatch failure releases the idempotency claim). All error bodies are generic `{"error": "..."}`.
- **Layers** (ADR-003) and their allowed imports are enforced by `tests/test_architecture.py` using `ast`: `security`, `messaging`, `idempotency`, `configuration` are stdlib-only and know nothing of HTTP; only `webhook` imports FastAPI; `dispatch.py` depends only on `messaging`. Nothing may import langgraph/langchain/groq/qdrant/redis/celery, Ava (`ai_companion`) or `archagenticrag`. No `print()` in `src/`.
- **Agent hand-off point is `dispatch.MessageDispatcher`** (a Protocol; default `NullDispatcher` does nothing). It must only enqueue/return fast; raising makes the webhook answer 5xx and release the claim. Everything past it is future work.
- **Idempotency is `claim(key) -> bool` / `release(key)`**, atomic by design (not has+mark). `InMemoryIdempotencyStore` is single-process and lost on restart; swap in a persistent store behind the same Protocol.
- `NormalizedMessage` (`messaging/models.py`) is the only message type downstream code should see; it intentionally omits the raw payload and hides sender/text in `repr`. Only the `type` string and `text.body` are read from Meta payloads.
- Fail closed on missing config: no app secret => POST 503; no verify token => GET 403 (never `None == None`). Settings come from `WAZI_WHATSAPP_VERIFY_TOKEN` / `WAZI_WHATSAPP_APP_SECRET` (`configuration/settings.py`); secret fields are excluded from `repr`.

## Testing conventions

- Tests must be offline and deterministic: `tests/conftest.py` has an autouse guard that fails any non-loopback connection. Time is injected (fake clock), fixtures in `tests/fixtures/` use fake values only (555 numbers, made-up ids).
- `tests/test_security_invariants.py` holds the named security rules (no/invalid signature rejected, tampered body rejected, no secrets/PII in responses or `wazi.*` logs, duplicates never dispatched twice). When changing security code, break it deliberately in a scratch copy to confirm a test fails; a past log-leak mutation initially went unnoticed.
- Signature behaviour is verified against a public HMAC-SHA256 test vector, **not against live Meta traffic**. Meta's docs do not state "HMAC" or "raw body"; that is inferred from pywa and AleBrito (both MIT) and still needs a real-Meta check.

## External context to keep in mind

- **Ava** (`neural-maze/ava-whatsapp-agent-course`, MIT) is a *reference only*, cloned unmodified at `D:\WORK_SPACE\Wazi-baselines\ava`. Do not fork, modify or copy it wholesale. Its known defects (no signature check, token printed to stdout, global un-filtered Qdrant memory, audio replies stored as human messages, provider drift) are documented in `docs/PHASE_2_BASELINE.md` and `docs/PHASE_3_ARCHITECTURE.md`.
- **ArchAgenticRAG** (`D:\WORK_SPACE\ArchAgenticRAG`) is the owner's separate learning project. Do not import, copy, modify or merge it without explicit mentor approval (ADR-002). It currently lacks a LICENSE file.
- Deployment gotcha: Meta's GET handshake puts `hub.verify_token` in the URL, so any server access log will record it. Disable or filter access logs when serving.
