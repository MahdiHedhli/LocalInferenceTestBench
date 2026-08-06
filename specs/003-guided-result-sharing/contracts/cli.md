# CLI contract: Post-run sharing

## Arguments on `litb run`

| Argument | Values/default | Contract |
|----------|----------------|----------|
| `--submission` | `ask` | `ask`, `none`, `save`, or `pr` |
| `--hardware` | `.local/hardware.json` | Existing closed, ignored, owner-only descriptor |
| `--measurement-evidence` | `.local/measurement-evidence.json` | Existing exact-bound sidecar for interactive/two-step use, or atomic owner-only output from the sampler integration |
| `--measurement-sampler` | unset | Explicit trusted POSIX executable for synchronous, exact-bound pre/post categorical sampling; required for non-interactive run-and-save/PR |
| `--submission-model` | unset | Optional single source report model ID |
| `--submission-dir` | `.local/leaderboard-submissions` | Ignored owner-only candidate directory |
| `--confirm-public` | false | Required with non-interactive `pr` |

## Arguments on `litb publish-submission`

| Argument | Values/default | Contract |
|----------|----------------|----------|
| `--candidate` | required path | Existing canonical, digest-named, owner-only regular minimized JSON; Git-ignored when inside a worktree |
| `--confirm-public` | false | Required for non-interactive publication; never bypasses literal interactive `PUBLISH` |

This command reruns candidate validation and the same disclosure, privacy, isolated-build, and
reviewed-PR flow as post-run publication. It never invokes inference. Cancellation causes no mutating
GitHub action.

## Eligibility

`save` and `pr` accept only an overall `valid` report from the complete `standard` profile. `ask`
offers choices only when both stdin and stdout are interactive and the same eligibility holds.
Non-interactive `run --submission save|pr` additionally requires `--measurement-sampler`; an
already-produced static sidecar is consumed by the separate `prepare-submission` command.

The sampler argument is one POSIX executable path of at most 16 MiB, never shell syntax. Windows
fails this option closed and retains the two-step exact-bound sidecar path. The CLI creates a UUIDv4/UTC run
identity before endpoint access, invokes the executable for `pre` and, only after a successful pre
sample and successfully returned complete run, once for `post`, and sends
strict JSON containing only schema version, source run ID, phase, and ordered public model IDs. Each
response must echo those fields and contain only a closed categorical sample. The adapter has a
30-second timeout and a 256 KiB in-flight stdout cap; stderr is discarded and credential environment
keys are absent. Its approved file identity is rechecked at launch, only a private non-writable
snapshot of approved bytes executes, and a dedicated standard-library supervisor owns its isolated
process tree. The supervisor observes leader exit without reaping, signals the group before the
reap, never signals the numeric PGID afterward, and on Linux requires child-subreaper setup and
bounded adopted-descendant reaping. Older supported macOS Python uses a `kqueue` observer when
`waitid` is unavailable.
The sampler must stay synchronous and must not daemonize, change session/process group, or
deliberately escape. The snapshot directory must be owner-only and its backing filesystem writable
and executable; an owner-controlled non-repository `TMPDIR` can replace a `noexec` default. A runner exception produces no post sample or export. Any
sampler failure blocks export after preserving a completed private report.

## Exit status

- `0`: run and requested action succeeded, user retained private, or existing public result found.
- `1`: runner/transport failure or invalid benchmark.
- `2`: configuration, descriptor, eligibility, or candidate-save failure.
- `3`: optional publication dependency, confirmation, local publication gate, GitHub, or PR failure
  after the candidate was safely saved or loaded.

Errors are categorical and never include subprocess stderr or private input values.
