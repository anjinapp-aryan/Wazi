# Wazi Project Constitution

Status: Phase 0 deliverable. Version 1.0. This document governs all later phases. Changes require mentor review.

---

## 1. Project Overview

Wazi is a learning-focused WhatsApp AI Agent that will eventually become an Agentic RAG WhatsApp assistant.

The developer is a beginner in building WhatsApp agents and Agentic RAG systems. The goal is not only to ship software but to learn the architecture, understand every major component, and reuse proven open-source solutions instead of reinventing them.

Wazi is built incrementally, one gated phase at a time (see sections 12 and 14).

## 2. Learning Objectives

By the end of the project the developer should be able to explain, without help:

1. How the WhatsApp Cloud API delivers and sends messages, and how webhook verification works.
2. How a webhook receiver is structured and why it must respond quickly and safely.
3. How an agent loop works: LLM call, tool selection, tool execution, response.
4. How RAG works end to end: ingestion, chunking, embeddings, vector search, retrieval, answer grounding.
5. What makes a RAG system "agentic" (the agent decides when and how to retrieve or use tools).
6. How conversation memory is stored, scoped per user, and bounded.
7. How to test, evaluate, secure, and deploy such a system.
8. How to evaluate open-source projects (license, maintenance, tests) and decide reuse vs. build.

Understanding is a deliverable. Code the developer cannot explain is not considered done.

## 3. Target Architecture

```
WhatsApp User
    |
WhatsApp Cloud API
    |
Webhook
    |
Wazi Agent
    |
LLM
    |
Tools / RAG / Memory
    |
WhatsApp Response
```

This is a **target only**. No framework, database, LLM provider, or hosting platform is mandated.

Candidate technologies (not decisions): WhatsApp Cloud API, LangGraph, Qdrant, Groq, OpenRouter, Gemini, Docker, Python.

A candidate becomes a decision only when selected in a reviewed phase using the WHAT → WHY → ALTERNATIVES → DECISION format (section 11).

## 4. Reuse Principle: REUSE → ADAPT → COMPOSE → BUILD

Before implementing any significant capability:

1. Search for existing open-source implementations.
2. Check the repository license.
3. Check project activity and maintenance.
4. Check tests and reproducibility.
5. Evaluate whether the existing implementation can be reused.
6. Prefer reuse over building from scratch.
7. Adapt existing code only when necessary.
8. Build from scratch only when no suitable reusable solution exists.

### Classification labels

Every external project or component is assigned one label, recorded with justification:

| Label | Meaning |
|-------|---------|
| REUSE | Suitable for direct reuse. |
| ADAPT | Suitable but requires modification. |
| COMPOSE | Combine with other proven components. |
| REFERENCE | Useful for learning; do not copy implementation. |
| REJECT | Unsuitable for Wazi. |
| BUILD | Implement ourselves, only when no suitable reusable solution exists. |

### Existing RAG knowledge

The developer has an earlier Agentic RAG learning project. When Wazi reaches the RAG phase, do not automatically build another independent RAG implementation. First evaluate what can be reused or adapted (document ingestion, chunking, embeddings, Qdrant, retrieval, LangGraph, evaluation). That project is not integrated during Phase 0.

## 5. Open-Source License Rules

Before reusing external code:

1. Identify the repository.
2. Verify its license (read the actual LICENSE file, not only the repository badge).
3. Record the license.
4. Check that the license permits the intended reuse.
5. Record attribution requirements.

Preferred permissive licenses: MIT, Apache-2.0, BSD.

If the license is missing or unclear, classify the repository as **REFERENCE ONLY**. Do not copy implementation code from it until the license is verified.

Copyleft or restrictive licenses (e.g. GPL, AGPL, non-commercial terms) require an explicit, documented mentor decision before any code is reused.

Every reused component is recorded with: repository URL, commit or version, license, attribution requirement, and what was reused or changed.

## 6. Dependency-Selection Rules

Do not add dependencies simply because they are popular. Never introduce a significant dependency without explaining why it is needed.

Before adding a significant dependency, document:

- Purpose: what problem it solves.
- License.
- Maintenance: recent activity, release cadence, open critical issues.
- Security: known vulnerabilities, supply-chain posture.
- Alternatives considered, including the standard library.
- Existing project capabilities: can something already present do this?
- Whether it is actually required now.

Avoid unnecessary frameworks and duplicate libraries. Pin versions. Add dependencies only in the phase that needs them.

## 7. Security Principles

Never:

- hard-code API keys,
- commit secrets,
- expose credentials in logs,
- copy credentials from repositories,
- disable security just to make the application work.

Secrets live in environment variables or a secrets manager; `.env` files are git-ignored; an `.env.example` with placeholders may be committed.

Future phases must explicitly consider:

- WhatsApp webhook verification (verify token and request signature)
- authentication
- authorization
- prompt injection
- tool abuse
- malicious documents
- sensitive-data leakage
- dependency vulnerabilities
- rate limiting
- logging (useful, but without secrets or unnecessary personal data)

Security is a requirement of each phase, not a final-phase add-on. Phase 9 consolidates and audits it.

## 8. Testing Principles

Every implementation phase includes appropriate validation, using the smallest suitable level:

```
Unit Test -> Integration Test -> End-to-End Test
```

- Tests must verify real behavior.
- Never claim a test passed unless it was actually executed.
- Report failures honestly, with the relevant output.
- Do not invent test results, performance numbers, repository statistics, or compatibility claims.
- If something was not tested, say "not tested".

## 9. Documentation Principles

For each piece of work, document:

- What was built
- Why it was built
- What was reused
- What was changed
- Alternatives considered
- Known limitations
- How to reproduce the result

Documentation must be accurate to what actually exists. Do not describe planned features as implemented.

## 10. Cost Principles

Prefer free, open-source, and local solutions where practical.

Always distinguish:

- **Free software** (open-source, no usage fee)
- **Free-tier infrastructure** (free within limits that may change)
- **Paid infrastructure**
- **API usage costs** (per-token or per-message charges, including WhatsApp conversation pricing)

Do not claim a service is permanently free without verification. Record the date any pricing or free-tier claim was checked. Obtain mentor approval before any step that incurs cost.

## 11. AI-Assisted Development Rules

The AI assistant works in service of the developer's learning.

1. **Learning first.** Do not assume advanced knowledge. Do not hide architectural decisions behind generated code.
2. **Explain decisions** in the format **WHAT → WHY → ALTERNATIVES → DECISION**.
3. **Honesty.** Do not claim code works unless it was tested. Do not invent test results, performance numbers, repository statistics, or compatibility claims. State uncertainty plainly.
4. **Reuse first.** Apply section 4 before writing significant code. Verify licenses (section 5) before copying anything.
5. **No scope creep.** Do not perform future-phase work to be helpful. Do not proceed to the next phase automatically.
6. **Smallest change.** Prefer minimal, reviewable changes over large generated drops.
7. **No secrets.** Never request, embed, or log real credentials.
8. **Verify, don't recall.** Repository facts (license, activity, stars, API behavior) must be checked against the source at the time, not recalled from memory.
9. **Review gate.** Stop at the end of each phase and wait for mentor review.

## 12. Phase-Gate Rules

- Never automatically proceed to the next phase.
- Each phase must define: **Objective, Tasks, Deliverables, Validation, Acceptance criteria, Known limitations**.
- A phase must be completed and reviewed by the mentor before the next phase begins.
- Final report of each phase states every acceptance criterion as PASS / FAIL / NOT APPLICABLE; PASS only when verified.
- Work belonging to a later phase must not be done early.
- If a later phase reveals a flaw in an earlier one, the earlier phase is reopened explicitly and re-reviewed.

## 13. Definition of Done

A unit of work (task or phase) is done only when all apply:

1. Objective of the phase is met and deliverables exist.
2. Validation was actually executed and results recorded honestly.
3. All acceptance criteria are marked, with evidence.
4. Reused components have recorded repository, version, license, and attribution.
5. New dependencies are justified per section 6.
6. No secrets are committed or logged.
7. Documentation covers the items in section 9, including how to reproduce.
8. Known limitations are listed.
9. The developer can explain what was done and why.
10. The mentor has reviewed and approved the phase.

## 14. Future Development Phases

| Phase | Name |
|-------|------|
| 0 | Project foundation and engineering constitution (this document) |
| 1 | GitHub/open-source reuse audit |
| 2 | Select and run the chosen existing WhatsApp Agent unchanged |
| 3 | Understand and document the architecture |
| 4 | First controlled Wazi customization |
| 5 | Add/reuse RAG and knowledge retrieval |
| 6 | Add Agentic tools and decision making |
| 7 | Add conversation memory |
| 8 | Testing and evaluation |
| 9 | Security and reliability |
| 10 | Deployment |

Each phase is gated per section 12. The list is a plan, not a commitment: scope and order may change through mentor-reviewed amendment.

### Phase 0 scope reminder

Phase 0 produces documentation only. No application code, no cloned repositories, no dependencies, no WhatsApp/LLM/Qdrant configuration, and no reuse audit (that is Phase 1).
