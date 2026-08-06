# Feature specification: Trusted submission auto-merge

**Feature Branch**: `feat/trusted-submission-auto-merge`

**Created**: 2026-08-06

**Status**: In progress

**Input**: Let identifier-minimized benchmark submissions reach the public leaderboard promptly
without a maintainer manually reviewing and merging every generated two-file pull request.

## User scenarios and testing

### User story 1: Request bounded automated review (Priority: P1)

After trusted base code proves that a pull request is an exact append-only benchmark submission and
validates its schema, content digest, duplicate status, and byte-exact generated leaderboard, the
repository requests Codex and CodeRabbit review once for that exact base and head commit.

**Acceptance scenarios**:

1. **Given** an exact benchmark-only pull request, **When** the trusted boundary passes, **Then** one
   idempotent review-request comment tags `@codex review` and `@coderabbitai review` for the full
   base and head SHAs.
2. **Given** a general, mixed, unsafe, stale, or malformed change, **When** the boundary runs, **Then**
   no automated review request, approval, or merge action occurs.
3. **Given** a synchronize event, **When** the head changes, **Then** the new head requires a new
   review signal and any old signal is ineligible.
4. **Given** a manually prepared benchmark PR, **When** its branch is not named
   `litb/submission-<submission-id>` or that digest does not identify the one added file, **Then** it
   is ineligible for automated approval and merge even if its two-file diff is otherwise valid.

### User story 2: Merge a clean submission without bypass (Priority: P1)

A clean Codex review signal for the current head causes the reviewer bot to arm squash auto-merge
for that exact commit and then approve it. GitHub still waits for every required review and status
check.

**Acceptance scenarios**:

1. **Given** a clean Codex bot comment pinned to the current head, an exact benchmark-only diff, no
   unresolved review threads, and a non-reviewer author, **When** the automation revalidates the PR,
   **Then** the configured reviewer bot arms exact-head auto-merge and submits an exact-head approval.
2. **Given** findings, a rate-limit notice, a stale commit, an unresolved thread, a draft, a non-main
   base, a non-submission branch, or failed validation, **When** the event is processed, **Then** the PR
   remains open without approval or auto-merge.
3. **Given** checks are pending, **When** auto-merge is enabled, **Then** GitHub waits for branch
   protection rather than bypassing or directly updating `main`.
4. **Given** GitHub has not finished computing mergeability, **When** the authorization workflow
   reads the PR, **Then** it retries for a bounded interval and leaves the PR open if mergeability
   never becomes known.
5. **Given** GitHub reports `mergeable=true` with state `unstable`, **When** every other authorization
   condition passes, **Then** the workflow may arm native auto-merge, but GitHub still decides whether
   required checks permit the merge.

## Requirements

- **FR-001**: Existing append-only, digest, deterministic-rebuild, file-mode, privacy, and trusted
  `pull_request_target` controls MUST remain unchanged in effect.
- **FR-002**: Review requests MUST be emitted only after validator bytes and builder code loaded from
  the trusted base classify the exact diff as `benchmark-only` and validate schema, canonical digest,
  filename, duplicates, privacy shape, and the byte-exact deterministic leaderboard.
- **FR-003**: Review requests MUST be idempotent per full base-and-head pair and contain no
  contributor-supplied content.
- **FR-004**: A merge signal MUST be a newly created, unedited comment from Codex user ID
  `199175422` through GitHub App ID `1144995`, use the documented clean-review form, and identify a
  commit prefix matching the current full PR head. The connector's ten-character prefix is advisory;
  the preceding trusted request marker supplies the full base-and-head binding.
- **FR-005**: CodeRabbit MUST be requested, but a rate-limit, skipped review, or green rate-limit
  status MUST NOT be represented as substantive approval.
- **FR-006**: Before the reviewer credential is used, trusted code MUST re-fetch and verify repository
  ID `1324333809`, PR number, state, draft status, mergeability, main base, exact head, submission
  branch digest, author, exact diff, safe file modes, canonical content, comment chronology, active
  review state, the publicly observable app-bound required checks, a native review decision
  consistent with either a fresh authorization or a validated partial-run retry, complete
  pagination, and zero unresolved threads. The live default-branch tip MUST still equal the
  authorized base SHA immediately before each possible credentialed mutation.
- **FR-007**: Reviewer credentials MUST be available only to the final trusted job, MUST never enter
  command arguments or logs, and MUST be identity-checked before mutation.
- **FR-008**: The reviewer bot MUST NOT approve its own PR and MUST pin the review to the full current
  head SHA.
- **FR-009**: For a fresh authorization, automation MUST first enable GitHub squash auto-merge with
  `expectedHeadOid`, a fixed digest-derived headline, and a fixed body, then submit an approval with
  `commitOID` for the same full head. A fully revalidated retry MAY re-arm missing auto-merge after a
  latest decisive exact-head reviewer approval already exists. It MUST verify returned actor, state,
  and commit and MUST NOT use an admin bypass, direct merge, contributor title/body, push to `main`,
  force-push, stale head, or weakened protection.
- **FR-010**: Repeated eligible events MUST be idempotent. Existing exact-head approval or auto-merge
  state MAY be reused only after complete revalidation. An approval is reusable only when it is the
  reviewer's latest decisive state and targets the current full head; a later dismissal, change
  request, or approval of another commit makes it ineligible.
- **FR-011**: Errors and public comments MUST be categorical and MUST NOT echo event payloads,
  credentials, private inputs, or untrusted diff content.
- **FR-012**: Automated approval and merge MUST require the live head ref
  `litb/submission-<submission-id>`, where the digest equals the sole added submission filename and
  its canonical content ID. The manual publication path MUST document this naming contract.
- **FR-013**: Per-run authorization MUST distinguish observable evidence from repository setup. It
  verifies protected status, the app-bound required-check summary, and native review decision, but
  MUST NOT claim to inspect administration-only settings unavailable to its read-only identities.
  Stale-review dismissal, last-push approval, conversation resolution, linear history, admin
  enforcement, and force-push/deletion prohibitions remain mandatory operator prerequisites.
- **FR-014**: A transient unknown mergeability result MUST receive only bounded retries. Established
  `blocked`, `clean`, and `unstable` states MAY continue when `mergeable=true`; conflict, stale-base,
  draft, closed, and still-unknown states MUST fail closed. `unstable` MUST NOT be treated as a passed
  required check or merge authorization.

## Success criteria

- **SC-001**: A valid generated submission needs no maintainer click after Codex emits a clean
  same-head signal; required GitHub gates still decide when it merges.
- **SC-002**: Fixture tests reject spoofed bot/app IDs, edited comments, stale prefixes, full-marker
  mismatches, malformed clean comments, general/mixed/corrupt diffs, unresolved feedback,
  changes-requested state, self-review, wrong digest branches, unsafe observable protection,
  malicious PR metadata, exhausted mergeability retries, and repeated events.
- **SC-003**: The existing 168-test baseline, deterministic dataset check, strict privacy/history scan,
  and cross-platform CI remain green.

## Assumptions

- Codex clean comments are an availability/review signal, not provenance or attestation.
- CodeRabbit is best-effort because its public review service can rate-limit a valid submission.
- Concurrent stale leaderboard PRs remain fail-closed and require regeneration from current `main`.
- GitHub does not expose every administration-only protection setting to the read-only workflow or
  non-admin reviewer identity. Operators verify and retain those settings outside contributor events.

## Pull request impact

- Publication workflow: changed for exact benchmark-only pull requests.
- Public submission and leaderboard contracts: unchanged.
- Runner/runtime contracts and experimental scope: unchanged.
- General code and documentation pull requests: no automated approval or merge path.
