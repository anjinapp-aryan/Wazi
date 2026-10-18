# Phase 3: Understand & Reconstruct the Architecture

Status: Phase 3 deliverable, awaiting mentor review. Date: **2026-10-18**.
Companion files: [WAZI_ARCHITECTURE_COMPARISON.md](WAZI_ARCHITECTURE_COMPARISON.md), [adr/001](adr/001-ava-reference-foundation.md), [adr/002](adr/002-archagenticrag-separate-project.md), [adr/003](adr/003-layer-separation.md).

Evidence rule used throughout: **source code > README > earlier reports > assumption.** File references are to Ava at commit `338fd68` (`D:\WORK_SPACE\Wazi-baselines\ava`, unmodified), written `path:line`. "Phase 2" means an observation made in [PHASE_2_BASELINE.md](PHASE_2_BASELINE.md). "Not tested" means inferred from code without running it.

---

## 1. Objective

Turn the Phase 2 discoveries into an accurate, beginner-readable map of how Ava really works, compare it with the owner's ArchAgenticRAG at the concept level, and propose (not build) a target architecture for Wazi. No code was written, nothing was fixed, no dependency was changed, no webhook was exposed, and neither Ava nor ArchAgenticRAG was modified.

## 2. Source Code Evidence

| What | How verified |
|---|---|
| Ava source | Read directly: `interfaces/whatsapp/*`, `interfaces/chainlit/app.py`, `graph/*`, `modules/memory/*`, `modules/speech/*`, `modules/image/*`, `modules/schedules/*`, `core/*`, `settings.py`, `Dockerfile*`, `docker-compose.yml`, `cloudbuild.yaml`, `pyproject.toml` |
| Runtime facts | Phase 2 probes (in-process FastAPI test client, fake env values) and one extra Phase 3 check: LangGraph's `add_messages` reducer converts a plain string into a `HumanMessage` (run in the locked environment) |
| Usage checks | `grep` over `src/` for state fields, settings, logging calls |
| ArchAgenticRAG | Read-only: `rag/vector_store.py`, `rag/settings.py`, `rag/ingestion.py` (top), `graphs/basic_rag.py`, `providers.py`, `eval/README.md`, an eval config, test layout. Test functions were counted (82), **not run** |
| Correction to the task brief | The brief's sample diagram mentioned PyWa. Ava has no PyWa dependency; WhatsApp calls are hand-written `httpx` calls |

## 3. Actual Ava Architecture

### 3.1 Component table

| Component | Actual implementation | File | Responsibility | Dependency |
|---|---|---|---|---|
| Web server / entry | `app = FastAPI()` plus one router; started by `fastapi run ... --port 8080` in the Dockerfile | `interfaces/whatsapp/webhook_endpoint.py:1-5`, `Dockerfile` | Host the webhook | FastAPI |
| Webhook handler | One async function on `GET/POST /whatsapp_response` | `interfaces/whatsapp/whatsapp_response.py:31-108` | Verify (GET), parse, run the graph, send the reply (POST) | FastAPI, httpx |
| HTTP client | `httpx.AsyncClient`, created per call | `whatsapp_response.py:110-215` | Download media, send messages, upload media | httpx |
| WhatsApp credentials | Module-level `os.getenv("WHATSAPP_TOKEN")`, `os.getenv("WHATSAPP_PHONE_NUMBER_ID")`; verify token read per request | `whatsapp_response.py:27-28, 37` | Authenticate to Meta | environment |
| Graph definition | `create_workflow_graph()` builds a `StateGraph` (cached with `lru_cache`); `graph_builder` is the **uncompiled** builder | `graph/graph.py:22-56`, `graph/__init__.py` | Define nodes and edges | LangGraph |
| Graph compile + invoke | `graph_builder.compile(checkpointer=...)` **on every request**, then `ainvoke` | `whatsapp_response.py:70-75` | Run one conversation turn | LangGraph, `langgraph-checkpoint-sqlite` |
| Graph state | `AICompanionState(MessagesState)` + 7 fields | `graph/state.py` | Data carried between nodes | LangGraph |
| Nodes | 8 async/sync functions | `graph/nodes.py` | See §6 | Groq, Qdrant, Together, ElevenLabs |
| Routing functions | `select_workflow`, `should_summarize_conversation` | `graph/edges.py` | Conditional edges | n/a |
| LLM chains | `get_router_chain`, `get_character_response_chain`; `get_chat_model()` builds `ChatGroq` | `graph/utils/chains.py`, `helpers.py` | Prompt + model + parser | `langchain-groq` |
| Prompts | Persona card, router prompt, memory prompt, image prompts | `core/prompts.py` | The text the LLM sees | n/a |
| Schedule | Fixed weekday time table; uses server local time | `core/schedules.py`, `modules/schedules/context_generation.py` | Gives the persona a "current activity" | n/a |
| Short-term memory | LangGraph `AsyncSqliteSaver` keyed by `thread_id` | `whatsapp_response.py:70-78` | Persist conversation state | sqlite (aiosqlite) |
| Long-term memory | `MemoryManager` (LLM classifier) + `VectorStore` (Qdrant) | `modules/memory/long_term/memory_manager.py`, `vector_store.py` | Remember facts about the user | Groq, Qdrant, sentence-transformers |
| Speech-to-text | `SpeechToText.transcribe` (Groq Whisper) | `modules/speech/speech_to_text.py` | Voice note to text | `groq` |
| Text-to-speech | `TextToSpeech.synthesize` (ElevenLabs) | `modules/speech/text_to_speech.py` | Reply as audio | `elevenlabs` |
| Image-to-text | `ImageToText.analyze_image` (Groq vision) | `modules/image/image_to_text.py` | Describe photos | `groq` |
| Text-to-image | `TextToImage` (Groq for the prompt, Together for the picture) | `modules/image/text_to_image.py` | Generate image replies | `groq`, `together`, `langchain` |
| Settings | `pydantic-settings` `Settings`, `.env` file | `settings.py` | Typed config | pydantic-settings |
| Errors | Four custom exceptions, wrapped around provider calls | `core/exceptions.py` | Tag failures | n/a |
| Chainlit UI | Chat UI that calls the same graph | `interfaces/chainlit/app.py` | Local testing UI | chainlit |
| Deployment | Compose: `qdrant`, `chainlit` (8000), `whatsapp` (8080); `cloudbuild.yaml` for Google Cloud Run | `docker-compose.yml`, `cloudbuild.yaml` | Run and ship | Docker, GCP |

### 3.2 Component diagram (reconstructed from code)

```
                       +--------------------------- Ava process (FastAPI) ---------------------------+
 WhatsApp user         |                                                                              |
      |                |   GET/POST /whatsapp_response                                                |
      v                |        |                                                                     |
 Meta Cloud API -----> |   whatsapp_handler ---(media)---> Graph API (download)                       |
 (webhook POST/GET)    |        |  \-- audio -> Groq Whisper   \-- image -> Groq vision               |
      ^                |        v                                                                     |
      |                |   compile StateGraph + AsyncSqliteSaver (thread_id = phone)                  |
      |                |        |                                                                     |
      |                |        v                                                                     |
      |                |   [memory_extraction] -> [router] -> [context] -> [memory_injection]         |
      |                |        |  Groq+Qdrant     | Groq                    | Qdrant search         |
      |                |        v                                                                     |
      |                |   [conversation | image | audio]  -> (maybe) [summarize]                     |
      |                |        | Groq    | Together | ElevenLabs                                     |
      |                |        v                                                                     |
      +----------------+--- send_response() -> Graph API /messages (and /media upload)                |
                       +------------------------------------------------------------------------------+
 External services: Meta, Groq, Together, ElevenLabs, Qdrant (local container or Cloud), SQLite file
```

## 4. WhatsApp Message Flow

Trace of one inbound **text** message, using the real code. Steps from the brief that do not exist as described are marked.

| # | Step | What actually happens | Where |
|--:|---|---|---|
| 1 | Meta sends webhook request | `POST /whatsapp_response` with JSON. Meta sends delivery/read **statuses** to the same URL | n/a |
| 2 | FastAPI receives | The one route accepts GET and POST | `whatsapp_response.py:31` |
| 3 | Request validated | **Does not exist.** No signature check, no authentication. The only "validation" is that `request.json()` and key lookups do not raise | `:41-43` |
| 4 | Message extracted | Takes `entry[0].changes[0].value`. If `messages` exists, uses `messages[0]` only; `from` = sender id. If `statuses` exists, returns 200. Otherwise 400 | `:43-47, 100-104` |
| 5 | Enters application logic | Content: audio → download + Groq Whisper; image → download + Groq vision (failure swallowed with a warning); **everything else is assumed to be text** and read from `message["text"]["body"]` | `:51-67` |
| 6 | LangGraph invoked | Opens SQLite checkpointer, **compiles the graph**, `ainvoke({"messages":[HumanMessage(content)]}, {"configurable":{"thread_id": phone}})` | `:70-75` |
| 7 | State created/updated | Checkpoint for this `thread_id` is loaded (empty on first message), the new message is appended by the `add_messages` reducer | LangGraph |
| 8 | Nodes execute | §6 | `graph/graph.py` |
| 9 | Memory accessed | `memory_extraction_node` (may write to Qdrant) at the start; `memory_injection_node` (reads Qdrant) before the reply | `nodes.py:125-142` |
| 10 | LLM called | At least 3 sequential Groq calls: memory classifier, router, reply (plus summary or image/voice extras) | §6 |
| 11 | Response generated | Reply string in the last message; `workflow` says text/image/audio | `:80-81` |
| 12 | WhatsApp API called | `send_response` POSTs to `https://graph.facebook.com/v21.0/<phone_number_id>/messages` (uploads media first for audio/image) | `:152-202` |
| 13 | Response sent | Returns 200 only if Meta answered 200; otherwise returns **500** to Meta | `:95-98` |

Key observation: **steps 3, 6-13 all happen inside the webhook request.** Meta expects a quick reply and retries on non-200, so a slow LLM chain or any error can produce retried deliveries and duplicate replies. This is inferred from the code and the retry behaviour described in Meta documentation summaries; the retry itself was not observed.

## 5. Webhook Architecture

### 5.1 GET verification (the handshake)

```
Meta (when you register the URL)
   |  GET /whatsapp_response?hub.mode=subscribe&hub.verify_token=T&hub.challenge=C
   v
whatsapp_handler (method == GET)
   |  params.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN") ?
   |-- yes -> 200, body = hub.challenge
   '-- no  -> 403 "Verification token mismatch"
```

Behaviour measured in Phase 2: correct token → 200 + challenge; wrong or missing token → 403; **if `WHATSAPP_VERIFY_TOKEN` is unset, a request with no token returns 200** because `None == None`. `hub.mode` is never checked. The comparison is not constant-time (low impact for this token).

### 5.2 POST message (events)

```
Meta
  |  POST /whatsapp_response   (JSON; no signature checked)
  v
whatsapp_handler (method == POST)
  |  data = await request.json()
  |  value = data["entry"][0]["changes"][0]["value"]
  |-- "messages" in value -> take messages[0] -> pick content by type
  |        -> compile graph -> ainvoke(thread_id = sender) -> read state
  |        -> send_response(...) -> 200 or 500
  |-- "statuses" in value -> 200 (ignored)
  '-- otherwise           -> 400
  any exception            -> 500 "Internal server error"
```

### 5.3 What the webhook does not do

| Property | Status |
|---|---|
| Signature validation (`X-Hub-Signature-256`) | Absent |
| Authentication / allow-list of senders | Absent |
| Idempotency (message id tracking) | Absent. `messages[0].id` is never read |
| Acknowledge-fast-then-process | Absent (work is inline) |
| Handles batches (`messages[1:]`) | Ignored |
| Handles non-text/audio/image types | Crashes to 500 (location tested) |
| Rate limiting | Absent |

## 6. LangGraph Architecture

### 6.1 Graph (extracted from code and confirmed by compiling it in Phase 2)

```
START
  |
  v
memory_extraction_node        (LLM decides if the user message holds a fact; may write Qdrant)
  |
  v
router_node                   (LLM picks 'conversation' | 'image' | 'audio')
  |
  v
context_injection_node        (reads the clock; sets current_activity)
  |
  v
memory_injection_node         (Qdrant search; sets memory_context)
  |
  +-- workflow == 'image' ----> image_node  ---+
  +-- workflow == 'audio' ----> audio_node  ---+--> if len(messages) > 20:
  '-- otherwise --------------> conversation_node -+       summarize_conversation_node -> END
                                                    '--> else END
```

Entry point: `START → memory_extraction_node`. Exit points: `END` directly after a response node, or after `summarize_conversation_node`. **Tool nodes: none.** There is no loop; the graph is a directed acyclic pipeline with two branch points.

### 6.2 Node table

| Node | Input (reads) | Output (writes) | Responsibility | Next |
|---|---|---|---|---|
| `memory_extraction_node` | last message | `{}` (side effect: Qdrant write) | Classify the user message with `gemma2-9b-it` structured output; if important and not a near-duplicate (score ≥ 0.9), store the fact | `router_node` |
| `router_node` | last 3 messages | `workflow` | `ChatGroq(temperature 0.3).with_structured_output(RouterResponse)` returns `conversation`, `image` or `audio` | `context_injection_node` |
| `context_injection_node` | `current_activity` (previous) | `apply_activity`, `current_activity` | Look up the activity from the server clock. `apply_activity` is never read anywhere | `memory_injection_node` |
| `memory_injection_node` | last 3 messages | `memory_context` | Join recent messages, embed, fetch top-3 memories, format as bullets | conditional `select_workflow` |
| `conversation_node` | `messages`, `summary`, `memory_context` | `messages += AIMessage` | Persona prompt + history → Groq → strip `*...*` | conditional `should_summarize_conversation` |
| `image_node` | `messages`, ... | `messages += AIMessage`, `image_path` | LLM writes a scenario and image prompt, Together draws it to `generated_images/`, then the persona replies | same |
| `audio_node` | `messages`, ... | `messages += <str>`, `audio_buffer` | Persona reply → ElevenLabs bytes | same |
| `summarize_conversation_node` | `messages`, `summary` | `summary`, deletions via `RemoveMessage` | Ask the LLM for/extend a summary; delete all but the last 5 messages | `END` |

### 6.3 Where the "agent" is

Ava has LLM calls at several steps, but **the model never chooses tools or loops**. The only model-made decisions are (a) "is this message a memorable fact" and (b) "reply as text, picture or voice". It is a *workflow with LLM steps*, not an autonomous agent. "Agentic" capabilities (tool selection, planning, multi-step retrieval) would be new work.

## 7. State Model

### 7.1 Fields

| Field | Type | Set by | Read by | Notes |
|---|---|---|---|---|
| `messages` | list of messages (`add_messages` reducer) | handler (input), response nodes, summariser (deletions) | all LLM nodes, edges | The conversation history |
| `workflow` | str | `router_node` | `select_workflow`, handler | Overwritten every turn |
| `memory_context` | str | `memory_injection_node` | response nodes | Recomputed every turn |
| `current_activity` | str | `context_injection_node` | `context_injection_node` only (response nodes re-query the clock themselves) | Mostly redundant |
| `apply_activity` | bool | `context_injection_node` | nobody | Dead field |
| `summary` | str | `summarize_conversation_node` | response nodes, summariser | Persists |
| `audio_buffer` | bytes | `audio_node` | handler | Raw MP3 bytes kept in state |
| `image_path` | str | `image_node` | handler | Path of a locally written file |

### 7.2 Lifecycle for a beginner (two messages from the same phone)

1. **Message 1 arrives from +1555…** The handler calls the graph with `thread_id="1555…"`. The checkpointer finds nothing, so state starts empty. The new message is appended to `messages`.
2. Each node receives the **whole state** and returns only the fields it changes; LangGraph merges those updates (for `messages` it *appends* via the reducer; other fields are *overwritten*).
3. When the graph reaches `END`, LangGraph **saves a checkpoint** to the SQLite file under that `thread_id`. This includes every state field, including `audio_buffer` bytes (by LangGraph design; not tested here).
4. The handler asks for the final state and sends `messages[-1]`.
5. **Between messages**, nothing is in memory in the process; everything is in SQLite (short-term) and Qdrant (long-term facts).
6. **Message 2 arrives** with the same `thread_id`. The checkpoint is loaded: old `messages`, old `summary`, and also old values of `workflow`, `audio_buffer`, `image_path`. The new message is appended. `workflow` and `memory_context` are recomputed; fields no node touches (such as a stale `image_path`) simply carry over.
7. Every request builds a new compiled graph and opens the SQLite file again. That is cheap here but is not how a long-lived service would normally be structured.

### 7.3 A real defect found by reading the state code

`audio_node` returns `{"messages": response, ...}` where `response` is a **plain string** (`nodes.py:99`). I confirmed that LangGraph's `add_messages` turns a plain string into a `HumanMessage`. So after a voice reply, Ava's own words are stored in history **as if the user had said them**; later turns, the router (which sees the last 3 messages), the summariser and the memory classifier (it only looks at `human` messages, `memory_manager.py:44`) can all be confused. This was found by reading plus a small reducer check; the end-to-end effect was not tested (needs an LLM). Not fixed.

## 8. Memory Architecture

| Aspect | Ava's implementation |
|---|---|
| Short-term (conversation) memory | Messages in the LangGraph state, checkpointed to SQLite per `thread_id` (= sender phone number in WhatsApp, constant `1` in Chainlit) |
| Summarisation | When `len(messages) > 20` the LLM writes/extends a summary and all but the last 5 messages are deleted |
| Long-term memory: extraction | Only for `human` messages. `MEMORY_ANALYSIS_PROMPT` + `gemma2-9b-it` (structured output `MemoryAnalysis{is_important, formatted_memory}`) |
| Embedding generation | `SentenceTransformer("all-MiniLM-L6-v2")`, 384 dims, loaded once in a singleton, runs on the app's CPU |
| Storage | Qdrant collection `long_term_memory`, cosine distance, payload `{text, id, timestamp}` |
| De-duplication | Before writing: nearest neighbour with cosine ≥ 0.9 means "already known", skip |
| Retrieval | Last 3 message contents joined → embed → top-3 (`MEMORY_TOP_K`) → bullet list in the persona prompt |
| Update | Effectively none. `store_memory` has an "update if similar" branch, but the caller returns early when a similar one exists, so it is never reached in the normal path |
| Deletion / expiry | None found |
| User identification | **None.** The WhatsApp sender id is used for the *conversation thread* but never reaches the memory code |
| Collection structure | One collection, fixed name, no `user_id` in payload, no payload index, no filter in `search` |

### 8.1 Why "one global collection, no per-user filter" is a problem

**Architectural:** the memory layer has no notion of *whose* memory it is. Any identity concept lives only in the checkpoint thread, so the two memories drift apart conceptually: conversations are per user, facts are shared.

**Security and privacy:**

1. **Cross-user leakage.** User A says "I work at Hospital X and have diabetes." The fact is embedded and stored without an owner. User B later sends a message that is semantically close; the top-3 search returns A's fact and it is injected into the prompt that answers B. B may read A's personal data in the reply.
2. **Cross-user manipulation.** B can plant false "facts" ("the user's name is Admin") that will be retrieved for A.
3. **No way to honour deletion requests**, because stored facts cannot be tied to a person.
4. **Wrong personalisation** even without malice: facts from different people mix.
5. Compounded by the unauthenticated webhook (anyone can post as any phone number), so isolation cannot rely on the sender id being trustworthy until signature checking exists.

This was established from code (`vector_store.py` collection constant and unfiltered `search`). It was **not** exercised at runtime (no Qdrant, no LLM available). It is documented, not fixed.

## 9. Qdrant Architecture

| Item | Value |
|---|---|
| Client | `QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)` created once (singleton) |
| Local setup | Compose service `qdrant/qdrant:latest`, storage mounted at `./long_term_memory`, port 6333; app uses `QDRANT_URL=http://qdrant:6333` |
| Cloud option | Qdrant Cloud URL + API key (docs) |
| Collection | `long_term_memory`, created lazily on first write with `VectorParams(size=<embedding dim>, distance=COSINE)` |
| Point | `id` = uuid4 string, `vector` = embedding, `payload` = `text`, `id`, `timestamp` |
| Search | `client.search(collection, query_vector, limit=k)` (a method **removed** in newer `qdrant-client`; Phase 2) |
| Image tag | `latest` (unpinned, so server and client versions can drift) |
| `QDRANT_PORT`, `QDRANT_HOST` | Declared in settings and set in compose, but **not used** by the code |
| Resilience | None: no retry/timeout settings; any Qdrant error in a node becomes a 500 for the webhook |
| What Qdrant is **not** used for | Documents. There is no RAG |

## 10. Provider Architecture

| Provider | Purpose | SDK / HTTP | Configuration | Used where |
|---|---|---|---|---|
| Meta WhatsApp Cloud API | Receive webhooks; send/upload/download messages and media | Raw `httpx` to `graph.facebook.com/v21.0` | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN` (via `os.getenv`) | `whatsapp_response.py` |
| Groq | Chat, router, memory classifier, summariser, scenario/prompt writing, Whisper STT, vision | `langchain-groq` (`ChatGroq`) and `groq` SDK | `GROQ_API_KEY`; model names in `settings.py`, Whisper name also hard-coded | `graph/utils/helpers.py`, `memory_manager.py`, `text_to_image.py`, `speech_to_text.py`, `image_to_text.py` |
| Together AI | Image generation (FLUX) | `together` SDK | `TOGETHER_API_KEY`, `TTI_MODEL_NAME` | `text_to_image.py` |
| ElevenLabs | Text-to-speech | `elevenlabs` SDK | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `TTS_MODEL_NAME` | `text_to_speech.py` |
| Qdrant | Vector memory | `qdrant-client` | `QDRANT_URL`, `QDRANT_API_KEY` | `vector_store.py` |
| Hugging Face Hub | Downloads the embedding model once | `sentence-transformers` | none (public model) | `vector_store.py` |
| SQLite (file) | LangGraph checkpoints | `aiosqlite` via `langgraph-checkpoint-sqlite` | `SHORT_TERM_MEMORY_DB_PATH` | handler, Chainlit |
| Google Cloud Run / Secret Manager | Optional deployment | `gcloud` in `cloudbuild.yaml` | secrets mapped from Secret Manager | deploy only |

**Why a provider abstraction matters.** A provider abstraction means the rest of the app asks for "a chat model" or "an embedding function" and one small module decides which vendor, model and key to use. In Ava, `ChatGroq(...)` is built in at least three modules and vendor SDKs are imported where used. Phase 2 showed the cost: three of the default model IDs are deprecated or past shutdown, a free image model likely vanished, and fixing that means touching many files. Behind an abstraction, replacing a model is one configuration change, tests can use a fake, and cost or privacy rules (for example "never send message text to vendor X") can be enforced in one place. ArchAgenticRAG's `providers.py` is a concrete example of the idea.

## 11. Configuration Architecture

Two mechanisms coexist, which is a source of confusion:

1. `pydantic-settings` `Settings` reads `.env` (and the environment) for the fields in `settings.py`.
2. Several modules call `os.getenv(...)` directly (`WHATSAPP_*`, and each speech/image class validates `GROQ_API_KEY` etc. via `os.getenv`). `pydantic-settings` does not copy `.env` values into `os.environ`, so running outside Docker with only a `.env` file would be expected to fail those checks. Compose avoids this with `env_file: .env`. (Expected from library behaviour; not tested.)

| Environment variable | Component | Purpose | Required? | Secret? |
|---|---|---|---|---|
| `GROQ_API_KEY` | `settings.py`, LLM chains, STT, vision, memory classifier | Groq authentication | **Yes** (no default; app fails without it) | Yes `<REDACTED>` |
| `ELEVENLABS_API_KEY` | `text_to_speech.py` | TTS authentication | **Yes** (declared without default) | Yes `<REDACTED>` |
| `ELEVENLABS_VOICE_ID` | same | Which voice | **Yes** | No (identifier) |
| `TOGETHER_API_KEY` | `text_to_image.py` | Image generation auth | **Yes** | Yes `<REDACTED>` |
| `QDRANT_URL` | `vector_store.py` | Qdrant address | **Yes** | No (may embed a hostname) |
| `QDRANT_API_KEY` | same | Qdrant auth (cloud) | Declared without default, so it must be present; compose passes the literal string `None` for local | Yes for cloud `<REDACTED>` |
| `QDRANT_PORT`, `QDRANT_HOST` | `settings.py` | Declared, unused | No | No |
| `WHATSAPP_TOKEN` | `whatsapp_response.py` | Bearer token for Graph API | Needed for real WhatsApp; **not validated at startup** (a missing value becomes `Bearer None`) | Yes `<REDACTED>` |
| `WHATSAPP_PHONE_NUMBER_ID` | same | Sender number id in the URL | Same as above | No (identifier) |
| `WHATSAPP_VERIFY_TOKEN` | same | GET handshake token | Same; if missing, GET without a token passes | Yes `<REDACTED>` |
| `TEXT_MODEL_NAME`, `SMALL_TEXT_MODEL_NAME`, `ITT_MODEL_NAME`, `TTI_MODEL_NAME`, `TTS_MODEL_NAME` | `settings.py` | Model IDs (defaults in code) | No | No |
| `STT_MODEL_NAME` | `settings.py` | Declared but not used (Whisper name is hard-coded in `speech_to_text.py`) | No | No |
| `MEMORY_TOP_K`, `ROUTER_MESSAGES_TO_ANALYZE`, `TOTAL_MESSAGES_SUMMARY_TRIGGER`, `TOTAL_MESSAGES_AFTER_SUMMARY` | graph/memory | Tuning knobs | No | No |
| `SHORT_TERM_MEMORY_DB_PATH` | handler, Chainlit | SQLite file (default `/app/data/memory.db`, a Linux path) | No | No |

Observations: four third-party credentials are mandatory even for text-only use; non-secret and secret values live in one flat file; model IDs are overridable by environment (useful for Phase 2b) but one is hard-coded.

## 12. Error Paths

"Current" columns are from Phase 2 probes where marked *(tested)*, otherwise from code *(code)*. "Desired future behaviour" is **documentation only**; nothing was implemented.

| Failure | Current behaviour | Risk | Desired future behaviour |
|---|---|---|---|
| Malformed JSON | 500, stack trace in logs *(tested)* | Meta retries; log noise; could be abused to fill logs | Reject with a 4xx before any parsing work, after authentication |
| Unsupported message type (e.g. location, sticker) | `KeyError: 'text'` → 500 *(tested, location)* | Retry loop; user gets no reply; duplicates | Recognise the type, reply with a friendly "I can't read that yet", return 200 |
| LLM failure (Groq 401/429/timeout/deprecated model) | Exception in a node → 500 *(tested with 401)* | User silence, retries, repeated LLM spend | Bounded retries with backoff, a user-facing fallback message, 200 to Meta, alert for operators |
| Qdrant failure | Exception in memory nodes (every turn reads Qdrant) → 500 *(code)* | One memory outage breaks all chats | Treat memory as optional: answer without memories, log the degradation |
| WhatsApp send failure (non-200 from Meta) | `send_response` returns `False` → handler returns 500; response body discarded and never logged *(code)* | Retry causes the whole LLM pipeline to run again; real error reason lost | Log status and error body (without secrets), retry only the send, never re-run the LLM |
| Media upload failure | Falls back to a text reply *(code)* | Acceptable; user loses the voice/image | Keep, and record the failure |
| Image analysis failure | Warning logged, message continues without the description *(code)* | Minor | Keep, tell the user the image could not be read |
| Speech-to-text or TTS failure | Wrapped in custom exception → propagates → 500 *(code)* | Voice messages cause silent failures | Fall back to a text reply or ask the user to retry |
| Webhook verification failure | 403 *(tested)* | Correct behaviour | Keep; add `hub.mode` check |
| Missing verify token configured | GET with no token returns 200 *(tested)* | Misconfiguration silently opens the handshake | Fail startup if required secrets are missing |
| Duplicate delivery of the same message | No detection; every delivery re-runs the pipeline *(code; error-path duplicate tested)* | Double replies, double LLM cost, duplicate memories | Record message ids and skip repeats |
| Invalid / missing signature | Accepted, 200 *(tested)* | Anyone can inject messages as any user | Reject with 401/403 before reading the body as JSON |
| Provider outage or removal (Groq, Together, ElevenLabs) | Same as LLM failure; no fallback provider *(code)* | Total outage on one vendor | Provider abstraction with configured fallback and health checks |
| Slow processing | Inline in the request; Cloud Run config uses `--timeout 120` *(code)* | Meta timeout/retry; Cloud Run kills slow requests | Acknowledge immediately and process in the background with idempotency |

## 13. Security Boundaries

Current boundaries, as built:

```
Internet ──(no auth, no signature)──> /whatsapp_response ──> LLM / Qdrant / SQLite / Graph API
                                         |                        (all trusted, shared, global)
                                         '── secrets: environment variables; token printed to stdout
```

| Concern | Current state | Evidence |
|---|---|---|
| Webhook authentication | None | Phase 2 test: unsigned and bogus-signature POSTs accepted |
| Webhook signature verification | Absent | no `hmac`/`signature` in repo |
| Secrets storage | `.env` (git-ignored) and environment; Cloud Run deploy file uses Secret Manager | `.gitignore`, `cloudbuild.yaml` |
| **Token logging** | `print(headers)` and `print(json_data)` write the bearer token and the recipient's phone number to stdout on every send | `whatsapp_response.py:191-192`; confirmed with a fake token in Phase 2 |
| Other logging | `logger.info` records stored memory text, image descriptions, prompts (likely not emitted unless logging is configured; no logging setup found, unverified) | `memory_manager.py:54-58`, `text_to_image.py` |
| User isolation (conversations) | Per phone number via `thread_id`, but the phone number is attacker-controlled without signatures | `:47` |
| User isolation (Qdrant) | None; one global collection | §8.1 |
| External API credentials | Passed to SDKs from settings; Meta token read from env at import | `:27-28` |
| Error leakage | Generic 500 body to callers, full stack trace in server logs | `:106-108` |
| Public exposure risks | Cloud Run config uses `--allow-unauthenticated` (needed for Meta, so signature checking would be the only gate); the compose file exposes Qdrant on 6333 with no key | `cloudbuild.yaml`, `docker-compose.yml` |
| Prompt injection | Not considered: raw user text goes into prompts, and "memory-worthy" text from users is stored and re-injected into future prompts (including other users', see §8.1) | `memory_manager.py`, `nodes.py` |
| Cost abuse | No rate limit; each unauthenticated POST can trigger several paid LLM calls | §4 |
| Dependencies | Only the lockfile path is reproducible; no vulnerability scanning in repo | Phase 2 |

## 14. Testing Boundaries

Ava has no tests. The table says what a test architecture for this design would need; **no tests were written**.

| Boundary | Testable how | Needs a mock/fake? | Needs real external service? |
|---|---|---|---|
| Webhook GET verification | Unit test with FastAPI `TestClient` | No | No. *Done ad hoc in Phase 2* |
| Webhook POST routing (statuses, unknown, malformed, unsupported types) | Unit test with `TestClient` | The graph and WhatsApp client | No. *Done ad hoc in Phase 2 for several cases* |
| Payload parsing/normalisation | Pure-function unit tests (fixtures of real Meta payloads) | No | No |
| Signature verification (future) | Unit tests with known HMAC vectors | No | No |
| Idempotency (future) | Unit test with an in-memory store | Store | No |
| Graph wiring (nodes/edges) | Compile and inspect; run with fake LLM | Fake chat model, fake memory | No. *Compile check done in Phase 2* |
| Routing functions (`select_workflow`, `should_summarize_conversation`) | Pure unit tests | No | No |
| State reducers (e.g. string → `HumanMessage`) | Small unit tests | No | No. *One check done in Phase 3* |
| Memory manager logic (dedupe threshold, only-human rule) | Unit tests | Fake LLM, fake vector store | No |
| Vector store | Integration test against a real Qdrant (local container) or Qdrant's in-memory client | Embedding model can be real (no key) | Qdrant server for the integration level |
| LLM prompts/router quality | Evaluation set run against a real model; unit tests use a fake | Fake for unit level | Yes, for quality checks (API key, cost, rate limits) |
| WhatsApp outbound client | Unit tests with a fake HTTP transport (for example `httpx.MockTransport`) | HTTP | No |
| WhatsApp end to end | Manual or scripted run against a Meta test number | n/a | Yes: Meta app, token, public HTTPS URL |
| Provider failures | Fakes that raise errors/timeouts | Provider fakes | No |

What was tested in Phase 2: import checks, GET handshake, POST routing for statuses/unknown/malformed/location/text, token-in-stdout, graph compile, embedding model load. Those were throwaway probes, not a suite.

Design obstacles to testing in Ava: SDK clients and singletons are created at import time; the graph is compiled inside the handler; `WHATSAPP_*` read at import; settings require every key to exist. Injection (as ArchAgenticRAG does) removes most of these.

## 15. Ava Limitations

Grouped list (all evidenced above):

1. **Security:** no signature or auth; token printed to stdout; no rate limiting; no sender allow-list; prompt-injection exposure.
2. **Reliability:** inline processing, 500-on-error, no idempotency, single-message parsing, no fallback providers, memory outage breaks chat.
3. **Privacy/data:** global vector memory; no deletion; memory text may be logged.
4. **Correctness:** audio replies stored as human messages; dead `apply_activity` field; unused settings; hard-coded Whisper model; schedule uses server time zone.
5. **Maintainability:** hard-coded provider construction in many files; imports create live clients; graph recompiled per request; two config mechanisms.
6. **Operations:** four mandatory third-party accounts; `latest` Qdrant image; Graph API v21.0 retirement scheduled; deprecated model defaults; broken documented install.
7. **Scope fit:** a fictional-persona product; no document RAG; no tools; no handoff; no evaluation; no tests.
8. **Dev environment:** the ephemeral in-memory volume in `cloudbuild.yaml` means short-term memory is lost on every Cloud Run restart (code).

## 16. Ava vs ArchAgenticRAG

Full comparison: [WAZI_ARCHITECTURE_COMPARISON.md](WAZI_ARCHITECTURE_COMPARISON.md). Summary: they are **complementary and not interchangeable**. Ava is a messaging application with persistence and memory but no knowledge base, evaluation or tests. ArchAgenticRAG is a document-RAG pipeline with an evaluation harness and good testability, but no network surface, no sessions, no memory and no agentic behaviour yet. Concept-level lessons transfer both ways; code does not transfer without separate review. Candidate classifications for later: Ava webhook = REFERENCE then BUILD; Ava checkpointer idea = ADAPT; ArchAgenticRAG provider abstraction, Qdrant guards, grounded prompt, evaluation = ADAPT (or REUSE after approval); per-user isolation, tools, handoff = BUILD.

## 17. Wazi Architectural Boundaries

Your seven-layer list, and where each exists today.

| Layer | In Ava | In ArchAgenticRAG | Missing for Wazi |
|---|---|---|---|
| WhatsApp layer (Meta transport, send/receive) | **Yes**, mixed into the handler, unsafe | No | Hardened, separate client with response checking and retries |
| Messaging / Webhook layer (verify, parse, dedupe, ack) | **Partial**: GET verify + naive parse only | No | Signature check, normalisation, idempotency, fast ack, supported-type matrix |
| Agent orchestration layer | **Yes**: LangGraph workflow, no tools, persona-bound | Partial: 2-node RAG graph | Channel-neutral orchestrator, per-user threading, decisions about retrieval/tools |
| Memory layer | **Yes**, global | No | Per-user, deletable, bounded memory |
| RAG layer | **No** (memory only) | **Yes**, for a fixed corpus | Ingestion of Wazi's own documents, access control, source citation in WhatsApp-sized answers |
| LLM / Provider layer | **No** (scattered) | **Yes**, config-driven | Single provider module with fallback, cost and privacy controls |
| External tools layer | **No** | **No** | Tool registry, permissions, abuse limits |
| Cross-cutting: evaluation, observability, security logging | None | Evaluation yes, observability optional (Langfuse) | Conversation evaluation, redacted logging |

## 18. Proposed Wazi Target Architecture

**This is a design for discussion, not a decision and not implemented.** It is derived from the evidence in §3-§17, not copied from a template. Labels: **EXISTING** = present today in Ava or ArchAgenticRAG and could be a source; **PROPOSED** = recommended for the next implementation phases; **FUTURE** = later, only after earlier phases are reviewed.

```
WhatsApp user
     |
Meta Cloud API
     |  HTTPS
[1] Webhook endpoint                                        (EXISTING in Ava, unsafe -> PROPOSED rebuild)
     |   GET handshake (constant-time token, mode check)
     |   POST: read RAW body
[2] Security gate                                           (PROPOSED; absent in Ava)
     |   verify X-Hub-Signature-256 with the app secret, reject otherwise
     |   size/time/rate limits
[3] Ingress queue / fast ack                                (PROPOSED; option)
     |   200 immediately; idempotency by message id (dedupe store)
[4] Message normaliser                                      (PROPOSED)
     |   Meta payload -> InboundMessage{user_id, message_id, type, text|media_ref, timestamp}
     |   unsupported types handled explicitly; statuses ignored
[5] Orchestrator (LangGraph, per-user thread)               (EXISTING pattern in Ava -> ADAPT)
     |   checkpointer keyed by user_id; channel-neutral Reply object
     |
     +--> [6] Conversation memory   per-user, bounded, deletable        (PROPOSED; Ava pattern ADAPT + BUILD isolation)
     +--> [7] RAG / knowledge       separate store, access-controlled   (FUTURE Phase 5; ArchAgenticRAG concepts, needs approval)
     +--> [8] Tools                 registry + allow-list + limits      (FUTURE Phase 6)
     '--> [9] Human handoff        queue + staff reply path            (FUTURE, optional)
     |
[10] Provider layer                                          (PROPOSED; ArchAgenticRAG concept)
     |   chat / embeddings / speech / vector store, selected by config, with fallbacks
[11] Outbound WhatsApp client                                (EXISTING in Ava -> ADAPT)
     |   send/upload with status + error handling, retry of the SEND only
Meta Cloud API -> WhatsApp user

Cross-cutting: secrets management; redacted logging (no tokens, minimal message content);
               tests at every boundary; evaluation set; observability (FUTURE)
```

### Design rules (each traceable to a Phase 2/3 finding)

| Rule | Finding it answers |
|---|---|
| Verify the signature on the raw body before parsing | No signature in Ava (§5.3) |
| Acknowledge fast; process after; deduplicate by message id | Inline processing and no idempotency (§4, §5.3) |
| The orchestrator never sees Meta payloads; the WhatsApp layer never sees graph internals | Handler does everything in one function (ADR-003) |
| Every memory and RAG call requires a trusted `user_id` or an explicit access rule | Global collection (§8.1) |
| Knowledge (shared documents) and memory (personal facts) are separate stores | Different lifecycle and risk (ADR-003) |
| Only the provider layer knows vendors, models, keys | Provider drift (§10) |
| Construct dependencies once, inject them | Import-time clients block testing (§14) |
| Memory failure degrades, never breaks, a reply | §12 |
| Redact logs; never print secrets | `print(headers)` (§13) |
| No persona, voice or image features until requested | They are Ava's product, not Wazi's goal (ADR-001) |

### Open design questions for the mentor (not decided here)

1. Webhook framework and hosting model (a tunnel for development; where it runs later).
2. Whether to use a queue/background worker or in-process background tasks.
3. Where idempotency and per-user state live (SQLite, Postgres, Redis, Qdrant payloads).
4. Per-user filter inside one collection versus a collection per user.
5. Whether Wazi answers only the owner's documents or also per-user uploaded documents (a security-sensitive choice).
6. Whether voice and image input matter for Wazi at all.
7. WhatsApp costs: still unverified (Phase 1 §6.3).

## 19. Architectural Decisions

Proposed ADRs (status: awaiting mentor review):

| ADR | Title | One-line summary |
|---|---|---|
| [001](adr/001-ava-reference-foundation.md) | Ava is a reference foundation, not a production-ready base | Learn from Ava and reuse small, understood pieces; keep the baseline clone pristine |
| [002](adr/002-archagenticrag-separate-project.md) | ArchAgenticRAG remains a separate learning project | No package/copy/merge; concept reuse and a reviewed, approved selective adaptation later |
| [003](adr/003-layer-separation.md) | Wazi separates WhatsApp, Agent, Memory/RAG and Provider layers | Module boundaries inside one app; injected dependencies; user-scoped memory |

No further ADRs were written; per-user isolation is recorded as a rule inside ADR-003 rather than as a separate record.

## 20. Lessons Learned

1. **Read the state code, not just the graph.** The graph diagram looks clean; the state reveals a dead field and a string that silently becomes a user message.
2. **A diagram that is not checked is a hypothesis.** The PyWa diagram was wrong; the real flow has no signature step.
3. **"Per-user" has to be designed into every store.** Ava is per-user for conversation and global for memory; both look correct in a demo with one user.
4. **Do the work in the request, pay the retry tax.** Inline LLM chains plus 500-on-error is a recipe for duplicate replies. Acknowledging fast and deduplicating is a separate mechanism from the agent.
5. **Provider abstraction is not an architecture luxury;** the Phase 2 drift showed what it costs without it.
6. **Dead and unused configuration is a smell** (`QDRANT_PORT`, `STT_MODEL_NAME`, `apply_activity`): the repo grew from a course narrative, not from a design.
7. **ArchAgenticRAG's best contribution so far is habit, not code:** validated config, metadata guards, injection, evaluation.
8. **Phase 2 findings held up under a second, deeper read.** The signature gap, token print, global memory and `None == None` handshake case were all re-confirmed in code (§5.1, §8.1, §13). New in Phase 3: the string-to-`HumanMessage` state defect (§7.3), unused settings and the dead `apply_activity` field.

## 21. Phase 4 Recommendation

Phase 4 in the original roadmap is the "first controlled Wazi customization". I recommend that the mentor decide among these (not started):

- **Option A (recommended): Phase 2b first** (finish the blocked baseline: working Docker, minimal credentials, model names changed through environment only), so that the next phase starts from an observed, working reference instead of a read-only one.
- **Option B: start Phase 4 with a fully offline, testable slice** that needs no credentials: a *new* `webhook + signature gate + payload normaliser` in the Wazi repo, with unit tests using recorded Meta-style payloads, following ADR-003. This directly answers the biggest Ava gaps (§5.3, §12, §13), has no cost and no external dependency, and teaches the WhatsApp side properly. It would **not** touch Ava or ArchAgenticRAG. If chosen, the first step is a mini reuse check (pywa's validator, AleBrito's signature function) before writing anything.
- **Option C: defer memory/RAG** until the ingress boundary exists; per-user isolation (§8.1) should be designed together with Phase 7 but kept visible as a blocking requirement.

Whichever is chosen: decide the open design questions in §18 first, keep the reuse log, and keep Ava's clone pristine.

---

# Concepts I Learned

Plain-language explanations, checked against the Ava code above.

**What is a webhook?** A web address on *your* server that another service calls when something happens. Instead of your app asking Meta "any new messages?" over and over, Meta sends an HTTP request to your URL the moment a message arrives. In Ava that URL is `/whatsapp_response`.

**What is the WhatsApp Cloud API?** Meta's official way for software to send and receive WhatsApp messages for a business number. It has two directions: Meta calls your webhook to give you incoming messages; your code calls Meta's Graph API (here with `httpx`) to send replies. It needs a Meta app, an access token and a phone number id, and it has pricing rules that were not verified in this project.

**What is FastAPI doing?** It is the web framework that listens for HTTP requests and runs the Python function you attached to each URL. In Ava it receives the Meta request, hands it to `whatsapp_handler`, and returns the HTTP status Meta sees. It does no AI; it is the front door.

**What is LangGraph doing?** It runs a *graph* of steps. Each step ("node") is a Python function; arrows ("edges") say what runs next, and some arrows depend on a condition. LangGraph passes shared data between steps, can save it between runs, and gives you a way to draw and test the flow. In Ava it chains: remember, route, add context, add memories, reply.

**What is graph state?** The shared data that travels through the graph, like a clipboard passed from step to step. Ava's state holds the message list plus a few extra notes (`workflow`, `memory_context`, `summary`...). A node reads the clipboard and returns only the notes it wants to change. For the message list, "change" means *append*; for the others it means *overwrite*.

**What is memory?** Anything the system keeps so that later turns can use earlier information. Ava has two kinds: short-term (the recent conversation, saved by LangGraph in a SQLite file per user) and long-term (small facts about the user saved in Qdrant).

**What is vector memory?** Memory you search by *meaning* instead of exact words. Each fact is turned into a list of numbers (an embedding), and searching means "find stored facts whose numbers are closest to the numbers of what the user just said". So "I'm vegetarian" can be found when the user asks "what should I cook?".

**What is Qdrant?** A database built for vectors. You store points (a vector plus some data) in a *collection* and ask for the nearest ones to a query vector. Ava runs it as a Docker container, or you can use Qdrant's cloud service.

**What is an embedding?** A list of numbers (384 of them for Ava's model) that represents the meaning of a piece of text, produced by a model. Similar meanings give nearby lists, which is what makes similarity search possible. Ava creates them locally with `all-MiniLM-L6-v2`.

**What is RAG?** Retrieval-Augmented Generation. Before the AI answers, the system *retrieves* relevant passages from a document collection and puts them in the prompt, so the answer is based on those documents rather than only on what the model memorised. Steps: split documents into chunks → embed → store → at question time embed the question → fetch nearest chunks → generate the answer from them. Ava does not do this; ArchAgenticRAG does.

**What is the difference between RAG and memory?** Both retrieve text and put it in the prompt, so they look alike. The difference is *what is stored and who owns it*. RAG retrieves from a body of *documents* (shared knowledge such as manuals), usually loaded in advance. Memory stores *facts about this user's conversation* and grows as people talk. They have different lifecycles (documents are updated by owners; memories are created automatically), different privacy rules (memory is personal and must be isolated per user), and different failure modes. That is why the proposed Wazi design keeps them separate.

**What is a provider abstraction?** One small layer between your app and AI vendors. Your code says "give me a chat model" and the layer decides whether that means Groq, OpenRouter or a local model, with which key and model name. It means swapping vendors is a config change, tests can use a fake, and vendor shutdowns (like Ava's deprecated models) do not ripple through the code.

**Why do we need webhook signatures?** A webhook URL is public. Without a check, anyone who finds it can send fake "WhatsApp messages" that your app will believe. Meta signs each real request with a secret only you and Meta know (an HMAC over the raw body, sent in `X-Hub-Signature-256`). Your server recomputes it and rejects mismatches. The verify token used in the GET handshake only proves the URL is yours once; it does not authenticate later messages. Ava skips the signature check, so in Ava anyone can post as anyone (and trigger paid LLM calls).

**Why is idempotency important?** Networks fail, so Meta retries a delivery when it does not get a quick success response. If your app is not idempotent, the same message is processed twice: two replies, two LLM bills, duplicate memories. Idempotency means "doing it twice has the same effect as once", usually by remembering message ids you already handled. Ava has no such memory and, because it returns 500 on errors, it actively provokes retries.

**Why should users be isolated in vector storage?** Because search returns "closest by meaning", not "belongs to this person". If everyone's facts share one collection, one user's private facts can be retrieved and shown to another, and one user can plant false facts for others. Isolation means every stored item carries an owner and every search is filtered by that owner (or uses a separate collection per owner). It is a security rule, not an optimisation, and it only works if the owner identity is trustworthy, which is another reason for signature checking.
