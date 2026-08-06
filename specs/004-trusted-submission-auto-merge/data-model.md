# Data model: Trusted submission auto-merge

## Review signal

- `repository`: fixed `MahdiHedhli/LocalInferenceTestBench`
- `pull_request_number`: positive integer from the trusted event document
- `reviewer`: fixed `chatgpt-codex-connector[bot]`, user ID `199175422`
- `reviewer_app`: fixed `chatgpt-codex-connector`, App ID `1144995`
- `reviewed_commit_prefix`: exactly ten lowercase hexadecimal characters
- `request_base_sha`: trusted full base SHA
- `request_head_sha`: trusted full head SHA
- `disposition`: clean only; findings and unknown forms are ineligible

## Merge authorization

- `base_ref`: fixed `main`
- `base_sha`: full hexadecimal Git commit ID returned by GitHub
- `head_sha`: full hexadecimal Git commit ID, equal across the trusted request marker, live PR,
  fetched ref, approval, and auto-merge request; the Codex event carries only its ten-character prefix
- `head_ref`: `litb/submission-` plus the 64-character submission digest
- `submission_id`: the same digest in `head_ref`, the one added filename, and canonical submission
  content
- `author`: live GitHub login, unequal to the reviewer bot login
- `mergeable`: established `true` after a bounded retry when GitHub initially reports unknown
- `mergeable_state`: `blocked`, `clean`, or `unstable`; `unstable` records GitHub state and grants no
  required-check waiver
- `change_class`: `benchmark-only`
- `unresolved_threads`: zero
- `active_changes_requested_reviews`: zero
- `reviewer_approval`: absent for a fresh authorization, or the reviewer's latest decisive state is
  `APPROVED` for the exact current head during an idempotent retry
- `auto_merge`: `SQUASH`, digest-derived headline, body explicitly saying self-reported/unverified,
  enabled by reviewer ID `275105272`

No review-signal or authorization record is persisted in the public dataset.

## Repository prerequisites

Per-run public evidence contains protected status, required check contexts with GitHub Actions App
IDs, their enforcement level, and the native review decision. Administration-only settings are not
part of that observable record. Operators must separately retain and verify stale-review dismissal,
last-push approval, conversation resolution, linear history, admin enforcement, and force-push and
deletion prohibitions.
