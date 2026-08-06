# Research: Hardware-Agnostic Local Inference Test Bench

**Feature**: [spec.md](spec.md)

**Date**: 2026-08-05

This document resolves the design choices needed by the implementation plan. Decisions are phrased
as portable contracts; none depends on a particular device, model family, inference application, or
private deployment.

## Decision 1: Use a narrow OpenAI-compatible boundary

**Decision**: The baseline client sends non-streaming chat-completions requests and consumes the
small response subset needed for message content, tool-call selection, model identity, usage, and
termination. Runtime lifecycle operations are outside the client contract.

**Rationale**: A small observable interface is supported by many local runtimes while keeping the
test process independent of their model-loading, scheduling, and telemetry APIs. Non-streaming
requests also reduce state and make bounded, sequential execution easier to audit.

**Alternatives considered**:

- Runtime-specific SDKs were rejected because they would make the standard guide product-specific.
- A universal provider abstraction was deferred because the first release needs one transparent
  reference path, not a framework.
- Streaming was deferred because it adds event-order and partial-output behavior without improving
  baseline semantic coverage.

## Decision 2: Separate preflight from execution

**Decision**: The command line exposes check and run. Both validate the manifest, local environment,
and endpoint policy; run cannot send inference requests unless the same preflight succeeds.

**Rationale**: An operator can inspect readiness without spending model time, and there is no
alternate execution path that bypasses the safety gate.

**Alternatives considered**:

- A run-only interface was rejected because dry preflight is valuable for environment and privacy
  troubleshooting.
- A warning-only preflight was rejected because a public or unresolved endpoint is a safety boundary,
  not a tuning suggestion.

## Decision 3: Resolve and classify every endpoint address

**Decision**: Parse the supplied endpoint as an HTTP or HTTPS URL; reject embedded credentials,
queries, and fragments; resolve its host; and allow a request only when every resolved address is in
an explicitly supported local range. Public, mixed, or unresolved results fail closed. The endpoint
may be used in memory but is never written to or echoed in a run record.

**Rationale**: Checking only a hostname string misses public resolution and rebinding-style ambiguity.
Requiring every result to be local avoids selecting a public address from a mixed result set.

**Alternatives considered**:

- String matching names such as localhost was rejected because resolution is the relevant network
  property.
- Allowing any non-global address through a broad library predicate was rejected because reserved and
  documentation ranges are not necessarily operator-local.
- Supporting public hosted endpoints in the baseline was rejected as outside local-inference scope;
  a reviewed adapter policy can define a different boundary.

## Decision 4: Keep the runner dependency-light

**Decision**: The installable reference package uses Python 3.11+ standard-library modules for HTTP,
JSON, address classification, command parsing, timing, dataclasses, and tests.

**Rationale**: A dependency-light implementation is easier to inspect, runs across common operating
systems, and avoids accelerator or runtime coupling. It also reduces the supply-chain surface of the
code that handles local credentials and endpoint policy.

**Alternatives considered**:

- A full HTTP or CLI framework was rejected because the required request and command surface is small.
- Embedding a general JSON Schema validator was rejected for runtime use; the package validates the
  two published contracts directly and contract tests keep that logic aligned.
- Implementing the external secret scanner was rejected; the local scanner complements rather than
  replaces a purpose-built secret detector.

## Decision 5: Version closed JSON contracts

**Decision**: Publish manifest and run-record contracts using JSON Schema draft 2020-12. Objects are
closed by default, schema versions are explicit, and raw-content-shaped fields are absent rather than
optional.

**Rationale**: Closed contracts make the public data boundary reviewable. A future raw prompt,
response, argument, environment, endpoint, or machine field cannot appear accidentally as an unknown
extension.

**Alternatives considered**:

- Free-form JSON was rejected because it cannot prove data minimization or stable comparison.
- CSV was rejected because nested provenance, outcome dimensions, and optional usage are awkward and
  error-prone.
- A database was rejected because append-only local files are sufficient for the initial scale and
  easier to keep ignored.

## Decision 6: Keep model provenance distinct from runtime selection

**Decision**: One manifest file is a versioned collection containing a suite version, an optional
credential environment-variable name, and one or more model entries. Each entry records a public ID,
display name, source, exactly one revision or digest, precision, declared context, a local runtime
selector, and non-secret generation settings. The endpoint and selected profile are run inputs, not
manifest fields. The run record copies public provenance and settings, records only whether the
runtime-reported identity matched, and fingerprints a canonical public manifest projection that
excludes the credential variable name and local runtime selectors.

**Rationale**: Display names alone collapse materially different artifacts. Separating public
provenance from the selector used by a local server supports reproducibility while making the
local-only field easy to exclude from sanitized exports when necessary.

**Alternatives considered**:

- Recording only the runtime model name was rejected because aliases can change.
- Persisting or hashing the runtime-reported identity was rejected because some runtimes expose a
  local path or private alias and a stable fingerprint remains correlatable; the record retains only
  a match boolean.
- Hashing the full manifest was rejected because changes to credential variable names and runtime
  selectors would fingerprint local configuration; only its canonical public projection is hashed.
- Storing the endpoint in the manifest was rejected because it adds no reproducibility value to a
  public comparison and can expose deployment details.

## Decision 7: Score independent dimensions

**Decision**: Each case records independent semantic and exact-envelope booleans, a categorical
combined outcome, a categorical route, reasoning-presence only, termination, latency, optional token
counts, and optional completion throughput. Summary counts and weighted completion throughput are
derived from those fields; no weighted quality score is normative. Read-only tool selection and the
unapproved change boundary are evaluated semantically, without persisting arguments, reasoning, or
free-form failure text.

**Rationale**: A correct answer wrapped in prose is semantically useful but violates a strict machine
contract. Likewise, truncation, timeout, refusal, and context-limit behavior mean different things.
Separate dimensions preserve those distinctions and let users apply their own priorities.

**Alternatives considered**:

- A single pass/fail bit was rejected because it hides actionable differences.
- A universal weighted score was rejected because weights depend on use case.
- Inferring context exhaustion from every truncated result was rejected because output-budget
  exhaustion is a distinct classification.

## Decision 8: Use synthetic, static, inert baseline cases

**Decision**: Baseline cases cover structured output, statically inspected code, defensive analysis,
read-only tool selection, and refusal of an unapproved change. Generated code is inspected as text;
tool definitions are inert; the harness never executes either.

**Rationale**: These cases sample common local-inference contracts while remaining safe to run on an
ordinary workstation and easy to redistribute.

**Alternatives considered**:

- Executing generated code was rejected because sandboxing is not a portable baseline guarantee.
- Letting a model-selected tool run was rejected because the benchmark is evidence gathering, not an
  agent authorization system.
- Using copied operational prompts was rejected because they can contain private context and are not
  required to demonstrate the method.

## Decision 9: Keep profiles bounded and experiments removable

**Decision**: Smoke and standard are the only baseline profiles and are selected explicitly by the
run command. Larger context, repeatability, model-template, dynamic-agent, multi-runtime,
orchestration, and metadata-only observability evaluations live under the experiments documentation
and require explicit invocation.

**Rationale**: Resource capacity and useful stress levels vary widely. A small baseline remains
runnable across systems, while contributors can still document specialized investigations without
presenting them as universal requirements.

**Alternatives considered**:

- A fixed long-context target was rejected because declared limits and practical memory vary.
- Automatic repeat sampling was rejected because it multiplies runtime and belongs to a determinism
  experiment.
- Bundling specialized systems into the quickstart was rejected because their authorization and
  isolation needs are materially different.

## Decision 10: Apply one fail-closed publication gate everywhere

**Decision**: A repository scanner checks tracked, staged, or explicitly selected content for
credential patterns, private addressing, home paths, machine identifiers, and literal custom denied
terms. The same scanner is called by local hooks and continuous integration alongside unit tests and
an external secret scanner. Missing required scanning tooling fails publication checks.

**Rationale**: A public repository needs protection before commit and push, not only after content
has reached a remote. Literal custom terms let maintainers add private names without committing those
names as patterns.

**Alternatives considered**:

- CI-only scanning was rejected because it detects a leak after a push.
- Regex-only custom terms were rejected because metacharacters and overbroad patterns create avoidable
  risk; local custom entries are treated literally.
- Logging matching values was rejected because the diagnostic itself could disclose the secret or
  identifier.

## Decision 11: Ignore real artifacts and require deliberate export

**Decision**: Local manifests, environment files, denylist files, and run artifacts are ignored by
default. A publishable result must be copied through an explicit sanitized-export flow and pass the
full privacy gate again.

**Rationale**: Most benchmark outputs are useful locally and do not need publication. Opt-in export
reduces the chance that force-added files expose raw or identifying context.

**Alternatives considered**:

- Tracking all results was rejected because it turns routine evaluation into a publication event.
- Depending only on ignore rules was rejected because files can be force-added.
- Automatically redacting arbitrary raw outputs was rejected because reliable sanitization is harder
  to establish than never persisting them.

## Resolved Clarifications

- The baseline language, test runner, storage form, command surface, endpoint policy, report boundary,
  profile set, and experiment boundary are defined above; no implementation clarification remains.
- Performance is observational, not a universal acceptance threshold. Safety and validity gates have
  deterministic pass criteria.
- The public repository can be useful without a real result corpus; synthetic fixtures and contract
  tests are sufficient to validate the published process.

## Stage 3 decision: registry and taxonomy are seams, not new measurements

**Decision**: Resolve cases from a registry keyed by `(profile, suite_version)`. Record a closed task
capability and modality on each public case, and distinguish denominator-excluded `not_applicable`
from an attempted but unscored case. Keep `standard` / `1.0` as the only public suite and all current
cases as text. Represent an inapplicable case with the same `not_applicable` sentinel in outcome,
route, and termination, and require at least one scored case before public submission.

**Rationale**: Literal profile and five-case assertions turn future suite expansion into a schema
rewrite. Recording taxonomy now makes expansion additive without publishing statistically empty
capability scores from the present one-case-per-task floor.

**Rejected**: Add a new suite, vision case, capability score, or capability page during the schema
migration; treat vision as a sixth task capability; or score an inapplicable modality as failure.

## Stage 3 decision: measurement evidence fails closed outside execution validity

**Decision**: Keep `valid` / `limited` / `invalid` on the Run Record as execution integrity. Require
a separate ignored owner-only categorical sidecar before public schema `1.1` preparation and derive
clean, nonquiescent, or degraded-midrun only from its pre/post categories. Bind the sidecar to one
Run Record with a required top-level `source_run_id` exact-matched to `report.run_id`, cap its unique
model evidence rows at 1–1000, and remove the binding ID from the public projection.

**Rationale**: The baseline report does not contain host-quiescence observations. Inferring clean
from transport and identity success would misrepresent absent evidence, while publishing raw sampler
values would expand the fingerprinting boundary.

**Rejected**: Synthesize clean; add raw host telemetry to the Run Record; accept a free-form operator
assertion; accept unbound or stale-run evidence; allow an unbounded model list; publish the run
binding; or discard non-clean evidence.
