# Data model: Trusted submission auto-merge

## Trusted workflow call

- `repository`: fixed `MahdiHedhli/LocalInferenceTestBench`
- `pull_request_number`: positive integer passed by the base-controlled caller
- `request_base_sha`: trusted full 40-character lowercase hexadecimal base SHA
- `request_head_sha`: trusted full 40-character lowercase hexadecimal head SHA
- `marker_comment_id`: positive integer returned by the successful marker job
- `caller`: local reusable workflow resolved from the same trusted caller commit
- `reviewer_secret`: repository secret `ERNEST_REVIEW_TOKEN`, explicitly mapped to reusable-workflow
  secret `reviewer_token`; inherited secrets are forbidden

## Audit marker

- `comment_id`: equal to `marker_comment_id` and fetched live from the canonical repository
- `author`: fixed `github-actions[bot]`, user ID `41898282`, type `Bot`
- `author_app`: fixed `github-actions`, App ID `15368`
- `body`: exact canonical text containing `request_base_sha` and `request_head_sha`; no contributor
  content
- `created_at`: equal to `updated_at`; edited comments are ineligible

The marker records trusted-boundary completion but grants no authorization by itself.

## Merge authorization

- `base_ref`: fixed `main`
- `base_sha`: full hexadecimal Git commit ID returned by GitHub
- `head_sha`: full hexadecimal Git commit ID, equal across the workflow-call input, trusted marker,
  live PR, fetched ref, approval, and auto-merge request
- `head_ref`: `litb/submission-` plus the 64-character submission digest
- `submission_id`: the same digest in `head_ref`, the one added filename, and canonical submission
  content
- `author`: live GitHub login, unequal to the Ernest reviewer login
- `mergeable`: established `true` after a bounded retry when GitHub initially reports unknown
- `mergeable_state`: `blocked`, `clean`, or `unstable`; `unstable` records GitHub state and grants no
  required-check waiver
- `change_class`: `benchmark-only`
- `reserved_head_ref`: a `litb/submission-<digest>` branch is valid only for `benchmark-only`; a
  general or non-submission transition fails the boundary
- `required_boundary`: final aggregate context, pending until the marker and called automation jobs
  reach their exact expected states
- `unresolved_threads`: zero
- `active_changes_requested_reviews`: zero
- `reviewer_approval`: absent for a fresh authorization, or the reviewer's latest decisive state is
  `APPROVED` for the exact current head during an idempotent retry
- `auto_merge`: `SQUASH`, digest-derived headline, body explicitly saying self-reported/unverified,
  enabled by reviewer ID `275105272`

No workflow-call, marker, advisory-review, or authorization record is persisted in the public
dataset.

## Repository prerequisites

Per-run public evidence contains protected status, required check contexts with GitHub Actions App
IDs, their enforcement level, and the native review decision. Administration-only settings are not
part of that observable record. Operators must separately retain and verify stale-review dismissal,
last-push approval, conversation resolution, linear history, admin enforcement, and force-push and
deletion prohibitions.
