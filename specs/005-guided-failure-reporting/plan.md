# Implementation plan: Guided benchmark failure reporting

**Branch**: `feat/guided-failure-reporting` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

## Summary

Add a separate, optional failure-reporting module and a narrow `litb run` integration. Detect only
structured actionable execution categories, build a closed minimized draft, preview every field,
and open a hardcoded GitHub issue composer only after interactive consent. Preserve every existing
benchmark, submission, publication, and workflow boundary.

## Technical context

- **Language**: Python 3.11+
- **Dependencies**: Python standard library only
- **Storage**: none; drafts exist in memory only
- **External boundary**: one user-confirmed `webbrowser` handoff to a fixed HTTPS URL
- **Testing**: unit tests with mocked browser/input/platform/descriptor boundaries plus full gates

## Constitution check

| Principle | Design evidence | Result |
|-----------|-----------------|--------|
| Privacy by Construction | Closed allowlist; complete preview; no raw data, IDs, logs, or exception text. | PASS |
| Hardware and Runtime Neutrality | Coarse hardware enums; optional validated public runtime triple. | PASS |
| Reproducible Evidence | Versioned draft and deterministic category priority. | PASS |
| Safe, Bounded Evaluation | No model/tool/lifecycle action; bounded URL; original status preserved. | PASS |
| Spec-Anchored Quality | Acceptance scenarios, contract, and tests precede implementation. | PASS |

## Design

1. Add `failure_reporting.py` with closed enums, report-category detection, platform reduction,
   validated public-descriptor projection, draft validation, deterministic rendering, and URL build.
2. Give `RunnerError` optional structured diagnostic phase/category fields for preflight failures;
   retain existing human-readable messages only for the private console path.
3. Add `--failure-report {ask,none}` to `litb run`. Track unexpected exceptions only across the
   narrow `runner.run` boundary and reduce them to `internal_harness_error`.
4. After a returned report is securely persisted, detect eligible case terminations and offer the
   same flow. Do not inspect semantic or content-bearing fields.
5. In the interactive offer, load the existing public descriptor best-effort, print the complete JSON
   and disclosure, require normalized single-letter ASCII `y` consent, then call
   `webbrowser.open_new_tab` once.
6. Treat a false result or exception as a categorical handoff failure and return the original run
   status. Never retry or auto-submit.

## Project structure

    src/local_inference_test_bench/failure_reporting.py
    src/local_inference_test_bench/cli.py
    src/local_inference_test_bench/runner.py
    tests/test_failure_reporting.py
    tests/test_cli.py
    tests/test_runner.py
    specs/005-guided-failure-reporting/

## Validation

Run the full unittest suite, deterministic leaderboard check, JavaScript syntax, Python compile,
`git diff --check`, strict full-tree/history publication scan, hooks, and Gitleaks. Inspect the
decoded issue query and confirm no browser call is possible before exact consent.
