# ADR-004: Acknowledge first, process in-process, persist the claims (at-most-once after ACK)

- **Status:** Proposed (awaiting mentor review)
- **Date:** 2026-10-29
- **Phase:** 5
- **Related:** [ADR-003](003-layer-separation.md), [PHASE_5_SKELETON.md](../PHASE_5_SKELETON.md), [PHASE_4_FOUNDATION.md](../PHASE_4_FOUNDATION.md) §13

## WHAT

1. The webhook validates, normalises and **claims** a message id, hands the message to a background worker, and answers 200 immediately.
2. The worker runs in the same process (a bounded thread pool). It calls the responder, sends the reply with a small bounded retry loop, and records `done` or `failed` against the claim.
3. Claims live in a **SQLite file** (standard library), so duplicate detection survives restarts.
4. Delivery semantics after the ACK are **at most once, best effort**. The message content is not stored.

## WHY (evidence)

* Meta retries every non-200 response and documents that retries can duplicate notifications (WhatsApp webhooks page, fetched 2026-10-18). Ava ran everything inside the request and returned 500 on any error, which provokes exactly those retries.
* The expensive work (LLM, retrieval, sending) must not hold the webhook open; Phase 4 left a `MessageDispatcher` contract for this.
* A persistent claim is the smallest change that closes the Phase 4 limitation "duplicates are forgotten on restart". AleBrito (MIT) uses the same atomic-insert pattern.
* Storing message content would add personal data at rest and a retention/deletion obligation. That is a real decision and it was not asked for.

## ALTERNATIVES

| Alternative | Why not now |
|---|---|
| Process inside the request (Ava) | Slow requests, retries, duplicate replies |
| FastAPI `BackgroundTasks` | Tied to one request object; no queue limit; harder to test and to swap out |
| A queue/broker (Redis, Celery, RabbitMQ, SQS) | New infrastructure and dependencies for a learning skeleton; the dispatcher Protocol keeps this a later swap |
| Durable inbox (store the normalised message, re-process unfinished work at start-up) | Gives at-least-once and crash recovery, but stores user text and phone numbers at rest. Needs a retention and privacy decision first |
| Release the claim when sending fails, so Meta's retry re-runs it | Meta has already received 200; it will not retry. The release would only help if we answered 5xx, which would re-run the responder (later: the paid LLM) just to repeat a failed send |

## DECISION (proposed)

Adopt the design above for the walking skeleton.

* **Back-pressure:** at most `max_pending` messages queued or running (default 100). Beyond that `dispatch` raises, the webhook releases the claim and answers 5xx, so Meta retries later and memory stays bounded. A batch may therefore be *partly* accepted; the retry re-sends the whole batch and the already-claimed messages are skipped as duplicates (tested).
* **Send retries:** transient failures (network, 429, 5xx, a short documented list of Meta error codes) retry with exponential backoff (0.5 s, 1 s, up to 3 attempts, `Retry-After` honoured and capped). Permanent errors (bad token, outside the 24-hour window, invalid request) are not retried.
* **State:** `claimed` (accepted), `done`, `failed`. A key still `claimed` after a restart means the process died mid-flight; `SqliteIdempotencyStore.unfinished_keys()` lists them so the loss is visible.

## CONSEQUENCES

* Positive: fast ACKs, bounded memory, no duplicate replies across retries or restarts, no personal data added to disk, no new infrastructure.
* Negative / accepted risks:
  * a crash between ACK and reply loses that reply (visible, not recoverable);
  * a reply that still fails after the retries is dropped (`failed`);
  * the retry sleeps occupy a worker thread;
  * one SQLite file means one machine.
* Revisit when: replies become expensive (LLM), when losing a message is unacceptable (move to a durable inbox, after deciding retention), or when more than one machine is needed (shared store or broker behind the same Protocols).
