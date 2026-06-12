---
name: commit-every-change
description: Use when the user asks to commit a dirty worktree, pile of edits, mixed completed work, uncommitted changes, or separate feat/fix/refactor changes.
argument-hint: ["[optional focus, exclude pattern, or verification command]"]
---

# /commit-every-change

Split the current working tree into clean, logical commits and create the commits directly. Optimize for reviewable history, not for minimizing commit count.

## Commit Standard

- One commit per logical change. Do not lump unrelated changes together just because they share a type.
- Autonomous default: decide the grouping and make the commits. Ask only when a stop condition applies.
- Use Conventional Commits: `type(scope): imperative subject`.
- Use a short body for non-trivial commits explaining why the change exists and what boundary it preserves.
- Never add `Co-Authored-By`, generator, assistant, or provenance trailers.
- Do not push, branch, rebase, reset the worktree, or rewrite existing history unless the user explicitly asks.

## Types

Use the most specific type:

| Type | Use for |
| --- | --- |
| `feat` | New user-visible capability or supported behavior |
| `fix` | Bug fix or regression fix |
| `refactor` | Behavior-preserving internal restructure |
| `perf` | Performance or memory improvement |
| `test` | Test-only changes |
| `docs` | Documentation-only changes |
| `build` | Dependencies, packaging, generated lockfiles, build config |
| `ci` | CI workflow changes |
| `chore` | Maintenance that changes no product behavior |
| `style` | Formatting-only changes when the project uses this type |

## Workflow

1. Inspect the full state: `git status --short`, staged diff, unstaged diff, and untracked files.
2. Identify logical changes by intent, dependency, and files that must ship together.
3. Order commits so earlier commits stand alone: prep refactors, then fixes/features, then docs or chores when independent.
4. Stage exactly one logical change with pathspecs or interactive staging.
5. Check the staged unit before committing:
   - `git diff --cached --name-status`
   - `git diff --cached --stat`
   - `git diff --cached --check`
   - the narrowest meaningful verification command when available
6. Commit with explicit messages only:
   - `git commit -m "type(scope): subject"`
   - `git commit -m "type(scope): subject" -m "Short body explaining why."`
7. Verify the created commit:
   - `git log -1 --format=%B`
   - `git show --stat --name-status --oneline --no-renames HEAD`
8. Continue until every safe, intended change is committed.

## Atomic Grouping Rules

- Keep implementation, tests, migrations, fixtures, and docs together only when they describe the same logical change.
- Split two features into two commits even if they touch the same subsystem.
- Split a bug fix from opportunistic cleanup unless the cleanup is required to make the fix safe.
- Split broad formatting from behavior changes.
- Keep dependency or lockfile changes with the code that requires them; otherwise use `build`.
- Keep generated files only when the repo normally commits them and they match the staged source change.
- For mixed hunks in one file, use interactive staging. For untracked files that need partial staging, use intent-to-add first.

## Stop Conditions

Stop and report the exact blocker instead of guessing when:

- A staged commit would include secrets, credentials, local databases, virtualenvs, logs, caches, personal exports, or unrelated runtime artifacts.
- A logical change cannot be separated without editing code or risking corruption.
- Verification fails for the staged unit and the failure is not clearly unrelated.
- A hook or commit template injects forbidden trailers and a message-only amend cannot remove them.
- Git refuses to commit because of permissions, dubious ownership, missing identity, or repository state.

## Message Rules

- Subject: 72 characters or less when practical, no trailing period.
- Scope: concise subsystem name from the touched paths or domain language.
- Body: one to three sentences for behavior changes, cross-module refactors, migrations, dependency changes, or risk-bearing fixes.
- Body should explain intent and review boundary, not restate the diff.
- Bare message means no trailers of any kind.

Good:

```text
fix(import): reject malformed snapshot rows

The importer now fails before persistence when a row lacks the required
symbol and timestamp fields. This keeps partial snapshots out of storage.
```

Good:

```text
refactor(quant4): isolate factor registry parsing
```

Bad:

```text
feat: update files
```

Any message with `Co-Authored-By`, generated-by, or assistant provenance trailers is bad.

## Final Report

Report the commits in order with hash, subject, and verification result. Also list any files intentionally left uncommitted and why.
