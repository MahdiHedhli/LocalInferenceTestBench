# Implementation plan: Trusted submission auto-merge

## Design

1. Extend the trusted benchmark validator with a `--require-benchmark` mode while preserving its
   current general-PR success behavior.
2. Keep the classifier base-controlled. Materialize only public data blobs, run the trusted
   schema/digest/deterministic builder, then post one fixed review-request and audit comment per exact
   base and head with job-scoped pull-request comment permission.
3. After that marker job succeeds, call a local reusable workflow from the same trusted caller
   commit. Pass only the exact pull request number, full base SHA, full head SHA, and marker comment
   ID, and map repository secret `ERNEST_REVIEW_TOKEN` explicitly to `reviewer_token` rather than
   inheriting secrets.
4. Fetch the marker by ID with standard-library Python and require its exact canonical body, full
   SHA binding, unedited timestamps, GitHub Actions user ID `41898282`, and GitHub App ID `15368`.
   Treat the marker as audit evidence, not authorization on its own, then re-read current PR state
   through GitHub with bounded retries while mergeability is still unknown.
5. Fetch the PR head as Git data only and pipe the validator from the verified base commit with
   `--require-benchmark`, binding the digest-named branch to the one added submission.
6. Reject unresolved threads, changes-requested state, missing app-bound checks or native review
   requirement, conflicts, exhausted mergeability retries, and self-review;
   identity-check the reviewer account; arm squash auto-merge with a fixed digest-derived commit
   message and full-SHA guard; then approve that same full SHA. Recheck that the live default-branch
   tip still equals the authorized base immediately before either mutation. On a partial-run retry,
   reuse only a latest decisive approval for that full SHA and re-arm missing auto-merge after
   complete revalidation.
7. Keep Codex and CodeRabbit requests advisory and non-blocking. Do not use an `issue_comment` clean
   signal as a gate; repository-`GITHUB_TOKEN` comments do not start downstream workflow runs.
8. Produce the branch-protection context `Trusted benchmark boundary` only from a final aggregator
   that waits for the reusable workflow to complete. An armed-but-failed downstream run therefore
   cannot merge after some other approval, and retries retain a pending native requirement.

## Security model

- No workflow executes or imports PR-head code.
- Untrusted comment or diff text is never interpolated into a shell program.
- The local reusable workflow is resolved from the same trusted caller commit, not from the pull
  request head. Its scalar inputs and the live marker are independently verified.
- The reviewer secret is passed by an explicit single-secret mapping, never `secrets: inherit`, and
  is bound only to the final mutation step after all public-token validation steps pass. Its account
  ID is checked before mutation.
- The per-run proof covers public protected status, app-bound checks, and native review decision.
  Administration-only protection settings are mandatory operator prerequisites, not properties the
  workflow claims to observe.
- Branch protection remains the final merge authority; an accepted `unstable` mergeable state never
  substitutes for a required check, and auto-merge waits for GitHub's decision.
- Any ambiguity, transport failure, missing secret, stale head, or unsupported review shape fails
  closed and leaves the PR open.

## Validation

- Unit fixtures for marker parsing and identity, exact workflow-call inputs, content validation,
  complete review pagination, protection settings, fixed merge metadata, and required-benchmark
  classification.
- Workflow contract tests for trusted checkout, pinned actions, credential boundaries, SHA guards,
  local reusable-workflow provenance, explicit secret mapping, fixed Actions/App identity, and
  absence of head checkout/execution.
- Complete unit, deterministic leaderboard, strict privacy/history, Gitleaks, shell, Python, and
  JavaScript checks.
