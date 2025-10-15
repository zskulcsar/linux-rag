# Feature Specification: Linux CLI Knowledge Assistant

**Feature Branch**: `001-linux-rag-specification`  
**Created**: 2025-10-15  
**Status**: Draft  
**Input**: User description: "Were developing a Linux RAG system that is to be used from the command line. The idea is that instead of using `man command` the user can install this service on their linux installation and after the initial data load, theu can ask more complicated questions, like how to enable automount on boot and the tool will reply with a dedicated answer using all the relevant information from its data sources. The system should use the local man pages along with various locally installed wikis for"

## Clarifications

### Session 2025-10-15
- Q: What retention policy applies to user queries and feedback? -> A: Retain queries and responses locally to accelerate repeat answers.
- Q: How should the installer offer Kiwix archive choices? -> A: Fetch archive list dynamically from Kiwix library API.
- Q: How should installation behave if the Kiwix API is unreachable? -> A: Allow install without archives; user can retry later.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guided Answers for Linux Tasks (Priority: P1)

A Linux user runs the `ragman` CLI, asks a natural-language question such as "How do I enable automount on boot?", and receives a concise, step-by-step answer with references to source material.

**Why this priority**: Delivering accurate, contextual answers is the core value proposition and unlocks immediate utility over traditional `man` pages.

**Independent Test**: Execute an acceptance script that seeds the knowledge base, submits representative queries, and verifies responses include actionable steps plus cited sources; the script MUST fail if answers are missing, inaccurate, or lack citations.

**Acceptance Scenarios**:

1. **Given** a user with the assistant installed and knowledge base loaded, **When** they run `ragman ask "How do I enable automount on boot?"`, **Then** the tool returns a step-by-step answer referencing relevant manuals or wiki entries.
2. **Given** the user asks a follow-up question related to the previous topic, **When** the assistant processes the query, **Then** the answer incorporates the new request while maintaining context-specific guidance.

---

### User Story 2 - Initial Knowledge Base Setup (Priority: P2)

An administrator uses the `ragman-admin` CLI to launch the knowledge stack, run the initial data load, and confirm local man pages and offline wiki archives are ingested without requiring ongoing internet access.

**Why this priority**: A reliable setup experience ensures the assistant reflects the user's system documentation and builds trust in the answers provided.

**Independent Test**: Run a setup checklist that installs the tool, configures data sources, executes ingestion, and verifies the knowledge base indexes required collections; the checklist MUST fail if any source is missing or out of sync post-ingestion.

**Acceptance Scenarios**:

1. **Given** a fresh installation, **When** the administrator runs `ragman-admin run` followed by `ragman-admin ingest`, **Then** the process completes with progress feedback and a summary of sources ingested, including counts of man pages and wiki articles.
2. **Given** the ingestion completes, **When** the administrator requests a status report with `ragman-admin status`, **Then** the assistant lists available sources and last refresh timestamps.

--- 

### User Story 3 - Source Transparency and Review (Priority: P3)

A power user requests to see the origin documents backing an answer, opens referenced passages, and submits feedback via `ragman-admin` that is stored locally for future review.

**Why this priority**: Transparency builds confidence in the assistant's guidance and enables users to verify or escalate documentation gaps.

**Independent Test**: Execute a review workflow that retrieves an answer, inspects its cited sources, records feedback locally, and verifies entries persist for later review; the workflow MUST fail if citations cannot be opened or feedback is not stored.

**Acceptance Scenarios**:

1. **Given** a user receives an answer, **When** they request sources, **Then** the assistant returns a list of manuals or wiki entries with section-level pointers.
2. **Given** the user believes an answer is outdated, **When** they submit feedback, **Then** the assistant stores the feedback entry locally with the associated query for follow-up.

---

### Edge Cases

- Empty or ambiguous queries should prompt clarifying guidance instead of returning unrelated results.
- If a data source is unavailable during ingestion, the process must report the failure, retry, and provide remediation steps.
- When users input unsupported flags or malformed commands, the assistant must respond with usage examples without exiting abruptly.
- Batch queries or long-running requests must maintain the performance budget (answers within 2 seconds p95) and degrade gracefully with progress feedback.
- Download interruptions during Kiwix archive acquisition must resume cleanly or provide recovery instructions without corrupting partial data.
- If the Kiwix catalog cannot be reached during setup, the installer must continue without wiki archives and clearly instruct users how to retry downloads later.
- Cache eviction must prevent storage growth beyond the 10% disk budget, and users must receive guidance when older answers are purged.
- If `ragman-admin run` fails to launch services, the command must surface actionable remediation steps (missing Podman, port conflicts) instead of leaving partial state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide the `ragman` CLI that accepts natural-language Linux administration questions and returns step-by-step answers with cited sources.
- **FR-002**: System MUST ingest local man pages and any wiki archives downloaded during setup, then confirm completion with a status summary.
- **FR-003**: System MUST allow users to request full source excerpts for any answer and open them in a readable format.
- **FR-004**: System MUST persist query and response cache entries locally, including raw query text and generated answer content, to accelerate repeat answers.
- **FR-005**: System MUST validate command usage, handle unsupported flags, and deliver actionable guidance without crashing.
- **FR-006**: System MUST provide an installation workflow that pulls the latest Kiwix wiki catalog from the Kiwix library API, allows the user to select desired sets, downloads them on demand, and verifies their integrity before ingestion.
- **FR-007**: System MUST provide the `ragman-admin` CLI with commands for `run`, `status`, `ingest`, `feedback`, and future administrative operations, eliminating the need for direct `podman-compose` or `uv run python -m` usage.
- **FR-008**: System MUST capture user feedback on answer accuracy and retain submissions for review.
- **FR-009**: System MUST refresh the knowledge base on demand or on a scheduled cadence and report any skipped or failed documents.

### Key Entities *(include if feature involves data)*

- **Knowledge Source**: Represents a manual page or wiki article with metadata such as title, category, version timestamp, and local file reference.
- **Answer Session**: Captures each user query, the generated response, referenced sources, response time, and optional user feedback flag.
- **Ingestion Job**: Records each data-load or refresh run, including start/end times, source coverage, error details, and retry status.

### Non-Functional Requirements *(align with Constitution)*

- **NFR-001 (Code Quality & Python Excellence)**: All deliverables MUST include type annotations, user-facing documentation, and pass agreed automated linting and typing gates before merge.
- **NFR-002 (Test Discipline & Safety Net)**: Automated unit, integration, and regression suites MUST exist for ingestion, querying, and feedback flows, and MUST fail without implementation before passing with completed work.
- **NFR-003 (Consistent User Experience)**: CLI commands MUST follow project-wide naming and flag conventions, provide both readable and machine-parsable outputs, and remain synchronized with help documentation.
- **NFR-004 (Performance & Resource Efficiency)**: Query responses MUST achieve p95 latency of 2 seconds or less on reference hardware, ingestion runs MUST complete within 1.5 times baseline duration, and memory usage during querying MUST stay under 12 GB.
- **NFR-005 (Caching Discipline)**: Persistent query/response caching MUST remain within 10% of allocated disk usage after all sources are ingested and MUST evict least-used entries before exceeding the budget.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 90% of benchmark queries return correct, actionable answers with at least two cited sources within 2 seconds.
- **SC-002**: Initial ingestion completes within 30 minutes for a standard workstation documentation set and reports 100% coverage of available man pages and targeted wikis.
- **SC-003**: At least 85% of pilot users report improved task completion confidence compared to using `man` alone, as measured by post-session surveys.
- **SC-004**: Repeat query benchmarks achieve at least an 80% cache hit rate, with cached responses returned in under 1 second.
- **SC-005**: All selected Kiwix archives download successfully with checksum verification on first attempt or present actionable retry instructions within 5 minutes of failure.
- **SC-006**: Installation succeeds even when the Kiwix catalog is offline, and users receive clear guidance for performing archive downloads after connectivity is restored.
- **SC-007**: Persistent cache storage remains at or below 10% of the system's allocated disk usage, verified automatically after ingestion and during monthly health checks.

## Assumptions & Dependencies

- Users operate on Linux environments with administrative privileges to install and index local documentation.
- Target installations already include the necessary man pages; wiki archives can be missing because the installer fetches a fresh catalog from the Kiwix library API, offering user-selected downloads.
- The CLI assistant will be distributed through the project's standard packaging process, and updates to documentation are expected at least quarterly.
- The assistant operates on user-controlled machines without additional privacy constraints on stored queries or feedback.
- Persistent caching may retain raw query text and answer content, provided the disk usage budget is enforced.
