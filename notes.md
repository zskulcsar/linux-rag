# Worfklow

## /constituttion

## /specify

## /tasks

## /analyze

## /checklist

## /implement

Implementing such a large feature is unwise. Use the following from the codex command line for iterate over the tasks: `/prompts:speckit.implement Implement <task-id> only. You **must not** consider any other tasks.`

### Phase 1

* At this stage the `/implement` command will always asks for confirming code generation as the requirements set in the `specs/xxx-feature-specification/checklists/*` likely are not met. This is understandable as we're in the project setup phase.

This will implement the task which you should verify and commit the changes to git

## Capture of codex **Next steps**

| Task ID | Codex **Next steps** |
|---------|----------------------|
| T002 | When network access is available, run `cd src/go && go mod tidy` so go.sum is populated before building downstream tasks. |
| T003 | You may next want to populate src/python or tests/python so the Python-specific targets run against real sources, and install pytest via your chosen workflow before trying make test. |
| T004 | 1) Have future stack orchestration code consume configs/local.yaml values; 2) Adjust the config as upcoming tasks introduce additional services or environment overrides. |
| T005 | Next up: 1) Align the build instructions with an eventual make cli target so docs and tooling stay in sync; 2) Expand docs as CLI commands are implemented (status, ingest options, troubleshooting). |
