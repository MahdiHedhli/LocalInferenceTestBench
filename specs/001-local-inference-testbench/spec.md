# Feature Specification: Hardware-Agnostic Local Inference Test Bench

**Feature Branch**: `001-local-inference-testbench`

**Created**: 2026-08-05

**Status**: Implemented

**Input**: Create a public, sanitized, hardware-agnostic version of an established local-model
evaluation process, documented with Spec Kit and protected against secret or lab-identifier leaks.

## User Scenarios & Testing

### User Story 1 - Compare Local Models Safely (Priority: P1)

An operator can evaluate one or more models exposed by a local OpenAI-compatible endpoint with
synthetic structured-output, static-coding, defensive-analysis, and inert tool-contract cases. The
operator gets comparable aggregate results without the harness changing model or machine state.

**Why this priority**: A repeatable, safe comparison is the primary value of the project.

**Independent Test**: Start a stub-compatible endpoint, run the smoke and standard profiles, and
verify the report distinguishes semantic success, format adherence, latency, usage, and termination.

**Acceptance Scenarios**:

1. **Given** a valid local endpoint and manifest, **When** an operator runs the smoke profile,
   **Then** all baseline cases run sequentially and only aggregate-safe artifacts are written.
2. **Given** a public or unresolved endpoint, **When** preflight runs, **Then** execution stops before
   any model request unless an explicitly documented adapter policy permits it.
3. **Given** a semantically correct response in the wrong envelope, **When** it is scored, **Then**
   semantic success and exact-format adherence are reported separately.

---

### User Story 2 - Publish a Sanitized Process (Priority: P2)

A maintainer can share the methodology and repository publicly with confidence that lab identifiers,
environment files, credentials, and raw model data are excluded.

**Why this priority**: The repository is useful only if its public boundary is trustworthy.

**Independent Test**: Seed staged files with representative secret and identifier patterns and verify
that the local publication gate and CI both fail; remove them and verify both pass.

**Acceptance Scenarios**:

1. **Given** a staged private address, home path, credential assignment, or custom denied term,
   **When** the local hook runs, **Then** the commit is rejected with a redacted file-and-line finding.
2. **Given** clean tracked content, **When** local checks and CI run, **Then** unit tests, the privacy
   scanner, and secret scanning pass.
3. **Given** a benchmark run, **When** reports are written, **Then** raw prompts, completions, tool
   arguments, token text, endpoint addresses, and machine names are absent.

---

### User Story 3 - Reproduce and Interpret Results (Priority: P3)

A reviewer can identify what artifact and configuration were tested, understand run validity, and
compare results without assuming that a passing benchmark authorizes deployment.

**Why this priority**: Comparable numbers require provenance and an explicit validity boundary.

**Independent Test**: Validate a report against the published schema and confirm it contains model
provenance, suite/settings identity, case outcomes, and validity notes but no raw content.

**Acceptance Scenarios**:

1. **Given** two model entries with the same display name but different revisions, **When** reports are
   compared, **Then** they remain distinct by source revision or digest.
2. **Given** a truncated response, **When** it is classified, **Then** output-budget exhaustion is not
   mislabeled as context-window exhaustion.
3. **Given** an invalid or disturbed run, **When** it is summarized, **Then** its validity is visible and
   it cannot be marked promotion-ready.

---

### User Story 4 - Add Optional Experiments (Priority: P4)

A contributor can propose model-template, long-context, determinism, dynamic-agent, multi-runtime, or
telemetry experiments without presenting them as the universal baseline.

**Why this priority**: Specialized tests are valuable but should not distort the general guide.

**Independent Test**: Review the documentation navigation and confirm every specialized test is in an
experimental section with prerequisites, risks, and a baseline exclusion note.

**Acceptance Scenarios**:

1. **Given** an experiment tied to a model family or external benchmark, **When** it is documented,
   **Then** it is labeled experimental and the baseline remains runnable without it.
2. **Given** an experiment that can invoke tools or vulnerable targets, **When** it is proposed,
   **Then** authorization, isolation, non-production targeting, and cleanup requirements are explicit.

### Edge Cases

- The endpoint requires no token, uses a loopback address, or resolves to multiple addresses.
- The server omits usage data, finish reasons, tool calls, or model-list metadata.
- A response contains valid content inside a fence or prefaced by prose.
- A reasoning model returns reasoning content but no usable final message.
- The declared context window is smaller than the requested full-profile target.
- A custom local denylist is absent, empty, contains regex metacharacters, or is accidentally staged.
- A generated artifact is force-added despite the ignore rules.
- Secret-scanning software is unavailable locally or a GitHub security setting cannot be enabled.

## Requirements

### Functional Requirements

- **FR-001**: The standard guide MUST be hardware-, operating-system-, model-, and runtime-neutral.
- **FR-002**: The reference runner MUST use an OpenAI-compatible chat-completions interface and MUST
  leave model lifecycle management to the operator or an optional adapter.
- **FR-003**: The runner MUST support smoke and standard profiles; expensive context and repeatability
  probes MUST be explicit experimental options.
- **FR-004**: Baseline cases MUST cover structured output, statically inspected code, defensive
  analysis, read-only tool selection, and an unapproved-change boundary.
- **FR-005**: Model-generated code MUST never be executed by the harness.
- **FR-006**: Reports MUST separate semantic correctness, exact-envelope adherence, performance,
  termination, and run validity.
- **FR-007**: Reports MUST exclude raw prompts, responses, reasoning, tool arguments, credentials,
  endpoint values, environment contents, and machine identifiers.
- **FR-008**: Manifests MUST record public model identity, source, revision or digest, precision or
  quantization, declared context, and non-secret generation settings.
- **FR-009**: The endpoint gate MUST allow loopback and locally resolved private addresses and reject
  public, unresolved, credential-bearing, or query-bearing endpoints before inference.
- **FR-010**: Secrets MUST be accepted only from the process environment or an ignored owner-only env
  file; secret values MUST never be accepted as command-line arguments.
- **FR-011**: A local publication gate MUST scan staged or full content for secret patterns, private
  network identifiers, absolute home paths, machine identifiers, and optional literal custom terms.
- **FR-012**: A version-controlled Git hook MUST invoke the publication gate and secret scanner.
- **FR-013**: CI MUST run tests, the full privacy scan, and secret scanning on pushes and pull requests.
- **FR-014**: GitHub secret scanning and push protection MUST be enabled and verified on the public
  repository when the hosting account supports them.
- **FR-015**: Generated artifacts, local manifests, env files, and custom denylist files MUST be ignored.
- **FR-016**: General guidance and experimental notes MUST be separate, with specialized named work
  omitted from the standard procedure.
- **FR-017**: The repository MUST retain the license notice for copied Spec Kit materials.
- **FR-018**: Tests MUST prove scoring, data minimization, endpoint safety, manifest validation, and
  identifier detection behavior.

### Key Entities

- **Model Manifest**: Public model provenance plus the local runtime selector and test configuration.
- **Benchmark Suite**: Versioned case definitions, profiles, expected semantics, and output contracts.
- **Run Record**: Aggregate-only results for one model/configuration under a declared validity state.
- **Case Result**: Semantic, format, latency, usage, termination, and categorical routing outcomes.
- **Publication Finding**: Redacted file, line, category, and remediation hint from the privacy gate.
- **Experiment Note**: Optional specialized evaluation with prerequisites, risks, and exit criteria.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A new user can copy the example configuration, pass preflight, and run the smoke profile
  against a compatible local endpoint using only the documented quickstart.
- **SC-002**: One hundred percent of committed fixtures and generated reports validate against their
  published schemas and contain no prohibited raw-content fields.
- **SC-003**: The local gate detects all repository test fixtures for private IPv4/CGNAT addresses,
  home paths, credential assignments, MAC addresses, private hostnames, and custom denied terms.
- **SC-004**: Unit and integration tests pass on current Python releases across Linux, macOS, and
  Windows runners without accelerator-specific dependencies.
- **SC-005**: The standard guide contains no lab-specific names, topology, fixed hardware capacity,
  private endpoint, or real benchmark result.
- **SC-006**: Every experimental item is clearly labeled and removable without breaking the baseline
  quickstart, runner, schemas, or tests.
- **SC-007**: The public GitHub repository reports secret scanning and push protection as enabled.

## Assumptions

- Users can expose their local inference runtime through an OpenAI-compatible endpoint or write an
  adapter that satisfies the documented request/response contract.
- Operators load and unload models outside the baseline runner and run large models sequentially.
- Python 3.11 or newer is available; the reference implementation uses only the standard library.
- Real run artifacts remain local by default; publication is a deliberate sanitized export workflow.
- The first public release favors clear, auditable cases over a large benchmark corpus.
