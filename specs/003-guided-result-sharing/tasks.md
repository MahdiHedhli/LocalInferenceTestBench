# Tasks: Guided result sharing

**Input**: Design documents from `specs/003-guided-result-sharing/`

## Phase 1: Post-run decision and safe local retry

- [x] T001 Add safe-default post-run CLI arguments and TTY gating in `cli.py`.
- [x] T002 Persist the private report before post-action eligibility or prompting.
- [x] T003 Add canonical submission rendering and idempotent owner-only saving.
- [x] T004 Add CLI tests for private, save, invalid, non-interactive, cancel, and multi-model paths.

## Phase 2: Reviewed GitHub publication

- [x] T005 Add fixed-host GitHub identity preflight and explicit public disclosure.
- [x] T006 Add strict denylist, Gitleaks, unit, deterministic, privacy, and exact-diff gates.
- [x] T007 Build candidate and leaderboard bytes in an isolated canonical clone.
- [x] T008 Add owner-branch and verified-fork Git-data API flow without direct `main` writes.
- [x] T009 Add accepted-result, open-PR, stale-base, ref-collision, and partial-failure behavior.
- [x] T010 Add mocked command/API tests proving fixed routing and minimized payloads.

## Phase 3: Hosted boundary and documentation

- [x] T011 Add benchmark PR exact-diff validation and unit tests.
- [x] T012 Add the exact-diff guard to the publication CI job.
- [x] T013 Update README, contribution, submission, privacy, and Pages guidance.
- [x] T014 Publish this Spec Kit feature set and CLI contract.
- [x] T015 Run the complete unit, syntax, deterministic, strict privacy, and secret checks.
- [x] T016 Exercise isolated clone preparation with a synthetic candidate and no GitHub mutation.
- [x] T017 Complete final privacy/security review and confirm the working tree contains no result data.

## Phase 4: Schema `1.1` evidence coordination

- [x] T018 Amend guided-sharing specifications and operator guidance for the owner-only measurement
  sidecar, execution/measurement validity split, schema `1.1`, month period, and `1.0` regeneration
  policy without weakening confirmation or the two-file publication boundary.
- [x] T019 Add `--measurement-evidence` to run sharing and manual preparation, require exact per-model
  categorical evidence, exact source-run binding, and 1–1000 model rows, while stripping the binding
  and keeping the sidecar outside every saved candidate and network payload.
- [x] T020 Add safe failure tests for missing, unsafe, malformed, stale-run, oversized, mismatched,
  and inconsistent sidecars plus exact schema `1.1` candidate/publish retry coverage.

## Phase 5: Exact-bound single-command measurement integration

- [x] T021 Add tests for preallocated identity validation, pre/run/post ordering, exact adapter
  binding, bounded capture, approved-byte snapshot execution, POSIX process-tree cleanup, Windows
  fail-closed behavior, credential-free invocation, no post after a runner exception, Linux
  subreaper/zombie cleanup, Darwin `kqueue` non-reaping fallback, kill-before-reap/PID-reuse safety,
  atomic owner-only retention, and private-report preservation on sampler failure.
- [x] T022 Implement the POSIX synchronous local adapter bridge, approved-byte snapshot, dedicated
  standard-library supervisor, Linux child-subreaper descendant reaping, Darwin `kqueue` observer,
  kill-before-reap cleanup, validated preallocated runner identity, Windows two-step fallback, and
  same-object post-run evidence handoff in `measurement.py`, `_measurement_supervisor.py`,
  `runner.py`, and `cli.py`.
- [x] T023 Update the CLI contract, plan, research, data model, quickstart, README, and operator
  documentation with the honest sampler and two-step sidecar boundaries, including the synchronous
  no-escape constraint and owner-controlled executable `TMPDIR` requirement.
