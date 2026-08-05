# Data model: Guided result sharing

## Post-run action

- `ask`: prompt only for a valid standard result on an interactive input and output terminal.
- `none`: retain the private report only.
- `save`: prepare and idempotently save selected minimized candidates.
- `pr`: save, review, confirm, validate, and propose one candidate publicly.

Transitions are one-way for a command invocation:

`report persisted` → `private` | `candidate saved` → `publication confirmed` → `PR result`

No publication failure rolls back or deletes the private report or saved candidate.

A later `publish-submission` invocation may start from `candidate saved`. The loader accepts only the
exact canonical bytes in a digest-named, owner-only regular file that is Git-ignored when inside a
worktree, then rejoins the same disclosure and confirmation transition without invoking the
benchmark runner. A candidate securely saved outside a worktree remains reusable.

## Publication identity

| Field | Meaning | Public use |
|-------|---------|------------|
| `login` | Authenticated `github.com` account | Disclosure, fork owner, PR head |
| `upstream_owner` | Fixed canonical repository owner | Routing only |
| `repository_name` | Fixed canonical repository name | Routing only |
| `base_branch` | Fixed canonical `main` branch | Exact base and PR target; default-branch drift fails closed |
| `can_push_upstream` | Whether a feature ref may live upstream | Select upstream branch or fork |

No token or credential value is represented.

## Prepared public change

| Field | Source | Constraint |
|-------|--------|------------|
| `base_sha` | Clean canonical clone | Must still equal upstream before mutation |
| `base_tree` | Same commit | Base for one atomic tree |
| `submission_bytes` | Canonical renderer | Closed, validated, digest-named |
| `leaderboard_bytes` | Deterministic builder | Includes all accepted upstream entries plus candidate |

If the reviewed local descriptor includes `runtime_configuration`, its closed values are preserved
in both byte payloads. Older candidates without that optional object remain valid; no defaults are
inferred during preparation or publication.

The only allowed tree entries are:

- `site/data/submissions/<submission_id>.json` as a new regular file;
- `site/data/leaderboard.json` as generated replacement data.

## Publication result

- `opened`: new feature branch and pull request.
- `existing_pull_request`: deterministic branch already has an open PR.
- `already_published`: exact candidate already exists on canonical `main`.

An existing deterministic branch without a PR is a collision and is never overwritten.
