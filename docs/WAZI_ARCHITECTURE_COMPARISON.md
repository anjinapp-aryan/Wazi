# Ava vs ArchAgenticRAG

Phase 3 comparison. **Concepts only.** No code was copied from either project and neither was modified. Ava was read at commit `338fd68` (`D:\WORK_SPACE\Wazi-baselines\ava`). ArchAgenticRAG was read from the local working copy `D:\WORK_SPACE\ArchAgenticRAG` at commit `f96c37c` (2026-10-14), which had uncommitted local changes in `README.md` and one learning-log file that I did not read or touch.

ArchAgenticRAG is the owner's independent **learning project**. It is not a production dependency of Wazi. Nothing here is a decision to import it; the classifications in §15 are *candidates for a later, mentor-approved phase*.

Evidence labels: **(code)** read from source; **(doc)** from a README/ADR; **(Phase 2)** observed in the Phase 2 baseline; **(not tested)** inferred.

---

## 1. Purpose

| | Ava | ArchAgenticRAG |
|---|---|---|
| What it is | A course project: a WhatsApp "companion" chatbot with a persona, voice and image replies (code, `core/prompts.py`) | A learning/portfolio project for Basic → Agentic RAG with an evaluation harness (README) |
| Main question it answers | "How do I connect WhatsApp to a LangGraph agent with memory?" | "How do I ingest documents, retrieve from Qdrant, answer with grounding, and measure whether it works?" |
| User interface | WhatsApp webhook and Chainlit chat | Command-line scripts (ingest, evaluate) |
| Current maturity | Finished course; not maintained since 2025-10 | In progress: Basic RAG and evaluation baseline done (README status table); agentic behaviour not yet built |

## 2. Architecture

**Ava** is an application: HTTP in, HTTP out.

```
Meta -> FastAPI route -> LangGraph (8 nodes) -> Groq/Qdrant/ElevenLabs/Together -> Graph API -> user
```

**ArchAgenticRAG** is a pipeline plus a test bench, with no network entry point.

```
corpus files -> docutils -> Docling HybridChunker -> FastEmbed -> Qdrant
question -> LangGraph (retrieve -> generate) -> answer + source documents
golden dataset -> runner -> Ragas/Langfuse scoring -> results/<run_id>/
```

Neither project has the other's layers: Ava has no document knowledge base or evaluation; ArchAgenticRAG has no messaging, sessions or memory.

## 3. LangGraph usage

| | Ava | ArchAgenticRAG |
|---|---|---|
| Graph | `StateGraph(AICompanionState)`, 8 nodes, 14 edges incl. 3 conditional sets (code, `graph/graph.py`) | `StateGraph(RAGState)`, 2 nodes, linear `START → retrieve → generate → END` (code, `graphs/basic_rag.py`) |
| Branching | LLM router chooses text/image/audio; summarise if > 20 messages | None yet |
| Loops / tools | None; no tool calling (Phase 2 grep) | None; reranker explicitly `None` (code, `settings.py`) |
| Build style | Module-level builder, **recompiled on every request** with a checkpointer | Factory function `build_graph(system, ...)` with injectable client, embeddings, LLM |
| Compile name / metadata | Unnamed | Named `basic_rag`, carries `eval_metadata` |

What each teaches: Ava shows a graph with *routing and persistence*; ArchAgenticRAG shows a graph designed to be *tested and measured* (dependency injection).

## 4. State management

| | Ava | ArchAgenticRAG |
|---|---|---|
| State type | `MessagesState` + 7 extra fields (`summary`, `workflow`, `audio_buffer`, `image_path`, `current_activity`, `apply_activity`, `memory_context`) | `TypedDict` with `question`, `documents`, `context`, `answer` |
| Persistence | SQLite checkpointer, `thread_id` = phone number (code) | None; each call is independent |
| Conversation history | Yes, in `messages` | No: single-turn Q&A |
| Quirks seen | `apply_activity` is written but never read; `audio_node` returns a plain string that LangGraph stores as a **HumanMessage** (verified, see Phase 3 doc §7) | Clean and minimal |

## 5. Qdrant usage

| | Ava | ArchAgenticRAG |
|---|---|---|
| Purpose | Long-term *user memory* facts | *Document knowledge* chunks |
| Collections | One fixed collection, `long_term_memory` | One collection per experiment, named in config |
| Client | `QdrantClient` used directly; calls `client.search` (removed in newer `qdrant-client`, Phase 2) | `qdrant-client` plus `langchain-qdrant`; uses current `query_points`-era APIs via the LangChain wrapper (not tested here) |
| Point ids | `uuid4` for new memories (and a `hash(text)` fallback that is never reached in the normal path) | Deterministic `uuid5(namespace, chunk_id)`, so re-indexing is idempotent |
| Collection metadata | None | Stores embedding model, dimension, chunking config, chunk count, timestamp; `open_store` refuses a collection whose metadata does not match the config |
| Safety checks | Existence check only | Dimension check, count-after-index check, config-mismatch errors |
| **Per-user filter** | **None** (Phase 2 finding, confirmed in code) | **Not applicable**: no concept of users |

## 6. Embeddings

| | Ava | ArchAgenticRAG |
|---|---|---|
| Library | `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dims), hard-coded | FastEmbed (ONNX, CPU) via LangChain; model from config (`BAAI/bge-small-en-v1.5`, 384 dims) |
| Weight | Pulls `torch` (large) | Lighter (ONNX runtime) |
| Configurable | No (class constant) | Yes, validated against the collection |

## 7. Retrieval

| | Ava | ArchAgenticRAG |
|---|---|---|
| Query | Last 3 messages joined into one string | The user's question |
| Method | Top-k (3) dense cosine search; similarity ≥ 0.9 used for de-duplication on write | Top-k (4) dense similarity; no hybrid, no rerank (config comment) |
| Result use | Bullet list injected into the persona prompt | Numbered passages with source labels injected into a "use only this context" prompt |
| Citations | None | Passage labels include `doc_id` and section; returned `documents` are used for source-recall scoring |

## 8. LLM provider abstraction

| | Ava | ArchAgenticRAG |
|---|---|---|
| Chat | `ChatGroq` constructed in `graph/utils/helpers.py` and again in `memory_manager.py`; Groq SDK also called directly for STT and vision | `providers.py`: presets for Ollama, Gemini, OpenRouter, NVIDIA, xAI, Groq, OpenAI, all via OpenAI-compatible endpoints; one `chat_model(provider, model, temperature)` factory |
| Model names | Defaults in `settings.py` (overridable by env), plus one hard-coded Whisper name | In the experiment YAML; validated at load |
| Swapping provider | Requires editing code in several modules | Change two config lines |
| Observed consequence | Three of Ava's default model IDs are deprecated or past shutdown (Phase 2) | Config comments record when each model/URL was verified |

Phase 2 shows why this matters: Ava's provider drift is painful precisely because the provider is woven through the code.

## 9. Memory

| | Ava | ArchAgenticRAG |
|---|---|---|
| Short-term | LangGraph SQLite checkpoint per phone number; summary after 20 messages | None |
| Long-term | LLM-judged facts in Qdrant; global, not per user | None |
| Deletion / expiry | None found | n/a |

Memory is entirely an Ava lesson.

## 10. Evaluation

| | Ava | ArchAgenticRAG |
|---|---|---|
| Evaluation | None | Golden QA dataset (versioned, with evidence-quote validation), Ragas metrics, optional Langfuse, run manifests with commit/config/dataset hashes, resumable runs for free-tier quotas (doc: `eval/README.md`) |

This is the largest conceptual gap in Ava and a strong lesson from ArchAgenticRAG: *"does it answer correctly?"* should be measured, not guessed. It would need adapting to measure **WhatsApp conversations** (multi-turn, per-user memory), which the current dataset does not cover.

## 11. Testing

| | Ava | ArchAgenticRAG |
|---|---|---|
| Automated tests | None (no `tests/`, no pytest) (Phase 2) | `tests/` with unit tests for settings, ingestion, vector store, basic RAG graph, and the evaluation code; plus `integration/` tests that need Qdrant or live keys. `grep "def test_"` finds 82 test functions |
| Were they run in Phase 3? | n/a | **No.** Counting test functions is not evidence they pass |
| Testability design | Hard: globals created at import, graph rebuilt per request, direct SDK calls | Easier: client, embeddings and LLM are injectable |

## 12. Security

| | Ava | ArchAgenticRAG |
|---|---|---|
| Untrusted input from the internet | Yes: unauthenticated webhook, no signature check, bearer token printed to stdout (Phase 2) | No network surface |
| Secrets | `.env`; Cloud Run deploy file uses Secret Manager (code, `cloudbuild.yaml`) | `.env` with `api_key_env` indirection, `.env.example` placeholders only (code) |
| Prompt injection | Not considered; user text goes directly into prompts and into memory writes | Corpus is a fixed set of public PEPs; user queries only |
| Data isolation | None between users | n/a |

ArchAgenticRAG's security posture is simply "no attack surface yet". That will change the moment it sits behind WhatsApp.

## 13. What Ava teaches

1. How a Meta webhook handshake and payload look in real code.
2. Persisting a conversation per user with a LangGraph checkpointer.
3. Using an LLM as a router (structured output) and as a memory classifier.
4. Short-term vs long-term memory as separate mechanisms.
5. What breaks when you do not pin dependencies or abstract providers.
6. (Negative lessons, equally valuable) signature checking, idempotency, user isolation and log hygiene are *not* optional.

## 14. What ArchAgenticRAG teaches

1. A complete document RAG pipeline: parse → chunk → embed → store → retrieve → grounded answer.
2. Treating configuration as validated, versioned data.
3. Provider abstraction through OpenAI-compatible endpoints.
4. Index/config consistency checks (collection metadata).
5. Evaluation: golden dataset, metrics, reproducible run manifests.
6. Dependency injection for testability.
7. How to record where every external fact was verified (dates in config comments).

## 15. What Wazi eventually needs

| Wazi need | Ava has | ArchAgenticRAG has | Candidate classification (for a later phase) |
|---|---|---|---|
| Webhook, message parsing | Yes, unsafe | No | Ava: **REFERENCE** now, then **BUILD** a hardened version (patterns from Phase 1's AleBrito/pywa review) |
| LangGraph orchestration with per-user persistence | Yes | Partial (graph, no persistence) | Ava pattern: **ADAPT** |
| Short-term memory | Yes | No | **ADAPT** the checkpointer idea |
| Long-term per-user memory | Yes, not isolated | No | **ADAPT** the idea, **BUILD** the isolation |
| Document ingestion and chunking | No | Yes (Docling + PEP-specific preprocessing) | **REFERENCE** first. The PEP-specific code does not transfer; the chunking approach might. Decide in the RAG phase |
| Embeddings | MiniLM via torch | FastEmbed | **REFERENCE**, choose once; avoid carrying two stacks |
| Qdrant collection management and guards | Minimal | Strong | **ADAPT** (concept: metadata guards, deterministic ids) |
| Retrieval + grounded generation prompt | No | Yes | **ADAPT** |
| Provider abstraction | No | Yes | **ADAPT** or **REUSE** after a mentor decision |
| Evaluation harness | No | Yes | **ADAPT** for conversational/WhatsApp cases |
| Tests | No | Yes | **REFERENCE** (patterns) |
| Tool calling, human handoff | No | No | **BUILD** (after a reuse audit for each) |
| Wazi-specific prompts, routing, access rules | No | No | **BUILD** |

Do not read this table as "import ArchAgenticRAG". The two projects have different goals; dependency versions already differ (Ava pins `langgraph>=0.2.60`, `pydantic==2.10.0`; ArchAgenticRAG pins `langgraph==1.2.12` and `qdrant-client==1.19.1`, which no longer has Ava's `.search()` call). Every reuse step needs its own review, license/notice check and mentor approval.
