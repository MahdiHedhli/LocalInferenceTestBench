# Research: Guided result sharing

## Decision: prompt after persistence, only on an eligible TTY

The report must survive any later descriptor, scanner, authentication, or GitHub failure. Interactive
users receive the option at the moment of highest intent, while scripts retain current behavior.
Enter, EOF, and unsupported input choose private retention.

**Rejected**: Prompt every run. Smoke and invalid results are ineligible and prompting breaks scripts.

## Decision: reuse one minimized contract

Local save and public PR use identical canonical bytes produced by the existing validator. This
avoids a second “shareable” report format and closes the gap between what the user reviewed, what was
scanned, and what is uploaded.

**Rejected**: Upload the aggregate run report. It retains correlation fields intentionally excluded
from the public leaderboard.

## Decision: require explicit public confirmation

The JSON can omit direct identifiers while exact hardware, performance, GitHub account, branch, and
timestamp still link a setup. The CLI therefore prints the complete candidate and named account and
requires literal confirmation. A non-interactive caller must add a second explicit flag.

**Rejected**: Publish automatically at run completion or rely on a generic yes/no prompt.

## Decision: GitHub CLI plus Git-data API

`gh` supplies authenticated GitHub access without putting a token in argv, configuration, or the
repository. The Git-data API creates blobs, one tree, one commit, one ref, and a PR without changing
the user's checkout or depending on a Git credential helper. A contributor fork is verified against
canonical source before use.

**Rejected**: `git add`, commit, and push in the user's checkout; browser tokens; direct `main` push;
or an arbitrary repository argument.

## Decision: validate in an isolated canonical clone

Existing accepted records must be included when rebuilding the leaderboard. A shallow clone of the
fixed upstream supplies that base. Only one candidate and the generated dataset are staged, while a
copied private denylist remains ignored. Unit, deterministic, strict privacy, and redacted secret
checks run before a fork, branch, or PR is created.

**Rejected**: Trust hosted CI as the first scanner. The branch and PR are already public by then.

## Decision: one result per automated PR

Local save may preserve every model from a run, but the public path requires one explicit model when
several exist. This keeps each review and result independently mergeable and prevents unnecessary
cross-linkage. The deterministic branch name makes retry and open-PR detection reliable.

**Rejected**: Multiple PRs created silently or one batch PR that links all models without a separate
choice.

## Decision: enforce the data-only diff in CI

When a submission path changes, the entire PR must be exactly one added digest-named JSON record and
one modified generated leaderboard. Validator, workflow, code, documentation, rename, delete, and
multi-record changes are rejected in that lane.

**Rejected**: Rely only on the PR template or execute a validator that the same benchmark PR may edit.
