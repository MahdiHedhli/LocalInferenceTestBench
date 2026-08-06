# Feature specification: Trusted submission auto-merge

**Feature Branch**: `feat/trusted-submission-auto-merge`

**Created**: 2026-08-06

**Status**: In progress

**Input**: Let identifier-minimized benchmark submissions reach the public leaderboard promptly
without a maintainer manually reviewing and merging every generated two-file pull request.

## User scenarios and testing

### User story 1: Record the trusted boundary decision (Priority: P1)

After trusted base code proves that a pull request is an exact append-only benchmark submission and
validates its schema, content digest, duplicate status, and byte-exact generated leaderboard, the
repository writes one fixed audit marker for that exact base and head commit. The successful marker
job directly invokes a local reusable workflow from the same trusted caller commit, passing the exact
pull request number, full base SHA, full head SHA, and marker comment ID.

**Acceptance scenarios**:

1. **Given** an exact benchmark-only pull request, **When** the trusted boundary passes, **Then** one
   idempotent fixed comment records the full base and head SHAs under GitHub Actions user ID
   `41898282` and GitHub App ID `15368`, and its successful job calls the local reusable workflow.
2. **Given** a general, mixed, unsafe, stale, or malformed change, **When** the boundary runs, **Then**
   no audit marker, reusable-workflow call, approval, or merge action occurs.
3. **Given** a synchronize event, **When** the head changes, **Then** the new head requires a new
   trusted marker and authorization run; any old marker is ineligible.
4. **Given** a manually prepared benchmark PR, **When** its branch is not named
   `litb/submission-<submission-id>` or that digest does not identify the one added file, **Then** it
   is ineligible for automated approval and merge even if its two-file diff is otherwise valid.
5. **Given** a branch in the reserved `litb/submission-<submission-id>` namespace, **When** its diff
   becomes general, mixed, or otherwise non-submission content, **Then** the trusted boundary fails
   rather than reclassifying the pull request into the normal code lane.

### User story 2: Merge a clean submission without bypass (Priority: P1)

The local reusable workflow independently revalidates the current pull request before the reviewer
bot may arm squash auto-merge for that exact commit and approve it. GitHub still waits for every
required review and status check. Codex and CodeRabbit feedback is advisory and is never the
authorization signal.

**Acceptance scenarios**:

1. **Given** a successful trusted marker job, an exact benchmark-only diff, no unresolved review
   threads or active changes request, and a non-reviewer author, **When** the reusable workflow
   independently revalidates the PR and the exact live, unedited marker, **Then** the configured
   reviewer bot arms exact-head auto-merge and submits an exact-head approval.
2. **Given** a timely changes request, a stale commit, an unresolved thread, a draft, a non-main base,
   a non-submission branch, or failed validation, **When** the authorization call is processed,
   **Then** the PR remains open without approval or auto-merge.
3. **Given** checks are pending, **When** auto-merge is enabled, **Then** GitHub waits for branch
   protection rather than bypassing or directly updating `main`.
4. **Given** GitHub has not finished computing mergeability, **When** the authorization workflow
   reads the PR, **Then** it retries for a bounded interval and leaves the PR open if mergeability
   never becomes known.
5. **Given** GitHub reports `mergeable=true` with state `unstable`, **When** every other authorization
   condition passes, **Then** the workflow may arm native auto-merge, but GitHub still decides whether
   required checks permit the merge.

## Requirements

- **FR-001**: All existing publication controls MUST remain unchanged in effect: (a) an automated
  benchmark PR adds exactly one mode-`100644` ordinary blob named `[0-9a-f]{64}.json` under
  `site/data/submissions/` plus the generated leaderboard and makes no other change; (b) the
  `submission_id` equals the SHA-256 digest of canonical payload JSON without the ID, equals the
  filename, and is not a duplicate; (c) deterministic rebuild is byte-compared in PR CI and the
  Pages deployment; (d) `pull_request_target` uses exact-base checkout, data-only head fetch with
  rev-parse equality, validator bytes from the base, non-interpolated environment inputs,
  SHA-pinned actions, and `persist-credentials: false`; (e) site rendering remains
  `textContent`-only; and (f) both closed-schema implementations retain enum allowlists,
  duplicate-key and constant rejection, control-character/bidi/lone-surrogate rejection, and size
  caps.
- **FR-002**: The marker and any advisory review request MUST be emitted only after validator bytes
  and builder code loaded from the trusted base classify the exact diff as `benchmark-only` and
  validate schema, canonical digest, filename, duplicates, privacy shape, and the byte-exact
  deterministic leaderboard.
- **FR-003**: The fixed audit marker MUST be idempotent per full base-and-head pair and contain no
  contributor-supplied content. Its job MUST receive only repository-content read and pull-request
  write permissions, use the write scope only for the fixed comment, and invoke no review or merge
  endpoint. The marker MUST be fetched live by its comment ID and match the canonical body, full base
  and head SHAs, unedited timestamps, GitHub Actions user ID `41898282`, and GitHub App ID `15368`.
  It is audit evidence, not sufficient authorization by itself.
- **FR-004**: The successful marker job MUST directly call a local reusable workflow from the same
  trusted caller commit with the exact pull request number, full base SHA, full head SHA, and marker
  comment ID. It MUST NOT rely on an `issue_comment` event: the comment event created with the
  repository's `GITHUB_TOKEN` does not start a new workflow run. The reusable workflow MUST
  independently revalidate all authorization state rather than trusting its inputs or the marker
  alone. The branch-protection context named `Trusted benchmark boundary` MUST be produced by a final
  aggregator that remains pending until this downstream call succeeds. For general, manual-lane, and
  draft changes, it MUST require the exact expected skipped/success states instead of invoking the
  automated lane.
- **FR-005**: Codex and CodeRabbit MAY be requested for best-effort advisory review, but automation
  MUST NOT wait for either service and a clean, absent, skipped, rate-limited, or connector-error
  response MUST NOT authorize or veto the lane. A timely review thread or changes request visible to
  the final revalidation still fails closed.
- **FR-006**: Before the reviewer credential is used, trusted code MUST re-fetch and verify repository
  ID `1324333809`, PR number, state, draft status, mergeability, main base, exact head, submission
  branch digest, author, exact diff, safe file modes, canonical content, exact live marker ID/body/
  actor/App/timestamps/full-SHA binding, active review state, the publicly observable app-bound
  required checks, a native review decision
  consistent with either a fresh authorization or a validated partial-run retry, complete
  pagination, and zero unresolved threads. The live default-branch tip MUST still equal the
  authorized base SHA immediately before each possible credentialed mutation.
- **FR-007**: The caller MUST map repository secret `ERNEST_REVIEW_TOKEN` explicitly to the local
  reusable workflow's `reviewer_token`; `secrets: inherit` is forbidden. The credential MUST be
  bound only to the final mutation step after all public-token checks pass, MUST never enter command
  arguments or logs, and MUST be identity-checked before mutation. The boundary and marker jobs MUST
  use only their ephemeral GitHub token and MUST NOT receive the reviewer credential.
- **FR-008**: The reviewer bot MUST NOT approve its own PR and MUST pin the review to the full current
  head SHA.
- **FR-009**: For a fresh authorization, automation MUST first enable GitHub squash auto-merge with
  `expectedHeadOid`, a fixed digest-derived headline, and a fixed body, then submit an approval with
  `commitOID` for the same full head. A fully revalidated retry MAY re-arm missing auto-merge after a
  latest decisive exact-head reviewer approval already exists; the pending final required boundary
  keeps that retry out of GitHub's already-clean state. It MUST verify returned actor, state, and
  commit and MUST NOT use an admin bypass, direct merge, contributor title/body, push to `main`,
  force-push, stale head, or weakened protection.
- **FR-010**: Repeated eligible calls MUST be idempotent. Existing exact-head approval or auto-merge
  state MAY be reused only after complete revalidation. An approval is reusable only when it is the
  reviewer's latest decisive state and targets the current full head; a later dismissal, change
  request, or approval of another commit makes it ineligible.
- **FR-011**: Errors and public comments MUST be categorical and MUST NOT echo event payloads,
  credentials, private inputs, or untrusted diff content.
- **FR-012**: Automated approval and merge MUST require the live head ref
  `litb/submission-<submission-id>`, where the digest equals the sole added submission filename and
  its canonical content ID. The manual publication path MUST document this naming contract. This
  namespace is reserved, and the trusted boundary MUST reject a general or otherwise non-submission
  diff under it rather than reclassifying the pull request.
- **FR-013**: Per-run authorization MUST distinguish observable evidence from repository setup. It
  verifies protected status, the app-bound required-check summary, and native review decision, but
  MUST NOT claim to inspect administration-only settings unavailable to its read-only identities.
  Native auto-merge may be omitted from the read-only repository response; when it is visible as
  disabled the lane MUST reject it. After the reviewer credential is bound, the lane MUST require an
  authoritative `allow_auto_merge: true` response immediately before each possible mutation. Native
  auto-merge, stale-review dismissal, last-push approval, conversation resolution, linear history,
  admin enforcement, and force-push/deletion prohibitions remain mandatory operator prerequisites.
- **FR-014**: A transient unknown mergeability result MUST receive only bounded retries. Established
  `blocked`, `clean`, and `unstable` states MAY continue when `mergeable=true`; conflict, stale-base,
  draft, closed, and still-unknown states MUST fail closed. `unstable` MUST NOT be treated as a passed
  required check or merge authorization.

## Success criteria

- **SC-001**: A valid generated submission needs no maintainer click after the trusted boundary and
  fixed marker jobs succeed; the final required boundary stays pending through exact-head approval,
  and GitHub's required gates still decide when it merges.
- **SC-002**: Fixture tests reject spoofed Actions user/App IDs, edited or stale markers, comment-ID
  or full-SHA mismatches, untrusted workflow-call inputs, general/mixed/corrupt diffs, unresolved
  feedback, changes-requested state, self-review, wrong digest branches, unsafe observable protection,
  malicious PR metadata, exhausted mergeability retries, and repeated events.
- **SC-003**: The complete test suite, deterministic dataset check, strict privacy/history scan, and
  cross-platform CI remain green.

## Assumptions

- Codex and CodeRabbit are best-effort advisory reviewers whose availability is not a merge gate.
- Deterministic validation proves schema conformance, digest integrity, and publication shape. It is
  not provenance or attestation that the self-reported benchmark run occurred.
- Concurrent stale leaderboard PRs remain fail-closed and require regeneration from current `main`.
- GitHub does not expose every administration-only protection setting to the read-only workflow or
  non-admin reviewer identity. Operators verify and retain those settings outside contributor events.

## Pull request impact

- Publication workflow: changed for exact benchmark-only pull requests.
- Public submission and leaderboard contracts: unchanged.
- Runner/runtime contracts and experimental scope: unchanged.
- General code and documentation pull requests: no automated approval or merge path.
