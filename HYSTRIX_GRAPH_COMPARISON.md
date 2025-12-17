# Hystrix Knowledge Graph: Two Approaches Compared

This document contrasts the current **chunk-centric code graph** (Approach A) with a **domain-enriched graph** (Approach B) for the Hystrix repository. It highlights structure, pros/cons, sample queries, visualization considerations, and realistic data snippets tailored to Hystrix.

---

## Quick Summary
- **Approach A (Current):** Single vertex type `CodeChunk` (method/class/file) with edges: `CALLS`, `IMPORTS`, `EXTENDS`, `IMPLEMENTS`, `IN_FILE`/`BELONGS_TO`. Optimized for speed, simplicity, and code Q&A.
- **Approach B (Richer Domain):** Multiple vertex types (Service, Application, JavaClass, Method, File, ConfigArtifact/Key, ExternalResource/System). Adds edges like `OWNS`, `BELONGS`, `USES_CONFIG`, `USES_RESOURCE`, `REFERENCES_KEY`, alongside code edges. Optimized for impact analysis and service/config visibility.

---

## Structural Differences
| Aspect | Approach A (Chunk Graph) | Approach B (Domain-Enriched) |
| --- | --- | --- |
| Vertices | `CodeChunk` (types: file/class/method) | Application, Service, JavaClass, Method, File, ConfigArtifact, ConfigKey, ExternalResource/System |
| Code edges | `CALLS`, `IMPORTS`, `EXTENDS`, `IMPLEMENTS`, `IN_FILE` | Same set, plus explicit `Declares_method` if needed |
| Domain edges | Minimal (`IN_FILE`/`BELONGS_TO`) | `OWNS` (App→Service), `BELONGS` (Class→Service), `USES_CONFIG`, `USES_RESOURCE`, `REFERENCES_KEY`, `Part_of_system` |
| Scope | Code structure & navigation | Code + config + external systems + service context |
| Storage/perf | Lightweight NetworkX; fast builds | Heavier ingestion; benefits from TigerGraph (or NetworkX with filters) |

---

## Pros & Cons
### Approach A (Current Chunk Graph)
- **Pros**
  - Simple schema; fast to build and traverse in-memory.
  - Lower extraction risk (fewer heuristics for services/config).
  - Lean visualization; fewer node types to render/filter.
  - Strong for code-centric questions: callers/callees, imports, type hierarchy.
- **Cons**
  - No first-class services/apps/config/external systems ⇒ impact to infra/config is implicit only.
  - Harder to answer service-level or config/key compliance questions.
  - Less explicit containment (method-to-class/file is metadata, not domain edges).

### Approach B (Domain-Enriched)
- **Pros**
  - Directly answers “which services own classes that touch config X or external system Y.”
  - Better impact analysis across config keys/resources/systems.
  - Service-level rollups and ownership views become first-class.
  - Enables governance/compliance checks (e.g., missing config, forbidden endpoints).
- **Cons**
  - More ingestion complexity (must extract service boundaries, configs, external resources).
  - Higher noise risk from imperfect heuristics; needs validation and filters.
  - Heavier visualization (more node types) unless UI filtering is solid.
  - Build time and memory/graph sync costs increase; may need TigerGraph for scale.

---

## Sample Queries (Hystrix)
| Question | Approach A | Approach B |
| --- | --- | --- |
| “Who calls `HystrixCommandDemo.startDemo`?” | ✅ via `CALLS` edges (methods) | ✅ |
| “Which classes implement `HystrixCommand`?” | ✅ via `IMPLEMENTS` edges | ✅ |
| “What config keys does `HystrixCommandDemo` use?” | ⚠️ implicit (parse code text) | ✅ `USES_CONFIG` → `ConfigKey` |
| “Which services use config key `hystrix.command.default.execution.isolation.thread.timeoutInMilliseconds`?” | ❌ not modeled | ✅ Service → Class → Method → `USES_CONFIG` → ConfigKey |
| “Which external systems are touched by `HystrixCommandAsyncDemo`?” | ⚠️ manual scan of strings/imports | ✅ `USES_RESOURCE` → ExternalResource/System |
| “Impact if we change `HystrixCommandMetricsPublisher`?” | ✅ callers/implements | ✅ plus service/external impact |
| “List all classes in service X that extend `HystrixCommand` and call external endpoint Y.” | ⚠️ hard (no service/external nodes) | ✅ multi-hop with Service + ExternalResource |

---

## Realistic Data Chunks (Hystrix-flavored)
Below are illustrative payloads (not full code) showing what the graph would carry.

### Approach A node examples
```json
{
  "id": "chunk_449",
  "type": "method",
  "fqn": "com.netflix.hystrix.examples.demo.HystrixCommandDemo.startDemo",
  "file_path": ".../hystrix-examples/.../HystrixCommandDemo.java",
  "repository_id": 2
}
```
```json
{
  "id": "chunk_454",
  "type": "class",
  "fqn": "com.netflix.hystrix.examples.demo.HystrixCommandDemo",
  "file_path": ".../hystrix-examples/.../HystrixCommandDemo.java",
  "repository_id": 2
}
```
Edges:
```json
{ "from": "chunk_449", "to": "chunk_497", "relationship": "calls" }
{ "from": "chunk_454", "to": "chunk_449", "relationship": "in_file" }
{ "from": "chunk_454", "to": "chunk_500", "relationship": "implements" }
```

### Approach B node examples
```json
{ "id": "svc_hystrix_examples", "type": "Service", "name": "hystrix-examples" }
{ "id": "cfg_timeout_ms", "type": "ConfigKey", "key": "hystrix.command.default.execution.isolation.thread.timeoutInMilliseconds" }
{ "id": "ext_metrics_stream", "type": "ExternalResource", "kind": "http", "name": "/hystrix.stream" }
{ "id": "chunk_449", "type": "Method", "fqn": "...HystrixCommandDemo.startDemo", "service": "svc_hystrix_examples" }
```
Edges:
```json
{ "from": "svc_hystrix_examples", "to": "chunk_454", "relationship": "owns" }
{ "from": "chunk_454", "to": "svc_hystrix_examples", "relationship": "belongs" }
{ "from": "chunk_449", "to": "cfg_timeout_ms", "relationship": "uses_config" }
{ "from": "chunk_449", "to": "ext_metrics_stream", "relationship": "uses_resource" }
{ "from": "chunk_449", "to": "chunk_497", "relationship": "calls" }
```

---

## Visualization Considerations
- **Approach A:** Keep as-is: force-directed view, filter by node type (method/class/file), edge labels small and unobtrusive. Good for call graph exploration.
- **Approach B:** Add filters for new node types (Service, Config, ExternalResource). Provide presets:
  - “Code only” (hide config/external/service)
  - “Config impact” (show ConfigKey/ConfigArtifact + related methods/classes/services)
  - “External systems” (show ExternalResource/System + callers)
  - “Service view” (show Service containers and their classes/methods)
- Increase edge spacing; cluster by service; allow toggling labels per node type.

---

## Pros/Cons Recap (Hystrix context)
- If primary workflow is **code navigation and call-graph Q&A**, stick with Approach A for speed and clarity.
- If you need **config/external impact analysis** (timeouts, streams, caches, endpoints) or **service ownership** views, Approach B adds meaningful value—provided extraction quality is acceptable.
- A hybrid path: keep Approach A as the core, add **optional typed nodes** for ConfigKey and ExternalResource plus a lightweight Service container, guarded by feature flags and UI filters to avoid clutter.

---

## Recommended Hybrid Minimal Increment
1) **Add nodes**: `ConfigKey`, `ConfigArtifact`, `ExternalResource`.
2) **Add edges**: `USES_CONFIG` (Method/Class→Config*), `REFERENCES_KEY`, `USES_RESOURCE`.
3) **Optional**: `Service` node with `OWNS`/`BELONGS` if service boundaries are derivable (e.g., module/package).
4) **UI filters**: default to code-only; toggle config/external/service layers on demand.
5) **Extraction heuristics (Hystrix)**:
   - Config keys: regex `hystrix\.[\w\.\-]+` in Java code/config files.
   - External resources: URLs/endpoints (`http`, `/hystrix.stream`, metrics), cache keys.
   - Service inference: module path (`hystrix-examples`, `hystrix-core`) as service name.

---

## Example Queries to Run (Hystrix)
- **Code-level (Approach A works well)**
  - “Who calls `HystrixCommandDemo.startDemo`?”
  - “List classes implementing `HystrixCommand` in `hystrix-examples`.”
  - “Show call graph for `HystrixCommandMetricsPublisherFactory.registerPublisher` up to depth 2.”
- **Domain-level (Approach B advantage)**
  - “Which methods in `hystrix-examples` use config key `hystrix.command.default.execution.isolation.thread.timeoutInMilliseconds`?”
  - “Which services touch `/hystrix.stream` or metrics endpoints?”
  - “What external systems are reached by methods that extend `HystrixCommand` in `hystrix-core`?”
  - “Find all config keys referenced by classes that implement `HystrixCommandMetricsPublisher`.”

---

## Takeaway
- Use **Approach A** for fast, reliable code graphing and day-to-day Q&A.
- Layer in **Approach B** selectively (config, external systems, optional service nodes) to unlock impact/compliance analyses without overwhelming ingestion or the UI. Feature-flag and filter aggressively to manage complexity.


