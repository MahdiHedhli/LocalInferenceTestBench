# Implementation plan: Guided result sharing

**Branch**: `003-guided-result-sharing` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

## Summary

Extend `litb run` with a safe-default post-run decision, idempotent local candidate saving, and an
optional GitHub CLI integration that builds a two-file submission change in isolation and opens a
reviewed pull request. Keep the standard-library runner and existing JSON contracts unchanged.

## Technical context

**Language/Version**: Python 3.11 or newer

**Dependencies**: Python standard library; optional GitHub CLI and Gitleaks for public PR publication

**Storage**: Existing ignored reports, public hardware descriptors, categorical measurement-evidence
sidecars, and candidate directory

**Testing**: Standard-library unit tests, mocked subprocess/API boundaries, Git diff fixtures,
deterministic builder checks, privacy scanner, Gitleaks, and hosted matrix CI

**Constraints**: No direct `main` write, token handling, shell interpolation, current-checkout
mutation, raw report upload, arbitrary repository target, or weakening of the existing contract

## Constitution check

| Principle | Design evidence | Result |
|-----------|-----------------|--------|
| Privacy by Construction | Existing minimizer is reused; full preview and linkage disclosure precede literal confirmation; strict local scans occur before mutation. | PASS |
| Hardware and Runtime Neutrality | The existing closed descriptor remains the only hardware input. | PASS |
| Reproducible Evidence | Candidate digest, exact base SHA, deterministic dataset, and hosted review remain intact. | PASS |
| Safe, Bounded Evaluation | Report is saved first; publication handles only bounded public JSON in a temporary clone. | PASS |
| Spec-Anchored Quality | CLI behavior, failure modes, payload boundary, CI guard, and tests trace to FR-001–FR-016. | PASS |

## Design

1. Add `--submission {ask,none,save,pr}`, `--hardware`, `--submission-model`,
   `--submission-dir`, and `--confirm-public` to `litb run`.
2. Persist the private report, then prompt only when the result is eligible and the terminal is
   interactive.
3. Reuse `prepare_submissions`; add canonical byte rendering and an idempotent secure save wrapper.
4. Add an optional `publishing.py` adapter that invokes `gh`, Git, Python checks, and Gitleaks only by
   fixed argv lists with suppressed stderr.
5. Clone only fixed canonical upstream into a private temporary directory, add one candidate,
   regenerate the dataset, stage exact paths, and run all local gates.
6. Use GitHub's Git-data and pull-request APIs through authenticated `gh api`; create or verify a fork
   only after local validation and confirmation.
7. Add a CI change-boundary validator that recognizes a benchmark-data PR and rejects every path or
   operation outside the two-file append-only shape.

## Stage 3 schema `1.1` coordination

Candidate preparation now also reads one ignored, owner-only `measurement-evidence` JSON sidecar.
The file carries one `source_run_id` exact-matched to the source report's `run_id`, 1–1000 unique
closed per-model pre/post threshold categories, and optional aggregate determinism; it never enters
Git staging, subprocess environment, GitHub payloads, or PR text. The source report must still be
execution-valid, and missing, stale-run, oversized, or inconsistent measurement evidence fails closed
rather than being inferred as clean. The private run binding is stripped from candidate bytes.

New candidates are schema `1.1`, include UTC month-resolution measurement period, and carry suite
registry capability/modality metadata plus denominator-safe `not_applicable`. Guided sharing does
not add cases, suites, scores, views, or ranking behavior. Retained schema `1.0` repository evidence
is not rewritten, but an open or saved `1.0` candidate must be regenerated before a new PR. The
fixed repository target, isolated clone, literal confirmation, two-file diff, deterministic digest,
and all privacy/secret gates remain unchanged.

## Project structure

    src/local_inference_test_bench/
    |-- cli.py
    |-- publishing.py
    `-- submissions.py
    scripts/
    `-- validate_benchmark_change.py
    tests/
    |-- test_cli.py
    |-- test_publishing.py
    `-- test_benchmark_change.py
    specs/003-guided-result-sharing/
    |-- spec.md
    |-- plan.md
    |-- research.md
    |-- data-model.md
    |-- quickstart.md
    |-- contracts/cli.md
    |-- checklists/requirements.md
    `-- tasks.md

## Validation

Run the full unit suite, deterministic leaderboard check, JavaScript and JSON parsing, Python compile
checks, `git diff --check`, strict full-tree/history publication gate, and Gitleaks. Exercise the
isolated clone/preparation path with synthetic public data without creating a branch or PR. Review
all subprocess arguments and GitHub payloads for private-input exclusion.
