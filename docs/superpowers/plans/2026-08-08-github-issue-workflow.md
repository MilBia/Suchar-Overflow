# GitHub Issues Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document, in `CLAUDE.md`, how the agent should branch, implement, and open pull requests when work originates from a GitHub issue.

**Architecture:** Single-file documentation change. Extend the existing "Pull requests and git" section of `CLAUDE.md` with a branch-naming rule and a short numbered "Working from a GitHub issue" workflow. No code, no automation, no new files besides the spec/plan already written.

**Tech Stack:** Markdown (`CLAUDE.md`), `gh` CLI (already installed and authenticated per prior verification).

## Global Constraints

- Branch naming for issue-driven work: `<type>/<issue-number>-<slug>` (e.g. `fix/42-vote-count-bug`) — from spec `docs/superpowers/specs/2026-08-08-github-issue-workflow-design.md`.
- Non-issue-driven branches keep the existing plain `<type>/<slug>` convention — unchanged.
- Every issue-linked PR description must include `Closes #<issue-number>` — no "Refs only" mode.
- Agent may propose `gh issue create` for out-of-scope problems found mid-task, but must get explicit user confirmation before running it — never unprompted.
- No `.github/ISSUE_TEMPLATE` / `PULL_REQUEST_TEMPLATE` scaffolding, no CI changes, no auto-assignment — explicitly out of scope per spec.

---

### Task 1: Add GitHub Issues workflow guidance to CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (the "## Pull requests and git" section, currently the file's final section)

**Interfaces:**
- Consumes: nothing (pure documentation, no code interfaces)
- Produces: nothing consumed by other tasks — this is the only task in the plan

- [ ] **Step 1: Read the current section to anchor the edit precisely**

Run: read `CLAUDE.md`, locate the exact current text of the last section:

```markdown
## Pull requests and git

- Branch from `main`; target `main` for PRs.
- Commit messages: imperative mood, explain *why* not *what*.
- Never force-push `main`.
- Run `pre-commit run --all-files` and `just test` before proposing a commit.
```

- [ ] **Step 2: Replace the section with the extended version**

Replace the block found in Step 1 with:

```markdown
## Pull requests and git

- Branch from `main`; target `main` for PRs.
- Commit messages: imperative mood, explain *why* not *what*.
- Never force-push `main`.
- Run `pre-commit run --all-files` and `just test` before proposing a commit.

### Working from a GitHub issue

When a task starts from a GitHub issue (the user gives you an issue number or link):

1. Run `gh issue view <number>` to read the full issue body and comments —
   don't work from the title alone.
2. Branch from `main` using `<type>/<issue-number>-<slug>`, e.g.
   `fix/42-vote-count-bug` or `feat/58-add-dark-mode`. Non-issue-driven work
   keeps using the plain `<type>/<slug>` convention above — nothing changes
   there.
3. Implement and test as usual (see "Workflow — mandatory steps after every
   task").
4. Open the PR with `Closes #<issue-number>` in the description, so the issue
   auto-closes when the PR merges to `main`. Every issue-linked PR closes its
   issue — there is no "reference only" mode.

If you find a problem unrelated to the current issue while working (e.g. an
unrelated bug), you may propose opening a new issue with `gh issue create`,
but always ask for explicit confirmation first — never create an issue
unprompted.
```

- [ ] **Step 3: Verify the edit**

Run: read back `CLAUDE.md` from the `## Pull requests and git` heading to
end-of-file and confirm:
- The four original bullets are unchanged and still present.
- The new `### Working from a GitHub issue` subsection is present with all
  four numbered steps and the closing paragraph about agent-initiated issues.
- No other section of `CLAUDE.md` was altered.

- [ ] **Step 4: Confirm no linting is required**

Run: `git -C /home/barabaszek/Projects/Suchar-Overflow status --short CLAUDE.md`
Expected: shows `CLAUDE.md` as modified. `CLAUDE.md` is plain Markdown, not a
Django template (djlint) or Python file (ruff) — no pre-commit hook targets it,
so no `pre-commit run` is required for this change specifically. (The project's
general "run pre-commit before proposing a commit" rule still applies to the
overall commit if other files are staged alongside it.)

- [ ] **Step 5: Report the diff to the user**

Show the user the diff (`git diff CLAUDE.md`) and do not commit — per this
project's standing rule, only commit when the user explicitly asks.
