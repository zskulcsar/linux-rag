# Worfklow

## /constituttion

## /specify

## /tasks

## /analyze

## /checklist

## /implement

Implementing such a large feature is unwise. Use the following from the codex command line for iterate over the tasks: `/prompts:speckit.implement Implement <task-id> only. You **must not** consider any other tasks.`. See notes.

### Phase 1

* At this stage the `/implement` command will always asks for confirming code generation as the requirements set in the `specs/xxx-feature-specification/checklists/*` likely are not met. This is understandable as we're in the project setup phase. Codex output: `Overall status: FAIL — some checklists are incomplete. Do you want to proceed with implementation anyway? (yes/no)`

This will implement the task which you should verify and commit the changes to git

## Capture of codex **Next steps**

| Task ID | Codex **Next steps** |
|---------|----------------------|
| T002 | When network access is available, run `cd src/go && go mod tidy` so go.sum is populated before building downstream tasks. |
| T003 | You may next want to populate src/python or tests/python so the Python-specific targets run against real sources, and install pytest via your chosen workflow before trying make test. |
| T004 | 1) Have future stack orchestration code consume configs/local.yaml values; 2) Adjust the config as upcoming tasks introduce additional services or environment overrides. |
| T005 | Next up: 1) Align the build instructions with an eventual make cli target so docs and tooling stay in sync; 2) Expand docs as CLI commands are implemented (status, ingest options, troubleshooting). |
| T006 | Next steps: 1) Ensure the host path /var/lib/linux-rag (or overridden LINUX_RAG_DATA_ROOT) exists with appropriate permissions before bringing the stack up; 2) Update upcoming automation (ragman-admin run) to pass the LINUX_RAG_DATA_ROOT value when launching podman-compose. |
| T007 | Next steps: 1) Adjust LINUX_RAG_REPO/LINUX_RAG_COMPOSE_FILE in /etc/linux-rag.env for the deployment host; 2) systemctl enable --now linux-rag once Podman and podman-compose are installed. |
| T008 |   1. git add src/go/internal/contracts/*.pb.go specs/001-linux-rag-specification/contracts/rag_service.proto specs/001-linux-rag-specification/tasks.md 2. Run go test ./... from src/go to confirm the module still builds |
| T010 | Next steps: 1) Install PyYAML and the type stub packages once network access is available, then rerun uv sync --dev and mypy. 2) Continue with T011 to fill in shared entity models that the dispatcher will  eventually call. |

## Notes

* In order to use [context7](https://context7.com/) the `.codex/prompts/speckit.implement.md` file was modified adding the text before the **## Outline**: `You **MUST** use the configured MCP servers. use context7.`. After this the context7 usage can be seen in the codex cli output.
* The `.codex/prompts/speckit.implement.md` file can be modified so that the whole prompt doesn't need to be typed every time and `/implement` can be called with a \<task_id\> only.
* Using the provided `make *` commands after the task implementation is a good idea to verify. On issues ask codex to fix them.
* Method documentation is really nothing, will need to fix later
* TODO: We're missing the stop/down command in go `ragman-admin`
* Due to socket permission issues (and for testability) a new environment variable was introduced: `LINUX_RAG_SKIP_STACK` with values `1`, `true`, `yes` to skip integration tests. It is now the default in `./tests/python/integration/test_ragman_admin_ingest.py`.

## Task notes

### T006

* TODO: `infra/podman-compose.yml` uses `TEXT2VEC_OLLAMA_API_ENDPOINT` for the weavite service. According to issue [#8406](https://github.com/weaviate/weaviate/issues/8406) this environment variable doesn't exist. Either we can use `host.docker.internal` as per [Configure the vectorizer](https://docs.weaviate.io/weaviate/model-providers/ollama/embeddings#configure-the-vectorizer) which likely [won't work in Linux](https://stackoverflow.com/questions/48546124/what-is-the-linux-equivalent-of-host-docker-internal) or we'll need to find the instructions on how to call `http://ollama:11434`. Anyways - main point is: the variable doesn't exist and needs some code adjusting to explicitly specify the endpoint. Can't be done yet as there is no code.

### T008

* `python3 -m grpc_tools.protoc` fails with `(ModuleNotFoundError: No module named 'grpc_tools')`: 1) `source .venv/bin/activate` for tool use; then 2) `uv pip install grpc_tools` so that codex can run generate the gRPC python code.

### T009

* This will likely use `protoc` which needs installing. Info @ [protobuf.dev](https://protobuf.dev/installation/); Installed via `sudo apt install -y protobuf-compiler`. This was followed with [goctl](https://go-zero.dev/en/docs/tasks/installation/protoc) and finally adjusting the `$PATH` variable in `~/.profile` such as `export PATH=$PATH:/usr/local/go/bin:/$HOME/go/bin`. Also adding `export GO111MODULE=on` to the `.envrc`.
* Install the dependencies via `go install google.golang.org/protobuf/cmd/protoc-gen-go@latest` and `go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest`
* At the end of the generation runing `make test-go` fails with module dependencies; here comes T002's next steps `cd src/go && go mod tidy` which pulls all dependencies fixing `make test-go`. Sadly: `[no test files]`, but at least it runs :)

### T025

* `src/python/linux_rag/server/handlers/ask.py: tightened imports, relaxed type annotations to Any` - not the best, but `make lint typecheck` works :)
* Also `ignore_missing_imports = True`, I mean ...

### T026

* First try didn't use spf13/cobra. it wasn't bad, but we asked for Cobra (although not much mention but T026 mentionds it and codex asked for specs via context7) - asked to rewrite (next time include, "use context7") ... and it did.
* But network access is not allowed in the sandbox, hence generating minimal api under vendor.
* also, test are failing `cd src/go && GOCACHE=$(pwd)/.gocache GOMODCACHE=$(pwd)/.gomodcache go test ./...`, asked codex about it, the answer as follows:
> 1. Regenerate the vendor manifest so `modules.txt` lists every dependency exactly the way the Go toolchain expects. Normally you do this with `go mod vendor`, which fills `vendor/` and writes the correct metadata;
    if we need offline copies we can run it in an environment with network access, then commit the resulting `vendor` tree.
> 2. If we’re keeping local replacements (e.g., our shim Cobra/pflag implementations), we must keep the replace directives in `go.mod` and ensure `modules.txt` includes the `## replace` lines the toolchain generates.
> 3. Alternatively, if we don’t truly need vendoring, we could remove the `vendor/` directory so Go stops enforcing `modules.txt`; but that only works if we regain network access.

## How to test

* start the stack with `PYTHONPATH=/home/zsoltk/git/linux-rag LINUX_RAG_SOCKET="${XDG_RUNTIME_DIR:-/tmp}/linux-rag/rag-service.sock" go run ./cmd/ragman-admin run --config /home/zsoltk/git/linux-rag/configs/test.yaml --wait-ready` in `src/go`

#### Where we left off
codex resume 0199eeaa-5207-7c22-8c9b-bed94f73cb5c
