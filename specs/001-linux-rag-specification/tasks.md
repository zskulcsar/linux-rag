# Tasks: Linux CLI Knowledge Assistant

**Input**: Design documents from `/specs/001-linux-rag-specification/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Automated tests are REQUIRED. Include unit, integration, and contract tasks that enforce failing-first execution per the constitution. Only omit a category with documented waiver.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish language toolchains, configuration scaffolding, and documentation so engineering work can begin.

- [X] T001 Configure Python 3.11 project dependencies with uv in `pyproject.toml` (include dev extras for `ruff`, `black`, `mypy`)
- [X] T002 Initialize Go 1.22 module and cobra dependencies in `src/go/go.mod`
- [X] T003 [P] Wire lint, format, type-check, and test targets (`ruff`, `black`, `mypy`, `go test`, `pytest`) in `Makefile`
- [X] T004 Author base runtime configuration with volume defaults in `configs/local.yaml`
- [X] T005 [P] Document setup prerequisites and bootstrap flow in `docs/cli.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Provide shared infrastructure, contracts, cache management, and core data scaffolding that all user stories rely on.

- [X] T006 Finalize Podman compose stack for Weaviate, Ollama, and shared volumes in `infra/podman-compose.yml`
- [X] T007 [P] Provide optional systemd unit to launch the stack in `infra/systemd/linux-rag.service`
- [X] T008 [P] Generate Python gRPC stubs from `contracts/rag_service.proto` into `src/python/linux_rag/contracts/rag_service_pb2.py`
- [X] T009 [P] Generate Go gRPC client bindings from `contracts/rag_service.proto` into `src/go/internal/contracts/rag_service.pb.go`
- [X] T010 Create Python gRPC application skeleton with server bootstrap in `src/python/linux_rag/server/main.py`
- [X] T011 [P] Define shared entities (`KnowledgeSource`, `CacheEntry`) in `src/python/linux_rag/data/models.py`
- [X] T012 Establish SQLite schema and migrations for cache/session tables in `src/python/linux_rag/cache/schema.sql`
- [X] T013 [P] Implement refresh scheduler service orchestrating on-demand and scheduled ingestion in `src/python/linux_rag/ingestion/scheduler.py`
- [X] T014 Persist refresh cadence configuration and next-run metadata for status reporting in `src/python/linux_rag/ingestion/schedule_store.py`
- [X] T015 [P] Implement cache eviction worker enforcing disk budget in `src/python/linux_rag/cache/eviction.py`
- [X] T016 Instrument eviction telemetry (counters, gauges) exposed to status reporting in `src/python/linux_rag/cache/telemetry.py`

---

## Phase 3: User Story 1 - Guided Answers for Linux Tasks (Priority: P1) MVP

**Goal**: Deliver the `ragman` CLI experience that answers natural-language Linux questions with cited sources and cache support.

**Independent Test**: Run `tests/python/integration/test_ragman_cli.py` after seeding sample documents; ensure answers include citations, respect cache toggles, and finish within the performance budget.

### Tests for User Story 1 (write first and watch them fail)

- [X] T017 [P] [US1] Add failing gRPC contract test for `Ask` in `tests/python/contracts/test_rag_service_ask.py`
- [X] T018 [P] [US1] Add CLI integration test for `ragman ask` workflow in `tests/python/integration/test_ragman_cli.py`
- [X] T019 [P] [US1] Add unit tests for retrieval and ranking pipeline in `tests/python/unit/test_retrieval_pipeline.py`
- [X] T020 [P] [US1] Add unit tests for cache eviction worker enforcing budget in `tests/python/unit/test_cache_eviction.py`
- [X] T021 [P] [US1] Add Go unit tests for `ragman` flag validation and error guidance in `src/go/cmd/ragman/main_test.go`
- [X] T022 [P] [US1] Add Go golden output tests for `ragman` JSON/text rendering in `src/go/cmd/ragman/output_test.go`

### Implementation for User Story 1

- [X] T023 [P] [US1] Implement retrieval orchestrator that queries Weaviate and reranks candidates in `src/python/linux_rag/retrieval/pipeline.py`
- [X] T024 [P] [US1] Implement answer synthesis with Ollama models and citation assembly in `src/python/linux_rag/llm/response_builder.py`
- [X] T025 [US1] Wire `Ask` gRPC handler and cache integration in `src/python/linux_rag/server/handlers/ask.py`
- [X] T026 [US1] Implement `ragman` cobra command with flags (`--model`, `--format`, `--no-cache`) in `src/go/cmd/ragman/main.go`
- [X] T027 [US1] Add output formatting (text/JSON) and citation rendering helpers in `src/go/cmd/ragman/output.go`
- [X] T028 [US1] Implement invalid flag handling and user guidance responses in `src/go/cmd/ragman/errors.go`
- [X] T029 [US1] Persist `AnswerSession` records with cache metadata in `src/python/linux_rag/retrieval/session_store.py`
- [X] T030 [US1] Update usage documentation for `ragman ask` scenarios in `docs/cli.md`

---

## Phase 4: User Story 2 - Initial Knowledge Base Setup (Priority: P2)

**Goal**: Enable `ragman-admin` to launch the stack, ingest man pages and Kiwix archives, schedule refreshes, and report ingestion status.

**Independent Test**: Execute `tests/python/integration/test_ragman_admin_ingest.py` to confirm the admin CLI starts services, performs ingestion, reports schedule metadata, and surfaces completion metrics.

### Tests for User Story 2 (write first and watch them fail)

- [X] T031 [P] [US2] Add gRPC contract test for `RunIngestion`, `GetStatus`, and scheduled refresh reporting in `tests/python/contracts/test_run_ingestion.py`
- [X] T032 [P] [US2] Add admin CLI integration test covering `run -> ingest -> status` with schedule assertions in `tests/python/integration/test_ragman_admin_ingest.py`
- [X] T033 [P] [US2] Add unit tests for ingestion job orchestration and error recovery in `tests/python/unit/test_ingestion_pipeline.py`
- [X] T034 [P] [US2] Add unit tests for refresh scheduler triggers and cadence management in `tests/python/unit/test_refresh_scheduler.py`
- [X] T035 [P] [US2] Add Go unit tests for `ragman-admin` flag validation and error handling in `src/go/cmd/ragman-admin/main_test.go`
- [X] T036 [P] [US2] Add Go golden output tests for status/ingest summaries in `src/go/cmd/ragman-admin/status_test.go`

### Implementation for User Story 2

- [ ] T037 [P] [US2] Implement Podman stack lifecycle control helpers in `src/python/linux_rag/server/control.py`
- [ ] T038 [P] [US2] Build man page ingestion pipeline emitting `KnowledgeSource` records in `src/python/linux_rag/ingestion/man_pages.py`
- [ ] T039 [P] [US2] Implement Kiwix archive download and import workflow in `src/python/linux_rag/ingestion/kiwix.py`
- [ ] T040 [US2] Persist ingestion jobs, last refresh metrics, and failure history in `src/python/linux_rag/ingestion/jobs.py`
- [ ] T041 [US2] Extend gRPC handlers for `RunIngestion`/`GetStatus` with telemetry and schedule metadata in `src/python/linux_rag/server/handlers/admin.py`
- [ ] T042 [US2] Implement `ragman-admin` commands (`run`, `ingest`, `status`) in `src/go/cmd/ragman-admin/main.go`
- [ ] T043 [US2] Implement invalid flag handling and user guidance responses in `src/go/cmd/ragman-admin/errors.go`
- [ ] T044 [US2] Add progress, retries, schedule summary, and eviction telemetry output in `src/go/cmd/ragman-admin/status.go`
- [ ] T045 [US2] Document refresh scheduling configuration, cache eviction reporting, and status expectations in `docs/cli.md`

---

## Phase 5: User Story 3 - Source Transparency and Review (Priority: P3)

**Goal**: Provide citation browsing and local feedback capture so users can inspect sources and flag issues.

**Independent Test**: Execute `tests/python/integration/test_ragman_feedback.py` to verify citation listing, source opening, and feedback persistence via CLI commands.

### Tests for User Story 3 (write first and watch them fail)

- [ ] T046 [P] [US3] Add gRPC contract test for `SubmitFeedback` and citation retrieval in `tests/python/contracts/test_feedback_and_sources.py`
- [ ] T047 [P] [US3] Add integration test for citation review and feedback submission in `tests/python/integration/test_ragman_feedback.py`
- [ ] T048 [P] [US3] Add unit tests for feedback repository and status transitions in `tests/python/unit/test_feedback_repository.py`

### Implementation for User Story 3

- [ ] T049 [P] [US3] Implement source excerpt retrieval service exposing local file pointers in `src/python/linux_rag/retrieval/sources.py`
- [ ] T050 [P] [US3] Persist `FeedbackEntry` records with status workflow in `src/python/linux_rag/feedback/store.py`
- [ ] T051 [US3] Extend gRPC handlers for feedback submission and source listing in `src/python/linux_rag/server/handlers/feedback.py`
- [ ] T052 [US3] Implement `ragman-admin feedback` subcommand with filtering in `src/go/cmd/ragman-admin/feedback.go`
- [ ] T053 [US3] Document transparency and review workflows in `docs/cli.md`

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Consolidate performance, observability, and documentation across all user stories.

- [ ] T054 [P] Add ingestion benchmark harness capturing duration and success metrics in `scripts/perf/ingestion_benchmark.py`
- [ ] T055 Integrate ingestion benchmark and cache metrics into CI/performance reports in `.github/workflows/perf-ingestion.yml`
- [ ] T056 [P] Add retrieval memory usage monitor with alert thresholds in `scripts/perf/retrieval_memory_check.py`
- [ ] T057 [P] Add latency benchmark harness to enforce 2s p95 in `scripts/perf/latency_benchmark.py`
- [ ] T058 [P] Build cache usage monitoring and eviction health script enforcing 10% budget in `scripts/perf/cache_budget_check.py`
- [ ] T059 Update operations guide with validation checklist in `docs/operations.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 → Phase 2**: Setup must complete before infrastructure work.
- **Phase 2 → Phases 3-5**: Foundational contracts, scheduler, and cache eviction services are required before any user story.
- **Phase 6**: Executes after the targeted user stories (Phases 3-5) reach completion.

### User Story Dependencies

- **US1 (P1)**: Depends on foundational gRPC server, cache infrastructure, and data models; unlocks answering capability.
- **US2 (P2)**: Depends on foundations plus scheduler and eviction services to provide ingestion, refresh, and status reporting.
- **US3 (P3)**: Depends on US1’s session records and US2’s ingestion metadata to surface citations and feedback.

### Task-Level Notes

- Complete tests in each story before implementing the corresponding features to preserve failing-first discipline.
- CLI tasks in Go can proceed in parallel with Python handler work once protocol stubs are generated (T008-T009).
- Scheduler tasks (T013-T014) and eviction tasks (T015-T016) must complete before US2 implementation to ensure FR-009 and NFR-005 compliance.
- Documentation updates should trail implementation to reflect actual behavior.
- CLI error-handling tasks (T028, T043) close FR-005 by ensuring actionable guidance for invalid usage.

---

## Parallel Execution Examples

- **US1**: Run T017-T022 concurrently to define failing tests, then develop T023 and T024 in parallel while T026 handles CLI wiring.
- **US2**: T038 and T039 can proceed simultaneously while T037 prepares stack control; Go CLI tasks T042-T044 can run once T041 stabilizes responses.
- **US3**: T049 and T050 can be developed together, followed by CLI extension T052 while T053 refreshes documentation.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Finish Phases 1 and 2 to establish tooling, containers, contracts, scheduler, and eviction scaffolding.
2. Deliver Phase 3 (US1) to ship the `ragman` answering experience with caching, citations, and resilient CLI usage guidance.
3. Validate using the US1 independent test suite before expanding scope.

### Incremental Delivery

1. After MVP, implement Phase 4 (US2) to cover ingestion, scheduled refreshes, and administration (including error guidance).
2. Layer Phase 5 (US3) for transparency and feedback, maintaining independent verification at each stage.
3. Close with Phase 6 polish to lock in performance budgets and operational documentation.

### Parallel Team Strategy

1. Team finishes Phases 1-2 collectively.
2. Assign separate engineers to US1, US2, and US3 once foundations are ready, coordinating through generated stubs, scheduler interfaces, cache services, and shared CLI patterns.
3. Rejoin for Polish tasks to ensure consistent benchmarks and documentation before release.
