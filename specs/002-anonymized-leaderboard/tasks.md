# Tasks: Anonymized benchmark leaderboard

**Input**: Design documents from `specs/002-anonymized-leaderboard/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Contract, privacy, ranking, browser-safety, and deployment checks are required.

## Phase 1: Public contracts and boundary

- [x] T001 Define the ignored public environment descriptor and sanitized example in
  `config/hardware.example.json` and `.gitignore`
- [x] T002 Publish closed descriptor, submission, and dataset contracts under
  `specs/002-anonymized-leaderboard/contracts/`
- [x] T003 Record the data boundary, ranking choices, rejected alternatives, and contributor flow in
  `data-model.md`, `research.md`, and `quickstart.md`

## Phase 2: Submission preparation and validation

- [x] T004 Add tests for report eligibility, one-model separation, field minimization, canonical
  identifiers, closed shapes, and arithmetic consistency in `tests/test_submissions.py`
- [x] T005 Add tests for owner-only ignored descriptors, non-symlink inputs, execution and memory
  consistency, duplicate accelerators, bounded files, and safe append-only writes
- [x] T006 Implement descriptor and submission validation plus deterministic identifiers in
  `src/local_inference_test_bench/submissions.py`
- [x] T007 Add `litb prepare-submission` with a safe ignored default output in
  `src/local_inference_test_bench/cli.py`

## Phase 3: Dataset and quality rank

- [x] T008 Add tests for exact filenames, duplicate records, dataset size, stable ordering, dense
  ties, and speed-independent rank in `tests/test_submissions.py`
- [x] T009 Implement the bounded deterministic builder in
  `src/local_inference_test_bench/submissions.py` and `scripts/build_leaderboard.py`
- [x] T010 Commit an honest empty generated dataset at `site/data/leaderboard.json`

## Phase 4: Pages and contribution path

- [x] T011 Build a small first page with a brief explanation followed by the leaderboard in
  `site/index.html`, `site/styles.css`, and `site/app.js`
- [x] T012 Render record strings as text, handle empty and error states, and add a browser-only
  prepared-file preview without third-party assets or requests
- [x] T013 Document exact hardware disclosure, weak fingerprinting, public pull-request identity,
  and maintainer review in `README.md`, `docs/submitting-benchmarks.md`, `CONTRIBUTING.md`, and
  `docs/security-and-privacy.md`
- [x] T014 Add the benchmark pull-request template under `.github/PULL_REQUEST_TEMPLATE/`

## Phase 5: Publication controls

- [x] T015 Validate accepted records and generated data in `.github/workflows/public-safety.yml`
- [x] T016 Add a pinned least-privilege Pages workflow at `.github/workflows/pages.yml`
- [x] T017 Update local scanning for the descriptor path and required Pages permission key, with
  regression tests in `tests/test_public_safety.py`
- [x] T018 Update the pinned Dependabot action versions locally and close the resulting remote
  update warnings through the default branch

## Phase 6: Release validation

- [x] T019 Run the complete unit suite, JSON and JavaScript parsing, shell checks, deterministic
  dataset check, publication gate, strict full-tree and history scans, and Gitleaks
- [x] T020 Review the site at desktop and narrow widths, enable GitHub Pages, and verify the live URL
- [x] T021 Verify remote continuous integration, Pages deployment, hosted secret scanning, push
  protection, and Dependabot state on the published commit

## Phase 7: Post-release adversarial hardening

**Sequence**: Complete T022–T026 as Stage 1. Plausibility and corroboration remain pending until the
later aggregation work; they are not part of this no-schema-change increment.

- [x] T022 Amend `spec.md`, `plan.md`, and `data-model.md` with model descriptor limits,
  reviewer-injection resistance, hardware-behavior preservation, and honest
  integrity-not-provenance framing
- [x] T023 Add shared behavioral Python/browser rejection fixtures for the three model labels, including length,
  URL, email, network, UUID/serial, reviewer instruction, bidi, and homoglyph cases, plus unchanged
  hardware descriptor regression fixtures
- [x] T024 Implement matching ASCII-only limits (`display_name` 160, `source` 240, `precision` 80)
  and descriptor/reviewer-injection rejection in `submissions.py` and `site/app.js`; encode portable
  ASCII/length boundaries in the current submission/dataset contracts while retaining
  Python/browser authority for prohibited-pattern checks; do not change schema version
- [x] T025 State in `site/index.html` and `README.md` that all entries are self-reported and
  unverified and hashes prove content integrity rather than provenance or that a run occurred
- [x] T026 Run Python/JavaScript parity, text-only DOM, deterministic build, cross-platform unit,
  privacy, history, and secret-scanning regression gates
- [ ] T027 Add a computed, non-authoritative plausibility caution that never drops or gates an entry
- [ ] T028 Add config-cell corroboration counts with an explicit definition that does not imply
  independent operators merely from distinct accepted content hashes

## Phase 8: Post-release Stage 2 scale hardening

**Sequence**: T029 fixes the transport contract in the specification. T030 precedes T031–T032.
Hosted verification remains open until the merged workflow and live Pages artifact prove the new
boundary. This stage does not change submission schema `1.0` or accepted submission bytes.

- [x] T029 Amend `spec.md`, `plan.md`, `data-model.md`, and `docs/guide.md` with the bounded hybrid
  committed transport, compact exact-key index, temporary Pages-only shards, deterministic
  exact-byte global pagination, load-on-demand path safety, append-only retention, and
  transport-only migration policy
- [x] T030 Add synthetic over-cap and exact-byte split fixtures proving complete deterministic output,
  individual index/shard byte caps, exact record coverage, corruption failure, fixed synthesized
  shard targets, and the unchanged exact two-file benchmark pull-request boundary
- [x] T031 Replace aggregate corpus failure with deterministic byte-sized pagination;
  make `site/data/leaderboard.json` a bounded deterministic index while retaining per-submission,
  per-index, and per-shard caps and schema `1.0` submissions
- [x] T032 Update the static site to load the exact-key index before fetching one-based contiguous
  shard IDs padded to at least six digits on demand, and update Pages to byte-check either canonical
  committed form before always generating the index and uncommitted exact-key shards in a temporary
  artifact directory
- [x] T033 Run the focused scale suite, complete cross-platform unit suite, deterministic index/shard
  rebuilds, JavaScript parsing and path-safety checks, exact PR-boundary regressions, and strict
  publication/privacy gates locally
- [x] T034 Verify required hosted checks, the trusted benchmark boundary, Pages deployment, live
  on-demand shard loading, and absence of committed shard files after the protected merge

## Phase 9: Post-release Stage 3 schema `1.1` and structural seams

**Sequence**: Land the public contract, evidence boundary, and migration together. This phase adds no
new benchmark case, capability score, or capability-specific UI.

- [x] T035 Amend the baseline, leaderboard, and guided-sharing specifications, plans, data models,
  task lists, operator docs, contribution guidance, and benchmark PR template for schema `1.1`, the
  measurement-evidence sidecar, month period, explicit legacy policy, suite taxonomy, facet seam,
  versioned config dimensions, and unused graduation policy
- [x] T036 Add the suite registry, required capability/modality metadata, denominator-excluded
  three-sentinel `not_applicable`, one-scored-public eligibility, and the `all-cases-text` facet while
  keeping standard `1.0` as the only public suite and leaving all current cases unchanged
- [x] T037 Implement lockstep Python/browser schema `1.1` validation, categorical
  measurement conditions bound to an exact private source run ID with 1–1000 model rows, optional
  determinism, `YYYY-MM`, clean-default filtering, stripped run binding, and retained `1.0` mixed
  projections without synthesizing evidence
- [x] T038 Add shared parity, registry-extension, not-applicable, one-scored-public, migration, month,
  source-run evidence bounds, unchanged-monolith, closed-key, fatal UTF-8/BOM, strict-JSON,
  duplicate-member, digest, exact-filename, fetched-transport, public-descriptor punctuation/Unicode,
  and deterministic-build regressions
- [ ] T039 Complete local and hosted cross-platform, Pages, exact-boundary, privacy, history, and
  secret-scanning verification before merging Stage 3
