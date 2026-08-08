# GitHub Issues workflow — design

Date: 2026-08-08
Status: Approved

## Problem

`CLAUDE.md` documents branch/PR conventions ("Pull requests and git" section) but
says nothing about GitHub Issues. There is no guidance on how the agent should
branch, name branches, or link pull requests when work originates from a GitHub
issue. The repo has no `.github/ISSUE_TEMPLATE` or `PULL_REQUEST_TEMPLATE`, and
no existing issue-linked branches to reverse-engineer a convention from — this
is a forward-looking policy, not a codification of existing practice.

## Decisions

- **Branch naming**: `<type>/<issue-number>-<slug>`, e.g. `fix/42-vote-count-bug`.
  Keeps the existing `feat/`/`fix/`/`release/` prefix convention already used on
  `main` (confirmed via `git log --merges`), just adds the issue number into the
  slug. Non-issue-driven work keeps using plain `<type>/<slug>` as today —
  nothing changes there.
- **Issue context lookup**: before creating the branch, run `gh issue view <number>`
  to pull the full issue body/comments rather than working from a title alone.
- **PR ↔ issue linking**: PR description always includes `Closes #<number>` when
  the branch is tied to an issue, so GitHub auto-closes the issue on merge to
  `main`. No separate "Refs #N, don't close" mode — every issue-linked PR closes
  its issue.
- **Agent-initiated issues**: the agent may propose `gh issue create` when it
  finds an out-of-scope problem while working (e.g. an unrelated bug), but must
  always get explicit user confirmation first. It never runs `gh issue create`
  unprompted.

## Out of scope (YAGNI)

- No `.github/ISSUE_TEMPLATE` / `PULL_REQUEST_TEMPLATE` scaffolding — not
  requested, and current PRs work fine without them.
- No auto-assignment of issues to the agent/user.
- No CI changes.

## Implementation

Single documentation change: extend the "Pull requests and git" section of
`CLAUDE.md` with the branch-naming rule and a short "Working from a GitHub
issue" numbered workflow (view issue → branch → implement + test → PR with
`Closes #N`), plus the confirm-before-creating rule for agent-initiated issues.
No code or automation changes.
