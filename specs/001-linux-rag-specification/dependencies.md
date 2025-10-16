# Dependencies - Linux CLI Knowledge Assistant

This document captures required development tools and runtime dependencies referenced in `tasks.md`. Status reflects availability on the current workstation at the time of analysis.

| Tool / Dependency | Purpose | Tasks | Status | Install Command |
|-------------------|---------|-------|--------|-----------------|
| Python 3.12.3 (`python3`) | Runtime for services, tests, scripts | T010-T041, T046-T058 | present | n/a |
| uv | Python package management / virtual env | T010-T041, T046-T058 | present | n/a |
| ruff | Python linting | T010-T016, T023-T025, T029-T034, T037-T041, T046-T051, T054, T056-T058 | present | n/a |
| black | Python formatting | T010-T016, T023-T025, T029-T034, T037-T041, T046-T051, T054, T056-T058 | present | n/a |
| mypy | Python type checking | T010-T016, T023-T025, T029-T034, T037-T041, T046-T051 | present | n/a |
| pytest | Python unit/integration tests | T017-T020, T031-T034, T046-T048 | present | n/a |
| pytest-asyncio | Async pytest support | T017-T020, T031-T034, T046-T048 | present | n/a |
| Go 1.25.3 (`go`) | Build/test Go CLIs | T021, T022, T026-T028, T035, T036, T042-T044, T052 | present | n/a |
| golangci-lint | Go linting bundle | T021, T022, T026-T028, T035, T036, T042-T044, T052 | present | n/a |
| staticcheck | Go static analysis | T021, T022, T026-T028, T035, T036, T042-T044, T052 | present | n/a |
| Podman | Container orchestration | T037, T038, T042, T044, T054 | present | n/a |
| podman-compose | Compose stack management | T037, T042, T054 | missing | `pip install --user podman-compose` |
| Ollama | Local model runtime | T024, T041, T054 | present | n/a |
| weaviate-python-client | Vector DB client | T023, T038 | present | n/a |
| grpcio | Python gRPC support | T010, T017, T031, T041, T046, T051 | present | n/a |
| protoc | Proto compiler | T017, T031, T046 | present | n/a |
| kiwix-manage | Manage Kiwix archives | T039, T042, T047 | missing | `sudo apt-get install kiwix-tools` |
| kiwix-serve | Serve Kiwix content | T039, T042, T047 | missing | `sudo apt-get install kiwix-tools` |
| sqlite3 | Inspect SQLite cache | T012, T029, T040, T050 | missing | `sudo apt-get install sqlite3` |
