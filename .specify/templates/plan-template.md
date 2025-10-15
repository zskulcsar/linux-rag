# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. Refer to the project tooling guide for command usage and required inputs.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!-- Document concrete values for this feature. Defaults should assume Python 3.11+, pytest, and the local Linux execution environment unless deliberately overridden. -->

**Language/Version**: [Python 3.11 or newer - confirm if different]  
**Primary Dependencies**: [e.g., FastAPI, Typer, Weaviate client]  
**Storage**: [e.g., Weaviate, on-disk index, N/A]  
**Testing**: [pytest + plugins, contract/integration harness]  
**Target Platform**: [Linux CLI runtime - specify distribution if relevant]
**Project Type**: [single/web/mobile - determines source structure]  
**Performance Goals**: [map to Constitution performance budgets or stricter targets]  
**Constraints**: [e.g., <2s p95 query latency, <12GB RAM steady state]  
**Scale/Scope**: [expected dataset size, number of commands, concurrent users]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Code Quality & Polyglot Excellence: Document linting/formatting for Python (`ruff`, `black`, `mypy`) and Go (`go fmt`, `golangci-lint`, `staticcheck`); confirm review checklist enforces both.
- Test Discipline & Safety Net: Outline failing-first test strategy covering unit, integration, regression, and CLI workflows across languages.
- Consistent User Experience: Describe CLI interactions, flag conventions, help text updates, and accessibility validation.
- Performance & Resource Efficiency: Provide measurement approach ensuring query and ingestion budgets stay within required thresholds.
- Engineering Standards: Note YAML configuration plan (no TOML/JSON) and dependency pinning strategy.

## Project Structure

### Documentation (this feature)

```
specs/[###-feature]/
|-- plan.md              # This file (/speckit.plan command output)
|-- research.md          # Phase 0 output (/speckit.plan command)
|-- data-model.md        # Phase 1 output (/speckit.plan command)
|-- quickstart.md        # Phase 1 output (/speckit.plan command)
|-- contracts/           # Phase 1 output (/speckit.plan command)
`-- tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
|-- models/
|-- services/
|-- cli/
`-- lib/

tests/
|-- contract/
|-- integration/
`-- unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
|-- src/
|   |-- models/
|   |-- services/
|   `-- api/
`-- tests/

frontend/
|-- src/
|   |-- components/
|   |-- pages/
|   `-- services/
`-- tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
`-- [same as backend above]

ios/ or android/
`-- [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
