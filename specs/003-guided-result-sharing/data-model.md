# Data model: Guided result sharing

## Post-run action

- `ask`: prompt only for a valid standard result on an interactive input and output terminal.
- `none`: retain the private report only.
- `save`: prepare and idempotently save selected minimized candidates.
- `pr`: save, review, confirm, validate, and propose one candidate publicly.

For `save` and `pr`, schema `1.1` preparation consumes three local inputs: the already-persisted Run
Record, the public hardware/runtime descriptor, and an ignored owner-only categorical measurement
sidecar. The run must have fully valid execution status. The sidecar independently supplies clean,
nonquiescent, or degraded-midrun measurement conditions; no action infers clean from the run state.

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
| `leaderboard_bytes` | Deterministic builder | Canonical monolith while bounded, otherwise the compact deterministic shard index for all accepted upstream entries plus candidate |

If the reviewed local descriptor includes `runtime_configuration`, its closed values are preserved
in both byte payloads. Older candidates without that optional object remain valid; no defaults are
inferred during preparation or publication.

The local measurement sidecar is not part of either byte payload. It has a closed `1.0` sidecar
contract with a top-level `source_run_id` exactly matching the source Run Record's `run_id`, 1–1000
unique source-report model IDs, categorical pre/post threshold outcomes and category lists, and
optional 3–5-run determinism aggregates. It cannot contain raw values, additional timestamps, paths,
process names, inventory, or free text. It must be regular, ignored, owner-only, and non-symlinked.
Missing, stale-run, oversized, or mismatched evidence prevents a candidate from being created. The
run binding stays local and is absent from both the saved candidate and network payload.

## Local sampler exchange

For POSIX single-command run-and-export, the CLI preallocates the same UUIDv4/UTC identity later retained
by the Run Record. It invokes one explicitly selected adapter for `pre`, runs the complete selected
model set, then invokes it for `post` only when `pre` and the complete benchmark return successfully.
A runner exception produces no post sample and no export. Each request contains exactly `schema_version`,
`source_run_id`, `phase`, and the ordered `model_ids`. Each response echoes those four fields and adds
exactly one `sample` with `outcome` and canonically ordered `categories`.

The two samples describe the envelope around the complete run and are repeated into one evidence row
per report model. Public validity and `hard_threshold_crossed` are deterministic derivations from
those categories, not additional measurements. No missing sample is defaulted. The validated
sidecar is atomically retained at the ignored owner-only evidence path and the same in-memory object
enters candidate preparation, eliminating a file-reload race.

The exchange has no raw values, free text, process names, paths, inventory, or extra timestamps. The
adapter is capped at 16 MiB and only a private non-writable snapshot of approved bytes executes.
A dedicated standard-library supervisor observes leader exit without reaping, signals the snapshot's
process group before the reap, and never signals that numeric PGID afterward. Linux child-subreaper
setup and bounded adopted-descendant reaping are mandatory; macOS uses `kqueue` when `waitid` is
unavailable and retains kill-before-reap ordering. The trusted adapter must
remain synchronous and must not daemonize, change its session/process group, or deliberately escape.
The snapshot directory must be owner-only and its backing filesystem writable and executable;
`TMPDIR` may select an owner-controlled non-repository location. Windows uses the two-step exact-bound sidecar path. The process boundary is
constrained by the CLI contract.

New candidate bytes use public schema `1.1`. The source report's UTC creation time is reduced to
`YYYY-MM`; exact event time remains private. Accepted repository schema `1.0` files stay unchanged,
but a newly proposed or previously saved `1.0` candidate is not publishable through this lane and
must be regenerated.

The only allowed tree entries are:

- `site/data/submissions/<submission_id>.json` as a new regular file;
- `site/data/leaderboard.json` as generated replacement data.

## Publication result

- `opened`: new feature branch and pull request.
- `existing_pull_request`: deterministic branch already has an open PR.
- `already_published`: exact candidate already exists on canonical `main`.

An existing deterministic branch without a PR may be resumed only when its base parent, commit tree,
two-file change, and payload bytes exactly match the freshly prepared result. Retry may then create
only the missing pull request. Any mismatch is a collision and is never overwritten.
