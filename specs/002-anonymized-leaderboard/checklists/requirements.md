# Requirements checklist: Anonymized benchmark leaderboard

**Purpose**: Check the written requirements before implementation and public release.

**Created**: 2026-08-05

**Feature**: [spec.md](../spec.md)

## Scope and user flow

- [x] CHK001 Does the specification cover visitors, contributors, and maintainers with independently
  testable scenarios? [Completeness, User scenarios]
- [x] CHK002 Does the first-page requirement keep the explanation brief and place the leaderboard
  immediately after it? [Clarity, FR-001 to FR-002]
- [x] CHK003 Does the contribution path acknowledge that a static Pages site cannot safely write to
  the repository? [Dependency, FR-017 to FR-018]
- [x] CHK004 Are empty, malformed, unavailable, narrow-screen, and no-JavaScript states covered?
  [Edge cases]

## Hardware and privacy

- [x] CHK005 Are the required CPU, memory, accelerator, execution, and runtime fields explicit?
  [Completeness, FR-023]
- [x] CHK006 Are direct identifiers, unused inventory, raw model content, and correlation fields
  explicitly prohibited? [Completeness, FR-013]
- [x] CHK007 Is the weak fingerprinting risk of hardware plus performance stated without calling the
  record fully anonymous? [Clarity, Assumptions]
- [x] CHK008 Is the local descriptor required to be closed, ignored, owner-readable, and separate
  from the source report? [Safety, FR-024]
- [x] CHK009 Does the browser accept only a prepared minimized record and keep inspection local?
  [Privacy, FR-017]
- [x] CHK010 Is public pull-request and GitHub-account visibility stated? [Privacy, FR-018]

## Eligibility, integrity, and ranking

- [x] CHK011 Are standard profile, validity, preflight, identity, and complete-case requirements
  objective and testable? [Measurability, FR-010 to FR-011]
- [x] CHK012 Is the content-derived identifier distinguished from proof that a run occurred?
  [Integrity, FR-014]
- [x] CHK013 Are exact filenames, duplicate rejection, bounded inputs, and closed contracts required?
  [Integrity, FR-015 to FR-016]
- [x] CHK014 Is dense quality rank defined by semantic then exact-format score? [Clarity, FR-004]
- [x] CHK015 Are latency and throughput excluded from rank and shown only with their hardware and
  runtime context? [Consistency, FR-005]
- [x] CHK016 Are records described as self-reported, reviewed, and not independently reproduced?
  [Accuracy, FR-006]

## Site and publication

- [x] CHK017 Are third-party scripts, fonts, analytics, cookies, and browser credentials excluded?
  [Security, FR-003]
- [x] CHK018 Is text-only rendering required for every untrusted record string? [Security, FR-007]
- [x] CHK019 Are default-branch deployment, pinned actions, and minimal permissions explicit?
  [Security, FR-020]
- [x] CHK020 Do README, site, security, contribution, contracts, and implementation share one data
  boundary and ranking method? [Consistency, FR-022]
- [x] CHK021 Are success criteria measurable with tests, scans, workflow results, and a live-site
  smoke check? [Measurability, Success criteria]
- [x] CHK022 Are all design questions resolved without a remaining clarification marker?
  [Ambiguity]

## Notes

- This checklist reviews requirement quality. Checked items do not replace implementation tests.
- Re-run the checklist when accepted hardware fields, suite eligibility, ranking, or publication
  architecture changes.
