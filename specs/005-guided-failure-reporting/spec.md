# Feature specification: Guided benchmark failure reporting

**Feature Branch**: `feat/guided-failure-reporting`

**Created**: 2026-08-05

**Status**: In progress

**Input**: After a benchmark execution or runtime-compatibility failure, offer an opt-in way to
open a minimized, prefilled GitHub issue so maintainers can see recurring failures without asking
users to paste logs or private machine details.

## User scenarios and testing

### User story 1: Recognize an actionable execution failure (Priority: P1)

An operator running `litb run` is offered a diagnostic issue draft only when a closed transport,
runtime-protocol, or harness category indicates that the benchmark did not execute normally.

**Acceptance scenarios**:

1. **Given** an eligible preflight exception or a completed report containing an eligible case
   termination, **When** the private run path finishes, **Then** one categorical failure signal is
   selected deterministically.
2. **Given** a semantic, exact-format, refusal, reasoning-only, output-budget, context-window,
   not-applicable, validity, configuration, safety, authentication, rate-limit, cancellation,
   measurement, submission, or publication outcome, **When** it is classified, **Then** no failure
   issue is offered.
3. **Given** an unexpected exception escaping the benchmark runner, **When** it is classified,
   **Then** only `runner_internal` / `internal_harness_error` is retained and the exception object is
   never rendered.

### User story 2: Review an identifier-minimized draft (Priority: P1)

An interactive operator can inspect every field that would be sent to GitHub before any browser or
network action occurs.

**Acceptance scenarios**:

1. **Given** an eligible failure on an interactive terminal, **When** the draft is prepared, **Then**
   it contains only the closed schema in the data model.
2. **Given** a valid owner-only ignored public environment descriptor, **When** the draft is built,
   **Then** it may include its already-public runtime name, version, and backend and a derived coarse
   hardware class; otherwise those values are `unknown`.
3. **Given** a draft preview, **When** it is shown, **Then** the disclosure states that opening the
   URL immediately transmits the draft to GitHub and may retain it in browser or network history,
   while GitHub Submit is the separate public-posting confirmation.

### User story 3: Open the GitHub composer without auto-submitting (Priority: P1)

An operator can type the normalized single-letter consent `y` to open the fixed repository issue
composer with a deterministic title and body. No token, GitHub CLI, issue API, shell command, or
local diagnostic file is used.

**Acceptance scenarios**:

1. **Given** Enter, EOF, Ctrl-C at the optional prompt, `n`, any other response, a non-interactive terminal, or
   `--failure-report none`, **When** failure handling completes, **Then** no browser call occurs.
2. **Given** normalized single-letter `y`, **When** the browser handoff succeeds, **Then** exactly one fixed-origin URL
   containing only `title` and `body` query keys is opened.
3. **Given** a false browser result or browser exception, **When** the handoff ends, **Then** the
   original benchmark exit status is unchanged and no retry occurs.
4. **Given** the GitHub composer, **When** the operator does not click Submit, **Then** no public issue
   is created.

## Requirements

- **FR-001**: Only `litb run` MAY expose `--failure-report {ask,none}`; it MUST default to `ask` but
  MUST prompt only when both stdin and stdout are interactive terminals.
- **FR-002**: Eligible categories MUST be exactly `timeout`, `network_error`, `server_error`,
  `http_error`, `request_rejected`, `invalid_json`, `protocol_error`, `response_too_large`, and
  `internal_harness_error`.
- **FR-003**: Eligible phases MUST be exactly `preflight`, `case_execution`, and `runner_internal`.
  Preflight classification MUST use a structured runner diagnostic and MUST NOT parse error text.
- **FR-004**: A returned report MUST be persisted before its closed termination categories are
  inspected or a prompt is shown. Multiple eligible categories MUST use a fixed priority.
- **FR-005**: The draft MUST use the exact closed schema in `data-model.md`; no exception text,
  traceback, log, prompt, completion, reasoning, tool argument, endpoint, credential, environment,
  path, host/user/process inventory, model identity, run/submission ID, precise time, raw telemetry,
  or hash of excluded data may enter it.
- **FR-006**: Operating system, Python, architecture, and hardware MUST be reduced to the closed
  coarse enums. Raw platform strings and exact hardware inventory MUST never be retained.
- **FR-007**: Runtime name, version, and backend MAY be copied only from an already-valid owner-only,
  ignored public descriptor and MUST pass descriptor-grade validation. Failure to read or validate
  it MUST yield `unknown` without replacing the original benchmark failure.
- **FR-008**: The issue destination MUST be hardcoded to
  `https://github.com/MahdiHedhli/LITB/issues/new`; the query MUST contain exactly
  `title` and `body`, and title, body, and URL MUST be bounded and deterministic.
- **FR-009**: The complete draft and transmission disclosure MUST be shown before consent. Only one
  ASCII `y` or `Y`, after trimming surrounding ASCII whitespace, MAY call the browser once. Opening
  the URL MUST be described as transmission to GitHub;
  clicking Submit MUST be described as the separate public confirmation.
- **FR-010**: Failure reporting MUST use only the Python standard library for the browser handoff and
  MUST NOT use a PAT, `gh`, the Issues API, a shell, background networking, or local draft storage.
- **FR-011**: Failure reporting MUST never change the original benchmark exit code or suppress its
  normal private report. Ctrl-C while this optional prompt is active MUST decline the prompt rather
  than replace that status. Its own failure MUST be categorical and best-effort.
- **FR-012**: This feature MUST NOT change benchmark cases, report/submission/leaderboard schemas,
  Pages, trusted workflows, or benchmark auto-merge behavior.

## Success criteria

- **SC-001**: Tests prove every decline and ineligible path performs zero browser calls.
- **SC-002**: Tests prove every opened URL has the fixed scheme, host, path, query-key set, and a
  round-trippable body equal to the previewed draft.
- **SC-003**: Adversarial exception, platform, and descriptor strings never reach the preview, URL,
  or browser call.
- **SC-004**: Existing unit, deterministic-build, privacy, history, and secret-scanning gates pass on
  macOS, Linux, and Windows.

## Assumptions

- “Identifier-minimized” is not anonymous: GitHub receives the URL request and associates normal
  account, request-time, IP, cookie, and browser metadata according to its service behavior.
- The draft is a self-reported diagnostic signal, not a benchmark result, attestation, or proof of a
  project defect.
