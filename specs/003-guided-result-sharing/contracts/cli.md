# CLI contract: Post-run sharing

## Arguments on `litb run`

| Argument | Values/default | Contract |
|----------|----------------|----------|
| `--submission` | `ask` | `ask`, `none`, `save`, or `pr` |
| `--hardware` | `.local/hardware.json` | Existing closed, ignored, owner-only descriptor |
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

## Exit status

- `0`: run and requested action succeeded, user retained private, or existing public result found.
- `1`: runner/transport failure or invalid benchmark.
- `2`: configuration, descriptor, eligibility, or candidate-save failure.
- `3`: optional publication dependency, confirmation, local publication gate, GitHub, or PR failure
  after the candidate was safely saved or loaded.

Errors are categorical and never include subprocess stderr or private input values.
