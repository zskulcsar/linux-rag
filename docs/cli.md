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

   `ragman ask` sends your query to the Python gRPC service and renders the answer with citations. Common flags:

   - `--model, -m`: choose between `gemma3:1b` (default) and `codegemma:2b`
   - `--format, -f`: switch between `text` and `json` output
   - `--no-cache`: bypass the local SQLite cache for a fresh response
   - `--hint`: pass additional retrieval keywords (repeatable)
   - `--socket`: override the Unix socket path (defaults to `/run/linux-rag/rag-service.sock`)
   - `--timeout`: adjust the RPC timeout (default `15s`)

   ```bash
   ./bin/ragman ask "How do I enable automount on boot?"
   ./bin/ragman ask --model codegemma:2b --hint automount --hint systemd \
     "Create a systemd unit to remount /data"
   ./bin/ragman ask --format json --no-cache \
     "Show me the command to list running services"
   ```

   Sample JSON output:

   ```json
   {
     "query": "Show me the command to list running services",
     "session_id": "1c5b6b86-a9a0-4d1c-9f0d-2d2e8dc4b9cd",
     "answer": "Use `systemctl list-units --type=service` to list running services.",
     "model": "gemma3:1b",
     "response_time_ms": 142,
     "cache_hit": false,
     "citations": [
       {
         "id": "doc-1",
         "title": "systemctl reference",
         "snippet": "`systemctl list-units --type=service` lists active service units.",
         "source_path": "/var/lib/linux-rag/man/systemctl.1"
       }
     ]
   }
   ```

   Use the `--socket` flag when the service runs under a non-default path or through a forwarded TCP endpoint. For quick smoke tests without starting the stack, `ragman` also supports `--socket mock://demo`, which renders deterministic sample data directly in the CLI.

## Testing (optional during bootstrap)

- Run Python tests: `uv run pytest`
- Run Go tests: `go test ./src/go/...`

These commands help confirm the environment is healthy before further development.
