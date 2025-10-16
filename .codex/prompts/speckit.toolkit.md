---
description: Check the implementation plan for tools and development dependencies by processing and executing all tasks defined in tasks.md
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Goal

Identify the tools and development dependencies across the three core artifacts (`spec.md`, `plan.md`, `tasks.md`) and other relevant project files like `Makefile`, `Dockerfile`, `packages.json` before implementation. This command MUST run only after `/tasks` has successfully produced a complete `tasks.md`.

## Operating Constraints

**STRICTLY READ-ONLY**: Do **not** modify any files except if the user instructs you in step 6. Output a structured analysis report.

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` once from repo root and parse JSON for FEATURE_DIR and AVAILABLE_DOCS. Derive absolute paths:

- SPEC = FEATURE_DIR/spec.md
- PLAN = FEATURE_DIR/plan.md
- TASKS = FEATURE_DIR/tasks.md

Abort with an error message if any required file is missing (instruct the user to run missing prerequisite command).
For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. Load and analyze the implementation context
   - **REQUIRED**: Read tasks.md for the complete task list and execution plan
   - **REQUIRED**: Read plan.md for tech stack, architecture, and file structure
   - **IF EXISTS**: Read data-model.md for entities and relationships
   - **IF EXISTS**: Read contracts/ for API specifications and test requirements
   - **IF EXISTS**: Read research.md for technical decisions and constraints
   - **IF EXISTS**: Read quickstart.md for integration scenarios

3. Parse tasks.md structure and extract:
   - **Task phases**: Setup, Tests, Core, Integration, Polish
   - **Task dependencies**: Sequential vs parallel execution rules
   - **Task details**: ID, description, file paths, parallel markers [P]
   - **Execution flow**: Order and dependency requirements

4. Generate an invisible implementation plan and extract tools and development dependencies:
   - For each incomplete tasks note what tools will be used, for example `protoc` for go gRPC bindings, `terraform` for managing `infrastructure`, `gcc` to compile C source code, and so on.
   - **Do not** implement any tasks, but note the tools

5. Produce a tool and development dependency report

You should list what tools or development dependencies to be used for a given task (if there are multiple tools or development dependencies for the task, list each of them as a new line item). You should also check if the tool or development dependency is installed in the execution envronment and report the result as follows:
   - <span style="color: red;">missing</span> if the tool or dependency can't be found
   - <span style="color: green;">present</span> if the tool or dependency can be found

If the tool or dependency can't be found, list the simplest possible command for installing said dependency.

Output a Markdown report (no file writes) based on the above information with the following structure:

## Tooling requirement report

| Required tool/dependency | Task ID(s) | Status | Installation command |
|--------------------------|------------|--------|----------------------|

Every tool should be listed only once, but if they are used for multiple tasks list all the tasks. The installation commands should be surrounded with backticks and should be as specific as possible. Build dependencies should not be added as runtime dependecies.

6. `dependecies.md` file generation
    - **STOP** and ask: "Do you want me to generate the `dependencies.md` file? (yes/no)"
    - Wait for user response before continuing
    - If user says "no" or "wait" or "stop", halt execution
    - If user says "yes" or "proceed" or "continue", generate the `dependencies.md` file under `specs/FEATURE_DIR/` folder.

Note: This command assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, suggest running `/tasks` first to regenerate the task list.
