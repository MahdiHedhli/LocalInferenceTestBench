# Tasks: Hardware-Agnostic Local Inference Test Bench

**Input**: Design documents from specs/001-local-inference-testbench/

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are required by FR-018. Test tasks precede the behavior they specify.

**Status rule**: Mark a task complete only when its named files contain the behavior and its relevant
validation passes. File existence alone is not completion.

## Format: ID, optional parallel marker, story label, action, and exact path

- [P] means the task can run in parallel because it targets different files and has no dependency on
  incomplete work.
Story labels US1 through US4 map directly to the four prioritized user stories in spec.md.

## Phase 1: Setup and Public Skeleton

**Purpose**: Establish the installable package, repository boundary, legal notices, and normative
design contracts.

- [x] T001 Configure Python 3.11+ packaging, the litb console entry, and standard-library-only runtime
  dependencies in pyproject.toml
- [x] T002 [P] Add package metadata and module execution entry points in
  src/local_inference_test_bench/__init__.py and src/local_inference_test_bench/__main__.py
- [x] T003 [P] Ignore local manifests, environment files, custom denylist files, and generated run
  artifacts while retaining artifacts/.gitkeep in .gitignore and artifacts/.gitkeep
- [x] T004 [P] Add the repository license and retain redistributed scaffold notices in LICENSE and
  THIRD_PARTY_NOTICES.md
- [x] T005 [P] Publish the data dictionary and closed manifest/run-record contracts in
  specs/001-local-inference-testbench/data-model.md,
  specs/001-local-inference-testbench/contracts/manifest.schema.json, and
  specs/001-local-inference-testbench/contracts/run-record.schema.json
- [x] T006 [P] Document runnable baseline and negative validation scenarios in
  specs/001-local-inference-testbench/quickstart.md
- [x] T007 Create a sanitized non-runnable collection example with no endpoint or credential value in
  config/models.example.json

**Checkpoint**: The package can be installed, local output stays untracked, and the public contracts
are reviewable before runner behavior is implemented.

---

## Phase 2: Foundational Safety and Contract Primitives

**Purpose**: Implement shared validation, transport, reporting, and command infrastructure that
blocks every user story.

**Critical**: Complete this phase before story implementation.

- [x] T008 [P] Add failing tests for collection shape, unique model IDs, exact revision-or-digest,
  settings, unsupported versions, and unknown fields in tests/test_models.py
- [x] T009 [P] Add failing tests for URL parsing, all-address local resolution, mixed/public/unresolved
  rejection, credential/query/fragment rejection, and environment-file permission handling in
  tests/test_client.py
- [x] T010 Implement manifest dataclasses, strict collection validation, and public projection models
  in src/local_inference_test_bench/models.py
- [x] T011 Implement fail-closed endpoint resolution plus ignored owner-safe environment-file loading
  in src/local_inference_test_bench/safety.py
- [x] T012 Implement a bounded non-streaming chat-completions transport and normalized client error
  categories in src/local_inference_test_bench/client.py
- [x] T013 Implement closed record serialization primitives with no raw-content or free-form error
  fields in src/local_inference_test_bench/reporting.py
- [x] T014 Implement shared argument parsing for check and run, including manifest, endpoint,
  env-file, profile, and artifacts-directory path options in src/local_inference_test_bench/cli.py

**Checkpoint**: The foundational validators reject unsafe inputs before a benchmark request and the
report writer can emit only contract-defined fields.

---

## Phase 3: User Story 1 - Compare Local Models Safely (Priority: P1) — MVP

**Goal**: Check a local endpoint and collection manifest, run synthetic smoke or standard cases
sequentially, and produce minimized results with independent semantic and exact-format outcomes.

**Independent Test**: Start a stub-compatible local endpoint, run check and both baseline profiles,
and inspect a record containing only provenance, settings, categorical outcomes, latency, usage,
termination, and validity.

### Tests for User Story 1

- [x] T015 [P] [US1] Add failing client tests for request envelopes, runtime metadata absence,
  response-size limits, finish-reason normalization including reasoning-only output, usage
  normalization, and redacted errors in
  tests/test_client.py
- [x] T016 [P] [US1] Add failing scoring tests for structured output, statically inspected code,
  defensive analysis, inert read-only tool selection, unapproved-change refusal, and independent
  semantic/exact-format outcomes in tests/test_scoring.py
- [x] T017 [P] [US1] Add failing runner tests for smoke-subset selection, standard coverage,
  sequential collection order, timeout behavior, and no code/tool/lifecycle execution in
  tests/test_runner.py
- [x] T018 [P] [US1] Add failing data-minimization tests proving records omit prompt, response,
  response fingerprint, reasoning, tool arguments, endpoint, credential, environment, host, raw
  identity, and exception fields in tests/test_runner.py

### Implementation for User Story 1

- [x] T019 [US1] Complete safe request construction and normalized response parsing in
  src/local_inference_test_bench/client.py
- [x] T020 [US1] Implement the five synthetic baseline case definitions and smoke/standard selection
  in src/local_inference_test_bench/runner.py
- [x] T021 [US1] Implement static semantic checks, exact-envelope checks, categorical inert routing,
  safe-refusal/change-boundary rules, reasoning-presence, and outcome composition in
  src/local_inference_test_bench/scoring.py
- [x] T022 [US1] Implement sequential case execution, bounded timing, and client-failure
  classification in src/local_inference_test_bench/runner.py
- [x] T023 [US1] Implement aggregate counts, optional usage totals, case and weighted completion
  throughput, termination categories, and atomic ignored artifact writes in
  src/local_inference_test_bench/reporting.py
- [x] T024 [US1] Wire check and run so every execution path performs the same preflight before requests
  in src/local_inference_test_bench/cli.py and src/local_inference_test_bench/__main__.py
- [x] T025 [P] [US1] Document the portable operator workflow and scoring rationale in docs/guide.md
  and docs/methodology.md

**Checkpoint**: User Story 1 is independently usable as the local-only MVP.

---

## Phase 4: User Story 2 - Publish a Sanitized Process (Priority: P2)

**Goal**: Reject credentials and deployment fingerprints locally and in continuous integration, keep
local inputs/results ignored, and document a trustworthy public boundary.

**Independent Test**: Seed a temporary repository with each prohibited category, observe redacted
local and CI failures, remove the fixtures, and observe tests plus both scanners passing.

### Tests for User Story 2

- [x] T026 [P] [US2] Add failing fixtures for credential assignments, private and shared address
  ranges, absolute home paths, machine identifiers, private hostnames, and literal custom denied
  terms in tests/test_public_safety.py
- [x] T027 [P] [US2] Add failing tests for staged versus full scan selection, force-added ignored
  artifacts, binary files, symlinks, metacharacter-containing literal terms, deterministic ordering,
  and redacted relative findings in tests/test_public_safety.py
- [x] T028 [P] [US2] Add failing tests for absent, tracked, group/world-readable, and safely ignored
  environment files in tests/test_public_safety.py
- [x] T029 [P] [US2] Add failing integration tests proving no prohibited report field can pass
  serialization or the publication scanner in tests/test_runner.py and
  tests/test_public_safety.py

### Implementation for User Story 2

- [x] T030 [US2] Implement staged, tracked, and full-tree identifier scanning with literal local
  denylist support and redacted findings in scripts/public_safety.py
- [x] T031 [US2] Compose tests, privacy scanning, environment-file checks, and fail-closed external
  secret scanning in scripts/public-check
- [x] T032 [P] [US2] Install the version-controlled hooks without copying private configuration in
  scripts/install-hooks
- [x] T033 [P] [US2] Invoke staged publication checks from .githooks/pre-commit and the complete gate
  from .githooks/pre-push
- [x] T034 [P] [US2] Run the cross-platform test matrix, full privacy scan, and external secret scan
  on pushes and pull requests in .github/workflows/public-safety.yml
- [x] T035 [P] [US2] Configure dependency-update review for pinned workflow actions in
  .github/dependabot.yml
- [x] T036 [P] [US2] Document prohibited data, ignored local configuration, disclosure handling,
  scanner prerequisites, and sanitized export review in SECURITY.md and
  docs/security-and-privacy.md
- [x] T037 [US2] Enable repository-host secret scanning and push protection where supported and
  record a provider-neutral verification procedure in SECURITY.md
- [x] T038 [US2] Run the full tracked-content gate and remediate every lab-identifying or secret
  finding through scripts/public-check

**Checkpoint**: User Story 2 is complete and the repository may cross the public boundary only after
the provider controls in T037 are verified.

---

## Phase 5: User Story 3 - Reproduce and Interpret Results (Priority: P3)

**Goal**: Preserve public artifact identity, settings, suite/profile version, model and run validity,
and distinct termination semantics so reviewers can compare evidence responsibly.

**Independent Test**: Validate a synthetic record against the contract, compare same-display-name
entries with different revision/digest values, and show that missing metadata, truncation, and
disturbance affect validity without authorizing deployment.

### Tests for User Story 3

- [x] T039 [P] [US3] Add failing tests proving the canonical public-manifest digest changes with
  public provenance/settings but not credential_env or runtime_model in tests/test_models.py
- [x] T040 [P] [US3] Add failing tests preserving distinct revisions/digests under identical display
  names and enforcing runtime-identity match/metadata-unavailable validity in tests/test_runner.py
- [x] T041 [P] [US3] Add failing tests distinguishing output_budget, context_window, length_unknown,
  request errors, limited runs, invalid runs, and false deployment authorization in
  tests/test_runner.py

### Implementation for User Story 3

- [x] T042 [US3] Implement canonical public projection and public_manifest_sha256 generation in
  src/local_inference_test_bench/models.py and src/local_inference_test_bench/reporting.py
- [x] T043 [US3] Implement metadata-availability and runtime-identity-match classification without
  persisting raw identity in src/local_inference_test_bench/client.py and
  src/local_inference_test_bench/runner.py
- [x] T044 [US3] Implement per-model and top-level valid/limited/invalid aggregation with immutable
  run IDs and deployment_authorization fixed false in src/local_inference_test_bench/reporting.py
- [x] T045 [P] [US3] Document provenance keys, fair comparison boundaries, missing usage, termination
  meanings, and the evidence-not-authorization rule in docs/interpreting-results.md
- [x] T046 [US3] Present only publication-safe counts, aggregate metrics, and validity in console
  summaries from src/local_inference_test_bench/cli.py

**Checkpoint**: User Story 3 can be tested from a synthetic contract fixture without access to a real
model response.

---

## Phase 6: User Story 4 - Add Optional Experiments (Priority: P4)

**Goal**: Give contributors a safe place to propose specialized work while leaving smoke, standard,
the runner, schemas, and tests independent of it.

**Independent Test**: Remove docs/experiments and confirm the baseline install, quickstart, runner,
contracts, and tests still operate; separately review each registered proposal for its Experimental label
and risk boundaries.

### Tests for User Story 4

- [x] T047 [P] [US4] Add a regression test that imports and executes the baseline without optional
  experiment or telemetry packages in tests/test_runner.py

### Implementation for User Story 4

- [x] T048 [P] [US4] Document the capability-based optional-adapter boundary without runtime-product
  assumptions in docs/adapters.md
- [x] T049 [P] [US4] Create an Experimental registry with prerequisites, risks, baseline exclusions,
  and exit criteria for context, repeatability, template, multi-runtime, and orchestration work in
  docs/experiments/README.md
- [x] T050 [US4] List metadata-only observability and isolated dynamic-agent evaluation only as
  Experimental studies, including authorization, isolation, non-production targeting, and cleanup
  requirements where applicable, in docs/experiments/README.md
- [x] T051 [US4] Add experiment contribution and retirement rules that prevent optional findings from
  becoming baseline claims in CONTRIBUTING.md and docs/experiments/README.md

**Checkpoint**: Experiments are visible and useful but completely removable from the standard
process.

---

## Phase 7: Polish and Cross-Cutting Release Gates

**Purpose**: Make the project understandable in a clean clone and reconcile every public-release
control.

- [x] T052 [P] Add a concise value proposition, safe install path, two-command example, documentation
  map, and experiment boundary to README.md
- [x] T053 [P] Add Spec Kit change workflow, test-first expectations, privacy review, and pull-request
  boundary declarations to CONTRIBUTING.md
- [x] T054 [P] Cross-link guide, methodology, privacy, interpretation, adapters, experiments, and
  feature artifacts from README.md and docs/guide.md
- [x] T055 Run python -m unittest discover -s tests -v and resolve all failures in tests/
- [x] T056 Run scripts/public-check --full-tree --strict and resolve every fail-closed publication
  finding through scripts/public-check
- [x] T057 Execute every baseline and negative scenario from
  specs/001-local-inference-testbench/quickstart.md in a clean temporary clone
- [x] T058 Review LICENSE, THIRD_PARTY_NOTICES.md, and redistributed .specify/ content for complete
  attribution
- [x] T059 Reconcile task completion markers against the delivered files and validation evidence in
  specs/001-local-inference-testbench/tasks.md

---

## Dependencies and Execution Order

### Phase dependencies

- Phase 1 has no dependency.
- Phase 2 depends on package and contract setup in Phase 1 and blocks all stories.
- User Story 1 depends on Phase 2 and is the local-only MVP.
- User Story 2 depends on Phase 2 and may proceed in parallel with User Story 1, but it blocks public
  release.
- User Story 3 depends on User Story 1 record production; its contract tests can begin after Phase 2.
- User Story 4 depends only on Phase 2 and may proceed in parallel with Stories 1–3.
- Phase 7 depends on every story intended for the release.

### User-story graph

    Setup -> Foundation -> US1 -> US3
                        \-> US2
                        \-> US4

US2 and US4 are implementation-independent of US1. US3 consumes the minimized record created by US1
but remains independently testable with a synthetic record fixture.

### Within each story

1. Add the failing tests listed for that story.
2. Implement the smallest behavior that satisfies the contracts.
3. Run the story's independent test.
4. Run existing tests to preserve earlier stories.
5. Check off tasks only after the named evidence passes.

## Parallel Opportunities

- T002–T007 can be divided by file after T001 establishes package metadata.
- T008 and T009 can be written in parallel before T010–T014.
- T015–T018 target separable client, scoring, runner, and privacy expectations.
- After Phase 2, User Stories 1, 2, and 4 can be staffed in parallel.
- Within US2, hook, workflow, dependency-update, and documentation tasks can proceed alongside scanner
  implementation.
- Within US3, the three test tasks and interpretation documentation can proceed independently.

## Parallel Example: User Story 1

    Task T015: client envelope and response-normalization tests in tests/test_client.py
    Task T016: independent scoring tests in tests/test_scoring.py
    Task T017: sequential profile and safety-boundary tests in tests/test_runner.py

After those tests define behavior:

    Task T019: client request/response implementation
    Task T020: suite/profile definitions
    Task T021: scoring implementation

## Parallel Example: User Story 2

    Task T032: hook installer
    Task T033: Git hook entry points
    Task T034: continuous-integration workflow
    Task T036: security and privacy documentation

These can proceed while T030 and T031 implement the shared scanner and wrapper, then converge in the
independent publication-gate test.

## Implementation Strategy

### Local MVP

1. Complete Setup and Foundation.
2. Complete User Story 1.
3. Stop and validate check, smoke, standard, result minimization, and no state mutation.

### Public-release minimum

1. Complete the local MVP.
2. Complete User Story 2.
3. Pass local hooks, the full publication gate, CI, secret scanning, and push protection.
4. Publish only after a second tracked-content review.

### Incremental completion

1. Add User Story 3 for reproducible interpretation.
2. Add User Story 4 as documentation-only optional scope.
3. Run Phase 7 release gates and reconcile this checklist.

## Task Summary

- Total tasks: 78
- Completed: 77
- Intentionally open: 1 (hosted Stage 3 deployment verification)
- Setup: 7
- Foundation: 7
- User Story 1: 11
- User Story 2: 13
- User Story 3: 8
- User Story 4: 5
- Polish and release gates: 8
- Post-release Stage 1 adversarial hardening: 5
- Post-release Stage 2 scale hardening: 6
- Post-release Stage 3 public evidence schema: 5
- Exact-bound single-command measurement integration: 3
- Suggested MVP: Phases 1–3
- Suggested public-release minimum: Phases 1–4

Release validation covers duplicate-ID/version cases, unresolved endpoint resolution, oversized
client responses, force-added ignored artifacts, tracked environment files, runtime identity
mismatch, and baseline import without experiment packages. Hosted secret scanning and push
protection were verified before the first push, and the full workflow passed from a clean temporary
clone using the deterministic local stub coverage.

---

## Phase 8: Post-release Stage 1 adversarial hardening

**Purpose**: Narrow reviewer-visible model labels and state the public evidence boundary honestly
without changing what the benchmark measures or changing hardware descriptor behavior.

- [x] T060 Amend `spec.md`, `plan.md`, and `data-model.md` with publication-only ASCII model
  descriptor limits (`display_name` 160, `source` 240, `precision` 80), descriptor-grade rejection,
  reviewer-injection resistance, and integrity-not-provenance framing
- [x] T061 Add shared behavioral Python/browser fixtures for length limits, URLs, emails, network values,
  UUID/serial labels, reviewer-directed instructions, bidi controls, and non-ASCII homoglyphs while
  proving existing hardware descriptors remain accepted in `tests/`
- [x] T062 Implement the same closed model-label validation in the Python submission path and browser
  validator, encode the portable ASCII and field-length boundaries in the current leaderboard JSON
  contracts, and retain Python/browser authority for descriptor and reviewer-pattern rejection,
  without changing schema version or local manifest/run-record acceptance
- [x] T063 State in `README.md` that image and video generation are out of scope because their
  similarity/preference scoring conflicts with the judge-free rule design and uses a different
  runtime stack; record that a separate bench may reuse this pipeline
- [x] T064 Re-run the complete cross-platform unit, parity, deterministic-build, privacy, history,
  secret, and static-site safety gates before merging the hardening increment

---

## Phase 9: Post-release Stage 2 leaderboard scale hardening

**Purpose**: Remove the aggregate publication time bomb without changing benchmark measurement,
submission schema `1.0`, accepted evidence, or the exact benchmark pull-request boundary.

- [x] T065 Amend both feature specifications, plans, data models, task lists, and `docs/guide.md` with
  the bounded hybrid committed transport, compact exact-key index, temporary Pages-only shards,
  append-only retention, deterministic UTF-8 byte pagination, and synthesized same-origin fetch
  boundary
- [x] T066 Add synthetic over-cap, exact-byte split, corruption, exact-coverage, deterministic-output,
  fixed-path, per-file-cap, and unchanged benchmark-PR-boundary regression tests
- [x] T067 Implement deterministic index and shard generation so valid aggregate growth paginates
  instead of failing while malformed, duplicate, inconsistent, and individually oversized inputs
  continue to fail closed
- [x] T068 Update Pages to byte-check either canonical committed form before always generating the
  exact-key index and uncommitted shards in a temporary site artifact, and update the browser to load
  one-based contiguous shard IDs padded to at least six digits on demand without accepting arbitrary
  paths or URLs
- [x] T069 Run the complete local cross-platform unit, deterministic build, browser safety,
  publication-boundary, privacy, history, and secret-scanning gates
- [x] T070 Verify required hosted checks, the trusted benchmark boundary, deployed on-demand shard
  behavior, full accepted-record coverage, and absence of committed shards after protected merge

---

## Phase 10: Post-release Stage 3 public evidence schema

**Purpose**: Coordinate public schema `1.1` and structural seams without changing the five measured
cases or adding capability views.

- [x] T071 Amend feature specifications, plans, data models, task lists, operator documentation,
  contribution guidance, and the benchmark PR template with the execution/measurement validity
  split, owner-only evidence sidecar, month-resolution period, legacy policy, suite taxonomy, facet
  seam, configuration dimensions, and unused graduation threshold
- [x] T072 Replace literal suite/profile assumptions with a `(profile, suite_version)` registry; add
  required capability/modality metadata and denominator-excluded, three-sentinel `not_applicable`
  behavior while preserving current standard behavior and requiring one scored public case
- [x] T073 Bump new public submissions and projected rows to schema `1.1`, require categorical
  measurement evidence bound by exact private source run ID with 1–1000 model rows and `YYYY-MM`,
  strip the binding from public output, support optional determinism, retain accepted `1.0` bytes,
  and reject newly proposed `1.0` submissions
- [x] T074 Mirror every schema rule in Python and browser validation—including strict raw JSON,
  fatal UTF-8/BOM rejection for candidate and fetched leaderboard bytes, duplicate-member rejection,
  canonical digest recomputation, and visible-ASCII/reviewer-neutral public descriptors—and add
  shared parity, source-run binding/bounds, migration, suite-registry, `not_applicable`, month,
  categorical-validity, punctuation-boundary, and unchanged-monolith regressions
- [ ] T075 Run the complete cross-platform, deterministic-build, browser-safety, privacy, history,
  secret, exact-boundary, and hosted Pages validation before merging Stage 3

---

## Phase 11: Exact-bound single-command measurement integration

**Purpose**: Remove the run-ID rewrite race from scripted save/PR while retaining real pre/post
categorical evidence and preserving the private report on optional sampler failure.

- [x] T076 Add regression tests for validated preallocated run identity, pre/run/post ordering,
  exact adapter binding, in-flight output bounds, executable safety, credential-free invocation,
  approved-byte snapshot execution, POSIX process-tree cleanup, Windows fail-closed behavior,
  atomic owner-only retention, and private-report preservation in `tests/test_runner.py`,
  `tests/test_measurement.py`, and `tests/test_cli.py`
- [x] T077 Implement the POSIX synchronous adapter bridge, approved-byte snapshot, bounded child
  process tree, exact-bound evidence construction, atomic local retention, Windows two-step
  fallback, and same-object export handoff in
  `src/local_inference_test_bench/measurement.py`, `runner.py`, and `cli.py`
- [x] T078 Document the single-command sampler and separate static-sidecar flow across the feature
  specifications, CLI contract, README, and operator guidance
