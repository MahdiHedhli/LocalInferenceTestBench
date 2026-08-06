# Workflow contract

## Trusted boundary

- Trigger: `pull_request_target` on opened, synchronize, reopened, and ready-for-review.
- Checkout: exact base SHA, pinned checkout action, no persisted credential.
- Head handling: fetch `pull/<number>/head` as Git data and compare `FETCH_HEAD` to event head SHA.
- Classification: execute validator bytes and schema/builder code from `BASE_SHA`; materialize only
  head data blobs; tag reviewers only after exact shape, schema, digest, duplicate, and deterministic
  byte validation.

## Auto-merge authorization

- Trigger: newly created issue comment from the exact Codex connector bot.
- Checkout: trusted default branch only; never PR head.
- Signal: immutable Codex user/App IDs, unedited strict clean-review parser, exact current-head prefix,
  and a preceding trusted full-base/full-head request marker.
- Revalidation: current live metadata after bounded unknown-mergeability retries, deterministic
  `litb/submission-<digest>` head ref, public app-bound protection summary, native review decision,
  exact data-only fetch, trusted base validator in
  `--require-benchmark --check-content` mode, complete review pagination, no active changes request,
  and zero unresolved review threads.
- Mergeable state: established `blocked`, `clean`, or `unstable` may continue. `unstable` is only an
  API state; it neither passes nor waives a required check. Conflict, stale-base, and exhausted
  unknown states fail closed.
- Mutation: arm native squash auto-merge with `expectedHeadOid` and fixed metadata, then submit the
  reviewer account's `commitOID`-bound approval. On a fully revalidated partial-run retry, a latest
  decisive exact-head reviewer approval may be reused and a missing native auto-merge request may be
  re-armed. Immediately before either possible mutation, the live default-branch tip must still
  equal the authorized base SHA. A stale, dismissed, changes-requested, or other-commit approval is
  never reusable. No direct merge operation is permitted.
- Failure: leave the PR open and emit only a categorical workflow failure.

## Operator prerequisites

The workflow can prove only the public protected-branch summary, GitHub-Actions-bound required
checks, enforcement level, and native review decision on each run. The operator MUST keep and verify
the administration-only controls listed in `quickstart.md`; their absence is not made safe by being
invisible to the workflow.
