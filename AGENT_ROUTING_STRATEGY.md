# Agent Routing Strategy (Ask / Plan / Observability-Ag / Analysis-Ag)

This document describes how to expose multiple agents in the conversation flow (similar to Cursor’s Ask/Plan) and route requests to specific workflows. It builds on the existing LangGraph conversation graph and code-intelligence services.

## Goals
- Let users pick an agent upfront (e.g., Ask, Plan, Observability-Ag, Analysis-Ag).
- Allow automatic fallback/upgrade when the task demands deeper analysis.
- Keep UI simple: a toggle or dropdown + an inline hint of what each agent does.
- Minimize latency by short-circuiting to the right workflow early.

## Agents and Behaviors
- **Ask**: fast answers; shallow retrieval (hybrid search, small K), light context; no long-running jobs.
- **Plan**: produces step-by-step plan, dependencies, and suggested actions; may expand retrieval depth; can return a plan block without executing.
- **Observability-Ag**: focuses on logs/metrics/traces; fetches observability snippets (via Splunk or other sources); surfaces runbook-style answers; may issue follow-up queries to telemetry indices.
- **Analysis-Ag**: deeper code/RAG reasoning; uses exhaustive or multi-hop traversal; higher K, more graph hops; can invoke advanced graph queries and completeness checks.

## Routing Strategy
1) **User selection (primary signal)**: UI exposes agent selector; conversation state stores `agent`.
2) **Intent heuristic (secondary)**: If agent not explicitly set, infer from message (e.g., “plan”, “steps”, “how to fix” → Plan; “logs”, “metrics”, “trace”, “error id” → Observability-Ag; “impact”, “all callers”, “exhaustive”, “migration” → Analysis-Ag; otherwise Ask).
3) **Escalation**: If Ask/Plan detects low confidence or incomplete coverage, escalate to Analysis-Ag (with a confirmation) to run deeper retrieval.
4) **Telemetry guardrails**: Observability-Ag avoids code-only context unless asked; Analysis-Ag can optionally include observability if relevant.

## Workflow Mapping
- **Ask →** standard hybrid search (OpenSearch + DB), small top_k, shallow graph (depth 1–2), quick synthesis.
- **Plan →** intent classifier + dependency lookup; returns steps; may call graph traversal for prerequisites; no heavy multi-hop unless requested.
- **Observability-Ag →** observability retriever (logs/metrics/traces) + optional code snippet lookup for context; answers include runbook tips and most recent signals.
- **Analysis-Ag →** advanced RAG: higher top_k, graph traversal (depth up to configured limit), multi-hop, completeness verification; can issue follow-up subqueries.

## Data/Config Needed
- Conversation state: `agent` (ask|plan|observability|analysis), `thinking_mode` can coexist.
- Routing table: maps `agent` to retrieval params (top_k, max_depth, include_graph, include_obs).
- UI: selector in chat header; optional per-message override.
- API: allow setting/updating `agent` on a conversation (similar to thinking-mode PATCH).

## Suggested API/UI Changes (incremental)
- Add `agent` field to `Conversation` model and DTOs.
- Add `PATCH /conversations/{id}/agent` to update selection.
- UI: small dropdown near the thinking-mode toggle with tooltips:
  - Ask: “Fast answer”
  - Plan: “Steps and actions”
  - Observability-Ag: “Logs/metrics/traces first”
  - Analysis-Ag: “Deep, multi-hop code analysis”

## Defaults and Limits
- Ask: top_k=5–8, graph depth=1–2, no exhaustive.
- Plan: top_k=8–12, graph depth=2, can call dependency/impact helper.
- Observability-Ag: obs-first retrieval; code lookup optional; short answers with runbook hints.
- Analysis-Ag: top_k=15–25, graph depth up to limit (e.g., 3–5), may run completeness check; enforce result and token caps.

## Safety & Performance
- Cap evidence size per agent; enforce timeouts.
- If observability sources are unavailable, fall back to code search with a disclaimer.
- For Analysis-Ag, add a short “this may take a moment” notice; stream progress if available.

## Examples
- User: “Show all callers of HystrixCommandDemo.startDemo and any downstream external calls.” → Analysis-Ag (deep, graph hops).
- User: “I see 500s; find related errors in the last hour.” → Observability-Ag (logs/metrics first).
- User: “Give me steps to add a new Hystrix command safely.” → Plan (steps, dependencies).
- User: “What does this class do?” → Ask (quick summary + citations).


