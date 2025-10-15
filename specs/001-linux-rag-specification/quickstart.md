# Quickstart - Linux CLI Knowledge Assistant

## Prerequisites

- Linux host with Podman 4.x and podman-compose
- Python 3.11 with `uv` for dependency management
- Go 1.22 toolchain for the cobra CLIs (`ragman`, `ragman-admin`)
- Ollama installed locally with GPU/CPU support (models: gemma3:1b, codegemma:2b, embeddinggemma)
- At least 30 GB free disk space under `/var/lib/linux-rag`

## 1. Clone and Bootstrap

```bash
git clone <repo-url>
cd linux-rag
uv sync  # installs python dependencies under .venv
make go-deps  # installs go modules and tooling (gofmt, golangci-lint)
```

## 2. Build CLIs and Support Binaries

```bash
make cli  # produces ./bin/ragman and ./bin/ragman-admin
```

## 3. Start the Knowledge Stack via Admin CLI

```bash
./bin/ragman-admin run --config configs/local.yaml
```

- Launches Podman compose services (Weaviate, Ollama) with shared volumes under `/var/lib/linux-rag`
- Boots the Python gRPC server and monitors readiness before returning control

## 4. Seed Documentation Sources

```bash
./bin/ragman-admin ingest --man-root /usr/share/man --wiki gemma-essential --wiki linux-desktop
```

- Admin CLI fetches the latest Kiwix catalog, downloads selected archives, and records ingestion jobs
- Use `./bin/ragman-admin status` to verify document counts and job history

## 5. Ask Questions with ragman

```bash
./bin/ragman ask "How do I enable automount on boot?"
./bin/ragman ask --model codegemma:2b --format json "Create a systemd unit to remount /data"
```

- Responses include citations; pass `--no-cache` to force regeneration when needed

## 6. Ongoing Operations

- `./bin/ragman-admin status` reports ingestion health, cache usage percentage, and active models
- `./bin/ragman-admin feedback --session <id> --rating negative --comment "Needs SELinux context"` stores review notes
- `./bin/ragman-admin stop` gracefully tears down services (optional if using systemd service)

## 7. Run Tests

```bash
uv run pytest
GOFLAGS=-mod=vendor go test ./src/go/...
uv run python -m linux_rag.tests.e2e.cli_workflows
```

All suites must pass before shipping; CI mirrors these commands in dedicated jobs.
