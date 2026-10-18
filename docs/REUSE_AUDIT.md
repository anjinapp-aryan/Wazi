# Wazi Phase 1: GitHub / Open-Source Reuse Audit

Status: Phase 1 deliverable, awaiting mentor review. Date of all repository data: **2026-10-18**.
Governing document: [PROJECT_CONSTITUTION.md](PROJECT_CONSTITUTION.md). Rule applied: **REUSE → ADAPT → COMPOSE → BUILD**.

---

## 0. Executive summary

1. **No single mature open-source project provides most of Wazi.** Nothing found combines the official WhatsApp Cloud API, a LangGraph agent, document RAG on Qdrant, memory, tool calling, human handoff, tests and Docker in one maintained, permissively licensed repo. Wazi will be a composition.
2. **Recommended foundation for Phase 2: `neural-maze/ava-whatsapp-agent-course`** (MIT). It is the only candidate that already matches the target architecture end to end (WhatsApp Cloud API → FastAPI webhook → LangGraph → Qdrant + SQLite memory → WhatsApp reply, with Docker Compose). It is a *course* project, so it has real gaps (no tests, no webhook signature check, stale since 2025-10). Those gaps are known and are filled by composing other sources in later phases.
3. **This recommendation overrides the numeric ranking** (Ava scores 59/100, 4th). Section 10 explains why, and flags it as a decision for the mentor.
4. **RAG should not be rebuilt.** The developer's own `ArchAgenticRAG` repo already has Docling → FastEmbed → Qdrant → LangGraph retrieve/generate, a provider abstraction and an evaluation harness. It is the planned RAG source (ADAPT/COMPOSE) in Phase 5.
5. **Hardening patterns come from two other MIT sources:** `AleBrito124356/whatsapp-ai-agent` (signature check, idempotency, handoff, dry-run, tests) as a REFERENCE/ADAPT-small source, and `david-lev/pywa` as an optional COMPOSE replacement for hand-written WhatsApp API code.

### Honest limits of this audit

- Search was done mainly with the GitHub search API (about 25 keyword queries) plus two web searches. Awesome-lists, blog posts and other forges were **not** systematically searched. A good project with poor GitHub keywords could have been missed.
- Repository metrics come from the GitHub API on 2026-10-18. Capability ratings come from reading files via the API. **I did not clone, install or run any candidate**, and I did not execute any candidate's tests. "Tests exist" is not "tests pass".
- README claims are labelled as claims unless the code was also read.
- Where I did not read a file, the rating is UNKNOWN or marked provisional.

---

## 1. Method

### 1.1 Search strategy

| Step | What was done |
|---|---|
| Repo search | `gh search repos` with ~25 keyword combinations (whatsapp + langgraph / rag / agent / agentic / llm / mcp / cloud api / qdrant / chatbot / openai / langchain / human handoff, plus chatwoot, pywa). Long queries return almost nothing, so short ones were used. |
| Metadata | `gh api repos/<r>`: stars, forks, license, push date, archived flag, releases, open issues. |
| Structure | Recursive file tree of each serious candidate (tests, CI, Docker, config). |
| Code reading | Webhook handlers, agent graph, vector store, security code, dependency files, README. |
| Code search | GitHub code search inside a repo (e.g. `hmac`, `bind_tools`) to confirm absence of features. |
| Licences | Read the actual LICENSE files for Chatwoot, Evolution API, lgesuellip; used the API licence field for the rest. |
| Official sources | Web search for Meta's webhook-signature and pricing documentation. |

### 1.2 What the search did not find

No repository combining *official Cloud API + LangGraph + document RAG + Qdrant + tests* was found. Queries like "whatsapp agent qdrant" and "whatsapp cloud api ai agent langgraph" returned zero repositories. Most hits have 0 to 10 stars, no licence, or use unofficial WhatsApp Web automation.

### 1.3 Candidates considered

| Candidate | Why considered | Outcome |
|---|---|---|
| neural-maze/ava-whatsapp-agent-course | LangGraph + Cloud API + Qdrant | Shortlist, recommended foundation |
| AleBrito124356/whatsapp-ai-agent | Cloud API, signed webhook, handoff, tests | Shortlist |
| david-lev/pywa | Mature Cloud API library | Shortlist (COMPOSE) |
| sarrazola/openlivery | Full agent platform, Cloud API, tools, KB | Scored highest; fails scope gate |
| cleven12/whatsapp-ai-assistant | Cloud API + RAG + Docker | Scored, not shortlisted |
| lgesuellip/langgraph-whatsapp-agent | LangGraph supervisor + MCP | Scored, not shortlisted |
| marketcalls/ragbot | Agentic RAG, WhatsApp | Scored, rejected for WhatsApp method |
| lucasboscatti/Whatsapp-Langgraph-Agent-Integration | LangGraph + WhatsApp | No licence, unofficial API |
| chatwoot/chatwoot | Human-handoff inbox | Out of scope, noted |
| evolution-foundation/evolution-api | WhatsApp gateway | Not shortlisted, noted |
| anjinapp-aryan/ArchAgenticRAG | The developer's own RAG project | Reuse source for Phase 5 |

---

## 2. Repository health (checked 2026-10-18)

Stars are one signal only. "Open issues" is GitHub's count (issues + PRs).

| Repo | ★ | Forks | Created | Last push | Latest release | Open | Archived | Licence (GitHub) |
|---|--:|--:|---|---|---|--:|---|---|
| neural-maze/ava-whatsapp-agent-course | 1681 | 418 | 2024-12-17 | 2025-10-20 | none | 7 | no | MIT |
| AleBrito124356/whatsapp-ai-agent | 8 | 1 | 2026-07-19 | 2026-09-23 | none (has CHANGELOG) | 0 | no | MIT |
| david-lev/pywa | 597 | 113 | 2023-06-11 | 2026-10-16 | 4.5.0 (2026-09-24) | 9 | no | MIT |
| sarrazola/openlivery | 68 | 49 | 2026-08-14 | 2026-10-16 | v0.4.0 (2026-08-31) | 0 | no | MIT |
| cleven12/whatsapp-ai-assistant | 3 | 2 | 2026-05-31 | 2026-06-24 | v1.0.0 (2026-06-24) | 0 | no | MIT |
| lgesuellip/langgraph-whatsapp-agent | 243 | 99 | 2025-04-11 | 2025-06-10 | none | 1 | no | Apache-2.0 (+ MIT in `src/`) |
| marketcalls/ragbot | 2 | 0 | 2026-08-10 | 2026-08-10 | none | 0 | no | MIT |
| lucasboscatti/Whatsapp-Langgraph-Agent-Integration | 128 | 36 | 2025-02-23 | 2025-02-23 | none | 1 | no | **none** |
| chatwoot/chatwoot | 37911 | 9242 | 2019-08-14 | 2026-10-18 | v4.18.0 (2026-09-18) | 1600 | no | MIT except `enterprise/` (GitHub: NOASSERTION) |
| evolution-foundation/evolution-api | 9876 | 7357 | 2023-06-09 | 2026-07-14 | 2.3.7 (2025-12-05) | 241 | no | Apache-2.0 + extra conditions (GitHub: NOASSERTION) |
| anjinapp-aryan/ArchAgenticRAG (own) | 0 | n/a | n/a | 2026-10-14 | none | n/a | no | **no LICENSE file** (pyproject says MIT) |

Health observations (evidence-based):

- **Ava:** ~12 months since the last push. Open PRs show provider drift: "Together AI has terminated the free tier" (#40), "updated deprecated Groq models" (#43), "refresh provider defaults" (#50), "Stop logging WhatsApp response payloads" (#49). Not archived, but not actively maintained.
- **AleBrito:** Active, but only ~3 months old, one author, 8 stars. Too young to call proven.
- **pywa:** Healthy. Release 4.5.0 on 2026-09-24, commits through late September, 65 test files, a test workflow. The most recent `dev` branch run (2026-10-16) is a **failure**, the previous runs (2026-10-13, Dependabot branches) succeeded. I did not investigate why.
- **cleven12:** 1,061 commits in about four weeks of repo life, plus a `CONTRIBUTION_ACTIVITY.md` file. That pattern is consistent with inflated activity; I treat commit count as non-evidence for this repo. It is also "open core" (paid Pro features).
- **OpenLivery / ragbot / AleBrito:** All created in mid-2026, so "healthy activity" is partly just "new".

---

## 3. Licence audit

| Repo | Exact licence | Evidence | Permits our use? | Attribution | Class |
|---|---|---|---|---|---|
| Ava | MIT | LICENSE in tree; GitHub API `MIT` | Yes (copy, modify, redistribute) | Keep copyright + licence notice | **SAFE TO REUSE** |
| AleBrito | MIT | LICENSE in tree | Yes | Keep notice | **SAFE TO REUSE** |
| pywa | MIT | LICENSE, `license = "MIT"` in pyproject | Yes (as a dependency) | Notice if code is copied | **SAFE TO REUSE** |
| OpenLivery | MIT | LICENSE in tree | Yes | Keep notice | SAFE TO REUSE (but out of scope) |
| cleven12 | MIT | LICENSE in tree | Yes for the free core; Pro features are separate paid offerings | Keep notice | REUSE WITH CONDITIONS (open-core) |
| lgesuellip | Apache-2.0 (root) and MIT (`src/LICENSE`, "Copyright 2024 lgesuellip") | Both files read; README only says "terms in the LICENSE file" | Probably yes, but two different licences in one repo is ambiguous | Apache needs NOTICE/changes statement | REUSE WITH CONDITIONS |
| ragbot | MIT | LICENSE in tree | Yes | Keep notice | SAFE TO REUSE (rejected for other reasons) |
| lucasboscatti | **None** | API returns 404 for licence | **No** | n/a | **REFERENCE ONLY**, do not copy code |
| Chatwoot | MIT Expat for everything outside `enterprise/`; `enterprise/` has its own licence | LICENSE header read | Core yes; enterprise dir no without review | Keep notice | REUSE WITH CONDITIONS |
| Evolution API | Apache-2.0 **plus** extra conditions: must display a usage notice if used in any project; cannot remove logo/copyright from its frontend; otherwise commercial licence may be needed | LICENSE read | Conditional | Mandatory usage notification | REUSE WITH CONDITIONS |
| ArchAgenticRAG (own) | pyproject says MIT; **no LICENSE file** in repo | tree listing | The developer owns the code, so own reuse is fine | n/a for self | Action item: add LICENSE file before others reuse it |

Note: GitHub reports `NOASSERTION` for Chatwoot and Evolution because their LICENSE files are non-standard, which is why the files were read directly.

---

## 4. Scoring model

### 4.1 Dimensions and weights

The suggested weights were kept. Each dimension is scored 0 to 5 and converted to a weighted total out of 100.

| Dimension | Weight | What a 5 means | What a 0 means |
|---|--:|---|---|
| WhatsApp integration | 20 | Official Cloud API, signature verification, idempotency, media, session handling | None or unofficial-only |
| Agent architecture | 15 | LangGraph or equivalent, state, tool calling, decision making | No agent loop |
| RAG capability | 15 | Ingestion, chunking, embeddings, vector store, retrieval, grounding | No retrieval |
| Code quality | 10 | Clear structure, error handling, config, logging | Messy or prototype |
| Maintenance | 10 | Recent releases and commits, issues handled | Stale or abandoned |
| Licence suitability | 10 | Permissive, clear | None or restrictive |
| Testing | 5 | Real automated tests in repo, CI | None found |
| Documentation | 5 | Setup, architecture, how-to | README only or none |
| Docker / self-host | 5 | Compose file, documented | None |
| Extensibility | 5 | Easy to adapt to Wazi's scope | Locked to one domain or huge |

### 4.2 Results

| Rank | Repo | WA | Agent | RAG | Qual | Maint | Lic | Test | Docs | Dock | Ext | **Total** |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | OpenLivery* | 4 | 3 | 3 | 4 | 4 | 5 | 3 | 5 | 4 | 2 | **74** |
| 2 | AleBrito | 5 | 2 | 2 | 4 | 3 | 5 | 4 | 4 | 3 | 3 | **70** |
| 3 | pywa† | 5 | 0 | 0 | 5 | 5 | 5 | 4 | 5 | 1 | 5 | **65** |
| 4 | **Ava** | 4 | 3 | 1 | 3 | 2 | 5 | 0 | 4 | 4 | 3 | **59** |
| 5 | cleven12* | 3 | 1 | 3 | 2 | 3 | 4 | 3 | 4 | 4 | 2 | **55** |
| 6 | ragbot | 1 | 3 | 4 | 2 | 1 | 5 | 0 | 3 | 0 | 2 | **46** |
| 7 | lgesuellip | 2 | 4 | 1 | 2 | 1 | 4 | 0 | 3 | 1 | 3 | **44** |
| 8 | lucasboscatti | 1 | 3 | 0 | 2 | 0 | 0 | 0 | 3 | 0 | 2 | **22** |

\* Provisional: scored from README, file tree and licence only; code not read in depth.
† pywa is a library, not an agent. It scores 0 on agent/RAG by design. It is scored to show where it stands, but it is classified as a COMPOSE component, not a foundation.

The arithmetic is in a small script (scratchpad, not part of the repo): total = Σ(weight × score) / 5.

### 4.3 Scope gate (added after scoring)

The rubric measures quality, not **fit for a beginner's learning project**. I added a pass/fail gate that is applied after scoring:

1. Can the architecture be understood end to end by a beginner in a few sessions?
2. Does it use the official WhatsApp Cloud API (not WhatsApp Web automation)?
3. Is the licence clear and permissive?

OpenLivery passes 2 and 3 but **fails 1**: it is a multi-tenant agency SaaS with a FastAPI backend, a Next.js frontend, a Go whatsmeow bridge, PostgreSQL, a Caddy gateway and a white-label portal. It would hide the very architecture Wazi is meant to teach. It becomes REFERENCE.

---

## 5. Per-candidate capability matrix

Legend: **Y** yes (verified in code or tree), **P** partial, **N** no, **?** unknown (not verified), (c) = README claim only, code not read.

| Capability | Ava | AleBrito | pywa | OpenLivery | cleven12 | lgesuellip | ragbot | lucasboscatti |
|---|---|---|---|---|---|---|---|---|
| WhatsApp Cloud API (official) | **Y** | **Y** | **Y** | Y (c) + unofficial QR option | Y (partly read) | **N** (Twilio) | **N** (unofficial) | **N** (unofficial wppconnect) |
| Webhook GET verification | **Y** | Y (c) | Y | Y (c) | **Y** | via Twilio | n/a | n/a |
| Webhook POST signature check | **N** (0 `hmac`/`signature` hits) | **Y** (code read) | **Y** (`hmac` hits in `pywa/server.py`, tests exist) | Y (c) "signed webhooks" | **N** found in `app/` | Twilio request validation (c) | n/a | n/a |
| Idempotent / duplicate handling | **N** | Y (c) | ? | ? | ? | ? | ? | ? |
| Receive messages | Y (text, audio, image) | Y | Y | Y | Y | Y (text + images) | Y (self only) | Y |
| Send messages | Y (text, audio, image) | Y (buttons, lists) | Y | Y | Y | Y | Y | Y |
| Templates | N | ? | Y | ? | ? | N | N | N |
| LLM integration | Y (Groq, Together, ElevenLabs) | Y (NVIDIA NIM, optional) | n/a | Y (OpenRouter) | Y (multi-LLM router) | Y (Gemini/OpenAI) | Y (LiteLLM) | Y (Groq) |
| Agent orchestration | **P** | **P** (state machine) | N | P (own engine) | N | **Y** (supervisor + react) | Y (Agno) | P |
| LangGraph | **Y** (`StateGraph`, 8 nodes) | N | N | N | N | Y | N | Y |
| Document RAG (ingest/chunk/embed/retrieve) | **N** | **P** (BM25 over markdown, no embeddings) | N | Y (c) | P (Pinecone, not read) | N | Y (anydoc → Chroma, README) | N |
| Vector DB | **Y** Qdrant, but for memory only | N | N | JSON embeddings in Postgres (c) | Pinecone | N | ChromaDB | N |
| Qdrant | **Y** (memory) | N | N | N | N | N | N | N |
| Conversation memory | **Y** (SQLite checkpointer + Qdrant long-term facts) | Y (SQLite transcript) | N | Y (c) | Y (SQLAlchemy, c) | Y (LangGraph threads, c) | Y (SQLite) | Y (Postgres) |
| Tool calling | **N** (0 hits: `bind_tools`, `ToolNode`, `create_react_agent`) | N | N | Y (HTTP tools, MCP) (c) | N | **Y** (MCP tools) | Y (Agno) | ? |
| MCP | N | N | N | Y (c) | N | Y | N | N |
| Human handoff | N | **Y** (queue + staff reply, c + file layout) | N | Y (inbox takeover, c) | N | N | N | N |
| Docker / compose | **Y** (compose: qdrant, chainlit, whatsapp) | P (Dockerfile only) | N | Y | Y | N (LangGraph Platform) | N | N |
| Tests in repo | **N** (no tests dir in tree) | **Y** (~20 test files + golden files) | **Y** (65 test files, CI) | Y (~86 test-named files) | P (3 test files) | **N** (only empty `__init__.py`) | N | N |
| CI | N | ? | Y (`tests.yml`) | Y (`.github`) | Y (Dependabot + workflows) | N | N | N |
| Observability | N | P (logs) | N | P (cost reports) | N | Y (LangSmith, c) | N | N |

---

## 6. WhatsApp-specific audit

### 6.1 Official vs unofficial

| Approach | Candidates | Risk |
|---|---|---|
| **Official Meta Cloud API** | Ava, AleBrito, pywa, cleven12, OpenLivery (option) | Requires a Meta developer app and business setup; message pricing applies (see §6.3) |
| **Via a reseller (Twilio)** | lgesuellip | Extra vendor and cost; not the Meta API directly |
| **Unofficial WhatsApp Web automation** (wppconnect, whatsmeow, Baileys, `wars`) | lucasboscatti, ragbot, OpenLivery QR mode, Evolution (Baileys mode) | **Flagged risky.** Violates WhatsApp terms in typical business use, can lead to number bans, and breaks when WhatsApp changes the web protocol. Not suitable for Wazi. |

### 6.2 Ava's WhatsApp handler (code read: `whatsapp_response.py`)

| Item | Finding |
|---|---|
| API | Official Cloud API (`graph.facebook.com/v21.0/...`). The API version is hardcoded. Whether v21.0 is still accepted by Meta today was **not verified**. |
| GET verification | `hub.verify_token` compared with `==` to an env var, returns `hub.challenge`. Works. Not constant-time (low impact for a verify token). |
| POST signature (`X-Hub-Signature-256`) | **Not implemented.** Any caller who knows the URL can post fake messages. |
| Duplicate handling | None. Meta retries deliveries. The handler returns HTTP 500 on any exception, which invites retries and duplicate replies. |
| Incoming types | text, audio (transcribed), image (described). Any other type falls into the `else` branch and reads `message["text"]["body"]`, which would raise for e.g. location/sticker, causing a 500 and a retry. |
| Outgoing | text, audio, image via the Graph API. |
| Sessions | `thread_id = sender phone number`, stored in an SQLite LangGraph checkpointer. |
| Templates | None. |
| Rate limiting | None. |
| Per-request cost | Re-opens SQLite and recompiles the graph on every webhook call. Fine for a demo, not for load. |
| Processing model | Handles the LLM call inside the webhook request (slow calls risk Meta timeouts/retries). |

### 6.3 Official-source checks

- **Webhook signing.** Several third-party guides and SDK docs agree: Meta signs POSTs with HMAC-SHA256 using the App Secret in `X-Hub-Signature-256`; verify over the raw bytes; use a constant-time compare; this is separate from the GET verify-token handshake. The search did **not** return Meta's own page, so the exact wording should be confirmed against Meta's "validate payloads" documentation in Phase 2/9.
- **Pricing.** Meta's pricing page states service conversations have been free since 2024-11-01. Third-party sites claim a change from 2026-10-01 (one says all service messages become paid; another says the first 1,000 per number per month stay free). These conflict and are **unverified**. Treat WhatsApp cost as **UNVERIFIED** until checked on Meta's rate card in Phase 2. Whether a free test phone number exists was not confirmed by this search.

### 6.4 AleBrito's WhatsApp layer (code read: `security.py`; rest from README)

`app/security.py` implements `X-Hub-Signature-256` correctly in about 30 lines (HMAC-SHA256 over raw bytes, `hmac.compare_digest`, fails closed when no secret is set). The README also claims idempotent ingestion (message ids in SQLite), a 200-immediately-then-background-task model, a 24-hour-window rule, opt-out handling and a no-credentials dry-run mode. Those are README claims; I read only the signature file.

### 6.5 pywa

A typed Python library for the Cloud API: send/receive, interactive messages, templates, flows, listeners, FastAPI/Flask integration, sync and async. Signature validation code exists (`pywa/server.py`, `pywa/utils.py`) with tests (`tests/test_server.py`).

---

## 7. Agent / RAG audit

### 7.1 Ava: is it "agentic"? Is it RAG?

| Question | Finding |
|---|---|
| State management | `AICompanionState` with LangGraph `StateGraph`; SQLite checkpointer per phone number. **Yes** |
| Agent loop | Linear pipeline: memory extraction → router → context injection → memory injection → {conversation, image, audio} → optional summarisation. The router chooses the *response modality*; there is **no loop** where the model chooses tools. |
| Tool selection / function calling | **None** (zero hits for `bind_tools`, `ToolNode`, `create_react_agent`). |
| Planning | None. |
| Long-term memory | An LLM (`with_structured_output(MemoryAnalysis)`) decides if a user message is memory-worthy, then stores it in Qdrant (`all-MiniLM-L6-v2` via sentence-transformers, similarity threshold 0.9 to avoid duplicates). This is *personal memory*, not document RAG. |
| Document ingestion, chunking, reranking, citations | **None.** |

Verdict: Ava is a **LangGraph conversational agent with vector memory**, not Agentic RAG. That is acceptable for Phase 2 (it teaches the WhatsApp ↔ LangGraph ↔ Qdrant plumbing). RAG and tools are Phase 5 and 6 work.

### 7.2 Others

- **lgesuellip:** a genuine tool-calling multi-agent template (supervisor, ReAct agent, MCP via `langchain-mcp-adapters`). Twilio-based, stale, no tests. Useful as a **REFERENCE for Phase 6** tool design.
- **ragbot (marketcalls):** An Agno agent decides whether to search a ChromaDB knowledge base (per README). Closest to "agentic RAG" on paper, but two commits old, no tests, single-user, and unofficial WhatsApp Web. **REFERENCE** for the pattern only.
- **AleBrito:** BM25 retrieval over a small markdown KB with a 40-question labelled retrieval check (README claims 18/40 → 38/40). Not embeddings, not agentic. Interesting for its evaluation habit.
- **cleven12:** README describes RAG over Pinecone. Retriever not read. Not agentic. Pinecone is not on our candidate list.

---

## 8. The existing ArchAgenticRAG project (read-only inspection)

Source: `github.com/anjinapp-aryan/ArchAgenticRAG` (public, pushed 2026-10-14, 76 files). **Not modified.**

| Wazi need | What ArchAgenticRAG has | Reuse type |
|---|---|---|
| Document ingestion | `rag/ingest.py`, `rag/ingestion.py` using Docling | ADAPT |
| Chunking | Docling chunking (`feat-chunking`) | ADAPT |
| Embeddings | FastEmbed (local ONNX) | REUSE |
| Vector DB | Qdrant (`qdrant-client`, `langchain-qdrant`, compose file) | REUSE |
| Retrieval + generation | LangGraph `retrieve → generate` in `graphs/basic_rag.py`, with a grounded system prompt and source labels in context | ADAPT |
| Provider abstraction | `providers.py`: one OpenAI-compatible client for Ollama, Gemini, OpenRouter, NVIDIA, xAI, Groq, OpenAI | REUSE |
| Evaluation | Ragas + Langfuse harness, golden dataset, runners | ADAPT (Phase 8) |
| Tests | `tests/` (rag, evaluation, integration) | pattern reuse |
| Agentic behaviour | **Not yet.** It is "Basic RAG". The agentic parts are future phases of that project | BUILD (shared) |

Compatibility notes:

- Both use **LangGraph** and **Qdrant**, so Ava's Qdrant memory and ArchAgenticRAG's Qdrant knowledge base can share one server (separate collections).
- Version pins differ: ArchAgenticRAG pins `langgraph==1.2.12`, Ava requires `langgraph>=0.2.60` (an old floor) and `pydantic==2.10.0`. Embedding stacks differ (FastEmbed vs sentence-transformers + torch). These need a deliberate reconciliation in Phase 5. Rating: MEDIUM risk.
- ArchAgenticRAG has **no LICENSE file** (pyproject says MIT). It is the developer's own code, so reuse is allowed, but add a LICENSE file and keep `THIRD_PARTY_NOTICES.md` current before copying code into Wazi's public repo.
- Docling is a heavy dependency; Wazi's Phase 5 must decide whether WhatsApp-scale use justifies it. Do not decide now.

---

## 9. Shortlist

### 9.1 Ava (`neural-maze/ava-whatsapp-agent-course`): **ADAPT** (recommended foundation)

| | |
|---|---|
| Gives Wazi | Working Cloud API webhook (text/audio/image), LangGraph pipeline, Qdrant vector memory, SQLite conversation memory, Chainlit local chat UI (test the graph without WhatsApp), Docker Compose, a written course, a `langgraph.json` for LangGraph Studio |
| Must modify | Remove the "Ava" companion persona, ElevenLabs/Together image features if not wanted; add webhook signature check, idempotency, 200-fast-then-background processing; update deprecated Groq models/provider defaults; unpin or reconcile dependencies; stop logging payloads |
| Still to build/compose | Document RAG, tools, tests, human handoff, evaluation, rate limiting, deployment hardening |
| Strengths | Closest match to target architecture; MIT; 1.7k stars/418 forks means many people have run it; educational docs; small enough to read (about 20 source files) |
| Weaknesses | No tests; no signature check; stale 12 months; provider drift; heavy install (`torch`, `sentence-transformers`); free-tier claims in README are partly outdated (#40) |
| Licence | MIT, SAFE TO REUSE |
| Health | Not archived; last push 2025-10-20; no releases |
| Learning value | **High**: end-to-end flow, LangGraph state, memory design |
| Risk | MEDIUM (see §12) |
| Classification | **ADAPT** |

### 9.2 AleBrito (`AleBrito124356/whatsapp-ai-agent`): **REFERENCE** now, selective ADAPT later

| | |
|---|---|
| Gives Wazi | A model of a hardened webhook: signature verification (code read), claimed idempotency, background processing, handoff queue, opt-out, dry-run mode, golden-file tests |
| Must modify | Almost everything domain-specific (barbershop booking, ES/EN, SQLite state machine). Only `security.py`-style pieces are directly portable |
| Still to build | LangGraph, vector RAG, tool calling |
| Strengths | Best engineering discipline of all candidates; runs offline without keys (`python -m app chat`, per README); MIT; mentions dry-run so you can test without Meta |
| Weaknesses | 3 months old, 8 stars, one author, domain-locked; not LangGraph/Qdrant; claims not independently verified; tests not run by me |
| Licence | MIT, SAFE TO REUSE |
| Learning value | **High for security/reliability** (Phase 9), lower for agent/RAG |
| Risk | MEDIUM (young, single maintainer) |
| Classification | **REFERENCE** (learn the patterns), with small **ADAPT** of the signature function (with MIT attribution) |

### 9.3 pywa (`david-lev/pywa`): **COMPOSE** (optional)

| | |
|---|---|
| Gives Wazi | A maintained, typed, tested Cloud API client and webhook server (FastAPI/Flask integration), signature validation, templates, interactive messages, listeners |
| Must modify | Nothing; it is a dependency |
| Still to build | Everything above the transport layer |
| Strengths | Active (release 2026-09-24), 65 test files, MIT, good docs; would replace Ava's hand-written `httpx` code |
| Weaknesses | Not an agent; adds a significant dependency and abstraction that hides the raw webhook/Graph API calls the developer is supposed to learn; latest `dev` CI run failed on 2026-10-16 (cause not checked) |
| Licence | MIT, SAFE TO REUSE |
| Learning value | Medium: speeds work but hides the protocol, so use it **after** the raw protocol is understood (Phase 3) |
| Risk | LOW-MEDIUM |
| Classification | **COMPOSE** (decision deferred to Phase 4) |

### 9.4 ArchAgenticRAG (own): **ADAPT / COMPOSE** for Phase 5

See §8. Not scored on the WhatsApp-centred rubric because it has no WhatsApp layer.

### 9.5 Considered but not shortlisted

| Repo | Class | Reason |
|---|---|---|
| OpenLivery | **REFERENCE** | Top rubric score (provisional), but fails the scope gate (§4.3). Worth reading later for tool/MCP design, SSRF guard, per-tenant isolation ideas. |
| cleven12 | **REFERENCE** | Open-core, Pinecone (not Qdrant), no signature check found, suspicious commit pattern. |
| lgesuellip | **REFERENCE** | Good tool-calling template, but Twilio, stale, no tests, mixed licences. Use for Phase 6 ideas. |
| ragbot | **REJECT** (as foundation) / REFERENCE (agentic RAG pattern) | Unofficial WhatsApp Web, single user, two commits, no tests. |
| lucasboscatti | **REFERENCE ONLY** | **No licence.** Do not copy code. Also unofficial (wppconnect). |
| Chatwoot | **REFERENCE** (Phase 6+ handoff idea) | Full Ruby/Rails helpdesk with 1,600 open issues. Far too large. Noted as the established open-source option if real human-agent inbox is ever needed. |
| Evolution API | **REJECT** for now | Mixed Baileys (unofficial) and Cloud API gateway; non-standard licence with mandatory usage notification; 241 open issues. Not needed if we talk to the Cloud API directly. |

---

## 10. Recommended foundation and why it overrides the score

**Ava is recommended even though the rubric ranks it 4th.** The reasoning, stated so the mentor can overrule it:

- The rubric rewards *current* quality. OpenLivery fails the scope gate. AleBrito and pywa score higher mostly because of WhatsApp hardening, tests and maintenance, which are exactly the things Wazi's later phases (8 and 9) are meant to add.
- Phase 2 is "run the chosen existing agent **unchanged**" and Phase 3 is "understand the architecture". For those, what matters is whether the project *already contains the target pipeline*. Only Ava does: Cloud API + LangGraph + Qdrant + memory + Docker.
- AleBrito is the strongest alternative for Phase 2 if the mentor prefers a safer, tested start: it runs offline with no keys, per its README. The cost is that it teaches no LangGraph and no vector retrieval.

**Decision point for the mentor:** Ava (architecture match, weaker engineering) vs AleBrito (engineering quality, weaker architecture match). My recommendation is Ava, with AleBrito's patterns composed in at Phases 4 and 9.

---

## 11. Architectural options

### Option A: Reuse one major project (Ava) + small customisation

- **For:** Fastest to a running WhatsApp agent; reading ~20 files teaches the whole flow; follows REUSE/ADAPT.
- **Against:** Inherits Ava's gaps and stale dependencies; the persona and voice/image features are not Wazi's goal; RAG and tools still to add.
- **Cost:** Lowest initial effort. Hidden work: dependency refresh, security fixes.

### Option B: Compose several proven pieces (recommended end state, reached incrementally)

Ava (pipeline) → harden with AleBrito patterns (signature, idempotency, background processing) → RAG from ArchAgenticRAG (Docling/FastEmbed/Qdrant/LangGraph) → optionally pywa for the transport layer → tool design informed by lgesuellip/OpenLivery.

- **For:** Every capability comes from something already proven or already written by the developer; matches the Constitution's COMPOSE step; each component is learned in its own phase.
- **Against:** Integration work (dependency pins, two LangGraph graphs, shared Qdrant); more moving parts.
- **Cost:** Moderate, spread across phases.

### Option C: Build from scratch

- **Justified?** No. The WhatsApp webhook, a LangGraph pipeline and a Qdrant memory already exist in MIT-licensed form, and RAG already exists in the developer's own repo. Building again violates the Constitution's reuse rule. The only parts that justify BUILD are Wazi-specific glue: the router between "answer from documents" and "use a tool", Wazi's prompts, the evaluation set for WhatsApp conversations, and per-user access rules.
- **Learning:** Writing a minimal webhook by hand *as a learning exercise* in Phase 3 is acceptable and encouraged (small, throwaway). That is a study task, not the product.

**Recommended architecture: Option A in Phase 2 (run), evolving into Option B from Phase 4 on.**

---

## 12. Risk analysis

| # | Risk | Where | Rating | Mitigation |
|---|---|---|---|---|
| 1 | Foundation is stale (12 months), deprecated provider models, dead free tier | Ava | **HIGH** for "run unchanged" | Phase 2 allows configuration-only changes (env vars, model names); log any deviation |
| 2 | No webhook signature verification | Ava | **HIGH** (security) | Add in Phase 4 using AleBrito/pywa pattern; do not expose a public URL before that |
| 3 | No tests in the foundation | Ava | **HIGH** | Write characterization tests in Phase 3/4 before changing behaviour |
| 4 | Unofficial WhatsApp automation | lucasboscatti, ragbot, OpenLivery QR, Evolution Baileys | **HIGH** if chosen | Excluded; Wazi uses only Cloud API |
| 5 | Unclear or missing licence | lucasboscatti; own ArchAgenticRAG (no file) | **HIGH** / LOW | Reference-only; add LICENSE to own repo |
| 6 | WhatsApp Cloud API pricing/setup uncertainty | All Cloud API options | **MEDIUM** | Verify rate card and test-number options in Phase 2; record the check date |
| 7 | Dependency conflicts between Ava and ArchAgenticRAG (langgraph, pydantic, embeddings) | Phase 5 | **MEDIUM** | Isolate with `uv` lock; decide embedding stack once |
| 8 | Heavy local install (`torch`, `sentence-transformers`, Docling) | Ava, ArchAgenticRAG | **MEDIUM** | Windows dev machine; evaluate CPU-only wheels in Phase 2 |
| 9 | Hosting a webhook for Meta needs a public HTTPS URL | All | **MEDIUM** | Decide tunnel vs host in Phase 2/10; do not decide now |
| 10 | LLM call inside the webhook → timeouts/duplicate replies | Ava | **MEDIUM** | Background processing + idempotency (Phase 4) |
| 11 | PII in logs/payloads | Ava (open PR #49) | **MEDIUM** | Review logging in Phase 9 |
| 12 | Single-maintainer young repos (AleBrito, ragbot, OpenLivery) | Shortlist | **MEDIUM** | Used as reference, not as a dependency |
| 13 | Open-core licensing | cleven12 | LOW | Not used |
| 14 | pywa abstraction hides protocol | pywa | LOW | Defer adoption until after Phase 3 |
| 15 | Vendor lock-in (Groq, ElevenLabs, Supabase keys) | Ava | LOW-MEDIUM | ArchAgenticRAG's provider presets are the planned way out |

---

## 13. Learning value

**What the developer will learn, using Ava as the base:**

- How a Meta webhook handshake and message payload really look (reading `whatsapp_response.py`, ~150 lines).
- How a LangGraph `StateGraph` is built, wired with conditional edges and checkpointed per user.
- The difference between short-term (checkpointer) and long-term (vector) memory.
- Then, by adding the missing pieces, why signatures, idempotency and background processing exist (AleBrito reference).
- Then RAG and tools, reusing the developer's own earlier work.

| Component | Treatment | Phase |
|---|---|---|
| Webhook + Graph API calls | Reused, then read and hardened | 2-4 |
| LangGraph pipeline | Reused, then trimmed to Wazi's needs | 2-4 |
| Qdrant memory | Reused, reviewed | 7 |
| Document RAG | Adapted from ArchAgenticRAG | 5 |
| Tool calling | Composed (reference patterns) then built | 6 |
| Tests / evaluation | Built, with ArchAgenticRAG's harness as a model | 8 |
| Security hardening | Adapted from AleBrito/pywa patterns | 4, 9 |
| Wazi persona/prompts/routing rules | Built | 4+ |

Why this beats building from scratch: it keeps the developer reading *working* code first, then changing it in small reviewed steps, which is faster to understand than staring at an empty folder. Why it beats a big framework: Ava is about 20 readable source files, with nothing hidden behind a platform.

---

## 14. Reuse map

| Wazi capability | Existing project | Reuse type | Status |
|---|---|---|---|
| WhatsApp send/receive | Ava `whatsapp_response.py` (pywa optional later) | ADAPT (pywa: COMPOSE, deferred) | Verified by reading code; not run |
| Webhook verification (GET) | Ava | REUSE | Verified by reading code |
| Webhook signature + idempotency | AleBrito `security.py` pattern, pywa | ADAPT (small) / REFERENCE | Missing in Ava; pattern verified for signature only |
| Agent pipeline | Ava LangGraph graph | ADAPT | Verified by reading code |
| Tool calling / decisions | lgesuellip, OpenLivery (patterns) | REFERENCE then BUILD | Not present in Ava |
| RAG (ingest, chunk, embed, retrieve) | ArchAgenticRAG (own) | ADAPT / COMPOSE | Verified by reading structure and key files; not run |
| Vector DB | Qdrant via Ava (memory) and ArchAgenticRAG (knowledge) | REUSE | Both use Qdrant; to be reconciled |
| Conversation memory | Ava (SQLite checkpointer + Qdrant facts) | REUSE / ADAPT | Verified by reading code |
| LLM provider abstraction | ArchAgenticRAG `providers.py` | REUSE | Verified by reading code |
| Human handoff | AleBrito (pattern), Chatwoot (heavy alternative) | REFERENCE | Not in Ava; likely later or out of scope |
| Testing | AleBrito, pywa, ArchAgenticRAG (patterns) | REFERENCE then BUILD | Ava has none |
| Evaluation | ArchAgenticRAG harness | ADAPT | Phase 8 |
| Docker | Ava compose + ArchAgenticRAG Qdrant compose | REUSE / COMPOSE | Verified by reading compose file; not run |
| Observability | ArchAgenticRAG (Langfuse), lgesuellip (LangSmith) | REFERENCE | Phase 8-9 |
| Wazi-specific prompts, routing, access rules | none | **BUILD** | Later phases |

---

## 15. Final recommendation

### Recommended Wazi Foundation

1. **Project:** Ava, the WhatsApp Agent course (`neural-maze/ava-whatsapp-agent-course`)
2. **URL:** https://github.com/neural-maze/ava-whatsapp-agent-course
3. **Licence:** MIT (LICENSE file present; copyright notice must be kept if code is copied)
4. **Why:** Only candidate that already contains the target pipeline (Cloud API → FastAPI → LangGraph → Qdrant/SQLite memory → reply) with Docker Compose, at a size a beginner can read. See §10 for the trade-off against AleBrito.
5. **Reuse:** Webhook GET verification, media download, LangGraph state/graph structure, SQLite checkpointer, Qdrant vector store, Docker Compose, Chainlit test UI.
6. **Adapt:** Remove the companion persona; update model/provider defaults; add signature verification, idempotency and fast-ack processing; refresh pinned dependencies; trim unused voice/image features if not needed.
7. **Compose:** RAG from ArchAgenticRAG; security patterns from AleBrito; optional pywa transport; tool-design ideas from lgesuellip/OpenLivery.
8. **Build:** Wazi prompts and routing between retrieval, tools and chat; tests; evaluation set; access control; deployment configuration.
9. **Major risks:** Stale foundation and drifted providers (HIGH); no signature verification (HIGH); no tests (HIGH); WhatsApp pricing unverified (MEDIUM); dependency reconciliation with ArchAgenticRAG (MEDIUM).
10. **Why suitable for learning:** It is a working, readable, end-to-end example whose gaps are precisely the topics Wazi is meant to teach.

### Proposed Phase 2 (NOT executed)

**Phase 2: Select and Run the Recommended Existing WhatsApp Agent**

- **Objective:** Run Ava as-is, locally, and observe it working, without redesigning it.
- **Tasks (proposed):**
  1. Re-confirm the commit to use; clone into a separate folder and record the commit hash and licence.
  2. Check the current Meta Cloud API setup path and pricing/test-number options; record the date and source.
  3. Decide which LLM/STT/vector providers to use for the *unchanged* run, preferring free or local options; record each cost class. Configuration-only changes (keys, model names) are allowed; code changes are not, unless a documented blocker forces one.
  4. Install dependencies in an isolated environment; record install size and problems.
  5. Run the Chainlit interface first (no WhatsApp needed) to test the graph; run Qdrant locally via Compose.
  6. Only then connect a WhatsApp test number through a tunnel, with secrets in `.env` (never committed), and send a message end to end.
- **Deliverables:** `docs/PHASE2_RUN_LOG.md` (what was run, versions, problems, deviations, how to reproduce), no changes to Ava's source.
- **Validation:** Real observed results only: webhook GET handshake succeeds; a text message gets a reply; failures recorded verbatim.
- **Acceptance criteria:** Reproducible run steps; any deviation from "unchanged" listed; no secrets in git; known limitations recorded.
- **Known limitations expected:** Provider drift may force config changes; no tests; no signature check, so the endpoint must not be left publicly exposed beyond testing.

Phase 2 requires mentor approval and has **not** been started.

---

## 16. Reproduction notes

- Repo metadata: `gh api repos/<owner>/<repo>`; file trees: `gh api repos/<owner>/<repo>/git/trees/HEAD?recursive=1`; file contents: `gh api repos/<owner>/<repo>/contents/<path> -H "Accept: application/vnd.github.raw"`.
- Feature absence checks: `gh api "search/code?q=<term>+repo:<owner>/<repo>"`. Code search can lag behind the latest commit.
- Re-running on a later date will give different star counts and push dates. Re-verify before Phase 2.

## 17. Sources (web)

- Webhook signing summaries (third-party, not Meta's own page): [Hookdeck guide](https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices), [Webhook Relay](https://webhookrelay.com/blog/whatsapp-cloud-api-webhooks/)
- Pricing: [Meta WhatsApp pricing page](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing) (search snippet only; the October 2026 change claims came from third-party pages and are unverified)
