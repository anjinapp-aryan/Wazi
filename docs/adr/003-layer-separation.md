# ADR-003: Wazi separates WhatsApp, Agent, Memory/RAG and Provider layers

- **Status:** Proposed (awaiting mentor review)
- **Date:** 2026-10-18
- **Phase:** 3
- **Related:** [PHASE_3_ARCHITECTURE.md](../PHASE_3_ARCHITECTURE.md) §17-18, [WAZI_ARCHITECTURE_COMPARISON.md](../WAZI_ARCHITECTURE_COMPARISON.md)

## WHAT

Wazi's design is split into layers with narrow, explicit interfaces:

1. **WhatsApp/Webhook layer**: receive, authenticate, parse and acknowledge Meta events; send outbound messages. Knows about Meta payloads and nothing else.
2. **Agent orchestration layer**: decide what to do for one normalized message of one user. Knows nothing about Meta payloads.
3. **Memory layer** and **RAG layer** (separate): per-user conversational memory; shared or access-controlled knowledge retrieval.
4. **Provider layer**: all LLM, speech, embedding and vector-store clients behind configuration.
5. **Tools layer** (future): explicitly registered, permissioned actions.

## WHY (evidence from Ava)

| Observed in Ava | Consequence | Boundary that prevents it |
|---|---|---|
| The webhook handler downloads media, calls Groq vision/STT, runs the graph, reads graph state, and calls the Graph API in one function (`whatsapp_response.py:32-108`) | Cannot test parsing without an LLM; any error becomes a 500 that Meta retries | WhatsApp layer produces a normalized message and returns quickly; agent layer is called separately |
| Graph state fields hold transport artifacts (`audio_buffer`, `image_path`) | Binary data is checkpointed with the conversation; graph is coupled to channel formats | Agent returns a channel-neutral reply object; WhatsApp layer renders it |
| Memory is one global collection (`vector_store.py:36`) | Cross-user leakage | Memory layer API requires a `user_id` and always filters by it |
| `ChatGroq` is constructed in several modules; model IDs are scattered | Provider drift breaks the app in many places (Phase 2) | Provider layer is the only place that knows vendors and model names |
| Singletons and SDK clients are created at import time | Hard to test; startup fails without every key | Dependencies are constructed once and **injected** |
| Memory and document knowledge would share a store | Different lifecycles, owners and access rules get mixed | Memory and RAG are separate layers (and separate collections) |

Evidence of the pattern working: ArchAgenticRAG injects `client`, `embeddings` and `llm` into `build_graph(...)`, validates config at load, and consequently has unit tests for its graph and vector store without live services (code read; tests not run in Phase 3).

## ALTERNATIVES

| Alternative | Trade-off |
|---|---|
| Keep Ava's single-module style | Fewer files, but every defect above stays structural |
| A heavyweight framework that hides layers | Less to write, but hides the architecture the project exists to teach |
| Microservices per layer | Overkill for a learning project; adds deployment complexity. Layers are *module* boundaries first |

## DECISION (proposed)

1. Adopt the layer boundaries above as **module/package boundaries** inside one deployable application. No separate services.
2. Each boundary is an interface (function/class contract) with data types defined in one place; tests can fake the other side.
3. Cross-cutting rules: every inbound event is authenticated before parsing; every memory/RAG access is scoped by user or by an explicit access rule; every external call goes through the provider layer; logs never contain credentials and avoid message content.
4. Build the layers in the order of the roadmap (webhook and orchestration first; memory isolation; RAG; tools), not all at once.

Technology choices (for example which web framework, queue, or vector store configuration) are **not** decided by this ADR.

## CONSEQUENCES

- Positive: testable, replaceable pieces; security checks have an obvious home; fits the phase plan.
- Negative: more initial structure than a prototype needs; risk of over-engineering if boundaries become ceremony.
- Mitigation: keep interfaces small; add a layer only when its phase begins.
- Revisit if: a boundary causes friction without paying back in testability or safety.
