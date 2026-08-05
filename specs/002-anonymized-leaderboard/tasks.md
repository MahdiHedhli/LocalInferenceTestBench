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
