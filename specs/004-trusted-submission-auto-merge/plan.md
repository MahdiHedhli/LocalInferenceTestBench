# Implementation plan: Trusted submission auto-merge

## Design

1. Extend the trusted benchmark validator with a `--require-benchmark` mode while preserving its
   current general-PR success behavior.
2. Keep `Trusted benchmark boundary` as the required base-controlled job. Materialize only public
   data blobs, run the trusted schema/digest/deterministic builder, then post one fixed review-request
   comment per exact base and head.
3. Add a default-branch `issue_comment` workflow that accepts only a strict Codex clean-review event.
4. Parse the event with standard-library Python, emit only validated numeric/SHA fields, then re-read
   current PR state through GitHub with bounded retries while mergeability is still unknown.
5. Fetch the PR head as Git data only and pipe the validator from the verified base commit with
   `--require-benchmark`, binding the digest-named branch to the one added submission.
6. Reject unresolved threads, changes-requested state, missing app-bound checks or native review
   requirement, conflicts, exhausted mergeability retries, and self-review;
   identity-check the reviewer account; arm squash auto-merge with a fixed digest-derived commit
   message and full-SHA guard; then approve that same full SHA. Recheck that the live default-branch
   tip still equals the authorized base immediately before either mutation. On a partial-run retry,
   reuse only a latest decisive approval for that full SHA and re-arm missing auto-merge after
   complete revalidation.

## Security model

- No workflow executes or imports PR-head code.
- Untrusted comment or diff text is never interpolated into a shell program.
- The reviewer secret is referenced only in the final mutation step after all public-token validation
  steps pass, and its account ID is checked before mutation.
- The per-run proof covers public protected status, app-bound checks, and native review decision.
  Administration-only protection settings are mandatory operator prerequisites, not properties the
  workflow claims to observe.
- Branch protection remains the final merge authority; an accepted `unstable` mergeable state never
  substitutes for a required check, and auto-merge waits for GitHub's decision.
- Any ambiguity, transport failure, missing secret, stale head, or unsupported review shape fails
  closed and leaves the PR open.

## Validation

- Unit fixtures for review-signal parsing, full request chronology, content validation, complete
  review pagination, protection settings, fixed merge metadata, and required-benchmark classification.
- Workflow contract tests for trusted checkout, pinned actions, credential boundaries, SHA guards,
  fixed bot identity, and absence of head checkout/execution.
- Complete unit, deterministic leaderboard, strict privacy/history, Gitleaks, shell, Python, and
  JavaScript checks.
