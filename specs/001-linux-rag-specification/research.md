# Research Summary - Linux CLI Knowledge Assistant

## Decision: Podman Compose Orchestration for Local Stack
- **Rationale**: Podman/podman-compose aligns with the project's container tooling, provides rootless isolation, and simplifies bundling Weaviate, Ollama-sidecar, and auxiliary services with predictable volumes at `/var/lib/linux-rag`.
- **Alternatives considered**: Docker Compose (incompatible with project Podman mandate); systemd units (higher maintenance, harder to share); ad-hoc scripts (fragile dependency ordering).

## Decision: Python Retrieval Service with Async gRPC Bridge
- **Rationale**: A dedicated Python 3.11 service exposes ingestion/retrieval/caching via gRPC (using `grpc.aio`), enabling the Go cobra CLIs to call into stable contracts while reusing Python's mature Weaviate + Ollama SDKs.
- **Alternatives considered**: REST over HTTP (slower startup, heavier deps); direct CLI-to-Python subprocess calls (complex state management, brittle streaming).

## Decision: Separate Go CLIs for User and Admin Workflows
- **Rationale**: Splitting into `ragman` (query UX) and `ragman-admin` (operations) keeps user command surface minimal, reduces flag ambiguity, and allows admin tooling to orchestrate stack startup (`run`), ingestion, status checks, and feedback without exposing internal switches to end users.
- **Alternatives considered**: Single CLI with subcommands (risk of confusing flags, harder onboarding); Python-only admin scripts (`uv run python -m ...`) (less discoverable, inconsistent with Go UX); GUI/dashboard (out of scope for CLI-focused workflows).

## Decision: Query/Response Cache via SQLite with Size Guard
- **Rationale**: SQLite offers ACID persistence, straightforward size accounting, and supports eviction policies (LRU via access timestamps) to enforce the 10 percent disk budget without external daemons.
- **Alternatives considered**: Plain files (harder eviction/bookkeeping); Redis (additional service weight); LMDB (less familiar to team, limited tooling).

## Decision: Kiwix Archive Downloads Managed by python-kiwix CLI Wrapper
- **Rationale**: Leveraging the `kiwix-serve` and `kiwix-manage` CLI via Python subprocess keeps compatibility with the official library catalog JSON and simplifies checksum verification before import.
- **Alternatives considered**: Direct HTTP downloads (manual catalog parsing); embedding Kiwix lib (build complexity); expecting users to preload archives (violates requirement to offer curated downloads).

## Decision: Model Selection Strategy with Ollama
- **Rationale**: Offer `gemma3:1b` as default lightweight model and `codegemma:2b` for technical instructions; use `embeddinggemma` for vectorization. All models fetched via Ollama APIs and documented in quickstart with switch flags.
- **Alternatives considered**: llama3 derivatives (larger footprints); remote APIs (break offline constraint); mixing providers (adds operator burden).

## Decision: Testing Strategy Across Python & Go Components
- **Rationale**: Python side covered by pytest (unit/integration) plus contract tests hitting the gRPC surface; Go CLIs validated via `go test` and golden-file expectations; end-to-end scenario scripts ensure ingestion, query, and cache metrics satisfy constitution gates.
- **Alternatives considered**: Fully manual acceptance (insufficient coverage); relying solely on integration tests (slow feedback); splitting repos (harder coordination).
