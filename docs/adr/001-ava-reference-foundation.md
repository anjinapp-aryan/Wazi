# ADR-001: Ava is a reference foundation, not a production-ready base

- **Status:** Proposed (awaiting mentor review)
- **Date:** 2026-10-18
- **Phase:** 3
- **Related:** [REUSE_AUDIT.md](../REUSE_AUDIT.md) §10, [PHASE_2_BASELINE.md](../PHASE_2_BASELINE.md), [PHASE_3_ARCHITECTURE.md](../PHASE_3_ARCHITECTURE.md)

## WHAT

Treat `neural-maze/ava-whatsapp-agent-course` (commit `338fd68`, MIT) as a **learning reference and source of patterns** for Wazi. Do not treat it as a codebase that Wazi will run in production or grow in place.

## WHY (evidence)

From Phase 2 and Phase 3 source reading:

1. **Not safely exposable:** no webhook signature check, no authentication, a catch-all that returns 500 (inviting Meta retries), no idempotency, and `print(headers)` writes the WhatsApp bearer token to stdout (`whatsapp_response.py:191-192`).
2. **No user isolation:** one global Qdrant collection with no user filter (`vector_store.py:36`, search at `:134`).
3. **No tests**, and a design that is hard to test: provider SDKs and singletons are created at import time, and the graph is recompiled per request.
4. **Provider drift:** three default model IDs are listed by Groq as deprecated or past shutdown; the Together free image model is likely gone; Graph API v21.0 is scheduled for removal 2027-01-21.
5. **Dependency drift:** only the lockfile path works; the documented install path fails.
6. **Persona-specific:** the graph, prompts, schedule and image/voice features exist to serve a fictional character ("Ava"), not an assistant.
7. **Not RAG:** no document ingestion or retrieval; only vector memory.

What it does well, and why it is still the best *teaching* base from Phase 1: it shows the complete path (webhook → LangGraph with per-user persistence → memory → provider calls → WhatsApp reply) in about 25 readable files.

## ALTERNATIVES

| Alternative | Why not (now) |
|---|---|
| Fork Ava and harden it in place | Hardening touches almost every module (webhook, state, memory, providers, config). The result would be mostly new code carrying a persona-shaped skeleton. It would also blur "what Ava did" and "what we changed", which is the thing the baseline is meant to keep clear |
| Switch to AleBrito `whatsapp-ai-agent` as the base | Better engineering (signature, idempotency, tests), but a booking-bot with no LangGraph or vector retrieval; 3 months old, single author (Phase 1) |
| Build from scratch with no reference | Violates REUSE → ADAPT → COMPOSE → BUILD; loses a working worked example |
| Use Ava unchanged | Not possible with current providers (Phase 2) and unsafe |

## DECISION (proposed)

1. Ava remains the **reference foundation**: read it, learn from it, and reuse or adapt specific, small, understood pieces (with MIT attribution).
2. The baseline clone in `Wazi-baselines/ava` stays **pristine** as the "before" picture.
3. Wazi's own code will be written in the Wazi repository as separate modules whose boundaries follow ADR-003. Each adapted idea is recorded in a reuse log (what, from where, license, what changed).
4. Anything copied from Ava is first checked against the findings above, so known defects are not carried over.

## CONSEQUENCES

- Positive: the learner understands each piece before it enters Wazi; known defects are not inherited silently.
- Negative: more writing than a fork; the "first working Wazi" is later.
- Revisit if: the mentor prefers a fork-and-harden path, or Phase 4 finds that a simpler adaptation is viable.
