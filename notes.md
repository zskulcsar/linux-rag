# Worfklow

## /constituttion

## /specify

## /tasks

## /analyze

## /checklist

## /implement

Implementing such a large feature is unwise. Use the following from the codex command line for iterate over the tasks: `/prompts:speckit.implement Implement <task-id> only. You **must not** consider any other tasks.`

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

## Notes

* In order to use [context7](https://context7.com/) the `.codex/prompts/speckit.implement.md` file was modified adding the text before the **## Outline**: `You **MUST** use the configured MCP servers. use context7.`. After this the context7 usage can be seen in the codex cli output.

## Task notes

### T006

* TODO: `infra/podman-compose.yml` uses `TEXT2VEC_OLLAMA_API_ENDPOINT` for the weavite service. According to issue [#8406](https://github.com/weaviate/weaviate/issues/8406) this environment variable doesn't exist. Either we can use `host.docker.internal` as per [Configure the vectorizer](https://docs.weaviate.io/weaviate/model-providers/ollama/embeddings#configure-the-vectorizer) which likely [won't work in Linux](https://stackoverflow.com/questions/48546124/what-is-the-linux-equivalent-of-host-docker-internal) or we'll need to find the instructions on how to call `http://ollama:11434`. Anyways - main point is: the variable doesn't exist and needs some code adjusting to explicitly specify the endpoint. Can't be done yet as there is no code.
