# Implementation Plan: Linux CLI Knowledge Assistant

**Branch**: `001-linux-rag-specification` | **Date**: 2025-10-15 | **Spec**: [/home/zsoltk/git/linux-rag/specs/001-linux-rag-specification/spec.md](/home/zsoltk/git/linux-rag/specs/001-linux-rag-specification/spec.md)
**Input**: Feature specification from `/specs/001-linux-rag-specification/spec.md`

## Summary

Deliver a local-first Linux RAG assistant that ingests man pages and optional Kiwix wikis, answers natural-language questions through the `ragman` CLI, and exposes administration tasks via a separate `ragman-admin` CLI that can start the service stack, monitor status, trigger ingestion, and capture feedback while respecting 2s p95 latency and a 10 percent disk cache budget.

## Technical Context

**Language/Version**: Python 3.11+ for ingestion/retrieval services; Go 1.22 for CLI tools (`ragman`, `ragman-admin`) using spf13/cobra  
**Primary Dependencies**: Weaviate (local podman-compose), weaviate-python-client, Ollama (gemma3:1b, codegemma:2b, embeddinggemma), Podman, python-kiwix CLI wrappers, cobra CLI framework, grpc-go/py  
**Storage**: Weaviate data and embeddings persisted under `/var/lib/linux-rag`, SQLite cache DB co-located under `/var/lib/linux-rag/cache`, Podman volumes for Ollama models  
**Testing**: pytest + pytest-asyncio, go test with testify, integration harness via podman-compose, CLI golden tests, e2e scripts for `ragman` and `ragman-admin`  
**Target Platform**: Linux (Fedora/Ubuntu) with Podman and podman-compose, local Ollama runtime, systemd optional for background services  
**Project Type**: Multi-language monorepo (Python services + Go CLIs)  
**Performance Goals**: <=2s p95 interactive answer latency, <=1.5x baseline ingestion duration, >=80 percent cache hit rate for repeat queries, <=1s cached response latency  
**Constraints**: Memory <12GB during retrieval, persistent cache <=10 percent of `/var/lib/linux-rag`, admin CLI must start/stop stack without manual podman commands, offline-friendly install beyond optional Kiwix downloads  
**Scale/Scope**: 5k-20k documents (man pages + selected wikis), single concurrent CLI user, ingestion runs on-demand or nightly

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Code Quality & Polyglot Excellence**: Apply `ruff`, `black`, and `mypy` for Python; `go fmt`, `golangci-lint`, and `staticcheck` for Go. Combined coverage (pytest + go test) must reach Python >=90 percent and Go >=85 percent before merge.
- **Test Discipline & Safety Net**: Failing-first tests per story - pytest unit suites for ingestion/caching, integration tests using podman-compose, gRPC contract tests, and CLI regression harness for `ragman` and `ragman-admin`; CI blocks merges on any failure.
- **Consistent User Experience**: `ragman` and `ragman-admin` share canonical flag names, support text and JSON outputs, ship markdown help, and update `docs/cli.md`; admin CLI includes `run`, `status`, `ingest`, `feedback`, and future ops commands.
- **Performance & Resource Efficiency**: Benchmark scripts capture latency, ingestion duration, cache disk usage, and admin CLI service launch times; alerts fire if cache exceeds 10 percent or responses breach 2s p95.

## Project Structure

### Documentation (this feature)

```
specs/001-linux-rag-specification/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
`-- tasks.md
```

### Source Code (repository root)

```
src/
|-- python/
|   `-- linux_rag/
|       |-- ingestion/
|       |-- retrieval/
|       |-- llm/
|       |-- cache/
|       |-- telemetry/
|       `-- server/
`-- go/
    |-- cmd/ragman/
    |   `-- main.go
    `-- cmd/ragman-admin/
        `-- main.go

infra/
|-- podman-compose.yml
`-- systemd/
    `-- linux-rag.service

tests/
|-- python/
|   |-- unit/
|   |-- integration/
|   `-- contracts/
`-- go/
    |-- ragman/
    `-- ragman-admin/
```

**Structure Decision**: Split Go binaries into `ragman` (user queries) and `ragman-admin` (operations) while centralizing Python services under `src/python/linux_rag`; shared IPC via gRPC Unix socket and reusable telemetry/cache modules.

## Complexity Tracking

No constitution violations anticipated; dual CLI approach introduces additional commands but remains manageable within lint/test gates.

## Phase 0 - Research Plan (Completed)

1. Validate Podman-compose stack for Weaviate, Ollama, and shared volumes at `/var/lib/linux-rag`.
2. Confirm async gRPC bridge enabling Go CLIs to invoke Python services securely over Unix socket.
3. Select SQLite-based query cache with enforced 10 percent disk budget via LRU eviction.
4. Establish python-kiwix workflow for catalog fetching and archive verification.
5. Define cross-language test approach (pytest, go test, CLI e2e) covering cache hit metrics and ingestion outputs.

See `research.md` for decisions and alternatives.

## Phase 1 - Design & Contracts (Completed)

- `data-model.md` documents KnowledgeSource, AnswerSession, FeedbackEntry, IngestionJob, and CacheEntry schemas.
- `contracts/rag_service.proto` provides gRPC endpoints consumed by both CLI binaries (Ask, RunIngestion, GetStatus, SubmitFeedback).
- `quickstart.md` details operator setup, CLI usage (`ragman`, `ragman-admin`), and testing commands.
- Agent context (`AGENTS.md`) updated with Python/Go/Weaviate/Ollama technology stack.

**Constitution Re-check**:
- Code Quality: Linting/formatting/coverage defined for both languages.
- Test Discipline: Unit, integration, contract, and CLI regression suites captured.
- Consistent UX: CLI separation and output formats documented.
- Performance & Resource: Benchmarks for latency, ingestion, and cache budget specified.

## Phase 2 - Implementation Outline (Preview)

1. **Infrastructure & Services**
   - Finalize podman-compose (Weaviate, Ollama, support services).
   - Implement Python gRPC server with ingestion, retrieval, cache, and admin control APIs (including service start helper used by `ragman-admin run`).
   - Build cache eviction worker with disk usage telemetry.
2. **Ingestion Workflows**
   - Man page ingestion command storing KnowledgeSource records and vectors.
   - Kiwix download + import pipeline with checksum validation and progress events.
   - Ingestion job auditing surfaced via `ragman-admin status`.
   - Refresh scheduler service (cron/systemd timer wrapper) that triggers periodic ingestion runs and records next-run metadata for status reporting.
   - Status aggregation endpoint surfacing last successful refresh, failures, and upcoming schedule to satisfy FR-009 transparency requirements.
3. **Retrieval & Generation**
   - Retriever orchestrating embedding queries, reranking, answer synthesis, and citation formatting.
   - Session persistence capturing model choice, response time, and cache metadata.
4. **Go CLIs**
   - `ragman`: single `ask` command supporting text/JSON output, model selection, context hints, cache control.
   - `ragman-admin`: commands for `run` (launch stack via Python control API), `status`, `ingest`, `feedback`, and future ops; includes completion scripts and logging.
5. **Testing & Tooling**
   - pytest suites (unit/integration/contract) with coverage enforcement.
   - go test suites for both CLIs, including golden outputs and gRPC mocks.
   - End-to-end CLI workflows verifying ingestion->ask->feedback loops and cache hit metrics.
   - Performance smoke harness measuring latency, ingestion duration, cache usage, and memory ceilings against constitution targets.
   - CI integration that surfaces ingestion benchmark results and resource metrics within `ragman-admin status` and release gates.
