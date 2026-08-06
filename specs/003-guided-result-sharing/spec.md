# Feature specification: Guided result sharing

**Feature Branch**: `003-guided-result-sharing`

**Created**: 2026-08-05

**Status**: Implemented

**Input**: Offer an option when a benchmark finishes to save identifier-minimized JSON or automate
submission to the public leaderboard repository, because a manual contribution process suppresses
the number of useful community results.

## User scenarios and testing

### User story 1: Decide when a standard run finishes (Priority: P1)

An operator completing a valid standard run can keep the result private, save minimized JSON, or
start a public pull-request submission without reconstructing commands from documentation.

**Independent test**: Run valid, limited, invalid, smoke, interactive, and non-interactive fixtures.
Confirm that only a valid interactive standard run prompts, Enter keeps the report private, and the
private report always exists before post-run processing begins.

**Acceptance scenarios**:

1. **Given** a valid interactive standard run, **When** it finishes, **Then** the CLI offers private,
   local JSON, and public PR choices with private as the default.
2. **Given** Enter, EOF, or an unsupported choice, **When** the prompt closes, **Then** no JSON export
   or network action occurs.
3. **Given** a smoke, limited, invalid, or non-interactive run without explicit sharing flags,
   **When** it finishes, **Then** current script-compatible behavior is preserved.
4. **Given** a post-run export or publication failure, **When** the command exits, **Then** the private
   aggregate report remains saved.

### User story 2: Save a reusable minimized record (Priority: P1)

An operator can turn the completed in-memory report, an approved public hardware descriptor, and a
closed categorical measurement-evidence sidecar into owner-only JSON immediately, then retry
publication later without rerunning inference.

**Independent test**: Save one- and multi-model fixtures twice. Confirm exact repeated content is
idempotent, permissions remain owner-only, and a symlink or different existing content is rejected.

**Acceptance scenarios**:

1. **Given** an eligible report and descriptor, **When** local save is chosen, **Then** one closed
   digest-named record per selected model is written under the ignored submission directory.
2. **Given** an exact secure existing candidate, **When** save is repeated, **Then** it succeeds
   without replacing the file.
3. **Given** an existing unsafe, visible, linked, or different destination, **When** save is attempted,
   **Then** it fails closed without overwriting data.
4. **Given** local save, **When** the action completes, **Then** no GitHub command is required or run.
5. **Given** a securely saved canonical candidate, **When** publication is retried later, **Then** the
   operator can use that file without rerunning inference and receives the same disclosure and
   confirmation boundary.
6. **Given** valid benchmark execution but no safe measurement sidecar, **When** save or PR is
   selected, **Then** preparation fails closed and the already-written private report remains intact.

### User story 3: Open a reviewed public submission automatically (Priority: P1)

An operator can review the complete minimized record and public-account disclosure, confirm once, and
have the tool create the isolated branch and reviewed pull request.

**Independent test**: Mock owner, contributor-fork, duplicate, stale-base, missing-tool, failed-scan,
branch-collision, and PR-failure paths. Confirm that network payloads contain only the candidate,
generated leaderboard, fixed digest metadata, and fixed repository routing.

**Acceptance scenarios**:

1. **Given** a selected public PR action, **When** preflight completes, **Then** the full minimized JSON,
   GitHub account, fork/branch/PR behavior, and fingerprinting risk are shown before confirmation.
2. **Given** no literal confirmation, **When** the disclosure prompt closes, **Then** no mutating
   GitHub action occurs and the local candidate remains saved.
3. **Given** confirmation and all gates passing, **When** publication runs, **Then** exactly one new
   submission and the regenerated leaderboard are committed to a feature branch and proposed through
   a pull request against canonical `main`.
4. **Given** no upstream write access, **When** publication runs, **Then** a verified canonical fork is
   created or reused; an unrelated same-named repository is rejected.
5. **Given** an accepted digest or matching open PR, **When** publication is retried, **Then** the
   existing public result is returned without creating a duplicate.

## Edge cases

- The run contains several models and no publication model is selected.
- The hardware descriptor exists but the strict local denylist is missing or empty.
- The measurement-evidence sidecar is missing, tracked, linked, broadly readable, has no exact model
  match, has a `source_run_id` different from the report's `run_id`, contains more than 1000 model
  rows, contains raw host values, or is inconsistent with its declared public validity.
- GitHub CLI is installed but authenticated to a host other than `github.com`.
- Gitleaks is absent, too old, or rejects the exact staged bytes.
- Upstream `main` changes between deterministic rebuild and branch creation.
- A public fork is created but branch or PR creation later fails.
- The deterministic branch already exists without a matching open pull request.
- A candidate is already accepted on `main`.
- A benchmark PR tries to change validators, workflows, documentation, or more than one result.
- A saved candidate is renamed, reformatted, visible to Git, broadly readable, or replaced by a link.

## Requirements

### Functional requirements

- **FR-001**: The private aggregate report MUST be persisted before any post-run export or publication.
- **FR-002**: The default `ask` action MUST prompt only for a valid interactive standard run and MUST
  default to keeping the result private.
- **FR-003**: Non-interactive runs MUST perform no post-action unless `save` or `pr` is explicit.
- **FR-004**: Local save MUST reuse the existing closed leaderboard-submission contract and separate
  public hardware descriptor. For schema `1.1`, it MUST also require a separate ignored, owner-only
  categorical measurement-evidence sidecar.
- **FR-005**: Local candidates MUST remain ignored, owner-only, regular, append-only files; an exact
  existing candidate MAY count as idempotent success.
- **FR-006**: Public publication MUST display the complete candidate and disclose the authenticated
  account, public timestamp, exact hardware/performance linkage, and fork/branch/PR effects.
- **FR-007**: Interactive publication MUST require literal confirmation. Non-interactive publication
  MUST require both `--submission pr` and `--confirm-public`.
- **FR-008**: Publication MUST use the fixed canonical repository and a reviewed feature-branch pull
  request. It MUST NOT push directly to `main`, force-push, or overwrite an existing ref.
- **FR-009**: Before a mutating GitHub call, publication MUST require an owner-only populated ignored
  denylist, Gitleaks 8.30.1 or newer, authenticated GitHub CLI for `github.com`, deterministic dataset
  validation, unit tests, staged privacy checks, and redacted secret scanning. Validation children
  MUST receive a scrubbed environment and uploaded bytes MUST be read from the checked Git index.
- **FR-010**: Publication MUST operate in an isolated private temporary clone of canonical upstream
  and MUST stage exactly one new digest-named submission plus the generated leaderboard.
- **FR-011**: Raw or private inputs—the source report, raw descriptor, measurement-evidence sidecar
  or environment, endpoint, credentials, artifact directory, denylist, local paths, and private model
  selector—MUST NOT enter a GitHub API request or PR body. Publication MAY upload only the validated
  candidate submission and deterministically generated leaderboard payloads, including the approved
  public `runtime_configuration` and categorical measurement projection retained in those bytes;
  other PR metadata MUST remain fixed and non-secret.
- **FR-012**: Publication MUST abort before branch creation when upstream changes during preparation.
- **FR-013**: A multi-model public PR MUST require explicit selection of one result; local save MAY
  preserve all separated candidates.
- **FR-014**: Retry MUST recognize an already accepted result, matching open PR, or verified
  deterministic branch left by failed PR creation only after verifying the exact repository,
  branch, base parent, file set, commit tree, and payload bytes. A verified orphan branch MAY be
  resumed only by creating its missing PR; any mismatch MUST be refused without overwriting it.
- **FR-015**: Continuous integration MUST reject any benchmark PR that changes anything beyond one
  append-only submission and the deterministically regenerated leaderboard, using validator bytes
  from the trusted pull-request base commit.
- **FR-016**: Errors MUST remain categorical and MUST NOT echo subprocess stderr, credentials,
  scanner matches, private inputs, or local absolute paths.
- **FR-017**: A saved-candidate retry MUST avoid inference and MUST accept only an owner-only regular
  file that is Git-ignored when inside a worktree, with a matching digest filename, valid closed
  contract, and exact canonical rendered bytes. A secure file outside a worktree MUST remain
  reusable. Retry MUST reuse FR-006 through FR-016 and require `--confirm-public` when
  non-interactive.
- **FR-018**: The post-run and manual preparation commands MUST expose one explicit
  `--measurement-evidence` path, defaulting to the ignored local area. The file MUST remain local and
  MUST NOT enter the prepared pull-request change, GitHub API payload, or PR metadata. Its required
  top-level `source_run_id` MUST exactly match the source report's `run_id`; its unique model list
  MUST contain 1–1000 entries; and the run binding MUST be omitted from prepared public bytes.
- **FR-019**: Guided sharing MUST distinguish source execution validity (`valid`) from public
  measurement validity (`clean`, `nonquiescent`, or `degraded_midrun`). It MUST NOT infer one from the
  other, and absent evidence MUST block candidate creation rather than silently selecting a public
  validity.
- **FR-020**: Newly prepared and published candidates MUST use public schema `1.1`. A saved schema
  `1.0` candidate MAY remain local historical evidence but MUST be regenerated from its source report
  and measurement evidence before entering a new benchmark pull request.
- **FR-021**: On POSIX, non-interactive `run --submission save` and `run --submission pr` MUST require an
  explicitly selected local measurement-sampler executable. The CLI MUST allocate and validate the
  run identity before endpoint access, invoke the adapter synchronously immediately before the run
  and, when the pre sample succeeds, immediately after the complete run, and require each closed
  categorical response to echo the exact run ID, phase,
  and ordered public model IDs. Invocation MUST use no shell, a credential-free allowlisted
  environment, discarded stderr, a bounded timeout, an in-flight stdout byte cap, isolated process
  execution, and bounded process-tree cleanup. The adapter file MUST be at most 16 MiB, regular,
  non-symlinked, executable, not group/world-writable, and identity/content rechecked at launch.
  Only a private non-writable snapshot of approved bytes MAY execute. Windows MUST fail this option
  closed and retain two-step exact-bound preparation. Missing,
  stale, malformed, oversized, timed-out, nonzero, or incomplete output MUST preserve the private
  report and block export. The CLI MUST NOT synthesize a missing sample or replace the binding on
  evidence that was not collected through this invocation.

### Key entities

- **Post-run action**: `ask`, `none`, `save`, or `pr` decision made after report persistence.
- **Publication identity**: Authenticated GitHub login, canonical owner, repository, base branch, and
  upstream branch permission used only for disclosure and fixed routing.
- **Prepared public change**: Candidate bytes, generated leaderboard bytes, and exact upstream commit
  and tree used to construct an isolated branch.
- **Publication result**: Newly opened PR, matching open PR, or already accepted leaderboard result.

## Success criteria

- **SC-001**: Tests prove that private/EOF/cancel paths issue zero mutating GitHub calls.
- **SC-002**: One hundred percent of published payload bytes come from the validated candidate,
  generated leaderboard, fixed digest metadata, or fixed repository routing.
- **SC-003**: Automated PRs contain exactly two changed paths and pass existing cross-platform tests,
  deterministic dataset validation, privacy scanning, and Gitleaks.
- **SC-004**: An operator can save a candidate or open a PR from the completed run without manually
  copying files, rebuilding data, creating branches, or composing PR text.
- **SC-005**: Existing non-interactive `litb run` users observe no prompt or network action by default.
- **SC-006**: A securely saved candidate can be published later without a model server or benchmark
  rerun, while renamed, reformatted, visible, or permission-broad candidates are rejected.
- **SC-007**: Tests prove missing, unsafe, raw-valued, stale-run, oversized, mismatched, and
  inconsistent measurement sidecars issue zero GitHub mutations, omit the private binding from
  public bytes, and leave the private run report intact.
- **SC-008**: A non-interactive standard run can save or prepare a PR in one command through an
  explicitly selected sampler, with tests proving pre → run → post ordering, exact binding, bounded
  capture, credential-free invocation, atomic owner-only evidence retention, and private-report
  preservation on every sampler failure.

## Assumptions

- “Anonymous” means identifier-minimized, not unlinkable; exact setup data and GitHub identity remain
  public by design.
- GitHub CLI is an optional publication dependency, not a core runner dependency.
- The original guided-sharing feature did not change JSON contracts. Stage 3 coordinates its CLI
  with public schema `1.1`; the exact two-file PR boundary, confirmation, and publication controls
  remain unchanged.
- Maintainer review and required hosted checks remain the acceptance boundary.
