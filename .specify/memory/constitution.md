<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0
Modified principles:
- Code Quality & Python Excellence -> Code Quality & Polyglot Excellence
- Engineering Standards (expanded with YAML configuration requirement)
Added sections:
- None
Removed sections:
- None
Templates requiring updates:
- updated .specify/templates/plan-template.md
- updated .specify/templates/spec-template.md
- updated .specify/templates/tasks-template.md
- updated specs/001-linux-rag-specification/quickstart.md
Follow-up TODOs:
- None
-->
# Linux RAG Constitution

## Core Principles

### Code Quality & Polyglot Excellence
All production Python code MUST target 3.11+, conform to PEP 8/PEP 257, include
type annotations for public APIs, and pass `ruff`, `black`, and `mypy` gates.
All Go code MUST build with Go 1.22+, pass `go fmt`/`goimports`, and clear
`golangci-lint` with `staticcheck`. Code reviews MUST block changes that reduce
readability, remove tests, or bypass lint/test workflows. Shared utilities
SHALL live in well-documented modules with explicit ownership and integration
notes across languages.

### Test Discipline & Safety Net
Every change MUST provide automated tests that fail before implementation, then
pass when the feature lands. Unit, integration, contract, and CLI regression
suites MUST run in CI and block release on failure. Python modules SHALL keep
>=90% statement coverage, Go packages SHALL keep >=85%, and critical data flows
MUST include regression tests reproducing prior incidents. Test fixtures MUST
avoid external network calls by default.

### Consistent User Experience
CLI commands, flags, and prompts MUST follow a single documented pattern, and
outputs MUST offer both human-readable text and machine-parsable variants.
Error messaging SHALL provide action-oriented guidance, and help/man pages MUST
stay synchronized with shipped behavior. Any UX-affecting change REQUIRES
acceptance criteria that confirm usability for both novice and expert users.

### Performance & Resource Efficiency
Interactive queries MUST return top-k answers within 2s p95 on reference Linux
hardware (8 vCPU, 16 GB RAM). Indexing jobs SHALL complete within 1.5x the
baseline ingestion benchmark, and memory usage MUST remain under 12 GB during
steady-state retrieval. Performance regressions REQUIRE documented profiling
data plus remediation tasks before merge.

## Engineering Standards

- Maintain a single source of truth package under `src/` with reproducible
  builds managed by `uv`; Go modules MUST reside under `src/go/` with tidy
  `go.mod` files.
- All configuration MUST be expressed in YAML; introducing TOML/JSON/INI
  requires an approved waiver.
- All new dependencies REQUIRE security review and pinned versions in lock
  files; transitive updates MUST run through the automated test suite.
- Observability MUST expose structured logs, latency counters, and retrieval
  hit rates consumable by local telemetry tooling.
- Documentation MUST live alongside code (`docs/`, `README`, docstrings) and be
  updated in the same pull request as functional changes.

## Workflow & Quality Gates

- Feature work MUST originate from a spec and plan derived via the `/speckit`
  commands, including Constitution Check sign-off.
- Pull requests REQUIRE at least one reviewer who verifies adherence to each
  principle and confirms gating tests executed locally or in CI.
- Releases MUST include CHANGELOG entries, performance validation evidence, and
  confirmation of UX documentation sync.
- Violations of principles MUST be resolved or formally waived with documented
  mitigation, time-bound follow-up, and product owner approval.

## Governance

This constitution supersedes conflicting team practices. Amendments REQUIRE a
recorded RFC, consensus of tech lead plus product owner, and version bump notes
documented in this file. Semantic versioning applies: MAJOR for removals or
breaking redefinitions, MINOR for new principles or expanded governance, PATCH
for clarifications. Compliance reviews MUST occur quarterly; findings feed into
the roadmap and cannot be deferred beyond one release cycle without leadership
sign-off.

**Version**: 1.1.0 | **Ratified**: 2025-10-15 | **Last Amended**: 2025-10-15
