# Phase 6: Meta WhatsApp Integration

Status: **BLOCKED at the credential boundary.** Everything that can be done without a Meta account was done and tested; the real-Meta steps were **not** run and are **not** claimed. Date: **2026-10-29**.

Final result: **BLOCKED** (see §15). Nothing in this document describes behaviour observed from the real Meta platform, because no Meta app, test number, access token, app secret or public callback URL exists on this machine (checked: all eight candidate environment variables unset, no `.env` file, no tunnel tool installed).

The path this phase must eventually prove:

```
real WhatsApp user -> Meta Cloud API -> Wazi webhook -> signature -> normalise -> idempotency
  -> queue -> worker -> echo responder -> Wazi outbound client -> Meta Cloud API -> real WhatsApp user
```

---

## 1. Objective

Connect the existing, offline-tested walking skeleton to the real Meta WhatsApp Cloud API and prove the round trip with evidence, without adding any agent, LLM, RAG, memory, tools or deployment. Because the external prerequisites are missing, this phase delivered: (a) a fresh check of Meta's current documentation, (b) the minimal code changes that documentation required, (c) opt-in live tests and a simulation tool so the real run is a short, safe procedure, and (d) an exact runbook for what only the owner can do.

Phase 5 code was reused unchanged except where Meta's documentation required otherwise (§12). Starting state: `git status` clean at commit `528414a` (the owner's Phase 5 commit).

Two notes on the brief:
* It names `docs/adr/004-ack-first-design.md`. The file is `docs/adr/004-ack-then-process-with-persisted-claims.md`. Same decision (ACK first, at-most-once afterwards); only the name differs.
* It suggests `META_*` variable names but also says to inspect the existing configuration first. The project uses `WAZI_*` names consistently; they were kept (no rename, no duplicate set). Names are in §5.

## 2. Official Meta Documentation Checked

All fetched on **2026-10-29**. None of the pages shows a "last updated" date. Pages exist under both `/docs/whatsapp/...` and `/documentation/business-messaging/whatsapp/...`; the content seen was identical.

| URL (shortened) | Topic | Important conclusion |
|---|---|---|
| `developers.facebook.com/docs/graph-api/webhooks/getting-started` | Generic Graph webhooks: verification, signature, retries | GET parameters `hub.mode=subscribe`, `hub.challenge` (an int), `hub.verify_token`; respond with the challenge. `X-Hub-Signature-256: sha256=...`, "SHA256 signature using the payload and your app's App Secret". Valid, non-self-signed TLS certificate required. Retries "over the next 36 hours" |
| `.../whatsapp/webhooks/create-webhook-endpoint` | WhatsApp webhook endpoint | **New since 2026-10-18 checks:** "HMAC-SHA256 hash, calculated using the post body payload and your app secret as the secret key". GET valid: "respond with HTTP status 200 and the hub.challenge value"; otherwise "a 400-level HTTP status code, or anything other than status 200". POST: respond 200. "Webhook payloads can be up to 3 MB"; batches "a maximum of 1000 updates"; retries "for up to 7 days". Still **not stated**: that the signed bytes are the raw body; Unicode escaping; a response-time limit |
| `.../whatsapp/webhooks/overview` and `docs/whatsapp/cloud-api/guides/set-up-webhooks` | Webhook setup | Subscribe to the `messages` field in App Dashboard > WhatsApp > Configuration; permission `whatsapp_business_messaging`; "Make sure your app is in Live mode; some webhooks will not be sent if your app is in Dev mode"; duplicates possible after retries; IP list via AS32934 or mTLS |
| `.../whatsapp/webhooks/set-up-whatsapp-echo-bot` | Meta's test echo bot | Sample verification handler: `res.status(200).send(challenge)`, otherwise `403`. "`messages` test webhooks work in both modes" |
| `.../whatsapp/webhooks/reference/messages` (+ `unsupported`) | Inbound message shape | `from`, `id`, `timestamp` (string of Unix seconds), `type`, `text.body`; `unsupported` messages carry an `errors` array (code 131051) and `unsupported.type` |
| `docs/whatsapp/cloud-api/get-started` | Test number and first message | "a **test** business phone number is generated and registered for you automatically"; "Add a **To** phone number that will receive the test message"; the temporary token "expires quickly and is not suitable for development purposes"; replying triggers "a customer service window" of 24 hours. **Not stated:** test-number limits, recipient-list size or verification, the error for a non-listed recipient |
| `docs/whatsapp/access-tokens` | Tokens | System-user tokens are long-lived; scopes `business_management`, `whatsapp_business_messaging`, `whatsapp_business_management` |
| `docs/whatsapp/cloud-api/guides/send-messages` | Sending and the 24-hour window | `POST https://graph.facebook.com/<version>/<phone_number_id>/messages`, `Authorization: Bearer`, body with `messaging_product`, `recipient_type`, `to`, `type`, `text`; max 4096 characters; 2xx "only indicates that the API successfully accepted your request"; the window starts when the user messages and resets on each message; outside it "you can only send pre-approved template messages"; Click-to-WhatsApp entry points can give up to 7 days |
| `docs/whatsapp/cloud-api/support/error-codes` | Errors | Documented: 130429, 131047, 131056, 190, 131026, 131000, 131016, 133004, 80007, 2, 4 and more. **No HTTP statuses** for Cloud API codes. **131030 does not appear** on the page |
| `docs/whatsapp/pricing` (also `/documentation/.../pricing`) | Pricing | Per delivered message since 2025-07-01. Service messages were free from 2024-11-01; "pricing updates ... effective as of October 1, 2026": "one free tier of 1,000 delivered service messages per month" per business phone number, charged beyond it; a payment method must be on file by 2026-09-30 or "Meta will stop delivering service messages" for Solution Providers and directly integrated businesses. **Not stated:** whether test-number messages are billed |
| `docs/graph-api/changelog/versions` and `.../guides/versioning` | Graph versions | Latest **v26.0** (2026-07-29), expiry TBD; v25.0 expires 2028-07-29; v21.0 expires 2027-01-21; v20.0 expired 2026-09-24. A version is unusable two years after its successor's release; expired versions default "to the next oldest, usable version"; unversioned calls use the dashboard's configured version |

Fetching limits: these results were gathered by sub-agents that read the pages and quoted them; the pricing page text was partly a model summary (the agent said which parts), so pricing details beyond the quoted lines should be re-read by the owner before sending real traffic.

## 3. Current Graph API Version

* **Version used: `v26.0`** (the latest on Meta's changelog on 2026-10-29, released 2026-07-29; Meta's own send-message examples use it).
* Configured in one place: `DEFAULT_GRAPH_API_VERSION` in `src/wazi/configuration/settings.py`, overridable with `WAZI_GRAPH_API_VERSION`. The client builds the URL from this value only; no other source file contains a version string (the live tests import the same constant).
* Why selected: newest supported; v21.0 (Ava's) is scheduled for removal on 2027-01-21 and v20.0 and older have already expired. The Phase 5 default was already `v26.0`; it was re-verified, not just kept.
* Lifecycle risk: Meta's rule makes any version usable for two years after its successor, so v26.0 is safe until at least a v27 plus two years. Review each time Meta releases a version.

## 4. Meta Test Environment (what the owner must set up; none of it exists yet)

Per Meta's Get Started page (§2), the owner needs:

1. A Meta developer account and a **Meta app created with the "Connect with customers through WhatsApp" use case**, attached to a business portfolio.
2. The **test business phone number** that Meta generates automatically, and its **Phone Number ID** (shown in the API Setup panel).
3. A **temporary access token** from the dashboard (expires quickly) or, for anything longer, a **system-user token** with the three scopes in §2.
4. One or more **recipient phone numbers** added in the dashboard ("To"). Meta's pages do not state the limit, whether verification is required, or the error for a non-listed number; treat these as unknown until observed.
5. The app's **App Secret** (needed for signature verification). Meta's fetched pages do not say where to find it; in the dashboard it is conventionally under the app's basic settings: unverified here.
6. A **verify token**: any string chosen by the owner, entered in the dashboard and in Wazi's configuration.
7. A **public HTTPS callback URL with a valid, non-self-signed certificate** (Meta: "Self-signed certificates are not supported").

Test recipient model: free-form replies are only possible inside the 24-hour customer service window opened by the recipient's own message (§11). For the first contact Meta's own flow sends a `hello_world` template from the dashboard; whether it is mandatory is not stated.

## 5. Configuration

Variable names only (set them in the shell or a git-ignored `.env`; `.env.example` has empty placeholders):

| Variable | Secret? | Purpose |
|---|---|---|
| `WAZI_WHATSAPP_VERIFY_TOKEN` | yes | Value Meta sends as `hub.verify_token` |
| `WAZI_WHATSAPP_APP_SECRET` | yes | Key for `X-Hub-Signature-256` verification |
| `WAZI_WHATSAPP_ACCESS_TOKEN` | yes | Bearer token for sending |
| `WAZI_WHATSAPP_PHONE_NUMBER_ID` | no | Sending number id (digits) |
| `WAZI_GRAPH_API_VERSION` | no | Optional; default `v26.0` |
| `WAZI_IDEMPOTENCY_DB` | no | SQLite file for restart-safe duplicate detection |
| `WAZI_LOG_LEVEL` | no | Optional; used only by the server entry point; default `INFO` |
| `WAZI_LIVE_META`, `WAZI_LIVE_TEST_RECIPIENT` | no / personal | Only for the opt-in live tests (§13) |

Behaviour with missing configuration: no verify token => GET always 403; no app secret => POST always 503; either outbound variable missing => dry-run sender (nothing is sent). None of these can be bypassed (tests in §13).

## 6. Webhook Verification

```
Meta -> GET /webhook?hub.mode=subscribe&hub.verify_token=<T>&hub.challenge=<C>
Wazi -> configured token present?  mode == "subscribe"?  token equal (constant time)?  challenge sane?
     -> 200, body = C (text/plain)       otherwise 403 (or 400 for an unusable challenge after a correct token)
```

This matches Meta's documented behaviour ("respond with HTTP status 200 and the hub.challenge value"; any other status fails). The test handler in Meta's own sample answers `403` with an empty body on mismatch; Wazi answers `403` with a generic JSON error. Automated tests cover correct token, wrong token, missing token, missing mode, missing challenge, **unconfigured token (fail closed, no `None == None`)**, and the exact response bytes. **The real Meta handshake was not run** (BLOCKED).

## 7. Signature Verification

```
raw request bytes + App Secret -> HMAC-SHA256 -> "sha256=<hex>" -> constant-time compare with header
```

* Meta now states HMAC-SHA256 with the app secret explicitly (§2). It still does not state "raw bytes" or Unicode-escaping rules. Wazi signs/verifies the exact received bytes, which is the only construction immune to re-serialisation tricks; it also means any Unicode-escaping Meta applied before signing is irrelevant, because Wazi never re-encodes.
* Automated tests cover: correct signature accepted; modified body, wrong signature, missing header, wrong secret, malformed prefix/length/non-hex, empty secret all rejected; raw bytes vs re-serialised JSON both ways; and agreement with an independent public HMAC test vector.
* **Not verified against a real Meta delivery.** This is the single most important thing the first live run settles. If real signatures fail, the likely suspects are (in order) wrong App Secret (a different app's secret), a proxy altering the body, or the raw-bytes assumption.
* The dashboard's "Test" webhook button: whether its deliveries are signed is not stated by Meta.

## 8. Real End-to-End Flow

**Not executed (BLOCKED).** The intended flow, with where each step is logged (identifiers are 8-hex fingerprints, never phone numbers, texts or raw ids):

```
WhatsApp user sends "Hello Wazi"
 -> Meta POST /webhook (signed)                          [webhook] "webhook accepted accepted=1 ..."
 -> signature gate -> JSON -> normalise                  [webhook]
 -> claim in SQLite                                      [webhook] "message queued id=<fp of inbound wamid>"
 -> worker -> EchoResponder -> WhatsAppCloudClient       [worker]  "reply sent id=<same fp> sent_id=<fp of Meta's id for our reply> attempt=1"
 -> Meta POST /v26.0/<phone_number_id>/messages
 -> WhatsApp user receives "Wazi skeleton echo: Hello Wazi"
```

Note: the reply text is `Wazi skeleton echo: <text>` (Phase 5 behaviour), not the brief's example `Echo: <text>`. The responder was not changed because the brief also says to keep the existing echo responder and avoid unnecessary changes; changing the prefix is a one-line edit if wanted.

Traceability: one inbound message can be followed by the same `id=<fp>` in the webhook and worker lines; Meta's id for our reply appears as `sent_id`. A test asserts the two fingerprints match and that no raw id, phone number or text is logged.

What was run instead (clearly **simulated, not Meta**): a real uvicorn server on 127.0.0.1 with fake secrets and dry-run outbound, driven by `scripts/simulate_inbound.py`, which builds a Meta-shaped payload and signs it with the configured secret:

| Request | Result |
|---|---|
| no signature | HTTP 403 |
| body altered after signing | HTTP 403 |
| valid, new message id | HTTP 200, `accepted:1` (reply recorded by the dry-run sender) |
| same message id again | HTTP 200, `duplicates:1` |
| server stopped (exact PID) and restarted on the same database, same id | HTTP 200, `duplicates:1` |
| new id after the restart | HTTP 200, `accepted:1` |
| database afterwards | `[('wamid.SIMPHASE6DUPLICATE01','done'), ('wamid.SIM73D0E2DD135B4D1AA8F7','done')]` |
| script pointed at a non-loopback URL | refused without `--allow-remote` |

## 9. Duplicate Test

**Result for the real path: NOT RUN (BLOCKED).** Evidence available: the simulated run above and the automated tests (`duplicate delivery sends one reply`, `a duplicate after a restart is still a duplicate`, 5 repeated deliveries dispatched once). These prove Wazi's behaviour, not Meta's.

Procedure for the real test (without capturing or logging any real webhook body): after the first real inbound message has been handled, read its id from the database and replay it with a validly signed simulated delivery:

```bash
.venv/Scripts/python -c "import sqlite3;print(sqlite3.connect('wazi.db').execute('select key,state from claims').fetchall())"
WAZI_WHATSAPP_APP_SECRET=<same secret as the server> \
  .venv/Scripts/python scripts/simulate_inbound.py --url http://127.0.0.1:8099/webhook \
  --sender <your allowed number> --text "Hello Wazi" --message-id <wamid from the database>
```

Expected: HTTP 200 with `duplicates:1`, **no second WhatsApp message arrives**, the log shows no new `message queued` or `reply sent`.

## 10. Restart Test

**Result for the real path: NOT RUN (BLOCKED).** Simulated and automated evidence: §8 and `test_a_duplicate_after_a_restart_is_still_a_duplicate`. Real procedure: after the real round trip, stop the server (by its exact PID), start it again with the same `WAZI_IDEMPOTENCY_DB`, repeat the §9 replay; expect `duplicates:1` and no message. Known limitation (unchanged from Phase 5): a message ACKed but not finished when the process dies stays `claimed` and is not re-run.

## 11. 24-Hour Window

Verified from Meta's documentation (§2), **not observed**:

* A user message starts a 24-hour "customer service window"; each further user message resets it to 24 hours.
* Inside it, free-form messages including text are allowed. A reply to a message that has just arrived is always inside the window, which is the only kind of reply Wazi sends in this phase.
* Outside it, "you can only send pre-approved template messages"; a free-form send then fails with error **131047** ("More than 24 hours have passed since the recipient last replied"). Wazi classifies 131047 as permanent: not retried, recorded `failed`.
* Click-to-WhatsApp entry points can open a longer "free entry point" window (up to 7 days); irrelevant here.
* Opt-in: Meta says you may only message users who have opted in; a user who writes first has started the conversation.
* Does the test-number environment change this? **Not stated** by the pages read. Meta's own flow suggests the same window rules apply (the `hello_world` template starts the thread; replying opens the window).
* Template messages are **not required** for the echo flow and were **not built**. Needed later only for proactive messages or replies after 24 hours.

## 12. Changes Made in Phase 6 (what, why, which Meta requirement, alternatives, deferred)

| # | Change | Why / Meta requirement | Why this way | Alternatives considered | Deferred |
|---|---|---|---|---|---|
| 1 | Default body limit 1 MiB -> **4 MiB** (`settings.py`) | Meta: "Webhook payloads can be up to 3 MB". A 1 MiB cap would reject a legitimate large delivery with 413, and Meta would retry it for up to 7 days | Smallest change: one constant, 4 MiB gives headroom over 3 MB while still bounding memory; streaming read already enforces it without buffering more | Remove the limit (unsafe); make it exactly 3,000,000 (no margin) | Per-request memory profiling at the maximum size |
| 2 | Default queue capacity `max_pending` 100 -> **1000** (`settings.py`, `worker.py`) | Meta: batches have "a maximum of 1000 updates"; an idle service should accept one maximal batch | Matches the documented maximum; Phase 5's partial-acceptance behaviour is kept as the overflow safety net | Keep 100 (a legitimate 150-message batch would be partly rejected and retried) | Real load numbers |
| 3 | "message queued" log at INFO (was DEBUG) and "reply sent ... sent_id=" at INFO (`app.py`, `worker.py`) | Brief requires each message to be traceable through the layers; Meta's reply id is a safe diagnostic | Fingerprints only (8-hex SHA-256 prefix), same helper as before | Log raw ids (rejected: identifiers of users' messages) | Metrics, tracing backend |
| 4 | `bootstrap.build_server_app` + `configure_logging` | Nothing configured logging, so INFO lines would be invisible in a real run | Separate entry point so tests (which capture logs at DEBUG) are not affected; test proves `build_app` leaves logger config untouched | Configure inside `build_app` (would silently weaken log-leak tests); a dependency like structlog (unneeded) | Structured JSON logs |
| 5 | Live-test scaffold `tests/live/` + `live_meta` marker, deselected by default | Brief: live tests must be separate and never run automatically | Marker deselection in `pyproject.toml` plus an opt-in env flag plus skip without credentials; they override the offline network guard only for themselves | Putting live checks in the normal suite (rejected) | Running them (needs credentials) |
| 6 | `scripts/simulate_inbound.py` | Lets the owner test receive, reply, duplicate and restart paths with the real secret before a tunnel exists, and replay a real message id without capturing real bodies | Stdlib only; refuses non-loopback URLs without a flag; reads the secret from the environment, not argv | Capturing real webhook bodies to disk (rejected: personal data at rest) | n/a |
| 7 | Signature module documentation updated | Meta now says HMAC-SHA256 explicitly; raw bytes still unstated | Honest wording of what is documented vs inferred | n/a | Live confirmation |
| 8 | Tests for the above (`tests/test_meta_requirements.py`) | Protect each Meta-derived rule | One file, 11 tests | n/a | n/a |

**Not changed on purpose:** the thin `httpx` client (PyWa rejected again, §14), SQLite, the worker, the ACK-first design (ADR-004), the echo responder, the `WAZI_*` names, the HTTP status mapping, the retry classification. Meta's pages give no HTTP statuses for Cloud API errors, so the classification keeps keying on the documented error `code` plus generic HTTP rules; `131030`, which some tutorials mention for non-listed recipients, is not in Meta's current error table and is therefore treated as permanent by default. Nothing in Meta's documentation contradicted the Phase 5 outbound request shape.

## 13. Tests

| Item | Result |
|---|---|
| Unit/integration suite (`pytest`) | **264 passed**, 2 deselected, 1 warning (the known Starlette `httpx` notice), about 2 s; 15 consecutive full runs stable |
| `ruff check .` / `ruff format --check .` | passed / 54 files formatted |
| Per file | architecture 31, GET 16, idempotency 10, **Meta requirements 11 (new)**, normaliser 44, outbound client 43, security invariants 15, signature 28, end-to-end skeleton 17, SQLite store 14, webhook integration 20, worker 15 |
| Live Meta tests (`tests/live`, 2) | **Not run.** Verified only that they are inert: deselected by default; skipped with `-m live_meta` alone; skipped with `WAZI_LIVE_META=1` but no credentials; none can connect or send without all prerequisites. **They have never executed against Meta**, so they are unverified code |
| Simulated server run | §8 |

New automated tests (Meta-derived): a ~3 MB signed payload is accepted and a 5 MB one refused; a 1000-message batch is fully accepted and answered with 1000 replies; Meta's own documented example payload (copied verbatim from the reference page into `tests/fixtures/`) normalises and flows through the whole skeleton; exact handshake response bytes; an unsupported-type message with the documented `errors` array is acknowledged without a reply; cross-layer trace correlation without leaking identifiers; logging configuration is opt-in and idempotent.

To run the live tests later:

```bash
WAZI_LIVE_META=1 WAZI_WHATSAPP_ACCESS_TOKEN=... WAZI_WHATSAPP_PHONE_NUMBER_ID=... \
WAZI_LIVE_TEST_RECIPIENT=<your allowed number, digits> \
  .venv/Scripts/python -m pytest -m live_meta tests/live -v
```

The first test is read-only (checks the token and phone number id). The second **sends one real WhatsApp message**.

## 14. Security

* **Secrets:** read only from the environment; `.env` is git-ignored; `.env.example` holds names with empty values; the access token is only referenced in `configuration/settings.py`, `bootstrap.py`, `outbound/client.py` (test-enforced); secret fields are excluded from `repr`.
* **Signature:** fail closed, constant time, raw bytes, before any parsing; 403 for every authentication failure.
* **Token redaction:** the token appears only in the Authorization header; never in errors, `repr`, responses or logs (mutation-tested in Phase 5; `httpx` additionally masks it in its own `repr`).
* **Phone numbers and messages:** not logged; identifiers appear only as 8-hex fingerprints; `NormalizedMessage`/`OutboundReply` hide them in `repr`; the SQLite file holds only message ids, states and timestamps.
* **Simulation tool:** reads the secret from the environment (not argv), refuses non-loopback URLs by default.
* **Exposure rule for the live run:** do not expose the webhook before it runs with real secrets set (so signature and verify-token checks are active) and with the server access log disabled (`--no-access-log`), because the GET handshake carries the verify token in the URL. A tunnel is a temporary development aid and is not added to the project.
* **Not addressed (unchanged limits):** no rate limiting; no replay window beyond message-id de-duplication; no mTLS or IP allow-listing (Meta documents both as options); the temporary access token is a bearer secret that expires quickly.

Dependency note (re-audit): no dependency was added or changed in Phase 6.

## 15. Reuse Audit (fresh, 2026-10-29)

| Source | License | State | Decision |
|---|---|---|---|
| Wazi Phase 5 foundation | project | tested, 253 tests at the start | **REUSE** unchanged except §12 |
| Meta's official documentation and its documented example payload | n/a | authoritative | **REUSE** as the specification and as a test fixture |
| pywa | MIT | 4.5.0 (2026-09-24), pushed 2026-10-26 | **REJECT as dependency** again: a full framework that hides the protocol this project is meant to teach; Wazi already has a tested thin client; the brief also says not to introduce it |
| AleBrito `whatsapp-ai-agent` | MIT | pushed 2026-09-23, unchanged | **REFERENCE** (patterns already adapted in Phases 4-5) |
| Meta's sample repos `WhatsApp/WhatsApp-Nodejs-SDK`, `fbsamples/graph-api-webhooks-samples` | NOASSERTION | both archived (2023-06, 2025-02) | **REFERENCE** only |
| Ava | MIT | not changed since 2025-10-20 | **REFERENCE** only (its `v21.0` is scheduled for removal 2027-01-21) |
| GitHub search for newer webhook/signature samples | n/a | two queries returned nothing relevant | nothing to adopt |

Conclusion: the thin-client design is preserved; no fresh evidence argues for a framework.

## 16. Failure Behaviour (observed = by automated tests or the simulated run; "live" = real Meta, none observed)

| # | Case | Behaviour | Observed |
|---|---|---|---|
| A | Invalid signature | 403 `{"error":"forbidden"}`, nothing dispatched | tests + simulated run |
| B | Invalid verify token | 403 | tests |
| C | Malformed payload | 400 `invalid_payload`; broken single item skipped and counted, still 200 | tests |
| D | Duplicate webhook | 200, `duplicates:n`, no second reply | tests + simulated run |
| E | Meta outbound 4xx | permanent unless the code is in the retryable list; recorded `failed`; webhook already ACKed | tests (mock transport); **live: not observed** |
| F | Meta outbound 5xx / 429 | retried up to 3 attempts with backoff (`Retry-After` honoured, capped) then `failed` | tests; **live: not observed** |
| G | Expired/invalid token (190) | permanent, `failed`, no retry | tests; live: not observed. Operationally: replace the token, restart |
| H | Outside the 24-hour window (131047) | permanent, `failed` | tests; live: not observed |
| I | Wazi restart | claims survive in SQLite; unfinished work is not re-run | tests + simulated run |
| J | Queue full | `DispatchRejected` -> 5xx, claim released, Meta retries; a batch can be partly accepted | tests |
| K | Worker failure | logged by exception type, marked `failed`, the thread survives | tests |

## 17. Runbook for the Live Run (what the owner does, then what is verified)

1. **Meta side** (§4): create the app, note Phone Number ID, create a token, add your own number as a recipient, find the App Secret, choose a verify token.
2. **Local config** (shell, not committed): set the six `WAZI_*` variables from §5, `WAZI_IDEMPOTENCY_DB=wazi.db`.
3. **Pre-flight, no internet exposure:** `pytest -q` (expect 264 passed); `pytest -m live_meta tests/live` with `WAZI_LIVE_META=1` (the first test is read-only; the second sends one real message to your recipient).
4. **Start the server:** `uvicorn --factory wazi.bootstrap:build_server_app --host 127.0.0.1 --port 8099 --no-access-log`.
5. **Local simulated round trip with the real token:** `simulate_inbound.py --sender <your number>`: you should receive one echo on WhatsApp (this proves outbound and the whole worker path; it does *not* prove Meta's inbound).
6. **Temporary tunnel** (not installed here; not part of the project): any tool that gives an HTTPS URL with a valid certificate, such as a Cloudflare quick tunnel or ngrok, pointing at `http://127.0.0.1:8099`. Not verified in this phase; follow that tool's own documentation and keep it running only during the test.
7. **Configure the webhook** in the dashboard (WhatsApp > Configuration): callback URL `https://<tunnel>/webhook`, your verify token, then **subscribe to the `messages` field**. Watch the server log for `webhook verification succeeded`.
8. **Real inbound:** from your allowed number, message the test number (if the window is not open yet, send Meta's `hello_world` template from the dashboard first, then reply). Expect the log lines in §8 and the echo on your phone.
9. **Duplicate and restart tests:** §9 and §10.
10. **Stop** the server and the tunnel. Revoke or let the temporary token expire.

Costs and rules to check first: service messages beyond 1,000 delivered per month per business phone number are charged since 2026-10-01 and Meta requires a payment method on file; whether the test number is billed is not stated. Do not send real traffic before reading Meta's current rate card.

## 18. Known Limitations

* **No real Meta evidence exists yet** for: the GET handshake, POST signatures, inbound delivery, outbound send, the 24-hour window, real error codes and HTTP statuses.
* Phase 5 limits stand: ACK first and **at-most-once afterwards** (a crash between ACK and reply loses that reply; a send failing after 3 attempts is dropped as `failed`); SQLite is single-machine; the queue is in-process and not durable; there is no production deployment.
* Meta's retry period is documented inconsistently (36 hours on the generic page, 7 days on the WhatsApp pages); the idempotency TTL covers 7 days.
* Meta's pages do not state a webhook response-time limit; the ACK-first design keeps responses fast regardless.
* Pricing details came from a partly summarised page; re-read it before real traffic.
* The echo text is `Wazi skeleton echo: ...`.

## 19. Phase 6 GO / NO-GO

| Criterion | Status | Evidence |
|---|---|---|
| Current Meta API verified | **PASS (documentation only)** | §2: pages fetched 2026-10-29; v26.0 latest; limits and pricing change found; items Meta does not state are listed |
| GET webhook verification | **BLOCKED (real); unit-tested** | No callback URL or Meta app; 16 + 1 automated tests incl. unconfigured token fail-closed |
| POST signature verification | **BLOCKED (real); unit-tested** | No app secret; 28 signature tests, vector test, raw-bytes tests; never run against a real Meta signature |
| Real inbound message | **BLOCKED** | No Meta app, test number, recipient or tunnel; not attempted |
| Real outbound message | **BLOCKED** | No access token or phone number id; live tests written but never executed |
| Duplicate protection | **PASS (simulated/automated); real BLOCKED** | §8 and §9 |
| Restart persistence | **PASS (simulated/automated); real BLOCKED** | §8 and §10, SQLite state shown |
| Secrets protected | **PASS** | §14; token/secret/recipient/text leak tests; no credential exists on disk |
| Existing tests pass | **PASS** | 264 passed, 2 deselected; lint and format clean |

**Final result: BLOCKED.** Not PASS, because the phase's single success criterion, a real WhatsApp message travelling through Meta and back, was not demonstrated. Not FAIL, because nothing attempted failed and no assumption was contradicted by Meta. Unblocking needs the items in §4 and the runbook in §17.

## 20. Lessons Learned

1. **Documentation moves.** In eleven days Meta's pages gained an explicit "HMAC-SHA256" statement, pricing changed on 2026-10-01, and two numeric limits (3 MB, 1000 updates) turned out to contradict Phase 4/5 defaults I had picked without checking. Defaults that guard against Meta's behaviour should cite Meta's numbers.
2. **A limit that is too strict is a bug that looks like security.** A 1 MiB cap would have turned a rare large but legitimate delivery into a week of retries.
3. **Be explicit about what a simulation proves.** The simulated duplicate and restart runs prove Wazi; only real traffic proves Meta.
4. **Make the real run a short procedure.** The opt-in live tests, the simulation tool and the runbook exist so that the blocked step costs minutes, not a debugging session.
5. **Observability needs a switch that is actually on.** Good log lines are useless if nothing configures logging; the fix needed care so that it did not weaken the tests that capture logs.
6. **Say BLOCKED.** The brief allows it, and an honest BLOCKED with a working preparation beats a PASS built on mocks.

## 21. Recommended Next Step

Not started. The logical next step is to **unblock Phase 6**: the owner completes §4 and §17, and the same phase is finished with the live evidence (handshake, signature, round trip, duplicate, restart, the 24-hour behaviour, real error shapes). Only after that does an agent phase (replace `EchoResponder` behind `ports.Responder`, after the open design questions in Phase 3 §18) make sense, because its failure modes will then be built on observed Meta behaviour instead of documentation.
