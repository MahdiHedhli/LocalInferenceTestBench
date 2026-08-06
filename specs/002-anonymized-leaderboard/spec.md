# Feature specification: Anonymized benchmark leaderboard

**Feature Branch**: `002-anonymized-leaderboard`

**Created**: 2026-08-05

**Status**: Implemented

**Input**: Add a GitHub Pages site with a brief explanation, an anonymized leaderboard, and a safe
way for people to prepare and submit benchmark results. Add the author's reason for building the
test bench to the README.

## User scenarios and testing

### User story 1: Read the leaderboard (Priority: P1)

A visitor lands on a small public site, learns what the test bench measures, and reaches the
leaderboard without working through a long product page. The table shows model provenance, the
hardware and runtime used for inference, task and format scores, and observed performance.

**Why this priority**: The site exists to make accepted results easy to inspect.

**Independent test**: Serve the static site with an empty dataset and with several fixture entries.
Confirm that the explanation, ranking method, privacy note, empty state, filters, and table all work
without a framework or third-party service.

**Acceptance scenarios**:

1. **Given** accepted standard-profile entries, **When** the page loads, **Then** it shows them in a
   quality-ranked table with the hardware and runtime needed to interpret latency and throughput.
2. **Given** entries with the same semantic and exact-format scores, **When** ranks are assigned,
   **Then** the entries share a rank and speed does not break the tie.
3. **Given** no accepted entries, **When** the page loads, **Then** it shows an honest empty state and
   a link to the submission process.
4. **Given** a string that contains HTML syntax, **When** a row is rendered, **Then** the browser
   treats it as text rather than markup.
5. **Given** any accepted entry, **When** it is presented in the site chrome or leaderboard header,
   **Then** the site says it is self-reported and unverified and explains that its hash establishes
   content integrity rather than provenance or proof that the run occurred.

---

### User story 2: Prepare an anonymized submission (Priority: P1)

An operator can turn a valid standard benchmark report plus a closed public hardware descriptor into
one minimized public record per model. The export removes local correlation fields and refuses a
report or descriptor that is not comparable or does not pass the existing privacy checks.

**Why this priority**: A public leaderboard is only useful if its submission boundary is clear and
repeatable.

**Independent test**: Export synthetic valid, limited, invalid, smoke, single-model, and multi-model
reports. Verify the accepted files contain only the closed public contract and that every rejected
case fails without echoing sensitive values.

**Acceptance scenarios**:

1. **Given** a valid standard report with verified model identity and valid categorical measurement
   evidence, **When** the operator exports it, **Then** the tool combines it with the public hardware
   descriptor and writes one closed schema `1.1` submission record per selected model.
2. **Given** a smoke, limited, invalid, or identity-unverified report, **When** export is attempted,
   **Then** the tool refuses it and does not create a submission.
3. **Given** an eligible report, **When** it is exported, **Then** the result retains bounded hardware
   product and runtime details but omits the run identifier, timestamp, local model selector,
   manifest digest, endpoint, environment, host identity, serial and inventory identifiers, and
   contributor identity.
4. **Given** an exported record on the Pages submission screen, **When** the visitor selects it,
   **Then** strict JSON parsing, duplicate-member rejection, closed-schema validation, canonical
   digest recomputation, and preview happen in the browser without uploading the file.
5. **Given** a prepared record, **When** the visitor continues, **Then** the site directs them to a
   reviewed pull-request workflow and explains that their GitHub account remains visible there.
6. **Given** a model display name, source label, or precision label containing reviewer-directed
   instructions, non-ASCII homoglyphs, or descriptor-like identifiers, **When** export or browser
   validation runs, **Then** the record is rejected before it can reach a public review surface.
7. **Given** a fully valid execution report but no safe measurement-evidence sidecar, **When** export
   is attempted, **Then** it fails closed instead of claiming the run was measured under clean
   conditions.
8. **Given** current categorical evidence, **When** a candidate is prepared, **Then** it records only
   pre/post threshold outcomes, closed threshold categories, optional aggregate determinism, and the
   UTC measurement month rather than raw host samples or an event timestamp.

---

### User story 3: Review and publish entries (Priority: P2)

A maintainer can validate submitted JSON, reject duplicates or unsupported records, generate the
public dataset deterministically, and deploy the site from the default branch.

**Why this priority**: GitHub Pages is static, so repository review is the publication boundary.

**Independent test**: Add valid, duplicate, malformed, oversized, and privacy-unsafe fixtures in a
temporary submission directory. Confirm that only valid unique entries produce a stable leaderboard
dataset and that Pages deployment runs only from the default branch.

**Acceptance scenarios**:

1. **Given** a pull request containing a valid record, **When** continuous integration runs, **Then**
   the closed schema, content digest, privacy rules, eligibility, and dataset build all pass.
2. **Given** a duplicate, renamed, malformed, unknown-field, or out-of-range record, **When** it is
   validated, **Then** publication fails with a categorical error that does not echo submitted data.
3. **Given** accepted records on the default branch, **When** the Pages workflow runs, **Then** it
   builds the public dataset and deploys only the static site directory.
4. **Given** a community result, **When** it appears on the site, **Then** the site calls it
   self-reported and unverified and does not imply that schema checks, repository review, or its
   digest attest that a benchmark run occurred.
5. **Given** an accepted corpus larger than the previous aggregate dataset cap, **When** publication
   runs, **Then** the deterministic committed index still byte-validates and the Pages build emits
   individually bounded deterministic shards without deleting, omitting, or rewriting an accepted
   submission.
6. **Given** the globally ranked row sequence exceeds one shard byte cap, **When** publication runs,
   **Then** it is paginated deterministically by rendered UTF-8 JSON byte size and the browser
   fetches only the pages needed for the current view.
7. **Given** a corrupt accepted record at any corpus size, **When** validation or publication runs,
   **Then** it fails closed rather than treating volume pagination as permission to skip the record.

### Edge cases

- A report contains more than one eligible model.
- A run uses only a CPU, shared memory, an accelerator row with a count greater than one, or a
  hybrid CPU and accelerator configuration.
- Two distinct entries earn the same quality score.
- Usage data is absent, so throughput is unavailable.
- A contributor renames a submission file or changes content without updating its digest.
- A model name contains markup, control characters, a local identifier, or an unusually long value.
- A model display name, source label, or precision label contains a URL, email address, network
  value, UUID, serial/inventory label, reviewer mention, role-prefix instruction, bidi control, or
  non-ASCII homoglyph.
- A submission uses a supported schema but an unsupported suite or profile.
- The dataset is empty, missing, malformed, or unavailable to the browser.
- The accepted corpus exceeds the size of one browser payload or requires multiple byte-bounded
  pages.
- A generated shard reports the wrong ordinal, or an index/shard carries an arbitrary path,
  cross-origin URL, duplicate record, missing record, or count inconsistent with its content.
- A visitor has JavaScript disabled or uses a narrow screen.
- A pull request is public before its checks finish.

## Requirements

### Functional requirements

- **FR-001**: The repository MUST publish a static GitHub Pages site from a dedicated site directory.
- **FR-002**: The first page MUST give a brief explanation and place the anonymized leaderboard
  immediately after it.
- **FR-003**: The site MUST work without third-party scripts, fonts, analytics, cookies, or a write
  credential.
- **FR-004**: The leaderboard MUST rank eligible entries by semantic score and then exact-format
  score, with dense ties.
- **FR-005**: Latency and throughput MUST be displayed with their hardware, runtime, and any reported
  runtime-configuration context and MUST NOT affect quality rank.
- **FR-006**: The site chrome and leaderboard header MUST identify every record as self-reported and
  unverified. They MUST state that hashes establish content integrity, not provenance, attestation,
  truthfulness, or proof that a benchmark run occurred.
- **FR-007**: The site MUST render all record strings through text-only DOM operations.
- **FR-008**: The site MUST provide a useful empty and load-error state.
- **FR-009**: The command-line tool MUST export one minimized record for each selected eligible model
  and MUST require a separate public hardware descriptor.
- **FR-010**: Export MUST call the existing closed run-record validator before reading result fields.
- **FR-011**: Export MUST accept only a complete suite resolved from the public registry, an overall
  valid report, verified model preflight, matching runtime identity, a valid model result, and the
  resolved ordered case set. The sole current public member remains `standard` / `1.0`.
- **FR-012**: A submission MUST retain only public model provenance, public generation settings,
  structured hardware and runtime context, minimized categorical case outcomes, and rounded
  aggregate quality and performance observations.
- **FR-013**: A submission MUST omit the source run identifier and time, local model selector,
  manifest digest, endpoint, credentials, environment, operating-system account, hostname, network
  data, serial number, inventory ID, device UUID, unused device inventory, contributor identity, raw
  prompts, completions, reasoning, and tool arguments.
- **FR-014**: Every submission MUST have a deterministic SHA-256 identifier derived from its canonical
  content, excluding the identifier field itself.
- **FR-015**: The validator MUST require an exact filename based on the submission identifier and
  MUST reject duplicate identifiers.
- **FR-016**: Submission and dataset contracts MUST be closed, bounded, and versioned.
- **FR-017**: The Pages submission screen MUST inspect only an already-minimized record and MUST NOT
  upload, transmit, or accept a raw run report. It MUST apply fatal UTF-8 decoding, reject byte-order
  marks, parse strict JSON, reject duplicate member names, apply the parallel closed-schema
  validator, and recompute the canonical payload-minus-ID digest before displaying a successful
  preview. These browser checks MUST NOT replace authoritative Python and pull-request validation.
- **FR-018**: Publication MUST use a reviewed pull request. The documentation MUST state that the
  pull request and its GitHub account are public even though the JSON record has no contributor field.
- **FR-019**: Continuous integration MUST validate all accepted records and build the dataset before
  a change can be treated as publishable.
- **FR-020**: The Pages workflow MUST deploy only from the default branch with pinned actions and
  minimal `contents: read`, `pages: write`, and `id-token: write` permissions.
- **FR-021**: The README MUST explain in the author's voice that the project began as a way to compare
  how local models handled a fixed set of tasks on the author's own hardware.
- **FR-022**: README, site, submission, security, and contribution documentation MUST agree on the
  privacy boundary and ranking method.
- **FR-023**: The public hardware descriptor MUST record the CPU model and logical core count, system
  memory and memory architecture, the accelerator devices used for inference, execution mode, and a
  bounded runtime name, version, and backend.
- **FR-024**: The hardware descriptor MUST use a closed versioned schema, remain ignored and
  owner-readable locally, and contain no free-form notes or general machine inventory.
- **FR-025**: The descriptor MAY include a closed `runtime_configuration` object containing exactly
  context-window tokens, concurrent requests, speculative-decoding state, and offload mode. Export
  MUST preserve it when supplied, MUST preserve legacy records without it, and MUST NOT infer a
  default. Known context-window tokens MUST not be smaller than the generation output budget.
- **FR-026**: Every public hardware, runtime, model-label, and artifact revision/digest descriptor
  MUST use visible ASCII and reject descriptor-grade UUID, serial/inventory-label, network, URL,
  email, private-host, automated-reviewer, and instruction-injection shapes. `model.display_name`,
  `model.source`, and `model.precision` MUST remain bounded to 160, 240, and 80 characters. Python and
  browser validation MUST enforce this in lockstep.
- **FR-027**: Submission IDs MUST continue to prove canonical-content integrity and exact duplicate
  identity only. No documentation, user interface, pull-request text, or automated review may call
  the digest an attestation or evidence of benchmark provenance.
- **FR-028**: Stage 2 scale handling MUST be a transport-only change. The then-accepted schema `1.0`
  submission files MUST remain append-only, and the benchmark pull-request boundary MUST remain
  exactly one added digest-named submission blob plus the modified generated
  `site/data/leaderboard.json` canonical transport file through later schema evolution.
- **FR-029**: Once sharding is active, the committed `site/data/leaderboard.json` MUST be a small,
  bounded, deterministic index derived from every accepted submission. Pull-request validation and
  the Pages workflow MUST byte-compare it with an independent deterministic rebuild before
  publication. Its sharded form MUST have exactly
  `{index_version, schema_version, entry_count, shard_count}`, with both version fields `1.0` for
  this transport-only increment.
- **FR-030**: After the committed leaderboard transport file passes its byte check, the Pages
  workflow MUST generate a constant-shape index and leaderboard shards from the validated accepted
  submissions into a temporary static-site artifact. Pages MUST always deploy that sharded form,
  whether the committed file is the bounded legacy monolith or the index. Generated shards MUST NOT
  be committed or accepted as benchmark pull-request changes. The artifact MUST copy only the
  allowlisted static site chrome plus generated transport data; it MUST NOT duplicate the retained
  `site/data/submissions/` source corpus.
- **FR-031**: Publication MUST retain hard byte caps for each submission, the committed leaderboard
  transport file, and each fetched shard. Corpus growth by itself MUST NOT be a hard failure;
  malformed, duplicate, inconsistent, or privacy-unsafe input MUST continue to fail closed.
- **FR-032**: Pagination, shard identifiers, and record order MUST be deterministic. The globally
  ranked rows MUST be paginated by the UTF-8 byte size of rendered shard JSON, not by an estimate or
  a platform-dependent character count. Shards MUST have exactly
  `{index_version, schema_version, shard_id, entry_count, entries}`, where `shard_id` is a contiguous
  one-based ordinal string zero-padded to a minimum width of six digits.
- **FR-033**: The site MUST load the bounded index first and fetch same-origin shard pages on demand.
  It MUST derive only one-based contiguous shard IDs padded to at least six digits from `shard_count`
  and synthesize `data/leaderboard-NNNNNN.json` locally; neither the index nor a submission may
  supply an arbitrary path or URL for the browser to fetch. The legacy monolith, index, and every
  shard response MUST be read as bounded bytes, decoded as fatal UTF-8 with byte-order marks
  rejected, and parsed by the strict duplicate-member-rejecting JSON parser before validation. Until
  every page is loaded, search, hardware filters, alternate sorting, and no-match messages MUST be
  explicitly scoped to loaded rows and MUST NOT claim that no matching published row exists.
- **FR-034**: Every accepted submission MUST remain retained in the repository and addressable by
  its digest. Pagination MAY change publication transport only and MUST NOT be a retention, pruning,
  or silent-drop mechanism.
- **FR-035**: The scale code change MUST leave the current bounded legacy monolith byte-identical and
  support both its closed `{schema_version, entry_count, entries}` shape and the sharded index shape.
  A deterministic build MUST switch to the index rather than fail when the legacy cap would be
  crossed by an otherwise valid exact two-file append-only benchmark submission. A
  leaderboard-only early migration is unsupported. Pages MUST generate the temporary sharded form
  even while the committed source remains the legacy monolith.
- **FR-036**: New leaderboard submissions and projected entries MUST use schema `1.1`. Export MUST
  require a separate ignored, owner-only categorical measurement-evidence sidecar and MUST NOT
  derive public measurement validity from the source report's `valid`, `limited`, or `invalid`
  execution state. Absence, unsafe permissions, untracked model IDs, or inconsistent categorical
  evidence MUST fail closed. The sidecar MUST carry a top-level `source_run_id` exactly matching the
  source report's `run_id` and between 1 and 1000 unique model evidence rows. The run binding MUST be
  consumed only locally and omitted from the public submission and projected leaderboard data.
- **FR-037**: Schema `1.1` MUST require `validity` (`clean`, `nonquiescent`, or
  `degraded_midrun`), a closed `measurement_conditions` object, and `measurement_period` at UTC month
  resolution (`YYYY-MM`). The condition object MAY name only threshold outcomes and categories for
  memory pressure, thermal state, sustained load, swap, and resident models; it MUST carry no raw
  values or free text. Future periods MUST be rejected.
- **FR-038**: Schema `1.1` MAY carry one closed determinism object containing 3–5 runs, semantic pass
  rate, envelope-class, finish-reason, and fingerprint stability, and a consistent `stable`,
  `warning`, or `blocking_instability` verdict. The pass rate MUST be arithmetically possible for the
  declared repetition count after six-decimal normalization. Missing determinism MUST remain missing.
- **FR-039**: Public validation MUST resolve cases from a suite registry keyed by
  `(profile, suite_version)` and derive all counts and percentages from the resolved length. Every
  `1.1` case MUST record its registry-defined `capability` and `modality`. Current behavior remains
  the five `text` cases of `standard` / `1.0`; the tags MUST NOT be aggregated or displayed in this
  stage.
- **FR-040**: `not_applicable` MUST be a distinct outcome excluded from scored counts and score
  denominators. The sum of applicable and not-applicable case positions MUST equal the resolved
  suite length, and a public candidate MUST retain at least one scored case across its complete
  suite. A result with no applicable case for a selected facet MUST be absent from that facet, never
  ranked zero. Outcome, route, and termination MUST all equal `not_applicable` for an inapplicable
  case; the route and termination sentinel MUST be rejected for every other outcome.
- **FR-041**: Accepted schema `1.0` files MUST remain byte-for-byte retained and valid as historical
  evidence, but the trusted append-only boundary MUST reject a newly proposed `1.0` file and require
  it to be regenerated as `1.1`. A mixed `1.1` leaderboard MUST annotate historical rows as
  `legacy_unreported` with null period and measurement conditions rather than inventing them. The
  current all-legacy six-entry monolith MUST remain byte-identical until a `1.1` record is accepted.
- **FR-042**: The site MUST present validity as a first-class field and default to clean rows only.
  A user MAY deliberately select nonquiescent, degraded, or legacy-unreported evidence. This is a
  comparison filter, not verification of self-reported conditions.
- **FR-043**: Ranking MUST accept a facet selector over capability subsets, modality, and versioned
  dimension filters. The only shipped selector is `all-cases-text`. Configuration dimensions MUST
  be named in one version `1.0` structure containing hardware, model identity including revision or
  digest, precision, runtime name/version/backend, runtime configuration, and settings. Browser
  validation MUST accept registry-bounded subset counts emitted by a non-default selector without
  adding a current UI view.
- **FR-044**: A version `1.0` facet-graduation policy MUST record 25 entries across five distinct
  model families as the minimum for a dedicated future page, but no current code or UI MUST read it.
  The transport `index_version` MUST remain `1.0` when projected entry `schema_version` becomes
  `1.1`.
- **FR-045**: The site MUST display `measurement_period` as an “as of” month and provide month
  filtering and recency sorting. Until every shard is loaded, these controls MUST be explicitly
  scoped to loaded rows and MUST NOT imply a corpus-wide absence or ordering.

### Key entities

- **Leaderboard submission**: One identifier-minimized benchmark result for one public model artifact
  and one fixed standard-suite configuration.
- **Submission identifier**: A deterministic digest of canonical submission content.
- **Leaderboard case**: A case identifier plus categorical outcome, termination, and route fields.
- **Hardware descriptor**: Structured public product details for the CPU, system memory,
  accelerators used during inference, execution mode, runtime, and optional runtime configuration.
- **Leaderboard index**: The constant-shape bounded deterministic count manifest from which
  contiguous one-based shard IDs padded to at least six digits are derived.
- **Leaderboard shard**: One bounded deterministic same-origin JSON page generated only in the
  temporary Pages artifact and fetched on demand.
- **Submission review**: The public pull request and automated checks used before an entry is accepted.

## Success criteria

### Measurable outcomes

- **SC-001**: One hundred percent of accepted submission files validate against the runtime contract
  and the published JSON Schema.
- **SC-002**: Export tests prove that every field listed in FR-013 is absent from generated records.
- **SC-003**: Ranking fixtures prove quality ordering and dense ties without using performance values.
- **SC-004**: Browser tests or equivalent DOM checks prove that untrusted record strings cannot add
  markup or script execution.
- **SC-005**: The full Python test suite and publication gate pass on Linux, macOS, and Windows.
- **SC-006**: The deployed Pages workflow completes its record validation, deterministic build,
  artifact upload, and deployment jobs successfully.
- **SC-007**: The live site loads the empty or populated leaderboard and exposes a working submission
  path without sending the selected JSON to a remote service.
- **SC-008**: Shared adversarial fixtures prove that Python and browser validators reject the same
  overlong, descriptor-like, non-ASCII, bidi, homoglyph, and reviewer-injection-shaped model labels
  while existing hardware descriptor fixtures remain unchanged.
- **SC-009**: A synthetic accepted corpus larger than the former aggregate cap builds successfully,
  while every generated index and shard remains within its individual byte cap and all submission
  identifiers occur exactly once.
- **SC-010**: Repeated builds on supported platforms produce byte-identical committed indexes and
  deployment shards, including deterministic exact-byte pagination of the global rank sequence.
- **SC-011**: Browser tests prove shard fetch targets use only synthesized
  `data/leaderboard-NNNNNN.json` names and cannot be redirected by an arbitrary path or URL in public
  data.
- **SC-012**: A shared fixture corpus proves Python and JavaScript accept and reject the same schema
  `1.1` suites, capability/modality values, three-sentinel not-applicable cases, one-scored-public
  boundary, measurement conditions, determinism blocks, month periods, and legacy projections.
- **SC-013**: Raw candidate fixtures prove the Python loader and browser parser both reject duplicate
  JSON member names and a payload whose declared submission ID differs from its recomputed canonical
  digest, while accepting the same valid canonical candidates.
- **SC-014**: Sidecar tests reject a missing or stale source-run binding and model lists outside
  1–1000, prove the binding is absent from public bytes, and browser-loading tests reject invalid
  UTF-8, byte-order-marked, or duplicate-member monolith, index, and shard responses.

## Assumptions

- GitHub Pages remains a static host. It does not receive benchmark writes directly.
- Community entries are self-reported and unverified. Schema validation, repository review, and
  canonical hashes do not prove that a model produced the submitted measurements or that a run
  occurred.
- Hardware combinations and performance values can weakly characterize a private setup. Contributors
  review the minimized JSON and choose whether to publish those details.
- The public suite registry currently contains only `standard` / `1.0`. A future suite is added by a
  reviewed registry entry and contract fixtures rather than by rewriting literal five-case checks.
- Accepted submission files are append-only. Corrections use a new reviewed record rather than an
  unreviewed rewrite.
- Git history is the retention store for accepted submission records. The committed leaderboard
  transport file is rebuildable, and the Pages index/shards are disposable deployment artifacts.
- A growing valid corpus is expected. Per-file bounds protect reviewers and browsers; no aggregate
  byte threshold may wedge all later submissions or require deletion of accepted evidence.
