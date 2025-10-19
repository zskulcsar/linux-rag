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

   The status command now surfaces ingestion progress, retry counts, refresh cadence, and cache eviction telemetry. A sample text report looks like:

   ```
   Latest ingestion job: job-123 (completed)
   Progress: 75.0% (stage: indexing)
   Retries: 1
   Man pages processed: 1234
   Wiki articles loaded: 567
   Errors: none

   Schedule summary:
     Cadence: 24h
     Next run: 2025-01-01T12:00:00Z
     Last success: 2025-01-01T09:00:00Z

   Cache usage: 42.5% (hit rate: 78%)
   Eviction telemetry:
     Total entries: 2048
     Total size: 512.0 MiB / 1.0 GiB
     Last eviction: n/a
     Removed: 12 entries (11.8 MiB)

   Active models: gemma3:1b, codegemma:2b
   ```

   Use `--format json` for machine parsing:

   ```bash
   ./bin/ragman-admin status --format json | jq .
   ```

   JSON output includes the same fields plus raw ingestion errors, making it easy to feed dashboards or alerting rules.

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

## Refresh Scheduling

- The scheduler defaults to a **24-hour cadence** for automatic refreshes. The configured cadence, next run, and last success timestamps are displayed under the “Schedule summary” section of `ragman-admin status`.
- Refresh metadata is persisted in `refresh_schedule.db` (default location: `/var/lib/linux-rag/state/refresh_schedule.db`). Update the cadence with SQLite if you need to change the schedule:

  ```bash
  sqlite3 /var/lib/linux-rag/state/refresh_schedule.db \
    "UPDATE refresh_schedule SET cadence_seconds = 43200 WHERE id = 1;"
  ```

  The example above switches the cadence to **12 hours** (`43200` seconds). Set `cadence_seconds` to `NULL` to disable automatic runs; `ragman-admin status` will then show “Cadence: disabled”.
- After adjusting the cadence, run `ragman-admin status --format json` to confirm the scheduler picked up the new value.

## Cache Eviction Reporting

- `ragman-admin status` reports cache health so you can keep `/var/lib/linux-rag/cache` within the 10% disk budget:
  - `Cache usage` displays the current percentage plus the query cache hit rate.
  - `Eviction telemetry` provides the total entries, total disk usage, the configured budget (default **1 GiB**), and details from the most recent eviction pass (timestamp, removed entries, bytes freed).
- If you see cache usage consistently above the budget or repeated evictions freeing large amounts of data, consider increasing the disk allocation or tightening ingestion cadence so stale data is recycled sooner.
- For troubleshooting, inspect `/var/lib/linux-rag/cache` directly or enable JSON output to feed the telemetry into monitoring tools:

  ```bash
  ./bin/ragman-admin status --format json | jq '.eviction'
  ```
