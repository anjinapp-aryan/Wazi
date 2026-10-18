# ADR-002: ArchAgenticRAG remains a separate learning project

- **Status:** Proposed (awaiting mentor review)
- **Date:** 2026-10-18
- **Phase:** 3
- **Related:** [WAZI_ARCHITECTURE_COMPARISON.md](../WAZI_ARCHITECTURE_COMPARISON.md), [REUSE_AUDIT.md](../REUSE_AUDIT.md) §8

## WHAT

ArchAgenticRAG (`github.com/anjinapp-aryan/ArchAgenticRAG`) stays an independent repository with its own goals and release pace. Wazi does **not** depend on it as a package, submodule or copied tree. Concepts and, after explicit mentor approval, small pieces may be reused or adapted in a later phase.

## WHY (evidence)

1. **Different purpose:** it is a learning project for RAG and evaluation. It has no messaging, sessions, memory or user model (code read in Phase 3).
2. **Not finished:** Basic RAG and an evaluation baseline exist; agentic behaviour is a future phase of that project. Its public status table says "Done, pending review" for its Phase 1.
3. **Corpus-specific code:** ingestion is built around Python PEPs (docutils PEP reader and header handling in `rag/ingestion.py`). That does not transfer to arbitrary WhatsApp-user documents.
4. **Version coupling would be real:** ArchAgenticRAG pins `langgraph==1.2.12` and `qdrant-client==1.19.1`; Ava pins `pydantic==2.10.0` and relies on a removed `qdrant-client` method. Tying Wazi to a moving learning project would import its churn.
5. **Housekeeping gap:** the repository has no `LICENSE` file (its `pyproject.toml` declares MIT), and its working copy has uncommitted changes. Neither blocks the owner's own use, but both must be settled before Wazi copies code into a public repo.
6. **Learning value:** if Wazi simply imported it, the learner would not have to understand retrieval inside the WhatsApp context, which is the point of the project.

## ALTERNATIVES

| Alternative | Why not |
|---|---|
| Add ArchAgenticRAG as a package dependency | Couples Wazi to a project that is still changing and is not designed as a library |
| Copy its RAG modules into Wazi now | Premature (Phase 5 scope), skips the learning, imports PEP-specific code |
| Merge the repositories | Mixes two learning goals and two histories |
| Ignore it and rebuild RAG independently | Duplicates work the owner has already done and violates REUSE |

## DECISION (proposed)

1. Keep the repositories separate.
2. In the RAG phase (Phase 5), run a short, explicit reuse review against ArchAgenticRAG, classify each candidate piece (REUSE / ADAPT / COMPOSE / REFERENCE / BUILD) and get mentor approval before anything is copied.
3. Before any code is copied: add a `LICENSE` file to ArchAgenticRAG, commit or stash its working changes, and carry over its `THIRD_PARTY_NOTICES.md` obligations.
4. The cleanest *concept-level* reuses are already visible: config-validated provider selection, Qdrant collection-metadata guards, deterministic point ids, grounded-answer prompt shape, and the evaluation approach.

## CONSEQUENCES

- Positive: both projects stay understandable; no accidental coupling.
- Negative: some duplicated effort when similar ideas are re-implemented in Wazi.
- Revisit if: ArchAgenticRAG matures into a documented, versioned library with its own tests and release process.
