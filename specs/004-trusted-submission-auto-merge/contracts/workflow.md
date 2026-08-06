# Workflow contract

## Trusted boundary

- Trigger: `pull_request_target` on opened, synchronize, reopened, and ready-for-review.
- Checkout: exact base SHA, pinned checkout action, no persisted credential.
- Head handling: fetch `pull/<number>/head` as Git data and compare `FETCH_HEAD` to event head SHA.
- Classification: execute validator bytes and schema/builder code from `BASE_SHA`; materialize only
  head data blobs; create an audit marker only after exact shape, schema, digest, duplicate, and
  deterministic byte validation. The `litb/submission-<digest>` namespace is reserved: a general or
  otherwise non-submission diff under that head ref fails instead of being reclassified.
- Review-request token scope: the request job explicitly requests only repository-content read and
  pull-request write permissions. Trusted code uses the write scope only for the fixed PR comment,
  invokes no review or merge endpoint, and has no repository-content write permission.
- Marker: fetchable by its returned comment ID; exact canonical body with full base and head SHAs;
  unedited; actor `github-actions[bot]` user ID `41898282`; GitHub Actions App ID `15368`. The marker
  is audit evidence, not authorization by itself.
- Handoff: only after the marker job succeeds, invoke a local reusable workflow from the same trusted
  caller commit with the exact PR number, full base SHA, full head SHA, and marker comment ID. Map
  repository secret `ERNEST_REVIEW_TOKEN` explicitly to `reviewer_token`; `secrets: inherit` is
  forbidden.
- Required context: emit `Trusted benchmark boundary` only from a final `always()` aggregator that
  requires the classifier, marker, and called automation jobs to have their exact success/skipped
  states. The protected context therefore remains pending throughout any exact-head mutation.

## Auto-merge authorization

- Trigger: direct local reusable-workflow call from the successful trusted marker job. A repository
  `GITHUB_TOKEN` comment does not trigger a downstream `issue_comment` workflow, and no Codex clean
  comment is an authorization signal.
- Checkout: exact trusted base SHA through the local workflow resolved from the caller commit; never
  PR head.
- Inputs: exact pull request number, full base SHA, full head SHA, and marker comment ID. Each value
  is independently matched to live repository state; inputs and marker together remain insufficient
  without the full revalidation.
- Revalidation: current live metadata after bounded unknown-mergeability retries, deterministic
  `litb/submission-<digest>` head ref, public app-bound protection summary, native review decision,
  exact live/unedited Actions/App marker, exact data-only fetch, trusted base validator in
  `--require-benchmark --check-content` mode, complete review pagination, no active changes request,
  and zero unresolved review threads.
- Mergeable state: established `blocked`, `clean`, or `unstable` may continue. `unstable` is only an
  API state; it neither passes nor waives a required check. Conflict, stale-base, and exhausted
  unknown states fail closed.
- Mutation: arm native squash auto-merge with `expectedHeadOid` and fixed metadata, then submit the
  reviewer account's `commitOID`-bound approval. On a fully revalidated partial-run retry, a latest
  decisive exact-head reviewer approval may be reused and a missing native auto-merge request may be
  re-armed while the final required boundary remains pending. That pending context prevents GitHub
  from treating the retry as an already-clean approved pull request. Immediately before either
  possible mutation, the live default-branch tip must still equal the authorized base SHA. A stale,
  dismissed, changes-requested, or other-commit approval is never reusable. No direct merge
  operation is permitted.
- Reviewer-token boundary: repository secret `ERNEST_REVIEW_TOKEN`, explicitly mapped as
  `reviewer_token`, is bound only in the final mutation step and its reviewer account is
  identity-checked before any write. Boundary, marker, and earlier revalidation steps neither bind
  nor reference it.
- Failure: leave the PR open and emit only a categorical workflow failure.

## Advisory reviewers

Codex and CodeRabbit are best-effort and non-blocking. Clean, missing, failed, skipped, or rate-limited
responses do not alter authorization. A thread or changes request visible by the final live
revalidation fails closed regardless of which reviewer created it.

## Preserved publication controls

The lane does not change the exact two-file append-only/mode/blob rule, canonical digest/filename and
duplicate checks, byte-exact deterministic rebuild in CI and Pages, hardened `pull_request_target`
checkout/data-fetch rules, `textContent`-only rendering, or the closed-schema and hostile-Unicode/
JSON/size checks shared by Python and JavaScript. These controls prove integrity and schema
conformance, not provenance that a self-reported run occurred.

## Operator prerequisites

The workflow can prove only the public protected-branch summary, GitHub-Actions-bound required
checks, enforcement level, and native review decision on each run. The operator MUST keep and verify
the administration-only controls listed in `quickstart.md`; their absence is not made safe by being
invisible to the workflow.
