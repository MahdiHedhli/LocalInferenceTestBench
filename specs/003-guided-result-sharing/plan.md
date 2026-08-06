# Implementation plan: Guided result sharing

**Branch**: `003-guided-result-sharing` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

## Summary

Extend `litb run` with a safe-default post-run decision, idempotent local candidate saving, and an
optional GitHub CLI integration that builds a two-file submission change in isolation and opens a
reviewed pull request. Keep the standard-library runner and existing JSON contracts unchanged.

## Technical context

**Language/Version**: Python 3.11 or newer

**Dependencies**: Python standard library; an operator-supplied local categorical sampler for
single-command export; optional GitHub CLI and Gitleaks for public PR publication

**Storage**: Existing ignored reports, public hardware descriptors, categorical measurement-evidence
sidecars, and candidate directory

**Testing**: Standard-library unit tests, mocked subprocess/API boundaries, Git diff fixtures,
deterministic builder checks, privacy scanner, Gitleaks, and hosted matrix CI

**Constraints**: No direct `main` write, token handling, shell interpolation, current-checkout
mutation, raw report upload, arbitrary repository target, unbounded adapter output, inferred clean
state, or weakening of the existing contract

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
8. For single-command non-interactive sharing, preallocate the ordinary UUIDv4/UTC run identity and
   invoke one explicitly selected adapter synchronously before the run and, after a successful pre
   sample and successful benchmark return, after the complete run. Require
   exact run/model/phase echo, accept only the existing closed categorical sample, retain the bound
   sidecar atomically, and pass the same in-memory evidence to preparation.

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

The adapter bridge is POSIX-local-only and standard-library-only. It caps the selected executable at
16 MiB, executes only a private non-writable snapshot of approved bytes without a shell, rejects
group/world-writable sources, rechecks source identity/content at launch, strips credential
environment keys, discards stderr, caps stdout while
the child runs, and delegates the isolated process tree to a dedicated standard-library supervisor.
That supervisor signals the adapter group before reaping its leader, never signals a reaped numeric
PGID, and observes leader exit without consuming its wait status (`waitid`, or `kqueue` on older
supported macOS Python). On Linux it fails closed unless it can adopt and boundedly reap descendants
as a child subreaper. The sampler must remain synchronous and inside its inherited session/process group. The
snapshot directory must be owner-only and its backing filesystem writable and executable; `TMPDIR`
can select an owner-controlled non-repository location if the default is `noexec`. A post sample is attempted only after the pre sample and complete
benchmark return successfully. A sampler failure is remembered while the benchmark continues; the private report is written before export fails. Static exact-bound
sidecars remain supported by the separate two-step `prepare-submission` command.
Windows fails the single-command option closed and uses that two-step path.

## Project structure

    src/local_inference_test_bench/
    |-- _measurement_supervisor.py
    |-- cli.py
    |-- measurement.py
    |-- publishing.py
    `-- submissions.py
    scripts/
    `-- validate_benchmark_change.py
    tests/
    |-- test_cli.py
    |-- test_measurement.py
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
