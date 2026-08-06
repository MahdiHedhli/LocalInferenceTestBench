# Implementation plan: Anonymized benchmark leaderboard

**Branch**: `002-anonymized-leaderboard` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-anonymized-leaderboard/spec.md`

## Summary

Add a standard-library export and validation path that combines an eligible benchmark report with a
closed public hardware descriptor, then reduces each result to a single-model public record. Accepted
records live in the repository and produce a deterministic quality-ranked JSON dataset. A small
static site reads that dataset, presents the leaderboard with hardware context, and checks prepared
submission files locally in the browser before directing contributors to a reviewed pull request.
GitHub Actions validates records and deploys the site from `main`.

## Technical context

**Language/Version**: Python 3.11 or newer; static HTML, CSS, and browser JavaScript

**Primary Dependencies**: Python and browser standard libraries; GitHub Actions and GitHub Pages for
deployment

**Storage**: Ignored local hardware descriptors, version-controlled minimized JSON submissions, and
a generated public leaderboard JSON artifact

**Testing**: Standard-library unit tests, deterministic temporary-directory fixtures, JSON contract
parsing, static-site source checks, publication scanning, and deployed-site smoke checks

**Target Platform**: Current desktop and mobile browsers; Python on Linux, macOS, and Windows

**Project Type**: Existing Python command-line package plus a static GitHub Pages site

**Performance Goals**: Keep the site small enough to load as static files with no build framework;
validate and rank the complete accepted dataset in one bounded local process

**Constraints**: No direct browser writes, backend, embedded token, third-party asset, analytics,
raw report upload, general machine inventory, contributor field, or speed-based quality rank

**Scale/Scope**: One record per model run; a simple table suitable for the first community dataset;
advanced aggregation and hardware-normalized performance ranking remain out of scope

## Constitution check

*GATE: Passed before design. Recheck after implementation.*

| Principle | Design evidence | Result |
|-----------|-----------------|--------|
| Privacy by Construction | Export removes local correlation fields and raw content; hardware input is closed, ignored, and owner-readable; submission records reject device and machine identifiers. | PASS |
| Hardware and Runtime Neutrality | The descriptor captures capabilities through generic CPU, memory, accelerator, execution, and runtime fields without assuming a vendor; quality rank uses the common task suite. | PASS |
| Reproducible Evidence | Public artifact provenance, suite, profile, settings, categorical outcomes, and validity eligibility remain in each record. | PASS |
| Safe, Bounded Evaluation | Export reads an existing validated report and performs no inference, code execution, tool call, or system change. | PASS |
| Spec-Anchored Quality | This feature has acceptance scenarios, contracts, tests, a validation guide, and traced implementation tasks. | PASS |

No constitutional exception is required. The leaderboard is the explicit sanitized export path that
the constitution already allows.

## Design decisions

- Keep Pages static. Repository pull requests provide review, history, and the only write path.
- Export from validated standard reports rather than accepting arbitrary manual fields.
- Read hardware and runtime context from a separate ignored descriptor so local run records keep their
  existing minimized contract.
- Use one record per model so entries remain easy to validate, deduplicate, rank, and review.
- Compute the submission identifier from canonical minimized content. The identifier detects content
  changes and exact duplicates but is not proof that a benchmark was run.
- Present every accepted entry as self-reported and unverified in the site chrome and leaderboard
  header. Describe the identifier as content-integrity evidence only, never provenance or
  attestation.
- Treat `model.display_name`, `model.source`, and `model.precision` as reviewer-visible descriptors,
  not arbitrary text: use 160, 240, and 80 ASCII-character limits and reject descriptor-grade UUID,
  serial/inventory-label, network, URL, and email shapes plus explicit automated-reviewer and
  instruction-injection shapes in both implementations. Do not change hardware descriptor behavior.
- Rank semantic results first and exact-format results second. Equal scores share a rank. Hardware and
  runtime context make speed interpretable, but performance still does not change the quality rank.
- Round retained aggregate performance values to reduce unnecessary precision. Do not retain source
  timestamps, local model IDs, manifest digests, or per-case performance traces.
- Let the browser inspect only minimized JSON. It uses text-only rendering and does not transmit the
  selected file.
- Build and deploy with pinned GitHub-authored actions and narrow job permissions.

The tradeoffs and rejected alternatives are recorded in [research.md](research.md).

## Project structure

### Documentation for this feature

    specs/002-anonymized-leaderboard/
    |-- spec.md
    |-- plan.md
    |-- research.md
    |-- data-model.md
    |-- quickstart.md
    |-- contracts/
    |   |-- hardware-descriptor.schema.json
    |   |-- leaderboard-submission.schema.json
    |   `-- leaderboard-dataset.schema.json
    |-- checklists/
    |   `-- requirements.md
    `-- tasks.md

### Repository additions

    docs/
    `-- submitting-benchmarks.md
    site/
    |-- index.html
    |-- styles.css
    |-- app.js
    `-- data/
        |-- leaderboard.json
        `-- submissions/
    src/local_inference_test_bench/
    `-- submissions.py
    scripts/
    `-- build_leaderboard.py
    tests/
    `-- test_submissions.py
    .github/
    |-- PULL_REQUEST_TEMPLATE/
    |   `-- benchmark-submission.md
    `-- workflows/
        `-- pages.yml

The exact implementation names remain subordinate to the contracts and acceptance behavior.

## Delivery and validation

1. Publish the submission and dataset contracts before treating export behavior as stable.
2. Test privacy removal, eligibility, canonical identifiers, closed fields, duplicate rejection,
   deterministic ranking, and dense ties.
3. Add the command-line export and repository dataset builder.
4. Add the static site, browser-only inspection screen, and plain-language submission guide.
5. Run unit tests, JSON parsing, static-site checks, full-tree and history privacy scans, and Gitleaks.
6. Enable GitHub Pages with Actions as the source, push the validated change, and verify the live URL.

## Post-design constitution check

The planned contracts contain public hardware product and runtime fields but no host identity,
network data, device identifier, endpoint, timestamp, contributor, or free-form note. Ranking is based
on common task outcomes. The browser does not receive a repository token and does not upload selected
files. Deployment reads only accepted `main` content. These choices preserve all five constitutional
principles.

## Post-release hardening sequence

Stage 1 tightens the three model descriptor labels and corrects public framing without changing what
is measured or bumping the schema version. Python and browser validators remain parallel
implementations and receive the same adversarial fixture corpus. Existing hardware descriptor
acceptance is a regression boundary, not part of this change.

The non-authoritative plausibility annotation and config-cell corroboration count remain later,
explicitly pending work. They will surface caution and repetition without dropping a record or
claiming that distinct content hashes prove independent operators.
