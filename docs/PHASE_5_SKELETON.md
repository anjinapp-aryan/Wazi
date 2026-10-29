# Phase 5: Walking Skeleton

Status: Phase 5 deliverable, awaiting mentor review. Date: **2026-10-29**. Option A from the Phase 4 report (chosen by the mentor).
Result: **253 automated tests pass (40 consecutive runs, no flakiness after one test was fixed); lint and format checks pass; everything runs offline with fake values.**

Scope: a fake responder, an outbound WhatsApp client and a persistent idempotency store, so that the complete loop works end to end:

```
signed webhook -> verify -> validate -> normalise -> claim (SQLite) -> queue -> 200 ACK
                                                                  \-> worker -> fake responder -> WhatsApp client -> (Meta)
```

Still **not** built: LLM, agent, LangGraph, Qdrant, RAG, memory, tools, handoff, media, a real Meta connection, deployment. No Ava or ArchAgenticRAG code was used.

Run it:

```bash
uv sync --extra serve
.venv/Scripts/python -m pytest -q                       # 253 tests, offline
.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .

# local server, loopback only, dry-run replies (nothing is sent anywhere)
WAZI_WHATSAPP_VERIFY_TOKEN=x WAZI_WHATSAPP_APP_SECRET=y WAZI_IDEMPOTENCY_DB=wazi.db \
  .venv/Scripts/python -m uvicorn --factory wazi.bootstrap:build_app --host 127.0.0.1 --port 8099 --no-access-log
```

---

## 1. Reuse Check (done before writing code)

| Source | License | What was examined | Finding | Decision |
|---|---|---|---|---|
| Meta's official docs (fetched 2026-10-29) | n/a | Send-text endpoint, headers, body, success and error JSON, error codes, 24-hour window, Graph versions | `POST /<version>/<phone_number_id>/messages`, `Authorization: Bearer`, body with `messaging_product`, `recipient_type`, `to`, `type`, `text`; max 4096 characters; success only means "accepted"; error codes documented with advice; **HTTP statuses for Cloud API error codes are not stated**; latest Graph version **v26.0** (2026-07-29), v21.0 expires 2027-01-21 | Source of truth for the request shape |
| AleBrito `whatsapp-ai-agent` `app/wa_client.py` | MIT | Transport split (live / dry-run / callback), sync `httpx` client used from a background task | Good dry-run idea. Weaknesses: failures return `None` (no classification), no retries, logs up to 500 characters of the response body | **ADAPT patterns** (dry-run sender, sync client in a worker). No code copied |
| AleBrito `app/db.py` | MIT | `processed_messages` table, atomic `INSERT`, `handled_at` column, per-call short-lived connections | Same idea as our `claim` | **ADAPT pattern** for the SQLite store |
| pywa `pywa/api.py` | MIT | Typed errors from `httpx`; no retry logic found in the files searched | Full framework that hides the protocol (the Phase 4 decision stands) | **REJECT as dependency**, **REFERENCE** |
| Python standard library (`sqlite3`, `concurrent.futures`) | PSF | Needed pieces for a restart-safe store and a bounded worker | Sufficient; no new dependency | **REUSE** |
| `httpx` | BSD-3-Clause | Already a dev dependency (FastAPI's test client needs it) | Now also the runtime HTTP client | **Dependency moved from dev to runtime** (see §9) |

Conclusion: no existing small component fits better than a thin client around `httpx` plus `sqlite3`; the patterns come from AleBrito and Meta's documentation.

## 2. Architecture

New or changed units (the dependency rules are enforced by `tests/test_architecture.py`, which now covers every module and package):

```
messaging/      + OutboundReply (channel-neutral reply)                     stdlib only
ports.py        Responder, ReplySender, SendResult, SendError               depends on: messaging
responder.py    EchoResponder  (fake; NOT the agent)                        depends on: messaging
outbound/       WhatsAppCloudClient, DryRunSender  (only place using httpx) depends on: messaging, ports
idempotency/    + SqliteIdempotencyStore, CompletionRecorder protocol       stdlib only
worker.py       BackgroundDispatcher, RetryPolicy, DispatchRejected         depends on: idempotency, messaging, ports, safe_logging
webhook/        unchanged logic; create_app() gained a lifespan hook        (FastAPI only here)
bootstrap.py    composition root: picks store, sender, responder from config depends on: everything; nothing depends on it
```

Direction of knowledge: the webhook knows nothing about WhatsApp sending; the worker knows nothing about HTTP or Meta; the outbound client knows nothing about the worker, storage or retries; only `bootstrap.py` knows the concrete pieces. The future agent replaces `EchoResponder` by implementing `Responder`.

Diagram (EXISTING vs FUTURE):

```
 HTTP request
   |  webhook (FastAPI)                         EXISTING (Phase 4)
   |  raw body -> signature -> JSON -> normalise EXISTING (Phase 4)
   |  claim in SQLite (or memory)               EXISTING (persistent since Phase 5)
   |  dispatcher.dispatch -> queue              EXISTING (BackgroundDispatcher)
   |  200 ACK                                   EXISTING
   v
 worker thread
   |  Responder.respond(message)                EXISTING as EchoResponder  --> FUTURE: the agent
   |  ReplySender.send(reply)  (bounded retry)  EXISTING: WhatsAppCloudClient / DryRunSender
   |  mark_done / mark_failed                   EXISTING
   v
 Meta Cloud API (graph.facebook.com)            NOT CONTACTED in Phase 5 (tests use a fake transport)
 durable inbox / crash recovery / queue broker  FUTURE, NOT IMPLEMENTED
```

## 3. Outbound WhatsApp Client

`outbound/client.py`, one `send(OutboundReply)` call = one HTTP attempt.

* Request exactly as documented by Meta (§1) and asserted field by field in tests. Default API version **v26.0** (the latest on Meta's changelog on 2026-10-29), configurable via `WAZI_GRAPH_API_VERSION`.
* Validation before anything is placed in a URL or body: `phone_number_id` digits only, API version `vNN.N`, base URL `https`, recipient digits 5-20 characters, non-empty text; text cut to 4096 characters.
* `httpx.Client` with a 10 s timeout, **redirects not followed** (a redirect would carry the bearer token elsewhere; tested).
* The token lives only in the `Authorization` header. It is absent from `repr`, from `SendError` text, and from logs (tested, including a transport error whose own message contains the token).
* Error classification (`SendError.retryable`): network errors and timeouts, HTTP 429 and 5xx, and the Meta codes 2, 4, 80007, 130429, 131000, 131016, 131056, 133004 are **retryable** (taken from Meta's error-codes page: "try again later", "wait and retry"); everything else, including 190 (token), 100 (bad request), 131026 and **131047 (outside the 24-hour window)**, is **permanent**. The classification is mine; Meta states the advice per code but not the HTTP statuses. `Retry-After` is parsed and capped at 60 s.
* `DryRunSender`: chosen automatically when `WAZI_WHATSAPP_ACCESS_TOKEN` **or** `WAZI_WHATSAPP_PHONE_NUMBER_ID` is missing (half-configured counts as not configured). It keeps the last 100 replies in memory and logs only a notice.

**Never exercised against the real Meta API**: no credentials exist. The request shape matches the documentation and is tested against a fake transport; the first real send must be treated as an experiment (§12).

## 4. Persistent Idempotency (SQLite)

`idempotency/sqlite_store.py`, standard library only.

* Table `claims(key PRIMARY KEY, state, claimed_at, updated_at)`. A test asserts the file holds **no message content and no phone numbers**, only the provider's message id, a state and timestamps.
* `claim` = one `BEGIN IMMEDIATE` transaction that purges expired rows and does `INSERT OR IGNORE`; `rowcount == 1` means "you won". Exactly one winner is proven with 12 threads on one store object and with 8 independent store objects on the same file (like separate processes).
* Survives restart (new object, same file => duplicate) and is checked again through the full application in `test_a_duplicate_after_a_restart_is_still_a_duplicate` and on a real server (§10).
* TTL 7 days by default (Meta's longest documented retry window); WAL mode; short-lived connection per call (like AleBrito); `:memory:` is rejected because it would be per-connection.
* States: `claimed` -> `done` | `failed`. `unfinished_keys()` lists claims that never finished (what a crash leaves behind).
* The in-memory store implements the same protocols and also tracks states.
* The database file pattern (`*.db`, WAL files) is git-ignored.

## 5. Background Worker

`worker.py`, `BackgroundDispatcher` implements the Phase 4 `MessageDispatcher` contract.

* `dispatch()` only enqueues (a bounded `ThreadPoolExecutor`, 4 threads by default) and returns. Test: the webhook answers 200 while the sender is still blocked, and the claim is still `claimed`.
* Send retries: up to 3 attempts, delay 0.5 s then 1 s (max 8 s), honouring `Retry-After`. Permanent errors are not retried. The sleep function is injected, so tests do not sleep.
* Failure isolation: a responder crash, a send failure or even a storage error while recording the outcome is logged by exception **type** only and never kills the worker thread.
* **Back-pressure:** `max_pending` (default 100) queued-or-running messages. Over the limit, `dispatch` raises `DispatchRejected`, the webhook releases the claim and answers 5xx, so Meta retries later. A batch can be partly accepted; on Meta's retry the already-accepted messages are skipped as duplicates and the rest proceeds (tested, and this scenario also exposed a flaky test of mine, see §11).
* `close()` stops accepting work, waits for queued replies, and closes the sender. The FastAPI lifespan calls it at shutdown.
* Delivery semantics are in [ADR-004](adr/004-ack-then-process-with-persisted-claims.md).

## 6. Fake Responder

`EchoResponder` replies `Wazi skeleton echo: <text up to 500 characters>` to text messages and nothing to others. It exists to prove the loop; it is replaced by implementing `Responder` in the agent phase.

## 7. Configuration (environment variables)

| Variable | Secret? | Purpose | If missing |
|---|---|---|---|
| `WAZI_WHATSAPP_VERIFY_TOKEN` | yes | GET handshake | GET always 403 |
| `WAZI_WHATSAPP_APP_SECRET` | yes | Verify POST signatures | POST always 503 |
| `WAZI_WHATSAPP_ACCESS_TOKEN` | yes | Bearer token for sending | dry-run |
| `WAZI_WHATSAPP_PHONE_NUMBER_ID` | no | Sending number id (digits) | dry-run |
| `WAZI_GRAPH_API_VERSION` | no | default `v26.0` | default |
| `WAZI_IDEMPOTENCY_DB` | no | SQLite file path | in-memory store, with a startup warning |

Tuning knobs exist on `Settings` (`worker_threads`, `max_pending`, `outbound_max_attempts`) but are not yet exposed as environment variables.

## 8. Security Review of the New Code

| Control | Evidence |
|---|---|
| The access token flows only `Settings -> bootstrap -> WhatsAppCloudClient` | Architecture test lists the three files that may mention `access_token` |
| `httpx` is confined to `outbound/`; FastAPI to `webhook/` and `bootstrap.py` | Architecture test |
| No token, recipient, text, response body or raw message id in logs, errors or responses | `test_outbound_client`, `test_worker`, `test_skeleton_end_to_end` (all at DEBUG level) |
| Redirects not followed; HTTPS only; timeouts; validated identifiers | `test_outbound_client` |
| Unsigned requests never reach the worker or Meta | `test_unsigned_request_never_reaches_the_worker_or_meta` |
| Queue bounded (no unbounded memory growth under a flood of signed requests) | `test_worker`, end-to-end |
| Database holds no content | `test_database_stores_no_message_content...` |
| No `print()` / literal secrets in `src/` | Architecture tests (the secret-literal pattern now ignores `WAZI_...` variable *names*) |

Open security items carried forward: access logs record the GET verify token (Phase 4 note); no rate limiting on the webhook; no signature replay window; the SQLite file is unencrypted (it holds only ids and states); message ids are stored in clear text.

## 9. Dependencies

| Package | Change | Why | License (package metadata) |
|---|---|---|---|
| `httpx` | **dev -> runtime** | The outbound client needs an HTTP client; it was already installed for FastAPI's test client; the Ava reference and AleBrito both use it | BSD-3-Clause |
| `sqlite3`, `concurrent.futures`, `threading` | none (standard library) | Persistence and background work | PSF |

No new third-party package was added; the lockfile still resolves **25 packages**. pywa was again rejected.

## 10. Test Results

Commands were run in this phase; numbers are from those runs.

| Check | Result |
|---|---|
| `pytest` | **253 passed**, 0 failed, 1 warning (Starlette's test-client deprecation note about `httpx`), about 2 s |
| Repeat run | 40 consecutive full runs: 253 passed each (a first series of 15 runs had 8 runs with one failure; see §11) |
| `ruff check .` / `ruff format --check .` | All checks passed / 47 files already formatted |
| Type checker | Not configured, not run |
| Mutation checks | 17 deliberate breakages of the new code in a scratch copy, **all caught** by at least one test: SQLite claim never loses, no expiry, retrying permanent errors, never retrying, running inline instead of queueing, no back-pressure, failures recorded as done, exception text logged, 131047 treated as retryable, redirects followed, real Authorization value logged, recipient logged, response body in the error, recipient validation removed, real sender always chosen, completion recorder dropped, reply sent to the wrong person. (A first "logs request headers" mutation survived only because httpx masks `Authorization` in its `repr`; replaced by one that logs the real value, which is caught) |
| Real-server smoke test (uvicorn on 127.0.0.1, dry-run, SQLite file) | first POST accepted; second POST duplicate; **server killed by its process id and started again on the same file; the same POST is a duplicate**; database holds `('wamid.FAKETEXT001', 'done')`; nothing listening afterwards |

Tests per file: architecture 31, GET 16, idempotency 10, normaliser 44, outbound client 43, security invariants 15, signature 28, end-to-end skeleton 17, SQLite store 14, webhook integration 20, worker 15.

**Not tested:** the real Meta API (send or receive), TLS, behaviour of several processes against one database under real load, very large queues, Windows file-locking edge cases beyond the two concurrency tests, crash recovery (not implemented).

## 11. Problems Found While Building

1. **Flaky test (mine).** The "full queue" test used `max_pending=1` and then expected a two-message batch to succeed on retry. Whether the first message had finished by the time the second was dispatched was a race, so 8 of 15 runs failed once. The code was right (a batch larger than the free capacity is partly accepted); the test asserted the wrong thing. It was rewritten as the real scenario (partial acceptance, then Meta's retry completes the batch with no double reply), and then 40 consecutive runs passed.
2. **A test pattern that was too broad.** The literal-secret check flagged the word `Bearer ` in the client's own header line and the variable *names* `WAZI_..._TOKEN`. It now looks for token-shaped literals and ignores names.
3. **Shell quoting.** A large heredoc failed and wrote nothing; the files were then created with the file tool. No partial state resulted.

## 12. Known Limitations

* **At most once after the ACK.** A crash between the 200 and the end of processing loses that reply; it stays `claimed` and is listed by `unfinished_keys()` but cannot be re-run because the content is not stored. A reply that fails after 3 attempts is `failed` and not resent. See ADR-004.
* **Retry sleeps hold a worker thread** (up to about 1.5 s with the defaults).
* **Single machine / single database file.** In-memory mode forgets on restart (a warning is logged).
* **Text only.** No media, templates, read receipts or typing indicator.
* **The 24-hour window** is not tracked. Replying to a message that just arrived is inside the window; a failure with code 131047 is permanent and recorded as `failed`.
* **Nothing is verified against the real Meta API:** send request shape, error codes and HTTP statuses, `Retry-After` behaviour, and (from Phase 4) the signature scheme. The first real test should use a Meta test number with a signature-checking path and very low volume.
* **Pricing is still unverified** (Phase 1 §6.3): do not send real traffic before checking Meta's rate card.

## 13. Lessons Learned

1. A "walking skeleton" is useful mostly because it forces every boundary to be real: the first end-to-end test immediately raised questions (what happens when the queue is full? what state is a message in after a restart?) that unit tests of each layer never asked.
2. **Acknowledge-first changes the failure model.** Once the webhook says 200, Meta will not retry, so the retry responsibility moves into our process. That is why retries, states and back-pressure exist, and why the remaining gap (crash recovery) is a real design decision, not a detail.
3. **Test the thing you think you are testing.** A queue-capacity test passed or failed depending on thread timing. Concurrency tests must control the timing (blocked senders, events), not hope.
4. **Libraries can mask what a mutation does.** My "log the headers" mutation survived because httpx hides `Authorization` in `repr`. Good to know, but the right response was a sharper mutation, not a weaker test.
5. **Enforce structure with tests.** Adding six modules was safe because `test_every_source_unit_is_covered_by_the_rules` fails if a new module is not given dependency rules.
6. **Privacy is easy to give up by accident.** A durable inbox would have made recovery easy and put user text on disk. Keeping only ids and states was a deliberate trade, written down in ADR-004.

## 14. Phase 6 Recommendation

Not started; for the mentor's decision.

* **Option A (recommended): Phase 2b / "first contact with reality".** Verify the assumptions this skeleton rests on: a Meta developer test number, a loopback or tunnelled endpoint behind the signature gate, one real send (cost and 24-hour rules checked first). It removes the "never exercised against real Meta" caveat for both the signature scheme and the send request.
* **Option B: Agent phase (roadmap Phases 5-6 content).** Replace `EchoResponder` with a first real `Responder`, with a reuse review of Ava's graph pattern and ArchAgenticRAG as ADR-002 requires. Open questions from Phase 3 §18 (provider layer, per-user memory scope, document scope) have to be answered first.
* **Option C: crash recovery / durable inbox**, only after a privacy decision on storing message content and its retention.

Decisions needed: which option; whether SQLite as the persistent store is accepted for now (it was chosen here as the standard-library default without a separate mentor decision); whether `v26.0` should stay the default Graph version; and whether ADR-004's "at most once after ACK" trade-off is acceptable.

I have not started any of them. Nothing from this phase has been committed or pushed.
