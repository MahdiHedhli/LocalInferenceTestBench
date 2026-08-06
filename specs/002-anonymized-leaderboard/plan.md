# Implementation plan: Anonymized benchmark leaderboard

**Branch**: `002-anonymized-leaderboard` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-anonymized-leaderboard/spec.md`

## Summary

Add a standard-library export and validation path that combines an eligible benchmark report with a
closed public hardware descriptor, then reduces each result to a single-model public record. Accepted
records live in the repository and produce a bounded deterministic committed leaderboard transport
file: the existing monolith while it fits, then a constant-shape index. After byte-checking that
file, the Pages job always generates the constant-shape index plus bounded deterministic shards in
its temporary static-site artifact. A small static site reads the index, loads shard pages on demand,
presents the leaderboard with hardware context, and checks prepared submission files locally in the
browser before directing contributors to a reviewed pull request. GitHub Actions validates records
and deploys the site from `main`.

## Technical context

**Language/Version**: Python 3.11 or newer; static HTML, CSS, and browser JavaScript

**Primary Dependencies**: Python and browser standard libraries; GitHub Actions and GitHub Pages for
deployment

**Storage**: Ignored local hardware descriptors, append-only version-controlled minimized JSON
submissions, a bounded generated leaderboard transport file, and disposable index/shard files
created only in the temporary Pages artifact

**Testing**: Standard-library unit tests, deterministic temporary-directory fixtures, JSON contract
parsing, static-site source checks, publication scanning, and deployed-site smoke checks

**Target Platform**: Current desktop and mobile browsers; Python on Linux, macOS, and Windows

**Project Type**: Existing Python command-line package plus a static GitHub Pages site

**Performance Goals**: Keep each public payload within an explicit byte cap with no build framework;
validate and rank every accepted record, load the bounded index first, and fetch shard pages only as
needed

**Constraints**: No direct browser writes, backend, embedded token, third-party asset, analytics,
raw report upload, general machine inventory, contributor field, or speed-based quality rank

**Scale/Scope**: One retained record per model run; an append-only corpus that may exceed one browser
payload; deterministic byte-bounded pagination of the global rank sequence; advanced aggregation and
hardware-normalized performance ranking remain out of scope

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
- Treat all public hardware/runtime labels, model labels, and artifact identity values as
  reviewer-visible descriptors, not arbitrary text: require visible ASCII and reject
  descriptor-grade UUID, serial/inventory-label, network, URL, private-host, and email shapes plus
  automated-reviewer/instruction-injection shapes in both implementations. Keep the model
  display/source/precision limits at 160/240/80.
- Rank semantic results first and exact-format results second. Equal scores share a rank. Hardware and
  runtime context make speed interpretable, but performance still does not change the quality rank.
- Round retained aggregate performance values to reduce unnecessary precision. Do not retain source
  timestamps, local model IDs, manifest digests, or per-case performance traces.
- Derive displayed score percentages with exact integer-ratio, half-up rounding to one decimal in
  both Python and JavaScript so future suite lengths cannot create language-specific tie behavior.
- Let the browser inspect only minimized JSON. It uses text-only rendering and does not transmit the
  selected file.
- Build and deploy with pinned GitHub-authored actions and narrow job permissions.
- Keep the submission contract at `1.0` for this scale-only increment. Submission retention,
  canonical identifiers, and validation semantics do not change.
- Preserve the benchmark pull-request boundary: one added digest-named submission blob and the one
  modified generated `site/data/leaderboard.json` transport file. Shards are deployment outputs,
  never version-controlled review inputs.
- Treat the committed leaderboard file as a bounded deterministic transport artifact. Both
  pull-request CI and Pages byte-compare it with an independent rebuild before any shard generation.
- Generate shards only after that byte check, in a temporary Pages artifact containing allowlisted
  static site files rather than a copy of the retained source-submission corpus. Derive shards from
  the already validated accepted records and discard them with the build workspace.
- Retain hard byte limits on every submission, the index, and each shard, but remove any aggregate
  corpus-size failure. Volume triggers pagination; corrupt, duplicated, inconsistent, or
  privacy-unsafe input still fails.
- Order every row by the existing deterministic global rank and greedily paginate it by exact
  rendered UTF-8 JSON bytes so operating system and character-count differences cannot change
  boundaries.
- Keep the sharded index constant-size with exactly `index_version`, `schema_version`, `entry_count`,
  and `shard_count`. Browser code derives one-based contiguous shard IDs padded to at least six
  digits, synthesizes `data/leaderboard-NNNNNN.json`, and never follows a data-provided path or URL.
- Retain every accepted submission in `site/data/submissions/`, addressable by content digest. The
  index and deployment shards are rebuildable publication transport, not evidence retention.
- Preserve the current six-entry legacy monolith byte-for-byte in the mixed code rollout. Readers and
  builders accept both the bounded legacy shape and the sharded index; a build switches the committed
  file to the index when the legacy cap would be crossed by an otherwise valid exact two-file
  append-only benchmark submission. Leaderboard-only early activation is unsupported. Pages always
  generates the index and shards in its temporary artifact.

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
        |-- leaderboard.json       # bounded legacy monolith or deterministic index
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

    temporary Pages artifact only/
    `-- data/
        `-- generated fixed-id shard pages

The exact implementation names remain subordinate to the contracts and acceptance behavior.

## Delivery and validation

1. Publish the submission and dataset contracts before treating export behavior as stable.
2. Test privacy removal, eligibility, canonical identifiers, closed fields, duplicate rejection,
   deterministic ranking, and dense ties.
3. Add the command-line export and repository dataset builder.
4. Add the static site, browser-only inspection screen, and plain-language submission guide.
5. Run unit tests, JSON parsing, static-site checks, full-tree and history privacy scans, and Gitleaks.
6. Enable GitHub Pages with Actions as the source, push the validated change, and verify the live URL.
7. Replace the aggregate dataset transport with a bounded committed index and temporary Pages
   shards without changing submission schema `1.0` or the exact benchmark pull-request boundary.
8. Cross the former aggregate cap with a synthetic corpus, force an exact-byte page split, and
   prove byte-identical output, complete retention, bounded payloads, load-on-demand behavior, and
   rejection of corrupt records and arbitrary shard targets.
9. Exercise the same candidate corpus through Python and browser validators, including strict raw
   JSON duplicate-member rejection and canonical digest recomputation in the local Pages preview;
   apply fatal UTF-8/BOM rejection and the same strict parser to every fetched leaderboard transport.

## Post-design constitution check

The planned contracts contain public hardware product and runtime fields but no host identity,
network data, device identifier, endpoint, timestamp, contributor, or free-form note. Ranking is based
on common task outcomes. The browser does not receive a repository token and does not upload selected
files. Deployment reads only accepted `main` content. These choices preserve all five constitutional
principles.

## Post-release hardening sequence

Stage 1 tightens the three model descriptor labels and corrects public framing without changing what
is measured or bumping the schema version. Stage 3 extends that publication-only rule to the other
public descriptor and artifact-identity values after parity fuzzing found cross-engine Unicode and
punctuation-boundary bypasses. Python and browser validators remain parallel implementations and
receive the same adversarial fixture corpus.

The non-authoritative plausibility annotation and config-cell corroboration count remain later,
explicitly pending work. They will surface caution and repetition without dropping a record or
claiming that distinct content hashes prove independent operators.

## Post-release Stage 2 scale hardening

Stage 2 changes publication transport only. Accepted submissions keep schema `1.0`, remain
append-only, and continue to be reviewed through the exact two-file benchmark pull-request boundary.
Once sharding is active, the generated file committed beside them is a constant-shape bounded
deterministic index rather than an ever-growing browser payload. The mixed code rollout leaves the
current bounded legacy monolith byte-identical and supports both forms; crossing its cap selects the
index automatically through the same exact two-file append-only benchmark boundary. A
leaderboard-only early migration is unsupported.

Pull-request CI continues to rebuild and byte-compare the canonical committed transport file. The
Pages workflow first performs the same check against trusted `main`, then copies only allowlisted
static site chrome into a temporary artifact directory and always generates the exact-key index plus one-based shard IDs
padded to at least six digits. The shard files are never committed. The browser loads the index
first, validates its counts, derives those contiguous IDs, synthesizes
`data/leaderboard-NNNNNN.json`, and fetches pages on demand.

Individual submission, index, and shard byte caps remain fail-closed. The removed failure is only the
aggregate corpus cap: valid growth adds deterministic pages split by exact rendered UTF-8 JSON byte
size. Corrupt records, duplicate IDs, inconsistent counts, missing records, oversized individual
files, and unsafe content still fail publication. All accepted source submissions remain retained
and digest-addressable; pagination never prunes them.

## Post-release Stage 3 schema `1.1` and expansion seams

Stage 3 changes the public evidence contract, not what the benchmark measures. New submissions and
projected rows use schema `1.1`; the sharded transport keeps independent `index_version: "1.0"`.
The current six-entry all-legacy monolith remains byte-identical until the first accepted `1.1`
submission. Every accepted `1.0` source file remains unchanged and digest-addressable, while new
benchmark pull requests must be regenerated as `1.1`. A mixed projection marks historical rows
`legacy_unreported` and leaves unmeasured condition and month fields absent.

Preparation continues to require a `valid` execution report and model result. It additionally reads
an ignored, owner-only measurement-evidence sidecar containing only closed pre/post threshold
outcomes and categories, a top-level `source_run_id` exact-matched to the report's `run_id`, and a
bounded 1–1000 unique model list. The exporter fails closed if that evidence is absent, stale,
oversized, or inconsistent and never maps execution validity to `clean`. The run binding stays local.
The public contract records `clean`, `nonquiescent`, or `degraded_midrun`, a UTC `YYYY-MM`
measurement period, and optional 3–5-run determinism aggregates. No run ID, raw pressure, thermal,
load, swap, process, inventory, or event-time value crosses the boundary.

A shared suite registry keyed by `(profile, suite_version)` supplies ordered case metadata and suite
length. The sole public entry remains `standard` / `1.0`. Each current case gains a task-capability
tag and the `text` modality; `not_applicable` is excluded from denominators and distinct from
`not_scored`. Inapplicable cases use the sentinel consistently in outcome, route, and termination;
the complete public candidate still needs one scored case. These are collection and validation seams
only—there are no new cases, capability scores, pages, or columns.

The builder accepts a versioned facet selector but ships only `all-cases-text`. Configuration
dimensions are a named version `1.0` structure reused by later filtering and config-cell collapse:
hardware, model identity including revision or digest, precision, runtime name/version/backend,
runtime configuration, and settings. The future view-graduation policy is also version `1.0`, with
25 entries across five model families; nothing reads it yet. Python and browser validation continue
as parallel closed-schema implementations exercised by shared fixtures. Since minimized accepted
records do not retain per-case timing or usage, any strict subset facet emits unavailable latency
and throughput plus zero usage coverage; it never presents the retained full-suite aggregate as a
facet-specific performance result. Such a subset uses the versioned logical `1.1` projection even
when all source records are legacy; only the shipped all-legacy full-suite projection retains the
byte-identical `1.0` transport.
