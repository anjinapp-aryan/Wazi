# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Wazi is a **learning project** building a WhatsApp AI agent step by step. The mentor/owner is the human user; work is organised in gated phases (0-10, listed in `docs/PROJECT_CONSTITUTION.md` §14). Execute only the phase you are asked to, report evidence, then stop. Never start the next phase on your own.

Current state: Phases 0-5 done; Phase 6 (first real Meta contact) is **BLOCKED** on Meta credentials: preparation, tests and a runbook exist in `docs/PHASE_6_META_INTEGRATION.md`, but nothing has run against the real Meta platform. Code covers the secure webhook ingress, a persistent idempotency store, a background worker, an outbound WhatsApp client and a fake echo responder. There is no agent, LLM, Qdrant, RAG, LangGraph, memory, tools or deployment yet, and nothing has ever been run against the real Meta API.

Project rules that shape every change (full text in `docs/PROJECT_CONSTITUTION.md`):
- **REUSE → ADAPT → COMPOSE → BUILD.** Run a short reuse/licence check before writing anything significant, and justify any new dependency.
- Do not claim a test passed unless it was run; do not invent numbers or repo statistics. Label unverified things as unverified.
- Phase deliverables are documents in `docs/` (`PHASE_*.md`, `REUSE_AUDIT.md`, `adr/`). Keep them accurate to what exists.

## Commands

Environment is `uv` with a project-local `.venv` (Python >=3.12). On this Windows machine call tools through the venv:

```bash
uv sync                          # install from uv.lock (add --extra serve for uvicorn)
.venv/Scripts/python -m pytest -q                      # all tests (264, offline, ~2 s; 2 live tests deselected)
.venv/Scripts/python -m pytest tests/test_signature.py::test_valid_signature_accepted   # one test
.venv/Scripts/python -m pytest -k handshake            # by keyword
.venv/Scripts/python -m ruff check .                   # lint
.venv/Scripts/python -m ruff format --check .          # format check (drop --check to apply)
```

Optional local server (loopback only; use made-up values, never real secrets):

```bash
WAZI_WHATSAPP_VERIFY_TOKEN=x WAZI_WHATSAPP_APP_SECRET=y WAZI_IDEMPOTENCY_DB=wazi.db \
  .venv/Scripts/python -m uvicorn --factory wazi.bootstrap:build_server_app --host 127.0.0.1 --port 8099 --no-access-log
```

`build_server_app` = `configure_logging()` + `build_app()`; keep logging configuration out of `build_app` (tests capture logs at DEBUG and would silently weaken). `scripts/simulate_inbound.py` posts a correctly signed Meta-style message to a loopback webhook (reads `WAZI_WHATSAPP_APP_SECRET` from the environment; `--message-id` replays an id for duplicate tests). It proves Wazi, not Meta.

Opt-in live Meta tests: `WAZI_LIVE_META=1 ... .venv/Scripts/python -m pytest -m live_meta tests/live` (deselected by default via `pyproject.toml`; one of them sends a real WhatsApp message; never executed so far).

Without both `WAZI_WHATSAPP_ACCESS_TOKEN` and `WAZI_WHATSAPP_PHONE_NUMBER_ID` the outbound side is a dry-run (nothing is sent). When stopping a server you started, kill it by its exact PID, never with a broad `taskkill /IM python.exe`.

No type checker is configured. There is no CI.

## Architecture (the part spanning several files)

Request path for `POST /webhook`, wired in `src/wazi/webhook/app.py` and deliberately in this order:

```
raw bytes (size-limited stream) -> signature gate -> strict UTF-8 JSON -> envelope validation
  -> normalise -> idempotency claim -> dispatcher.dispatch (enqueue only) -> fast 200 ACK
                                              |
                                              v  worker thread (worker.py)
                             Responder.respond -> ReplySender.send (bounded retry) -> mark_done/failed
```

Composition is in `bootstrap.py` (`build_app`), the only module that knows the concrete pieces: SQLite store if `WAZI_IDEMPOTENCY_DB` is set else in-memory; `WhatsAppCloudClient` only if both outbound variables are set else `DryRunSender`; `EchoResponder` (fake, to be replaced by the agent implementing `ports.Responder`).

- **Signature is verified on the original bytes before any parsing** (`security/signature.py`: HMAC-SHA256, header `X-Hub-Signature-256: sha256=<hex>`, constant-time, fails closed). Never verify re-serialised JSON.
- **Status codes encode Meta's retry policy**: Meta retries any non-200, so final outcomes (accepted, duplicate, unsupported type, status receipts) return 200. 4xx only for things retrying cannot fix; 5xx only when a retry could succeed (dispatch failure releases the idempotency claim). All error bodies are generic `{"error": "..."}`.
- **Layers** (ADR-003) and their allowed imports are enforced by `tests/test_architecture.py` using `ast`, with a per-module/package table (`ALLOWED_WAZI_IMPORTS`; a test fails if you add a module without giving it rules). `security`, `messaging`, `idempotency`, `configuration` are stdlib-only; only `webhook`/`bootstrap` import FastAPI; only `outbound` imports httpx; `ports.py` holds the contracts the worker depends on; nothing imports `bootstrap`. Nothing may import langgraph/langchain/groq/qdrant/redis/celery, Ava (`ai_companion`) or `archagenticrag`. No `print()` in `src/`. The access token may only appear in `configuration/settings.py`, `bootstrap.py`, `outbound/client.py`.
- **Hand-off point is `dispatch.MessageDispatcher`** (a Protocol; implemented by `worker.BackgroundDispatcher`, default `NullDispatcher` does nothing). It must only enqueue/return fast; raising (including `DispatchRejected` when the bounded queue is full) makes the webhook answer 5xx and release the claim, so a batch can be partly accepted and Meta's retry completes it. After the ACK, delivery is at-most-once (ADR-004): failed sends are marked `failed`, a crash leaves the key `claimed` (`SqliteIdempotencyStore.unfinished_keys`), and message content is deliberately not persisted.
- **Idempotency is `claim(key) -> bool` / `release(key)`**, atomic by design (not has+mark), plus the optional `CompletionRecorder` (`mark_done`/`mark_failed`). `SqliteIdempotencyStore` (stdlib) is restart-safe and stores only key, state and timestamps; `InMemoryIdempotencyStore` is lost on restart.
- **Outbound** (`outbound/client.py`) makes one HTTP attempt per `send` and classifies failures as `SendError(retryable=...)`: network errors, 429, 5xx and a short list of Meta codes are retryable; 131047 (24-hour window) and auth errors are permanent. It never puts the token, recipient, text or response body in errors or logs. Retries live in the worker, not the client. Default Graph version `v26.0`.
- `NormalizedMessage` (`messaging/models.py`) is the only message type downstream code should see; it intentionally omits the raw payload and hides sender/text in `repr`. Only the `type` string and `text.body` are read from Meta payloads.
- **Limits come from Meta's docs** (checked 2026-10-29): webhook payloads up to 3 MB (default body limit 4 MiB), batches up to 1000 updates (default `max_pending` 1000), Graph API default `v26.0` (single constant `DEFAULT_GRAPH_API_VERSION`). Re-check them when Meta's docs change; do not lower them without a reason.
- Fail closed on missing config: no app secret => POST 503; no verify token => GET 403 (never `None == None`). Settings come from `WAZI_WHATSAPP_VERIFY_TOKEN` / `WAZI_WHATSAPP_APP_SECRET` (`configuration/settings.py`); secret fields are excluded from `repr`.

## Testing conventions

- Tests must be offline and deterministic: `tests/conftest.py` has an autouse guard that fails any non-loopback connection. Time and sleeping are injected, outbound is tested with `httpx.MockTransport` (`tests/fakes.py` has `FakeSender`), fixtures in `tests/fixtures/` use fake values only (555 numbers, made-up ids). Concurrency tests must control timing with events and `dispatcher.wait_idle()`, not luck: a racy test once failed 8 of 15 runs. After touching threading code, run the suite 20-40 times.
- `tests/test_security_invariants.py` holds the named security rules (no/invalid signature rejected, tampered body rejected, no secrets/PII in responses or `wazi.*` logs, duplicates never dispatched twice). When changing security code, break it deliberately in a scratch copy to confirm a test fails; a past log-leak mutation initially went unnoticed.
- Signature behaviour is verified against a public HMAC-SHA256 test vector, **not against live Meta traffic**. Meta's docs do not state "HMAC" or "raw body"; that is inferred from pywa and AleBrito (both MIT) and still needs a real-Meta check. The same applies to the send request and error codes: the shape follows Meta's docs, but Meta does not state HTTP statuses for Cloud API error codes.

## External context to keep in mind

- **Ava** (`neural-maze/ava-whatsapp-agent-course`, MIT) is a *reference only*, cloned unmodified at `D:\WORK_SPACE\Wazi-baselines\ava`. Do not fork, modify or copy it wholesale. Its known defects (no signature check, token printed to stdout, global un-filtered Qdrant memory, audio replies stored as human messages, provider drift) are documented in `docs/PHASE_2_BASELINE.md` and `docs/PHASE_3_ARCHITECTURE.md`.
- **ArchAgenticRAG** (`D:\WORK_SPACE\ArchAgenticRAG`) is the owner's separate learning project. Do not import, copy, modify or merge it without explicit mentor approval (ADR-002). It currently lacks a LICENSE file.
- Deployment gotcha: Meta's GET handshake puts `hub.verify_token` in the URL, so any server access log will record it. Disable or filter access logs when serving.
