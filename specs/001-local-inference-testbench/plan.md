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
        ├── cli.py
        ├── client.py
        ├── models.py
        ├── runner.py
        ├── scoring.py
        ├── safety.py
        └── reporting.py
    tests/
    ├── test_client.py
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
