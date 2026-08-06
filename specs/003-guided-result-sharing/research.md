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

## Stage 3 decision: require measurement evidence as a separate local input

**Decision**: Public schema `1.1` preparation reads a closed categorical sidecar from an ignored,
owner-only path. Execution validity continues to describe endpoint, identity, request, and scoring
integrity; the sidecar separately describes coarse pre/post measurement conditions. Missing evidence
fails closed. The sidecar binds to exactly one Run Record through a required `source_run_id` exact-
matched to `report.run_id`, and its unique model evidence list is capped at 1–1000 entries. The
binding is validation-only and is stripped from public output.

**Rationale**: Treating `report.validity == valid` as proof of host quiescence would invent evidence
the baseline runner did not collect. Keeping the sampler or adapter output separate also prevents
raw host instrumentation from expanding the retained run record or public candidate.

**Rejected**: Map execution-valid to clean; accept a CLI validity assertion; reuse unbound or stale-
run evidence; accept an unbounded model list; collect general machine inventory in the core runner;
publish the run binding; or publish raw pressure, thermal, load, swap, memory, or process values.

## Post-review decision: integrate an exact-bound synchronous sampler

**Decision**: Make non-interactive POSIX run-and-export use an explicitly selected local adapter. Allocate
the ordinary run identity first, send it with the phase and ordered public model IDs to a synchronous
`pre` invocation, run the benchmark with that identity, then perform the matching `post` invocation
when `pre` succeeded.
Require closed categorical responses to echo every binding field. Build and atomically retain the
ordinary sidecar only from those two measured samples, and reuse that in-memory object for export.
Cap the source at 16 MiB, execute a private non-writable snapshot of approved bytes, and keep Windows
on the two-step exact-bound sidecar flow until equivalent process-tree containment exists.

**Rationale**: A random run ID created only after inference cannot appear in a pre-existing sidecar,
so the former documented one-command flow required an external rewrite race. Merely replacing the ID
afterward would make stale measurements look bound. Supplying the ID to the collector before both
samples makes the flow usable without treating binding as provenance or inventing host conditions.

**Rejected**: Rewrite an arbitrary sidecar after the run; choose the report ID from a fully formed
pre-existing sidecar; accept a free-form validity flag; invoke shell fragments; inherit credential
variables; capture unbounded output; or let sampler failure prevent retention of an otherwise
completed private benchmark report.

## Stage 3 decision: regenerate new candidates without rewriting legacy evidence

**Decision**: Newly prepared candidates use public schema `1.1`. Accepted schema `1.0` repository
files retain their exact bytes and digests; a saved or open `1.0` candidate must be regenerated before
new publication.

**Rationale**: Rehashing historical files would destroy their content identities, while accepting
new `1.0` files would let callers invisibly omit validity and recency. Explicit legacy projection
preserves both facts.

**Rejected**: Rewrite accepted source submissions, synthesize legacy measurement fields, or keep
accepting new schema `1.0` proposals indefinitely.
