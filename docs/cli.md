# Linux RAG CLI Setup

This guide covers the local prerequisites and bootstrap flow for bringing up the Linux RAG stack and its Go CLIs (`ragman`, `ragman-admin`).

## Prerequisites

- Linux host with Podman 4.x and `podman-compose`
- Python 3.11 with [`uv`](https://github.com/astral-sh/uv) available on `PATH`
- Go 1.22 toolchain
- Local Ollama installation with the following models downloaded: `gemma3:1b`, `codegemma:2b`, `embeddinggemma`
- At least **30 GB** of free space under `/var/lib/linux-rag` for Weaviate data, cache storage, and model assets
- Optional: Network access to the Kiwix catalog for downloading wiki archives during ingestion

## Bootstrap Flow

1. **Clone and install dependencies**

   ```bash
   git clone <repo-url>
   cd linux-rag
   uv sync
   ```

   Running `uv sync` provisions the `.venv/` environment used by linting, tests, and Python services.

2. **Build the Go CLIs**

   ```bash
   mkdir -p bin
   go build -o bin/ragman ./src/go/cmd/ragman
   go build -o bin/ragman-admin ./src/go/cmd/ragman-admin
   ```

   A future `make cli` target may automate these builds; the manual commands above ensure binaries exist until that target is available.

3. **Review local runtime configuration**

   The default configuration lives in `configs/local.yaml`. Key paths include:

   - `runtime.socket_path`: `/run/linux-rag/rag-service.sock`
   - `paths.data_root`: `/var/lib/linux-rag`
   - `paths.ollama_models_dir`: `/var/lib/linux-rag/ollama`

   Adjust values if your host uses different locations or if Podman requires alternative volume mounts.

4. **Launch the stack**

   ```bash
   ./bin/ragman-admin run --config configs/local.yaml
   ```

   The admin CLI orchestrates the Podman compose stack (`infra/podman-compose.yml`), waits for Weaviate and Ollama readiness, and starts the Python gRPC service.

5. **Seed documentation sources**

   ```bash
   ./bin/ragman-admin ingest \
     --man-root /usr/share/man \
     --wiki gemma-essential \
     --wiki linux-desktop
   ```

   Ingestion records reside under `/var/lib/linux-rag/kiwix` and `/var/lib/linux-rag/weaviate`. You can override archive IDs or rerun ingestion later if the Kiwix service is temporarily unavailable.

6. **Verify status**

   ```bash
   ./bin/ragman-admin status
   ```

   Confirm cache usage, active models, and the latest ingestion job status before handing the system to end users.

7. **Ask questions**

   ```bash
   ./bin/ragman ask "How do I enable automount on boot?"
   ./bin/ragman ask --model codegemma:2b --format json "Create a systemd unit to remount /data"
   ```

   Use `--no-cache` to bypass the SQLite response cache when you need fresh answers.

## Testing (optional during bootstrap)

- Run Python tests: `uv run pytest`
- Run Go tests: `go test ./src/go/...`

These commands help confirm the environment is healthy before further development.
