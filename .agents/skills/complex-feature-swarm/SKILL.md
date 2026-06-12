---
name: complex-feature-swarm
description: Use when OpenCode is planning or implementing a complex feature, phased implementation plan, large refactor, multi-subsystem change, or any request mentioning swarm orchestration, Ruflo, claude-flow, native-agent, build agent, or automatic agent spawning. Coordinates architect, researcher, tester, reviewer, and build roles while keeping one writer.
---

# Complex Feature Swarm

Coordinate complex feature work with a small, phase-gated swarm. Keep the main OpenCode session as coordinator, and keep the build/native-agent as the only role allowed to edit files.

## Complexity Check

Treat a task as complex when any of these are true:

- It touches three or more subsystems, apps, packages, or ownership boundaries.
- It changes schemas, migrations, API contracts, background jobs, auth, ingestion, retrieval, or UI workflow behavior.
- It needs an implementation plan, phased delivery, rollback path, or careful validation.
- The user mentions `swarm`, `orchestration`, `Ruflo`, `claude-flow`, `native-agent`, or `build`.

For small isolated fixes, do not spawn a swarm. Use the normal build flow.

## Operating Rules

- Use one writer. Only the build/native-agent edits files.
- Keep architect, researcher, tester, and reviewer roles read-only unless the user explicitly says otherwise.
- Prefer 4-6 agents. Do not exceed 6 without a clear reason.
- Use hierarchical coordination when Ruflo or another swarm tool is available.
- Work one phase at a time. Do not start the next phase until the current phase passes its gate.
- Keep the plan aligned with the repository's existing architecture and `AGENTS.md` rules.
- Stop and ask when the requested scope implies a broad rewrite, duplicate architecture, or unclear ownership boundary.

## Spawn Workflow

Before implementation, coordinate these roles:

| Role | Mode | Responsibility |
| --- | --- | --- |
| coordinator | read/write plan only | Owns scope, phase gates, and final integration decisions. |
| architect | read-only | Checks boundaries, data flow, contracts, and architecture fit. |
| researcher | read-only | Finds existing patterns, docs, tests, and prior implementations. |
| tester | read-only | Defines regression tests, validation commands, and failure cases. |
| reviewer | read-only | Reviews diffs for bugs, drift, missing tests, and maintainability. |
| build/native-agent | writer | Implements the approved current phase only. |

If Ruflo MCP tools are available, initialize a small hierarchical swarm before planning:

```text
swarm_init topology=hierarchical maxAgents=6 strategy=specialized
agent_spawn coordinator
agent_spawn architect
agent_spawn researcher
agent_spawn tester
agent_spawn reviewer
agent_spawn build-native-agent
```

If Ruflo is not available, invoke the equivalent OpenCode subagents by role. If a role-specific subagent does not exist, run that role as a separate read-only reasoning pass in the main session.

## Planning Output

Produce this plan before editing:

```text
Feature goal:
Non-goals:
Architecture boundary:
Affected modules:
Phase table:
- Phase:
- Intent:
- Likely files:
- Tests:
- Exit gate:
Risks:
Open questions:
```

Ask for approval before implementation when the user has not already approved the plan.

## Phase Execution

For each approved phase:

1. Ask the researcher to refresh relevant local context.
2. Ask the architect to confirm the phase boundary.
3. Tell the build/native-agent to implement only that phase.
4. Run the narrowest meaningful validation command.
5. Ask the tester to compare tests against the phase intent.
6. Ask the reviewer to inspect the diff for drift, bugs, and missing tests.
7. Fix only current-phase findings before moving on.

## Review Gate

A phase is complete only when all of these are true:

- The implementation matches the phase intent and does not include later-phase scope.
- New functions or changed behavior have tests.
- Validation commands pass, or failures are clearly unrelated and reported.
- The reviewer finds no blocking drift, architecture mismatch, or missing regression coverage.
- The coordinator can summarize changed files, tests run, remaining risks, and the next phase.

## Prompt Templates

Use this planning prompt:

```text
Use complex-feature-swarm.

Plan this feature with a small read-only swarm before implementation:
<feature request>

Keep build/native-agent as the only writer. Produce phased work with tests,
exit gates, risks, and open questions.
```

Use this implementation prompt:

```text
Use complex-feature-swarm.

Implement Phase <N> only from the approved plan. Keep later phases out of scope.
Run the phase validation, then request tester and reviewer passes before
continuing.
```
