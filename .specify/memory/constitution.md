<!--
Sync Impact Report
- Version change: template -> 1.0.0
- Adopted principles: Privacy by Construction; Hardware and Runtime Neutrality;
  Reproducible Evidence; Safe, Bounded Evaluation; Spec-Anchored Quality
- Added sections: Publication and Data Boundaries; Development and Review Workflow
- Removed sections: none
- Follow-up TODOs: none
-->
# LocalInferenceTestBench Constitution

## Core Principles

### I. Privacy by Construction (NON-NEGOTIABLE)

Tracked content MUST NOT contain credentials, private network addresses, machine or account names,
absolute home-directory paths, inventory identifiers, serial numbers, private service names, raw
environment values, or other deployment fingerprints. Benchmark artifacts MUST retain aggregate
metrics and categorical outcomes only; prompts, completions, tool arguments, authorization headers,
and raw telemetry payloads MUST NOT be persisted. A local identifier denylist, the repository privacy
scanner, and secret scanning MUST pass before every commit and push.

### II. Hardware and Runtime Neutrality

The standard workflow MUST describe capabilities and observable contracts rather than a particular
accelerator, memory size, operating system, model family, or inference application. Runtime-specific
loading, unloading, telemetry, and tuning belong in optional adapters or experiments. Defaults MUST
be conservative and adjustable, and context tests MUST derive targets from declared model limits
rather than a fixed lab value.

### III. Reproducible Evidence

Every comparison MUST identify the model source, revision or digest when available, quantization or
precision, runtime-reported identity, test-suite version, generation settings, and validity conditions.
Semantic correctness, output-envelope adherence, latency, throughput, and failure classifications
MUST be recorded separately. Results MUST be append-only and attributable to a manifest and suite
version; a friendly model name alone is insufficient evidence.

### IV. Safe, Bounded Evaluation

Baseline cases MUST use synthetic inputs and inert tool definitions. Model-generated code MUST be
parsed or inspected but never executed. The default runner MUST NOT load or unload models, change
providers, modify network policy, contact production systems, or invoke model-selected tools.
Resource-intensive profiles MUST be explicit, sequential, time-bounded, and separable from routine
smoke tests. A benchmark result is evidence, never authorization to deploy a model.

### V. Spec-Anchored Quality

Spec Kit artifacts under `specs/` are the living source of truth for requirements, design decisions,
contracts, validation, and work status. User-facing behavior MUST trace to an acceptance scenario and
automated test. Standard guidance and experimental extensions MUST remain visibly separate. Local
tests, the publication/privacy gate, and continuous integration MUST pass before tracked content is
published.

## Publication and Data Boundaries

- The public baseline includes the general methodology, protocol-neutral data model, runnable
  OpenAI-compatible reference client, safe reporting format, templates, and contribution guidance.
- Named model-template investigations, dynamic agent benchmarks, multi-node orchestration, and
  observability integrations MUST be labeled experimental and MUST NOT become baseline requirements.
- Real benchmark outputs are ignored by default. Publishing a result requires an explicit sanitized
  export and a second privacy-gate pass.
- Local configuration and custom denylist files MUST remain ignored, owner-readable only when they
  contain secrets, and referenced by variable name rather than copied into documentation.
- Third-party scaffold and template notices MUST be retained when their files are redistributed.

## Development and Review Workflow

1. Update the feature specification before changing public behavior or data contracts.
2. Add or amend contract and unit tests before implementation for safety, privacy, and scoring logic.
3. Run the complete local check command, including unit tests, identifier scanning, and secret
   scanning, before commit and push.
4. Review generated reports for data minimization and verify that only synthetic case identifiers and
   aggregate metrics are retained.
5. Record experimental proposals separately, with an authorization boundary and an exit/cleanup
   condition where the experiment can affect systems or networks.

## Governance

This constitution supersedes conflicting project guidance. Amendments require a documented rationale,
an updated Sync Impact Report, and semantic versioning: MAJOR for incompatible governance changes,
MINOR for new or materially expanded principles, and PATCH for clarifications. Every pull request MUST
state whether it changes the public data boundary, runtime contract, or experimental scope. Reviewers
MUST block publication when any privacy or safety gate is unresolved.

**Version**: 1.0.0 | **Ratified**: 2026-08-05 | **Last Amended**: 2026-08-05
