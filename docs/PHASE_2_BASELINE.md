# Phase 2: Reproduce & Validate Existing Agent

Status: **BLOCKED** (external credentials and Docker daemon unavailable), with several confirmed **FAIL** findings. Awaiting mentor review.
Date of all observations: **2026-10-18**. Machine: Windows 11 Pro, Python 3.12.10, uv 0.12.15, Docker Desktop 29.5.3 (client only responsive).

Governing documents read before starting: [PROJECT_CONSTITUTION.md](PROJECT_CONSTITUTION.md) and [REUSE_AUDIT.md](REUSE_AUDIT.md). No conflict with this phase's instructions was found. Two notes are in §21.

---

## 1. Objective

Answer one question: **can the existing Ava WhatsApp agent be reproduced and run as-is, without changing its architecture?** The result is a baseline that separates (1) problems already in Ava, (2) problems caused by dependency/provider drift since Ava was published, and (3) problems that our future Wazi changes might cause.

Rules followed: no Ava source file was edited, no fix was applied, no ArchAgenticRAG code was copied, imported or modified, no real credentials were used, nothing was exposed to the internet.

## 2. Repository Information

| Item | Value (verified 2026-10-18 by `git clone` and `gh api`) |
|---|---|
| Name / owner | `ava-whatsapp-agent-course` / `neural-maze` (The Neural Maze) |
| URL | https://github.com/neural-maze/ava-whatsapp-agent-course |
| Default branch | `main` |
| **Commit tested** | `338fd6870df9097165fceb3bbfc3cb0c95e584cd` (short `338fd68`) |
| Commit date / message | 2025-10-20, "Create run.bat" |
| Repository state | Not archived. No releases. About 12 months without a push. Open PRs (not merged) are about provider defaults and logging (#40, #43, #49, #50) |
| Local copy | `D:\WORK_SPACE\Wazi-baselines\ava` (outside the Wazi repo on purpose, so Ava is never mixed into Wazi's history) |
| Python required | `>=3.12` (`pyproject.toml`, `.python-version` = 3.12; docs say 3.12.8). Tested with 3.12.10 |

## 3. License Verification

`LICENSE` read from the clone: **MIT License, Copyright (c) 2024 The Neural Maze.** Permits use, copy, modification and redistribution provided the copyright and licence notice are kept. Status: SAFE TO REUSE for Ava's own code. The licences of its many transitive dependencies (for example `torch`, `chainlit`, `elevenlabs`) were **not** audited in this phase.

## 4. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.12.10 |
| Package manager | uv 0.12.15 |
| Docker | Docker Desktop 29.5.3 installed; client works; **daemon never became responsive** (§8) |
| Env A ("documented path") | `D:\WORK_SPACE\Wazi-baselines\ava\.venv`, created with `uv venv` then `uv pip install -e .` exactly as `docs/GETTING_STARTED.md` says. **Ignores `uv.lock`.** |
| Env B ("locked path") | `D:\WORK_SPACE\Wazi-baselines\ava-venv-locked`, created with `uv sync --frozen` (the same command the project's `Dockerfile` runs), then Ava added on `PYTHONPATH=src` |
| Credentials | None available. All eight variables (GROQ, ELEVENLABS ×2, TOGETHER, QDRANT ×2, WHATSAPP ×3) were unset in the environment. **No `.env` file was created.** Probes used obviously fake placeholder values |

## 5. Prerequisites (from the original instructions)

| Need | Source | Status here |
|---|---|---|
| Python 3.12, uv | README / GETTING_STARTED | Available |
| Docker + Docker Compose | `make ava-run` / `.\run.ps1 ava-run` | Docker daemon not reachable (BLOCKED) |
| `.env` with 3 WhatsApp variables | `.env.example` | Not available. Docs say they can be left empty for the first run |
| Groq API key | `settings.py` (required field) | Not available |
| ElevenLabs API key + voice id | `settings.py` (required fields) | Not available |
| Together AI API key | `settings.py` (required field) | Not available |
| `QDRANT_URL` (+ key) | `settings.py`; compose sets it to the local container | Not available (no container) |
| Meta WhatsApp Cloud API app, phone number id, token, verify token | `whatsapp_response.py` | Not available |

**Important finding:** `Settings` (`settings.py`) declares `GROQ_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `TOGETHER_API_KEY` and `QDRANT_URL` with no defaults. The application will not even start without **all** of them, including the image generation (Together) and voice (ElevenLabs) keys, even if you only want text chat. That means four third-party accounts are needed to run the unchanged project. Whether each has a usable free tier today was **not verified** (see §15 and the Together result).

## 6. Architecture (verified from source)

The assumed diagram in the task prompt mentioned PyWa. **Ava does not use PyWa.** `pyproject.toml` has no `pywa`; the WhatsApp calls are hand-written `httpx` calls to `graph.facebook.com`. The actual architecture:

```
WhatsApp user
   |
Meta WhatsApp Cloud API   --POST/GET-->   FastAPI route /whatsapp_response
                                              (interfaces/whatsapp/whatsapp_response.py)
                                              |  downloads media (httpx, Graph v21.0)
                                              |  audio -> Groq Whisper (STT)   image -> Groq vision (ITT)
                                              v
                              LangGraph StateGraph "graph_builder"  (graph/graph.py)
                              compiled per request with AsyncSqliteSaver checkpointer
                              thread_id = sender phone number
                                              |
   memory_extraction_node -> router_node -> context_injection_node -> memory_injection_node
        |  (Groq LLM + Qdrant)   (Groq LLM)    (hard-coded schedule)   (Qdrant search)
        v
   conversation_node | image_node (Together FLUX) | audio_node (ElevenLabs TTS)   [Groq LLM]
        |
   (optional) summarize_conversation_node when > 20 messages
                                              |
                              send_response() -> Graph API /messages (+ /media upload)
```

A second front end, Chainlit (`interfaces/chainlit/app.py`), calls the same graph for local chat.

### Component table

| Component | File : symbol | Responsibility | External dependency | Config |
|---|---|---|---|---|
| Webhook route | `interfaces/whatsapp/whatsapp_response.py` : `whatsapp_handler` | GET verify; POST parse (text/audio/image/statuses); run graph; send reply | Meta Graph API v21.0 | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN` |
| App entry | `interfaces/whatsapp/webhook_endpoint.py` : `app` | `FastAPI()` plus the router; run by `fastapi run` in the Dockerfile on port 8080 | FastAPI | n/a |
| Media in | same file : `download_media`, `process_audio_message` | Fetch media by id with bearer token | Graph API | `WHATSAPP_TOKEN` |
| Send | same file : `send_response`, `upload_media` | Send text, or upload then send audio/image | Graph API | same |
| Graph | `graph/graph.py` : `create_workflow_graph` | Wires 8 nodes and conditional edges | LangGraph | n/a |
| State | `graph/state.py` : `AICompanionState` | Messages, summary, workflow, audio/image, activity, memory_context | LangGraph | n/a |
| Nodes | `graph/nodes.py` | Router, conversation, image, audio, summarise, memory extract/inject | Groq, Together, ElevenLabs, Qdrant | `settings.py` |
| Router | `graph/utils/chains.py` : `get_router_chain` | LLM chooses reply modality: `conversation`, `image` or `audio` (structured output) | Groq | `TEXT_MODEL_NAME` |
| Edges | `graph/edges.py` | Pick node by workflow; summarise when > 20 messages | n/a | `TOTAL_MESSAGES_SUMMARY_TRIGGER` |
| Long-term memory | `modules/memory/long_term/memory_manager.py`, `vector_store.py` | LLM decides if a user message is memory-worthy; store in Qdrant; retrieve top-3 | Groq, Qdrant, sentence-transformers `all-MiniLM-L6-v2` | `QDRANT_URL`, `QDRANT_API_KEY`, `MEMORY_TOP_K`, `SMALL_TEXT_MODEL_NAME` |
| Short-term memory | `whatsapp_response.py` (`AsyncSqliteSaver`), Chainlit app | LangGraph checkpoint per phone number in SQLite | `langgraph-checkpoint-sqlite` | `SHORT_TERM_MEMORY_DB_PATH` (`/app/data/memory.db`) |
| STT / TTS / ITT / TTI | `modules/speech/*`, `modules/image/*` | Whisper, ElevenLabs, Groq vision, Together FLUX | Groq, ElevenLabs, Together | model names in `settings.py` |
| Persona | `core/prompts.py`, `core/schedules.py`, `modules/schedules/context_generation.py` | "Ava" character card and a weekday schedule | none | n/a |
| Deployment | `Dockerfile`, `Dockerfile.chainlit`, `docker-compose.yml`, `cloudbuild.yaml` | Compose services `qdrant`, `chainlit` (8000), `whatsapp` (8080) | Docker | `.env` |

The graph's nodes and edges were also extracted by compiling it (§9): 10 nodes including `__start__`/`__end__`, matching the code.

## 7. Actual Message Flow (inbound text message)

1. Meta POSTs JSON to `/whatsapp_response`. There is no signature check; the handler reads `entry[0].changes[0].value`.
2. If `messages` is present it takes `messages[0]` only, `session_id = from`. If the type is audio or image it downloads the media and calls Groq; **any other type, including text, goes to `message["text"]["body"]`** (line 67).
3. Opens the SQLite checkpointer, compiles the graph (every request), `ainvoke`s with the user's text.
4. Graph: `memory_extraction_node` (Groq call to classify; if memory-worthy, embeds locally and upserts to Qdrant) → `router_node` (Groq call) → context injection → `memory_injection_node` (Qdrant search) → one response node (Groq call) → maybe summarise.
5. Handler reads the last message and workflow from state, calls `send_response`, which `print`s the request headers and body (§14), then POSTs to Graph API.
6. Returns 200, or 500 on any exception.

All of this runs **inside the webhook request**. A message costs at least 3 sequential Groq calls (classify memory, route, reply), so WhatsApp timeouts and retries are a realistic risk. This was inferred from the code, not measured.

## 8. Run Procedure

### 8.1 What the original instructions say

`docs/GETTING_STARTED.md`: clone → `uv venv .venv` → `uv pip install -e .` → create `.env` with keys → `make ava-run` (Linux/macOS) or `.\run.ps1 ava-run` (Windows) → open Chainlit at `localhost:8000`. `ava-run` is `docker compose up --build -d`, which builds images with `uv sync --frozen` (lockfile).

### 8.2 What was actually done

| Step | Command (summary) | Result |
|---|---|---|
| Obtain | `git clone` into `Wazi-baselines/ava`, no edits | Done, commit `338fd68` |
| Documented install (Env A) | `uv venv .venv`; `uv pip install -e .` | Exit 0 (installs). Resolved to langchain 1.2.18, langgraph 1.1.10, qdrant-client 1.19.1, chainlit 2.11.1 |
| Locked install (Env B) | `uv sync --frozen --no-install-project` into an external venv | Exit 0. langchain 0.3.13, langgraph 0.2.60, qdrant-client 1.13.0, chainlit 1.3.2 |
| `.env` / `make ava-run` | not executed | **BLOCKED**: no credentials; and the Docker daemon never answered |
| Docker | Started Docker Desktop (processes `com.docker.backend`, `Docker Desktop` were running); `docker ps` and `docker info` hung and were killed after 20–30 s, repeatedly over several minutes | **BLOCKED**: daemon unresponsive. Cause not diagnosed (could be WSL/virtualisation/first-run prompt); not investigated further because compose also needs the missing keys |
| Local probes | Python scripts in the session scratchpad (outside Ava and Wazi), using fake env values and FastAPI `TestClient` (in-process, no listening socket, no public exposure) | Results in §9 |

The real server process (`fastapi run ...:8080`) and the Chainlit server were **not started**. The webhook was exercised in-process only.

## 9. Validation Results

PASS / FAIL / BLOCKED / NOT TESTED only.

| Area | Result | Evidence | Notes |
|---|---|---|---|
| Repository obtained | **PASS** | `git rev-parse HEAD` = `338fd68…`; `git status` shows 0 tracked-file modifications | Untracked `.chainlit/translations/*.json` appeared after importing Chainlit (auto-generated by the library; see §20) |
| Dependencies installed: documented path (`uv pip install -e .`) | **PASS** (installs) | exit 0 | But it ignores `uv.lock` and produces a broken environment (next rows) |
| Dependencies installed: locked path (`uv sync --frozen`) | **PASS** | exit 0; versions listed in §15 | This is the path the Dockerfile uses |
| Application import/startup, documented-path env (Env A) | **FAIL** | 9 of 15 modules fail to import. `ModuleNotFoundError: No module named 'langchain.prompts'` (from `modules/image/text_to_image.py:9`) breaks `graph`, `nodes`, `chains`, `helpers`, `whatsapp_response`, `webhook_endpoint`. Chainlit app: `RuntimeError: Unable to apply constraint 'host_required' to schema of type 'function-wrap'` | Root cause: `pyproject.toml` has `langchain>=0.3.13` with no upper bound (resolves to 1.x) and `pydantic==2.10.0` pinned against a new Chainlit |
| Application import/startup, locked env (Env B) | **PASS** | all 15 modules import OK, including the FastAPI app and Chainlit app | With fake env values. Real `fastapi run` server **NOT TESTED** |
| Docker | **BLOCKED** | `docker ps` hangs (rc 124) after Docker Desktop was started | Environment issue; `docker-compose.yml` was read, never executed |
| LangGraph | **PASS** (build) / **BLOCKED** (execution) | `graph_builder.compile()` succeeds in Env B; 10 nodes, 14 edges extracted | Execution needs a Groq key |
| LLM | **BLOCKED** | Request reached `memory_extraction_node` and failed with `groq.AuthenticationError 401 Invalid API Key` using a fake key | Proves the call path and that the Groq endpoint answers; says nothing about model availability. Default models are past Groq's documented shutdown dates (§11) |
| Qdrant | **BLOCKED** | No server (Docker down). `QdrantClient.get_collections()` → `ResponseHandlingException` | Client library compatibility is separately shown in §12 |
| Embedding model | **PASS** | `SentenceTransformer("all-MiniLM-L6-v2")` loaded; `encode()` returns dimension 384; model cached under the HF hub cache | Download needs no credentials |
| Memory (short-term, SQLite checkpointer) | **NOT TESTED** | Code path is reached only after LLM calls succeed | |
| Memory (long-term, Qdrant) | **BLOCKED** | Needs Groq (to classify) and Qdrant | |
| RAG over documents | **NOT TESTED** | Feature does not exist in Ava: no ingestion, chunking or document retrieval in the source tree | Only vector *memory* exists (§12) |
| Webhook GET verification | **PASS** | Correct token → 200 and echoes challenge; wrong or missing token → 403 | Also see edge case in §14 |
| Webhook POST signature validation | **FAIL (SECURITY GAP)** | Statuses payload with no signature header → 200; with bogus `X-Hub-Signature-256` → 200. No `hmac`/`signature` anywhere in the repo | Not fixed |
| Webhook POST error handling | **FAIL** | Malformed JSON, missing `entry`, and a `location` message each return 500 (`KeyError`), which makes Meta retry | Not fixed |
| Webhook duplicate/idempotency | **FAIL** | No message-id tracking in code; the same location message delivered twice gave two identical 500 responses (and the code has no dedup logic) | Not fixed |
| WhatsApp Cloud API (external) | **BLOCKED** | No Meta app/token | See §10 |
| Message receive (parse and dispatch to graph) | **PASS** | A text-message payload was accepted, parsed, and dispatched into the graph (reached `memory_extraction_node`) | The reply then failed at the LLM step |
| Agent response | **BLOCKED** | Needs Groq (and Qdrant) | |
| Message send | **BLOCKED** | `send_response` builds the request correctly; the outgoing call was intercepted in the probe, nothing sent | No Meta credentials |
| Repo lint (`ruff check .`, repo's own `lint-check`) | **FAIL** | `ruff 0.17.1` (latest, not pinned by repo) reports 20 errors, 13 auto-fixable | Not fixed. Ruff version differs from what authors used |
| Repo tests | **NOT TESTED** | There is no `tests/` directory, no pytest configuration and no test dependency | Nothing to run. Confirmed from the tree |

## 10. WhatsApp Validation

**WhatsApp external validation = BLOCKED.**

Required to proceed: a Meta developer app with the WhatsApp product, a phone number id, an access token, and a verify token of our choosing; a public HTTPS URL that Meta can reach (a tunnel or a host); and — because Ava has no signature check — a decision about how to protect that URL. Do not expose Ava's current webhook publicly.

What was validated locally without the internet: GET handshake behaviour, POST routing for `statuses`, unknown events, malformed input, a non-text message, and a text message path (§9).

Other WhatsApp facts, verified from code and an official-source search:

- Ava hard-codes **Graph API v21.0** in four URLs. A web search returned Meta's 2026-07-29 announcement that v21.0 is removed on **2027-01-21**; Meta's own version-changelog page still showed "TBD". Meta also says calls to an unusable version fall back to the next available version. Treat as: works now, scheduled for removal, and also a v26.0 change set was announced for all versions on 2026-10-27. Not tested against the live API.
- WhatsApp pricing remains **UNVERIFIED** (see REUSE_AUDIT §6.3).

## 11. LLM Validation

| Item | Value (from `settings.py`, `helpers.py`, modules) |
|---|---|
| Provider | Groq (chat, router, memory classifier, summariser, Whisper STT, vision). Together AI (image generation). ElevenLabs (text to speech) |
| SDK | `langchain-groq` (`ChatGroq`), `groq`, `together`, `elevenlabs` |
| Chat model | `llama-3.3-70b-versatile` (`TEXT_MODEL_NAME`) |
| Small model | `gemma2-9b-it` (`SMALL_TEXT_MODEL_NAME`, memory classifier) |
| STT | `whisper-large-v3-turbo` (also hard-coded in `speech_to_text.py`) |
| Vision | `llama-3.2-90b-vision-preview` (`ITT_MODEL_NAME`) |
| Image gen | `black-forest-labs/FLUX.1-schnell-Free` (Together) |
| TTS | `eleven_flash_v2_5` (ElevenLabs) |
| Env vars | `GROQ_API_KEY`, `TOGETHER_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` |
| Live compatibility | **Not tested** (no keys). The one live call returned 401 for a fake key, so the endpoint is up |

### PROVIDER DRIFT (from Groq's official deprecations page, fetched 2026-10-18)

| Model Ava uses | Groq page says | Ava's default |
|---|---|---|
| `gemma2-9b-it` | Listed, date **10/08/25**, replacement `llama-3.1-8b-instant` | Memory classifier: **deprecated** |
| `llama-3.2-90b-vision-preview` | Listed in the **04/14/25** deprecation batch, replacement `meta-llama/llama-4-scout-17b-16e-instruct` | Vision: **deprecated** |
| `llama-3.3-70b-versatile` | Listed, date **08/16/26**, replacement `openai/gpt-oss-120b` or `qwen/qwen3.6-27b` | Main chat model: **past its shutdown date** |
| `whisper-large-v3-turbo` | Not listed as deprecated (appears as a replacement for another model) | STT: no drift found |

The page does not itself say "already shut down"; that conclusion is inferred from the dates being before today. Groq states that after a shutdown date requests to those model IDs return errors. **This was not confirmed with a live call**, because no key was available.

Together's `FLUX.1-schnell-Free`: Ava's own open PR #40 says Together terminated the free tier. A web search found no official Together notice either way, and only the original "3 months free" launch post (Oct 2024). Status: **likely unavailable, UNVERIFIED**.

Per instructions nothing was replaced. Status: PROVIDER DRIFT recorded; NOT FIXED, intentionally preserved. Suggested future phase: provider modernisation.

## 12. Qdrant / RAG Validation

What Ava does (read from code):

- **No document RAG.** No ingestion, chunking, reranking, or citations exist.
- **Vector memory only.** `VectorStore` uses `sentence-transformers` `all-MiniLM-L6-v2` (384 dimensions, cosine). Collection `long_term_memory` is created on first write. `store_memory` upserts a point whose id is the existing memory id if a similar one (score ≥ 0.9) exists. `search_memories` fetches the top `MEMORY_TOP_K` (3) by similarity of the last three messages joined together. Memories are written only after an LLM (`with_structured_output(MemoryAnalysis)`) judges a user message "important".
- **One global collection**, no per-user filter or payload key: every WhatsApp sender's memories land in the same `long_term_memory` collection and `search_memories` has no user filter, so users can retrieve each other's remembered facts. This is a privacy gap found in code reading; not exercised at runtime.
- Qdrant connection: `QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)`.

Runtime state: Qdrant server **BLOCKED** (Docker daemon). Embedding model **PASS**.

Library drift on this path (`vector_store.py:134` calls `self.client.search(...)`):

| Environment | qdrant-client | `QdrantClient.search` present? |
|---|---|---|
| Env A (documented, unlocked) | 1.19.1 | **No** (removed; only `query_points` remains) |
| Env B (locked) | 1.13.0 | Yes |

So in an unlocked install long-term memory retrieval would break even if Qdrant were running. Not fixed.

## 13. Memory Validation

| Memory | Mechanism | Verified how | Result |
|---|---|---|---|
| Short-term | LangGraph `AsyncSqliteSaver`, `thread_id` = sender phone, DB at `SHORT_TERM_MEMORY_DB_PATH` (`/app/data/memory.db` by default, which is a Linux path; on Windows it must be overridden) | Code read; checkpointer opened in the request path | NOT TESTED at runtime |
| Summary | After > 20 messages, an LLM summary replaces older messages (keeps 5) | Code read (`edges.py`, `nodes.py`) | NOT TESTED |
| Long-term | Qdrant facts, global (not per user) | Code read, embedding model run | BLOCKED |

Note: the Chainlit front end hard-codes `thread_id = 1`, so all browser sessions share one conversation. Code read only.

## 14. Webhook Security Review

All items tested in-process with `TestClient` and fake values, except where marked "code".

| Check | Finding | Rating |
|---|---|---|
| Endpoint | `GET/POST /whatsapp_response` | n/a |
| GET verification | `params.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN")`; correct token → 200 and challenge echoed. `hub.mode` is not checked | PASS |
| GET edge case | If `WHATSAPP_VERIFY_TOKEN` is **unset**, a GET with **no** token returned **200** and the challenge (None == None). An empty token string correctly gave 403 | FAIL (minor, config-dependent) |
| POST signature (`X-Hub-Signature-256`) | Not implemented. A POST with no header, and with a bogus header, was accepted (200) | **FAIL / SECURITY GAP** |
| Authentication/authorisation | None. Any caller who knows the URL can inject a message "from" any phone number and trigger LLM spend and memory writes | **FAIL / SECURITY GAP** |
| Message parsing | Only `entry[0].changes[0].value.messages[0]`; additional messages in a batch are ignored (code). Non-text, non-audio, non-image types hit `message["text"]["body"]` → `KeyError` → 500 (tested with `location`) | FAIL |
| Idempotency | None. Meta retries on non-200; the handler returns 500 for any error, so failures invite retries and duplicate side effects | FAIL |
| Error handling | Catch-all returns 500 with a generic body; stack trace logged (tested) | PARTIAL |
| Response handling | Everything runs inline in the request; replies sent from the same call | Risk (code) |
| **Credential leak in logs** | `send_response` does `print(headers)` and `print(json_data)` (lines 191–192). `headers` contains `Authorization: Bearer <WHATSAPP_TOKEN>`. Probe with a fake token confirmed the token and the recipient phone number both appear in stdout. In Docker this goes to container logs | **FAIL / SECURITY GAP** (violates the Constitution's "no credentials in logs") |
| Per-request cost | Re-compiles the graph and reopens SQLite on every webhook call (code) | Risk |
| Rate limiting | None (code) | FAIL |
| Prompt injection / tool abuse | Not assessed; Ava has no tools. User text goes straight into prompts and into memory writes | Not assessed |

None of these were fixed. All are candidates for the hardening work in later phases, in particular the signature check and the log leak, which should be addressed before any public exposure.

## 15. Dependency / Provider Drift

| Dependency | `pyproject.toml` constraint | Documented install (A) resolved | Locked install (B) | Effect |
|---|---|---|---|---|
| langchain | `>=0.3.13` | **1.2.18** | 0.3.13 | `langchain.prompts` removed → import failure |
| langchain-core | via above | 1.6.12 | 0.3.28 | |
| langgraph | `>=0.2.60` | 1.1.10 | 0.2.60 | A: imports OK (graph module failed only due to langchain.prompts) |
| langchain-groq | `>=0.2.2` | 1.1.3 | 0.2.2 | |
| groq | via langchain-groq | 0.37.1 | 0.13.1 | |
| qdrant-client | `>=1.12.1` | **1.19.1** | 1.13.0 | `.search()` removed in A |
| chainlit | `>=1.3.2` | **2.11.1** | 1.3.2 | A: import error with `pydantic==2.10.0` |
| pydantic | `==2.10.0` (exact) | 2.10.0 | 2.10.0 | Exact pin conflicts with newer libraries |
| sentence-transformers | `>=3.3.1` | 6.1.0 | 3.3.1 | A: imports OK |
| torch | `>=2.0.0` | 2.14.1 | 2.5.1 | Heavy download |
| numpy | `>=1.24.0` (platform-conditional) | 2.5.4 | 1.26.4 | |
| elevenlabs | `>=1.50.3` | 2.73.1 | 1.50.3 | A: speech module imports OK |
| together | `>=1.3.10` | 2.41.0 | 1.3.10 | A: only fails indirectly via `langchain.prompts` |
| fastapi | `>=0.115.6` | 0.143.5 | 0.115.6 | |

(Rows marked "A: imports OK" mean the module imported in Env A; runtime behaviour was not tested.)

**Conclusion about drift:** the repository is reproducible only through its lockfile (`uv.lock`), which the Dockerfile uses. The documented `uv pip install -e .` path ignores the lock and fails. This is a defect in the instructions as much as in the code. Provider drift (Groq models, Together free tier, Graph v21.0 retirement) is a separate, additional problem.

## 16. Known Problems (summary)

| # | Problem | Class | Status |
|---|---|---|---|
| 1 | Documented install path produces a non-importable environment | Existing in Ava (unbounded `langchain`, exact `pydantic` pin) plus drift | NOT FIXED |
| 2 | All three Groq model defaults are deprecated or past shutdown per Groq's page | Provider drift | NOT FIXED |
| 3 | Together free image model likely gone | Provider drift (unverified) | NOT FIXED |
| 4 | No webhook signature verification; no auth | Existing in Ava | NOT FIXED |
| 5 | Bearer token and phone number printed to stdout | Existing in Ava | NOT FIXED |
| 6 | 500 on non-text message types and malformed input; no idempotency | Existing in Ava | NOT FIXED |
| 7 | GET verify passes with no token if env var unset | Existing in Ava | NOT FIXED |
| 8 | Long-term memory is global across users | Existing in Ava | NOT FIXED |
| 9 | `qdrant-client.search` removed in newer versions | Drift | NOT FIXED |
| 10 | Four third-party keys required even for text chat | Existing in Ava | NOT FIXED |
| 11 | No tests; 20 ruff errors with current ruff | Existing in Ava | NOT FIXED |
| 12 | Graph v21.0 scheduled for removal 2027-01-21 | Drift | NOT FIXED |
| 13 | LLM calls run inline in the webhook request; graph recompiled per request | Existing in Ava | NOT FIXED |
| 14 | Docker daemon unresponsive on this machine | Environment | Unresolved |

## 17. What Worked

- Cloning, and `uv sync --frozen` from the lockfile.
- All 15 Ava modules import in the locked environment; FastAPI and Chainlit app objects build.
- The LangGraph compiles; its structure matches the code.
- GET webhook verification works for the normal case.
- POST routing for status updates and unknown events.
- A text-message payload is parsed and dispatched into the graph.
- Local embedding model loads and produces 384-dimension vectors without credentials.

## 18. What Failed

- Documented install path: broken environment (`langchain.prompts`, Chainlit/pydantic).
- Webhook security checks (signature, auth, idempotency, error handling, GET with unset token).
- Credential printing in `send_response`.
- Repo lint check (20 errors with ruff 0.17.1).
- Provider/model defaults per Groq's page.

## 19. What Was Blocked

| Blocked item | Needs |
|---|---|
| Docker Compose (Qdrant, Chainlit, WhatsApp services) | Responsive Docker daemon, and a `.env` with keys |
| Any LLM call, agent reply, router, memory classification, summary | Groq API key (with currently available models) |
| Image and voice replies | Together and ElevenLabs keys |
| Qdrant read/write, long-term memory | Qdrant server (local container or Qdrant Cloud) |
| WhatsApp end-to-end | Meta app, phone number id, token, verify token, public HTTPS endpoint |
| Real server process test (`fastapi run`) and Chainlit UI | Not started; would need the keys above for meaningful behaviour |

## 20. What Was NOT Changed

- **No tracked file in Ava was modified** (`git diff --name-only` = 0 before and after every probe).
- **Untracked files in the Ava clone created as a side effect:** 12 untracked files (`.chainlit/translations/*.json`), auto-generated by Chainlit when its module was imported. They are generated, not source edits. They can be removed with `git clean` in the baseline folder.
- No `.env` created. No secrets used or stored. Fake placeholder values existed only in the process environment of the probe scripts.
- Probe scripts live in the session scratchpad, not in Ava or in the Wazi repo: `probe_imports.py`, `probe_webhook.py`, `probe_graph.py`. A temporary SQLite file may exist under the OS temp directory.
- Two virtualenvs exist outside the Wazi repo (`ava\.venv`, `ava-venv-locked`); `ava\.venv` is git-ignored.
- ArchAgenticRAG: not copied, imported, modified or run.
- The Wazi repo contains only documentation (this file, plus the earlier two).

Side effects outside the project: Docker Desktop was launched; the sentence-transformers model was downloaded to the Hugging Face cache (~90 MB); several GB of packages (including `torch`) were downloaded by uv into two venvs.

## 21. Lessons Learned

1. **A lockfile is part of the product.** Ava works from `uv.lock` and breaks from its own docs. For Wazi: pin everything, install only from the lock, and write the setup docs to match.
2. **Ten months of drift matters more than code quality.** Three model IDs and a Graph API version in Ava's defaults are deprecated or scheduled for removal. Model names must be configuration, with a check that fails loudly at startup.
3. **"Runs with no WhatsApp setup" is false for Ava.** It needs four unrelated accounts to boot. A minimal Wazi should degrade gracefully when optional providers are missing.
4. **The task prompt's example diagram (PyWa) was wrong for Ava.** Verifying against source mattered. Ava hand-rolls its WhatsApp calls.
5. **Security gaps in the course code are real and concrete.** Missing signature, token printed to logs, global memory. These come first in hardening.
6. **Phase 1 corrections:**
   - Phase 1 said the Chainlit UI lets you test the graph without WhatsApp. True, but it still needs all the provider keys, and the Chainlit module fails in the unlocked environment.
   - Phase 1 rated Ava's staleness as a risk but did not know the main text model was already past its shutdown date. The overall recommendation of Ava as a *learning scaffold* stands, but "run unchanged" is not achievable with the current provider landscape; some provider configuration change is unavoidable. The Phase 1 note that configuration-only changes are acceptable is therefore important.
7. **ArchAgenticRAG boundary.** This phase's instructions describe ArchAgenticRAG as a learning project, not a production dependency, reusable only after explicit mentor approval. REUSE_AUDIT.md described it as a reuse source for Phase 5 in firmer language. There is no conflict with the Constitution (every reuse needs a later reviewed decision), but I suggest the mentor confirms or softens that wording in the audit.
8. **Docker on this machine** needs a separate look (daemon never responded). It is a Wazi prerequisite.

## 22. Recommended Next Phase

Not started; for mentor decision.

**Option 1 (recommended): Phase 2b, complete the baseline** once credentials and Docker are available: start Docker, bring up only Qdrant, create a `.env` from `.env.example` with real keys (never committed), change **configuration only** (model names via environment variables, since `settings.py` reads them from env) to current Groq models, run Chainlit, then run the WhatsApp leg with a Meta test number through a tunnel placed in front of a signature-checking proxy or kept off the internet until hardened. Output: updated baseline with the BLOCKED rows resolved.

**Option 2: Phase 3 (understand and document the architecture)** can proceed now using only §6–§7, since the architecture has been verified from source. Runtime unknowns would be listed as open questions.

Either way, hardening (signature, log leak, idempotency, per-user memory) and provider modernisation should be explicit later phases, not folded into the baseline.

Credentials and decisions needed from the mentor to unblock Option 1:
1. Which accounts to create (Groq, ElevenLabs, Together, Qdrant local vs cloud, Meta developer app), and whether free tiers are acceptable (their current limits are not verified).
2. Whether to treat "model names via env" as an allowed configuration change for "as-is".
3. How to expose a test webhook safely (tunnel plus signature check, or a local-only simulator).
