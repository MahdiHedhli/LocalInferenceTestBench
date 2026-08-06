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
4. **Given** an append-only public submission corpus that no longer fits one leaderboard payload,
   **When** publication runs, **Then** all accepted source evidence remains retained while a bounded
   deterministic index and temporary byte-bounded Pages shards carry the public view.

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
4. **Given** a retained model display name, source label, or precision label containing
   reviewer-directed instructions, non-ASCII homoglyphs, or descriptor-like private identifiers,
   **When** that evidence is projected into a public leaderboard submission, **Then** public
   validation fails before the value can enter the review surface.

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
- A model display name, source label, or precision label contains a URL, email address, network
  value, UUID, serial/inventory label, reviewer mention, role-prefix instruction, bidi control, or
  non-ASCII homoglyph.
- The accepted public-result corpus exceeds a previous aggregate payload cap and requires multiple
  byte-bounded pages.
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
  quantization, declared context, and non-secret generation settings. They MAY record one closed
  nullable total/active parameter-scale object in billions; omission MUST preserve existing manifest
  compatibility and supplied values MUST flow into public run provenance.
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
- **FR-019**: When retained evidence is projected into a public leaderboard submission, every public
  hardware, runtime, model-label, and artifact revision/digest descriptor MUST use visible ASCII and
  MUST reject descriptor-grade UUID, serial/inventory-label, network, URL, email, private-host, and
  automated-reviewer/instruction-injection shapes. `display_name`, `source`, and `precision` remain
  bounded to 160, 240, and 80 characters respectively. Local manifest/run-record acceptance remains
  unchanged; this is a public-projection boundary.
- **FR-020**: Any public presentation of benchmark results MUST state that the measurements are
  self-reported and unverified. A content digest may be described only as evidence of content
  integrity; it MUST NOT be described as provenance, attestation, or proof that a run occurred.
- **FR-021**: Public-result scale handling MUST preserve the then-accepted append-only schema `1.0`
  submissions and the exact benchmark pull-request boundary. A valid corpus that exceeds one
  aggregate payload MUST be paginated into a bounded deterministic committed index and bounded
  Pages-delivery shards rather than rejected or pruned. Later schema evolution MUST retain those
  source bytes and the same pull-request file boundary.
- **FR-022**: Pages-delivery shards MUST be generated only after the canonical committed leaderboard
  transport file passes its byte check, in a temporary deployment artifact, and MUST never become
  accepted source evidence. The artifact MUST contain allowlisted static site chrome and generated
  transport data, not a duplicate of the retained submission corpus. Per-submission, per-index, and
  per-shard byte caps and all corrupt-input failures MUST remain fail-closed.
- **FR-023**: Public shard identifiers and pagination MUST be deterministic. Browser fetch targets
  MUST be one-based contiguous IDs padded to at least six digits and synthesized as
  `data/leaderboard-NNNNNN.json`, never a path or URL supplied by public records. Every fetched
  legacy monolith, index, and shard MUST use fatal UTF-8 decoding, reject byte-order marks, and pass
  through the strict duplicate-member-rejecting parser before transport or entry validation.
- **FR-024**: The mixed scale-code rollout MUST leave the current bounded legacy monolith
  byte-identical and support both closed transport shapes. The deterministic builder MUST switch to
  the constant-shape index when the monolith cap would otherwise be crossed. A leaderboard-only
  early migration is unsupported; the transition MUST retain the exact append-only two-file
  benchmark boundary. Pages MUST always emit an index with exactly
  `{index_version, schema_version, entry_count, shard_count}` and shards with exactly
  `{index_version, schema_version, shard_id, entry_count, entries}` in its temporary artifact.
- **FR-025**: Suite selection MUST resolve through a registry keyed by `(profile, suite_version)`.
  Validation, case ordering, counts, and percentages MUST derive from the resolved suite rather than
  a module-level five-case constant. The only registered public suite in this increment remains
  `standard` / `1.0`; `smoke` remains a local report profile and is not publicly submit-eligible.
- **FR-026**: Every schema `1.1` public case MUST record a closed `capability` value of
  `structured_output`, `coding`, `agent_tool_use`, `cyber_triage`, or `safety_boundary` and a closed
  `modality` value of `text` or `vision`. The current five cases MUST retain their existing behavior
  and be tagged `text`; this metadata MUST NOT create capability scores, columns, pages, or new test
  cases in this increment.
- **FR-027**: `not_applicable` MUST be distinct from `not_scored`. A not-applicable case MUST be
  excluded from scored counts and every score denominator, and a result with no applicable case in a
  selected facet MUST be absent from that facet rather than ranked as zero. The complete resolved
  public suite still requires `scored_case_count` plus the number of `not_applicable` outcomes to
  equal its resolved length and at least one case to be scored; an attempted `not_scored` case and a
  whole-suite all-not-applicable result are not public-submission eligible. Outcome, route, and
  termination MUST all use the `not_applicable` sentinel for an inapplicable case, and MUST all avoid
  it for every other outcome.
- **FR-028**: Local run execution validity (`valid`, `limited`, or `invalid`) and public measurement
  validity (`clean`, `nonquiescent`, or `degraded_midrun`) MUST remain separate concepts. Public
  preparation MUST first require fully valid execution evidence and then require a separate ignored,
  owner-only categorical measurement-evidence sidecar. Missing, unsafe, incomplete, or inconsistent
  sidecar evidence MUST fail closed; the exporter MUST NOT infer `clean` from execution validity.
  The sidecar MUST contain a top-level `source_run_id` that exactly equals the Run Record's `run_id`
  and a bounded list of 1–1000 unique model entries. That private binding ID MUST NOT enter the public
  submission or leaderboard projection.
- **FR-029**: New public submissions MUST use schema `1.1` and carry required `validity`, closed
  `measurement_conditions`, and UTC month-resolution `measurement_period` (`YYYY-MM`) fields.
  Conditions MUST contain only pre/post threshold outcomes, a hard-threshold-crossed boolean, and
  closed categories for memory pressure, thermal state, sustained load, swap, and resident models;
  they MUST contain no raw sample values or free text. An optional closed determinism block MAY carry
  3–5-run aggregate stability evidence.
- **FR-030**: Accepted schema `1.0` submissions MUST remain byte-for-byte retained and
  digest-addressable, but a newly added benchmark pull request MUST use schema `1.1`. Legacy rows in
  a mixed `1.1` projection MUST be labeled `legacy_unreported` with absent measurement period and
  conditions rather than receiving synthesized evidence. The current all-legacy six-entry monolith
  MUST remain byte-identical until the first accepted `1.1` submission causes the deterministic
  mixed projection.
- **FR-031**: Ranking MUST expose a facet-selector seam over capability subsets, modality, and named
  dimension filters. This increment MUST ship only the `all-cases-text` facet. Configuration
  dimensions MUST be defined once in a versioned `1.0` structure covering hardware, model identity
  including revision or digest, precision, runtime name/version/backend, runtime configuration, and
  settings so later config-cell collapse does not require redefining identity.
  Browser dataset validation MUST accept registry-bounded subset counts emitted by a non-default
  selector even though no additional selector is published in this increment.
- **FR-032**: The versioned facet-graduation policy MUST be recorded as `1.0` with a threshold of at
  least 25 entries across at least five distinct model families. Nothing MUST read or enforce that
  policy in this increment. The leaderboard transport `index_version` MUST remain `1.0`, independent
  of the public submission and projected-row schema bump to `1.1`.
- **FR-033**: The public site MUST render `measurement_period` as an “as of” month and support month
  filtering and recency sorting. On a paginated board those controls, like other client-side
  controls, MUST be labeled as applying to loaded rows until every shard is present.
- **FR-034**: Non-interactive single-command run-and-export on POSIX MUST use an explicitly selected local
  measurement-sampler executable. The runner MUST accept only a validated preallocated UUIDv4/UTC
  identity, and the CLI MUST pass that identity plus the ordered public model IDs to synchronous
  closed `pre` and `post` adapter calls around the complete run, with `post` required only after a
  successful `pre` sample and a successfully returned complete benchmark. A runner exception MUST
  produce no `post` call and no export. Responses MUST echo the exact
  binding and contain only the existing categorical sample. Invocation MUST use no shell, an
  allowlisted credential-free environment, discarded stderr, a timeout, and an in-flight stdout
  cap, isolated execution, and bounded process-tree cleanup. A dedicated standard-library
  supervisor MUST start the snapshot in its own process group, observe leader exit without reaping
  it, signal that group before reaping its leader, and never signal the numeric PGID after that
  leader has been reaped. Supported macOS Python versions MAY use `kqueue` when `waitid` is absent;
  they MUST retain the same non-reaping ordering. On Linux the supervisor MUST fail
  closed unless it can become a child subreaper and MUST boundedly reap adopted descendants. The
  trusted sampler MUST remain synchronous and MUST NOT daemonize, create another session or process
  group, or otherwise deliberately escape the supervisor boundary. The executable MUST be at most 16 MiB,
  regular, non-symlinked, executable, not group/world-writable, and identity/content rechecked at
  launch. Only a private non-writable snapshot of the approved bytes MAY execute. Its directory MUST
  be owner-only and its backing filesystem MUST be writable and permit execution; an operator MAY
  select an owner-controlled location through `TMPDIR`, but MUST NOT use a tracked or shared
  repository directory. Before writing approved bytes, the runner MUST resolve the selected temp
  base and reject an ordinary or linked worktree, Git directory, or bare repository using
  filesystem repository markers, and MUST reject active repository-routing `GIT_*` state. Every
  resolved ancestor MUST be owned by root or the current user; a group/world-writable ancestor MUST
  have the sticky bit. Directory creation and sampler-byte writes MUST be anchored to open directory
  descriptors. Cleanup MUST nonblockingly inspect without following links, compare the exact created
  identity/type immediately before descriptor-relative removal, and fail closed on a mismatch. The
  contract MUST state that portable POSIX cannot make pathname removal atomically
  identity-conditional and does not contain root or same-UID adversaries. Windows MUST fail
  this option closed and retain the two-step exact-bound sidecar path. A sampler or evidence failure
  after the benchmark returns MUST leave the completed private report intact while blocking export;
  a runner exception follows the existing no-completed-report path. Missing samples and clean
  conditions MUST never be synthesized. Cleanup failure MUST be surfaced without masking a primary
  failure. A handled cleanup failure, `SIGKILL`, or a host crash MAY leave the owner-only private
  snapshot until local or system temporary-file cleanup; the snapshot path and bytes MUST never be
  published. Static exact-bound sidecars remain supported by the separate
  two-step preparation command.
- **FR-035**: A schema `1.1` public submission MUST contain explicit nullable total and active model
  parameter counts in billions even when an older manifest omitted them. Known values MUST be
  positive, bounded, at most three decimal places, and internally consistent. Export MUST copy only
  explicit provenance and MUST NOT parse model names to infer scale.
- **FR-036**: The schema `1.1` leaderboard projection MUST collapse repeated records by the existing
  versioned configuration dimensions, retain a deterministic score-neutral representative, show
  fixed corroboration and performance-spread summaries, and compute representative-only Wilson rank
  bands plus caution-only plausibility. Anonymous repeats MUST NOT narrow quality intervals, and
  plausibility/performance MUST NOT gate, drop, verify, or rank a record.

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
- **SC-008**: A synthetic public corpus larger than the former aggregate cap produces byte-identical,
  individually bounded index and shard outputs with every projected configuration cell present
  exactly once, every accepted digest retained at its source path, and no committed shard files.
- **SC-009**: Shared Python/browser fixtures prove registry-based suite resolution, required
  capability/modality tags, `not_applicable` denominator behavior, categorical measurement validity,
  month validation, and `1.0` legacy handling remain in lockstep without changing the five current
  benchmark cases.
- **SC-010**: Tests prove stale source-run evidence and a model-evidence list outside 1–1000 are
  rejected, the source run ID is absent from public bytes, and every browser-fetched leaderboard
  transport rejects invalid UTF-8, a byte-order mark, and duplicate JSON member names.
- **SC-011**: Tests prove single-command measurement ordering is pre → run → post only after a
  successfully returned run, adapter responses are exact-bound and byte-bounded during execution,
  malformed identities fail before preflight, credential values do not cross the process boundary,
  Linux descendants are adopted and reaped without post-reap PGID signaling, macOS Python 3.11 and
  3.12 observe exit without reaping, retained evidence is atomic and owner-only, and sampler failure
  preserves a completed private report while producing no candidate.

## Assumptions

- Users can expose their local inference runtime through an OpenAI-compatible endpoint or write an
  adapter that satisfies the documented request/response contract.
- Operators load and unload models outside the baseline runner and run large models sequentially.
- Python 3.11 or newer is available; the reference implementation uses only the standard library.
- Real run artifacts remain local by default; publication is a deliberate sanitized export workflow.
- Accepted public submission files remain append-only and digest-addressable. The committed
  leaderboard transport file and temporary Pages index/shards are rebuildable delivery artifacts,
  not a pruning or evidence-retention policy.
- The first public release favors clear, auditable cases over a large benchmark corpus.
- Image and video generation are outside this test bench because their evaluation generally requires
  similarity models or human preference and a different runtime stack. A separate generation bench
  may reuse this project's submission, privacy, and validity pipeline.
