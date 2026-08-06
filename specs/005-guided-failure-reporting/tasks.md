# Tasks: Guided benchmark failure reporting

**Input**: Design documents in `specs/005-guided-failure-reporting/`

## Phase 1: Contract and tests

- [x] T001 Publish the closed failure signal, issue draft, consent, and URL contracts.
- [x] T002 Add exhaustive eligible/ineligible classification and priority tests.
- [x] T003 Add schema, platform reduction, runtime projection, injection, bound, and URL round-trip
  tests.
- [x] T004 Add CLI tests for private-report-before-prompt ordering, TTY/default/decline/EOF paths,
  exact consent, browser false/error, and original-status preservation.

## Phase 2: Implementation

- [x] T005 Add structured preflight diagnostics to `RunnerError` without parsing messages.
- [x] T006 Implement the dependency-free closed draft, report detector, renderer, and fixed URL.
- [x] T007 Integrate `--failure-report {ask,none}` into only `litb run` and add the complete preview,
  disclosure, consent, and one-shot browser handoff.
- [x] T008 Bump the package feature version and keep code-controlled version fields synchronized.

## Phase 3: Documentation and verification

- [x] T009 Update the baseline specification, README, contribution, guide, interpretation, and
  privacy documentation without changing benchmark/public-result contracts.
- [ ] T010 Run full unit, deterministic-build, syntax, compile, privacy, history, hooks, and Gitleaks
  validation across supported platforms.
- [ ] T011 Obtain independent review, resolve findings, merge through branch protection, and verify
  the protected main checks.
