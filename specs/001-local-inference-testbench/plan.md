# Implementation Plan: Hardware-Agnostic Local Inference Test Bench

**Branch**: 001-local-inference-testbench | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from specs/001-local-inference-testbench/spec.md

## Summary

Publish a small, auditable command-line test bench that compares models behind a local
OpenAI-compatible chat-completions endpoint without managing the model lifecycle or persisting raw
model content. The reference implementation uses Python 3.11+ and the standard library, executes
synthetic cases sequentially, validates a versioned manifest, applies an endpoint safety gate before
requests, scores semantic and envelope behavior separately, and writes schema-conforming,
aggregate-safe run records. Repository hooks and continuous integration apply the same privacy and
secret-scanning boundary before content can be published. Specialized context, determinism,
model-template, agent, orchestration, and telemetry work remains optional and explicitly
experimental.

## Technical Context

**Language/Version**: Python 3.11 or newer

**Primary Dependencies**: Python standard library for the runner and scanner; Git and an external
secret scanner for publication gates; GitHub Actions for continuous integration

**Storage**: Version-controlled JSON Schema contracts and example configuration; ignored local JSON
manifests, environment files, and append-only JSON run artifacts

**Testing**: Python standard-library unittest discovery, temporary-directory integration tests, and
script-level publication-gate tests

**Target Platform**: Accelerator-independent Linux, macOS, and Windows hosts with a reachable local
OpenAI-compatible endpoint

**Project Type**: Single Python command-line application with documentation and repository-security
automation

**Performance Goals**: Preserve observed latency and token-usage metrics without imposing
hardware-specific pass thresholds; run one request at a time; keep smoke coverage small enough for a
routine preflight and standard coverage bounded by explicit per-request timeouts

**Constraints**: No model-generated code execution; no model load, unload, or provider changes; no
model-selected tool invocation; no public or unresolved endpoints; no secret values on the command
line; no raw prompts, completions, reasoning, tool arguments, endpoint values, environment values,
or machine identifiers in reports

**Scale/Scope**: One or more manifest entries evaluated sequentially against five baseline case
categories and two standard profiles; larger context, repeated sampling, multi-runtime, dynamic
agent, and telemetry probes are out of the baseline

## Constitution Check

*GATE: Passed before research and passed again after design.*

| Principle | Design evidence | Result |
|-----------|-----------------|--------|
| Privacy by Construction | Strict report schema omits raw-content and deployment fields; endpoint and secret values stay outside manifests and reports; local and CI publication gates use the same deny rules. | PASS |
| Hardware and Runtime Neutrality | The baseline depends on an observable chat-completions contract, not a device, accelerator, model family, operating system, or runtime product. | PASS |
| Reproducible Evidence | Manifest and run-record contracts capture model provenance, suite version, non-secret generation settings, runtime-reported identity, validity, and distinct outcome dimensions. | PASS |
| Safe, Bounded Evaluation | Cases are synthetic and inert, execution is sequential and time-bounded, code is static-only, tools are never invoked, and lifecycle management remains external. | PASS |
| Spec-Anchored Quality | Behavior traces to FR and acceptance-scenario IDs; contract and safety tests are planned before implementation; experiments have a separate documentation surface. | PASS |

The Phase 1 artifacts introduce no constitutional exception. The contracts deliberately disallow
unknown fields so raw-content additions require an explicit specification and governance change.

## Design Decisions

- Use a two-command interface: litb check performs manifest, environment, and endpoint preflight;
  litb run performs the same gate and then executes smoke or standard cases.
- Accept the endpoint as a command option but never persist or echo its value. A collection manifest
  declares one or more public model entries, a suite version, and the optional credential environment
  variable name; its value is read only from the process environment or an explicitly selected
  ignored environment file. The selected smoke or standard profile remains an explicit run option.
- Keep manifest and run-record contracts in JSON Schema draft 2020-12. Runtime validation is
  implemented with the standard library so the baseline does not require a schema package.
- Represent scoring as independent categorical fields for semantic outcome, exact envelope, tool
  routing, termination, and failure class. Performance observations never determine semantic
  correctness.
- Treat a run record as immutable after final write. Comparisons consume records by the sha256 of a
  canonical public manifest projection, public model revision or digest, suite version, and
  generation settings rather than display name. The projection excludes credential variable names
  and local runtime selectors.
- Use the same public-safety scanner in local hooks, the public-check wrapper, tests, and continuous
  integration. Secret-scanner unavailability is a failed gate, not a warning, for publication paths.
- At the leaderboard-export boundary, treat hardware labels, runtime labels, model identity, and
  model labels as compact public descriptors rather than general text. Require visible ASCII, reuse
  descriptor-grade rejection for UUIDs, serial/inventory labels, network values, URLs, private hosts,
  and email addresses, and reject automated-reviewer/instruction-injection shapes. Keep the model
  display/source/precision limits at 160/240/80 and leave local manifest/run-record acceptance
  unchanged.
- Frame every published result as self-reported and unverified. Canonical hashes establish that the
  accepted content has not changed; they do not establish who produced it, that inference occurred,
  or that the measurements are truthful.
- Decouple public evidence retention from browser transport as the accepted corpus grows. Keep
  accepted schema `1.0` submissions append-only and keep the exact two-file benchmark pull-request
  boundary for every schema; commit only the bounded leaderboard transport file, then always generate
  the exact-key index and deterministic byte-bounded shards in a temporary Pages artifact after that
  file's byte check.
- Preserve individual submission, index, and shard caps while eliminating aggregate corpus failure.
  Valid volume selects deterministic byte-sized pages; corrupt evidence still fails. Browser fetch
  targets are synthesized as `data/leaderboard-NNNNNN.json` from one-based contiguous IDs padded to
  at least six digits and remain same-origin.
- Keep the current six-entry legacy monolith byte-identical in the mixed code rollout. Support both
  its closed shape and the constant-shape sharded index; switch deterministically when the monolith
  cap would be crossed by an otherwise valid exact two-file append-only benchmark submission.

The tradeoffs and rejected alternatives are recorded in [research.md](research.md).

## Project Structure

### Documentation for this feature

    specs/001-local-inference-testbench/
    ├── spec.md
    ├── plan.md
    ├── research.md
    ├── data-model.md
    ├── quickstart.md
    ├── contracts/
    │   ├── manifest.schema.json
    │   └── run-record.schema.json
    ├── checklists/
    │   └── requirements.md
    └── tasks.md

### Repository root

    README.md
    CONTRIBUTING.md
    SECURITY.md
    THIRD_PARTY_NOTICES.md
    LICENSE
    .gitignore
    pyproject.toml
    .local/
    └── privacy-denylist.example
    config/
    └── models.example.json
    docs/
    ├── guide.md
    ├── methodology.md
    ├── security-and-privacy.md
    ├── interpreting-results.md
    ├── adapters.md
    ├── sanitization-record.md
    └── experiments/
        └── README.md
    src/
    └── local_inference_test_bench/
        ├── __init__.py
        ├── __main__.py
        ├── _measurement_supervisor.py
        ├── cli.py
        ├── client.py
        ├── measurement.py
        ├── models.py
        ├── runner.py
        ├── scoring.py
        ├── safety.py
        └── reporting.py
    tests/
    ├── test_client.py
    ├── test_measurement.py
    ├── test_models.py
    ├── test_scoring.py
    ├── test_runner.py
    └── test_public_safety.py
    scripts/
    ├── public_safety.py
    ├── public-check
    └── install-hooks
    .githooks/
    ├── pre-commit
    └── pre-push
    .github/
    ├── dependabot.yml
    └── workflows/
        └── public-safety.yml
    artifacts/
    └── .gitkeep

**Structure Decision**: A single installable Python package keeps the reference client, safety gate,
scoring, and reporting inspectable without runtime-specific dependencies. Public process
documentation is separate from the executable package. Spec Kit contracts remain under the feature
directory as the normative interface; the example configuration demonstrates them without embedding
a usable endpoint or credential.

## Delivery and Validation

1. Contract and safety tests define manifest validation, report minimization, endpoint classification,
   scoring separation, and publication findings before the corresponding implementation.
2. User Story 1 is the minimum useful increment: check a manifest and safe endpoint, run synthetic
   smoke cases sequentially, and produce a minimized record.
3. User Story 2 adds the publication boundary and must be complete before the repository is made
   public.
4. User Story 3 completes provenance, comparison interpretation, and validity handling.
5. User Story 4 adds only documentation and guarded extension points; no experiment is needed for the
   baseline quickstart.
6. The final local acceptance command runs unit tests, the full repository privacy scan, contract
   validation, and the external secret scanner before a push.

## Post-Design Constitution Check

The data model, schemas, and quickstart preserve every pre-design gate:

- Manifest fields contain a suite version, public model provenance, runtime selectors, and an optional
  credential variable name, not secret or endpoint values.
- Run records are closed schemas with categorical failure information and no free-form payload fields.
- The quickstart requires a successful check command before run and does not teach model lifecycle
  mutation.
- Baseline profile names are limited to smoke and standard; experiment definitions live under
  docs/experiments and are removable.
- Validation scenarios cover privacy, safety, reproducibility, and failure states without requiring a
  particular accelerator, model family, or runtime product.

No complexity exception is required.

## Post-release Stage 1 hardening

The first adversarial-hardening increment changes no benchmark measurement and introduces no new
schema version. It narrows the three model provenance labels at the public leaderboard boundary in
both validation implementations, encodes portable ASCII and length limits in the current JSON
contracts, adds behavioral parity and injection-shaped regression fixtures, and updates the static
site and repository documentation with the integrity-versus-provenance boundary. Stage 3 extends the
same reviewer-neutral visible-ASCII rule to all public hardware/runtime and artifact-identity labels
after cross-engine Unicode and punctuation-boundary bypasses were found; local manifest/run-record
acceptance remains unchanged.

Image and video generation remain outside this implementation plan. Their similarity- or
preference-based scoring and separate runtime stack belong in a distinct benchmark, although that
project may reuse the submission, privacy, and validity pipeline defined here.

## Post-release Stage 2 scale hardening

The second adversarial-hardening increment changes leaderboard delivery, not benchmark measurement
or the accepted submission contract. Every schema `1.0` submission stays retained by digest. Once
sharding is activated in the source tree, `site/data/leaderboard.json` is a bounded deterministic
index that remains the only generated leaderboard file allowed in a benchmark pull request,
alongside exactly one newly added submission.

The mixed code rollout first leaves the current six-entry legacy monolith byte-identical and accepts
both closed transport forms. The deterministic output switches to the constant-shape index when the
legacy cap would be crossed by an otherwise valid exact two-file append-only benchmark submission.
This stage does not authorize a leaderboard-only early migration.

Pull-request validation continues to rebuild and byte-compare the canonical committed transport
file. On trusted `main`, Pages performs the same check before copying only allowlisted static site
chrome to a temporary artifact directory and always generating the exact-key index and one-based
shard IDs padded to at least six digits. The retained source submissions are not duplicated into the
artifact. Shards are discarded with the build workspace and are never committed. The
browser loads the index first and fetches only synthesized `data/leaderboard-NNNNNN.json` pages on
demand. Every monolith, index, and shard response uses bounded byte reads, fatal UTF-8/BOM rejection,
and the strict duplicate-member-rejecting parser before validation. Until every page is loaded,
search, hardware filters, alternate sorting, and empty-state copy are explicitly scoped to the loaded
rows.

Per-file caps remain on submissions, the index, and each shard. The former aggregate corpus cap is
replaced with exact rendered UTF-8 byte pagination of the deterministic global rank sequence. All
source records must occur exactly once across the generated pages; missing, duplicated, malformed,
inconsistent, or privacy-unsafe records remain publication failures.

## Post-release Stage 3 public evidence contract

Stage 3 coordinates one public submission and projected-row schema bump to `1.1` without changing
the prompts, scoring rules, or five cases currently measured. A suite registry keyed by
`(profile, suite_version)` replaces literal profile and case-count assumptions. The sole public
registry member remains `standard` / `1.0`; smoke stays local. Each public case gains validated
`capability` and `modality` metadata, with every current case tagged `text`, and `not_applicable`
becomes a denominator-excluded outcome distinct from an attempted but unscored case. Its outcome,
route, and termination use one deterministic sentinel, and a whole-suite all-not-applicable result
remains private-only because a public candidate requires at least one scored case.

Execution integrity and measurement conditions stay separate. The ordinary run record continues to
classify transport, preflight, identity, and completion as `valid`, `limited`, or `invalid`.
Submission preparation requires that execution evidence to be fully valid and separately reads a
closed categorical measurement-evidence sidecar. The sidecar is ignored, owner-only, and contains
one `source_run_id` equal to the source Run Record's `run_id`, plus 1–1000 unique per-model pre/post
threshold outcomes and categories with optional aggregate determinism. Its absence, stale run
binding, excess size, or inconsistency blocks export; execution validity is never relabeled as clean
measurement conditions. The binding stays local. The public result derives `clean`,
`nonquiescent`, or `degraded_midrun` and carries the source report's UTC month as `YYYY-MM`, not a
precise timestamp or run ID.

Accepted `1.0` submissions remain unchanged and digest-addressable, while new benchmark pull
requests must use `1.1`. Mixed projections identify retained rows as `legacy_unreported` and leave
their unmeasured period and conditions absent instead of synthesizing them. The current all-legacy
six-entry monolith remains byte-identical until an accepted `1.1` record creates a mixed projection.
The transport envelope remains independently versioned as `index_version: "1.0"`.

Ranking is parameterized through a facet selector, but this increment exposes only
`all-cases-text`; it adds no capability view or score. The reusable configuration-dimension
structure is version `1.0` and names hardware, model identity including revision or digest,
precision, runtime name/version/backend, runtime configuration, and settings. A separate unused
graduation-policy value fixes the future threshold at 25 entries across five model families. Wilson
rank bands, config-cell collapse, corroboration, and plausibility remain the following implementation
stage on top of these seams.

## Exact-bound single-command measurement integration

On POSIX, non-interactive run-and-export preallocates the same UUIDv4/UTC identity later written into the
ordinary Run Record. One explicitly selected local executable receives a closed request immediately
before the complete run and, only when that pre sample succeeds and the complete benchmark returns
successfully, another immediately afterward. A runner exception produces no post sample and no
export. The adapter must echo the schema version, run ID,
phase, and ordered public model IDs and return only one closed categorical sample. The CLI derives
only the contract-defined validity and hard-threshold boolean, validates one row per report model,
atomically retains the ignored owner-only sidecar, and passes that same in-memory object into public
preparation.

The adapter is not a shell extension or a source of raw telemetry for the report. Its size is capped
at 16 MiB; its file mode, identity, and content are checked at launch; and only a private non-writable
snapshot of approved bytes executes. Inherited environment keys are allowlisted without
credentials, stderr is discarded, execution is timed, stdout is capped while the child is running,
and a dedicated standard-library supervisor owns its isolated process tree. The supervisor passes
the bounded standard streams through, observes leader exit without consuming its wait status,
signals the adapter process group before reaping its leader, and never signals that numeric PGID
afterward. Linux uses `waitid`, fails closed unless child-subreaper setup succeeds, then boundedly
reaps adopted descendants. macOS uses `waitid` where available and a `kqueue` `NOTE_EXIT` fallback on
older supported Python, retaining the same kill-before-reap order.
The trusted sampler must remain synchronous and must not daemonize, create another session/process
group, or deliberately escape the boundary. Snapshot storage is owner-only under the system
temporary location; `TMPDIR` may select an owner-controlled, non-repository directory on a writable
filesystem that permits execution when the default is `noexec`. The implementation resolves that
base and rejects ordinary/linked worktrees, Git directories, and bare repositories before writing
approved bytes, and rejects repository-routing `GIT_*` state. Root/current-user ownership and sticky
shared-write rules protect the ancestor chain. Directory-FD creation and writes close the
different-UID checked-path redirection seam; cleanup nonblockingly rechecks exact identity/type immediately before
descriptor-relative removal. Root/same-UID races remain an explicit portable-POSIX limitation. Sampling failure is
remembered while inference completes so the private report is still persisted; candidate creation
then fails closed. A static exact-bound sidecar remains a valid input to the separate two-step
`prepare-submission` flow.
Windows uses that two-step flow until equivalent process-tree containment is available.
