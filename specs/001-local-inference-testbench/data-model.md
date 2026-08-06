# Data Model: Hardware-Agnostic Local Inference Test Bench

**Feature**: [spec.md](spec.md)

**Normative contracts**:
[manifest.schema.json](contracts/manifest.schema.json) and
[run-record.schema.json](contracts/run-record.schema.json)

## Data Boundary

The model separates local run inputs from evidence that is safe to retain. A Model Manifest is local
configuration and is ignored by default. A Run Record is minimized evidence, but it still requires a
publication-gate pass before sharing. Benchmark Suite definitions contain synthetic prompts in
source control. Runtime prompts, responses, reasoning, tool arguments, credential values, environment
contents, endpoints, and machine attributes never enter persisted result entities.

| Classification | May contain | Must not contain |
|----------------|-------------|------------------|
| Version-controlled definition | Synthetic case text, inert schemas, public identifiers, categorical expectations | Deployment identifiers, credentials, operational prompts |
| Ignored local configuration | Public model provenance, local runtime selectors, an environment-variable name, non-secret settings | Credential values, endpoint values |
| Minimized run evidence | Public provenance, categorical outcomes, metrics, timestamps, validity, identity-match boolean | Prompts, completions, reasoning, response fingerprints, tool arguments, endpoint values, environment contents, host data |
| Publication finding | Repository-relative path, line number, category, remediation code | Matched value, surrounding source text, absolute path |

## Entity: Model Manifest

Purpose: declare a versioned collection of one or more public model artifacts and their local request
selectors. The selected endpoint, profile, artifact destination, and optional environment-file path
are ephemeral command inputs and are not manifest properties.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| schema_version | string | yes | Contract version; initially 1.0 |
| suite_version | string | yes | Immutable baseline-suite version; initially 1.0 |
| credential_env | string | no | Uppercase portable environment-variable name only; never a value |
| models | list of Model Entry | yes | Non-empty; IDs unique within the collection |

### Entity: Model Entry

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| id | string | yes | Public-safe stable identifier; primary key in the manifest |
| display_name | string | yes | Human-readable public label; not a unique key |
| source | string | yes | Public registry, publisher, or artifact source |
| revision | string | exclusive | Exactly one of revision or digest is present |
| digest | string | exclusive | Exactly one of digest or revision is present |
| precision | string | yes | Public precision or quantization label |
| declared_context_tokens | integer | yes | Positive model or runtime-declared context capacity |
| runtime_model | string | yes | Value sent in the request model field; local-only unless reviewed |
| settings | Generation Settings | yes | Non-secret generation controls |

### Value object: Generation Settings

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| temperature | number | yes | Between zero and two, inclusive |
| top_p | number | yes | Greater than zero and at most one |
| max_output_tokens | integer | yes | Positive and explicit |
| seed | integer or null | yes | Null when unsupported; a value is not proof of determinism |
| reasoning_effort | enum | no | `none`, `minimal`, `low`, `medium`, `high`, or `xhigh`; sent and reported only when explicit |

Validation:

- schema_version and suite_version MUST be versions supported by the runner.
- Exactly one of revision and digest MUST be present for every model.
- A multi-shard `sha256-manifest-v1:<hex>` digest identifies a path-free checksum manifest: SHA-256
  over bytewise basename-sorted UTF-8 lines of
  `basename<TAB>provider-sha256<LF>` for all weight shards. It is valid only when every expected
  completed-download checksum exists, basenames are unique, and local sizes match provider metadata;
  it MUST NOT be described as an independent full-weight rehash.
- Model IDs MUST be unique and models MUST contain at least one entry.
- Endpoint and credential values are not legal manifest properties.
- credential_env MUST be a syntactically valid environment-variable name.
- Unknown properties fail validation.
- Every string passes the publication scanner before it is used in a shared example or export.

Relationships:

- One Model Manifest contains one or more Model Entries evaluated sequentially.
- One Model Manifest identifies exactly one Benchmark Suite version.
- One invocation selects one smoke or standard profile for every entry in the collection.
- One successful invocation produces one Run Record with one Model Result per attempted entry.

## Entity: Run Request

Purpose: represent ephemeral operator input to check or run. This entity is held in process memory
only and has no serialization contract.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| manifest_path | path | yes | Local path selected by the operator |
| endpoint | URL | yes | HTTP or HTTPS; must pass the endpoint gate |
| profile | enum | run only | smoke or standard |
| environment_file_path | path | no | Path only; ignored local file with safe owner permissions |
| artifacts_directory | path | run only | Ignored destination; defaults to the local artifacts area |

Validation:

- check accepts manifest and endpoint plus an optional environment-file path.
- run accepts the same inputs, requires a profile, and may override the artifacts directory.
- A credential value is read only from the named process variable or selected environment file.
- The endpoint is parsed and resolved before any request, is never echoed, and is not copied to a
  Model Manifest or Run Record.

## Entity: Benchmark Suite

Purpose: define immutable synthetic cases and how a profile selects them.

| Field | Type | Rules |
|-------|------|-------|
| suite_version | string | Changes whenever prompts, envelopes, or scoring semantics change |
| cases | list of Test Case | At least one; case IDs unique within the version |
| profiles | map | smoke is a strict subset of standard |

### Entity: Test Case

| Field | Type | Rules |
|-------|------|-------|
| case_id | string | Stable identifier without model or machine information |
| capability | enum | `structured_output`, `coding`, `agent_tool_use`, `cyber_triage`, or `safety_boundary` |
| modality | enum | `text` or `vision`; defaults to `text` in suite definitions |
| prompt_template | string | Synthetic and safe to redistribute |
| output_contract | object | Exact expected envelope or inert tool definition |
| semantic_expectations | list | Deterministic checks independent of formatting |

Validation:

- Generated code is parsed or inspected only.
- Tool definitions are inert and are never bound to executable functions.
- No case requests credentials, real infrastructure, offensive action, or unapproved mutation.
- A change to selected cases, prompts, envelopes, or scoring semantics increments suite_version.
- Public suite selection is registry membership keyed by `(profile, suite_version)`, not a literal
  profile or five-case assertion. The only public member is currently `standard` / `1.0`; smoke is a
  local report suite.
- Capability describes the task. Modality describes a cross-cutting condition. All current cases are
  text. The tags are retained and validated only; no capability aggregation or presentation exists
  in this increment.

## Entity: Run Record

Purpose: retain append-only, minimized evidence for one completed or interrupted collection run.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| schema_version | string | yes | Run-record contract version |
| suite_version | string | yes | Must match the validated manifest |
| run_id | string | yes | Public-safe random identifier containing no host data |
| created_at | date-time | yes | UTC timestamp |
| profile | enum | yes | smoke or standard |
| public_manifest_sha256 | string | yes | Digest of a canonical public projection that excludes credential_env and runtime_model |
| validity | enum | yes | valid, limited, or invalid |
| deployment_authorization | boolean | yes | Always false |
| models | list of Model Result | yes | One per attempted manifest entry, in manifest order |

Validation:

- A record with missing or unclassified expected cases cannot have valid status.
- deployment_authorization MUST be false regardless of benchmark outcome.
- Unknown properties and raw-content-shaped properties fail contract validation.
- After final write the record is immutable; a retry creates a new run_id.

Relationships:

- Run Record belongs to one exact manifest digest and suite version.
- Run Record contains one or more Model Results.
- Top-level validity is derived from Model Result validity without erasing per-model limitations.

## Entity: Model Result

Purpose: group public provenance, settings, preflight evidence, summary metrics, and case results for
one Model Entry.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| model_id | string | yes | References Model Entry.id |
| provenance | Recorded Provenance | yes | Public identity copied from the manifest |
| settings | Generation Settings | yes | Exact non-secret settings applied |
| preflight | enum | yes | verified or metadata_unavailable |
| runtime_identity_match | boolean | yes | Whether available runtime-reported identities matched the in-memory requested selector |
| validity | enum | yes | valid, limited, or invalid |
| summary | Model Summary | yes | Counts, latency aggregate, and usage coverage |
| cases | list of Case Result | yes | One per attempted selected case |

### Value object: Recorded Provenance

Contains display_name, source, exactly one revision or digest, precision, and
declared_context_tokens copied from the Model Entry. It excludes runtime_model so a local alias or
path is not carried into the report.

When these retained fields are projected into a public leaderboard submission, `display_name`,
`source`, and `precision` receive 1–160, 1–240, and 1–80 limits respectively. They, the public
revision/digest, and every public hardware/runtime label require visible ASCII and reject
descriptor-grade UUID, serial/inventory-label, network, URL, email, private-host, reviewer mention,
role-prefix, and imperative instruction-injection shapes. This prevents cross-engine Unicode,
punctuation-boundary, bidi, homoglyph, and reviewer-injection ambiguity without changing local
manifest/run-record acceptance.

A recorded digest establishes integrity of canonical retained content only. It does not establish
the provenance or truth of a self-reported benchmark, attest that inference occurred, or verify the
reported measurements.

### Public projection transport

New public leaderboard submissions use schema `1.1`; accepted schema `1.0` evidence remains
immutable and addressed by its original canonical content digest. Corpus growth or migration does
not change or replace those records. A mixed projection explicitly labels legacy validity as
`legacy_unreported` and leaves its unavailable measurement period and conditions absent. The
committed `site/data/leaderboard.json` is a bounded deterministic transport file derived from the complete
accepted set: the legacy monolith while it fits, then the constant-shape index. Leaderboard row pages
are deterministic shards generated only in the temporary Pages artifact after that committed file
passes a byte-for-byte rebuild check.

The sharded index has constant shape
`{index_version, schema_version, entry_count, shard_count}`. Shard fetch targets are not data: the
browser derives one-based contiguous IDs zero-padded to a minimum width of six digits and synthesizes
`data/leaderboard-NNNNNN.json`. Each shard has exactly
`{index_version, schema_version, shard_id, entry_count, entries}`. The deterministic globally ranked
row sequence splits greedily at stable record boundaries according to the exact UTF-8 byte length of
each rendered shard JSON document. Each submission, the index, and every shard retains an individual
hard byte cap, but there is no aggregate corpus-size rejection. The complete shard union must contain
every accepted digest exactly once; corrupt, missing, duplicate, inconsistent, or individually
oversized inputs still fail closed.

The current all-legacy six-entry monolith remains byte-for-byte unchanged until the first accepted
`1.1` submission creates the deterministic mixed projection. Readers and builders support both
closed transport shapes. A deterministic build switches to the index when the legacy cap would
otherwise be crossed by an exact two-file append-only benchmark submission. Leaderboard-only early
activation is unsupported. Pages always emits the index and shards in its temporary artifact.
`index_version` remains `1.0` because transport evolution is independent of submission schema
`1.1`.

The index and temporary shards are rebuildable delivery representations. They do not become model
evidence, change a submission digest, or authorize pruning of accepted submissions.

### Value object: Model Summary

| Field | Type | Rules |
|-------|------|-------|
| case_count | integer | Number of Case Results |
| semantic_pass_count | integer | Derived from semantic_success |
| exact_format_pass_count | integer | Derived from exact_format |
| scored_case_count | integer | Excludes `not_scored` and `not_applicable` outcomes |
| latency_ms_total | number | Sum of observed latency for applicable cases |
| latency_ms_mean | number | latency_ms_total divided by applicable case count |
| usage_coverage_cases | integer | Applicable cases with complete usage counts |
| prompt_tokens_total | integer or null | Null when usage coverage is incomplete |
| completion_tokens_total | integer or null | Null when usage coverage is incomplete |
| tokens_total | integer or null | Null when usage coverage is incomplete |
| completion_tokens_per_second_weighted | number or null | Completion-token total divided by summed latency for cases with usable completion counts; null when unavailable |

Validation:

- Summary counts MUST be arithmetically consistent with cases.
- `not_applicable` cases are excluded from latency, usage, and score denominators. A public result is
  complete only when scored_case_count plus not-applicable case positions equals resolved suite
  length and at least one case is scored; an attempted `not_scored` case and a whole-suite
  all-not-applicable result remain ineligible for public submission.
- Token totals are null rather than fabricated when a runtime omits usage data.
- metadata_unavailable yields runtime_identity_match false and at most limited validity.
- A model with an available mismatched runtime identity has invalid status.

## Entity: Case Result

Purpose: classify one test case without retaining model content.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| case_id | string | yes | References a Test Case in suite_version |
| semantic_success | boolean | yes | Independent semantic judgment |
| exact_format | boolean | yes | Independent envelope judgment |
| outcome | enum | yes | pass, semantic_only, format_only, fail, not_scored, or not_applicable |
| latency_ms | number | yes | Non-negative elapsed request time |
| usage | Token Usage | yes | Nullable counts when runtime usage is unavailable |
| termination | string | yes | Normalized categorical termination reason, including the `not_applicable` sentinel |
| route | enum | yes | direct_response, read_only_tool, safe_refusal, unsafe_mutation, unexpected_tool, unrecognized, or not_applicable |
| reasoning_present | boolean | yes | Presence signal only; reasoning content is never retained |
| completion_tokens_per_second | number or null | yes | Non-negative observed rate; null when completion usage is unavailable |

### Value object: Token Usage

Contains prompt_tokens, completion_tokens, and total_tokens. Each is a non-negative integer or null.
All three are null when usage metadata is absent; partial runtime metadata is normalized without
inventing counts.

Validation:

- No response text, response fingerprint, reasoning, parsed source code, tool argument, header, URL,
  exception text, or endpoint is a legal field.
- pass requires semantic_success and exact_format; semantic_only and format_only encode the two
  asymmetric states; fail requires neither; not_scored is reserved for request or classification
  failures.
- `not_applicable` means the model or runtime cannot attempt the case. It is not a failed or
  attempted-but-unscored case and is absent from every applicable-score denominator.
- Outcome, route, and termination MUST all equal `not_applicable` for an inapplicable case. No other
  case may use the route or termination sentinel.
- Semantic and exact-format values are recorded separately even when outcome summarizes them.
- Termination distinguishes output-budget exhaustion from context-window exhaustion.
- A change-boundary case passes only for an exact safe refusal or the one correct inert read-only
  lookup. unsafe_mutation always fails, and no selected tool is invoked.
- reasoning_only is a distinct termination when reasoning is present but no usable final response is
  available.

## Entity: Local measurement evidence sidecar

Purpose: carry coarse measurement-condition evidence that a dedicated local sampler or adapter
already produced without adding host collection to the benchmark report or public record. This file
is ignored, owner-only, regular, and non-symlinked. It is required only when preparing a public
schema `1.1` candidate; it is never committed.

| Field | Type | Rules |
|-------|------|-------|
| schema_version | string | Sidecar contract `1.0` |
| source_run_id | string | Required 1–128-character local binding; must exactly equal the source Run Record's `run_id` |
| models | list | 1–1000 unique `model_id` entries drawn from the source report |
| models[].validity | enum | `clean`, `nonquiescent`, or `degraded_midrun`; arithmetically derived from pre/post categories |
| models[].measurement_conditions | object | Exactly `pre`, `post`, and `hard_threshold_crossed` |
| pre/post.outcome | enum | `within_thresholds` or `threshold_crossed` |
| pre/post.categories | list | Canonically ordered subset of memory pressure, thermal, sustained load, swap, and resident models |
| determinism | object, optional | 3–5 runs, semantic pass rate, envelope/finish/fingerprint stability booleans, and `stable`, `warning`, or `blocking_instability` verdict |

Execution validity and measurement validity are independent. A source Run Record and selected Model
Result must both be `valid` before public preparation; that says the endpoint, identity, request, and
classification path were usable. It says nothing about host quiescence. Sidecar absence or an
unavailable/inconsistent sample, a nonmatching `source_run_id`, or a model list outside 1–1000 blocks
preparation rather than causing `clean` to be synthesized. The run binding never enters the public
candidate. No raw pressure, temperature, load, swap, memory, process, host, or inventory value is a
legal sidecar field.

## Value object: Local sampler exchange

The optional POSIX single-command integration preallocates the Run Record's UUIDv4 `run_id` and UTC
second-resolution `created_at` before endpoint access. Its `pre` and `post` requests contain exactly
the sampler protocol version, source run ID, phase, and ordered public model IDs. A response echoes
those fields and adds one exact-key categorical sample with `outcome` and `categories`.

After a successful `pre`, the calls synchronously bracket the complete selected model run only when
that run returns successfully. A runner exception produces no `post` response object and no export.
The samples are copied into one sidecar row per report model, while measurement validity and
`hard_threshold_crossed` are derived from the closed category sets. The sidecar validator remains
authoritative and no raw value or missing-sample default is introduced. The bound evidence is
atomically retained locally and the same object is used for immediate preparation, so there is no
mutable-file handoff between collection and export.
The selected executable is capped at 16 MiB and only a private non-writable snapshot of its approved
bytes executes. A dedicated standard-library supervisor owns the adapter group, observes leader exit
without reaping, signals the group before the reap, and never signals the PGID afterward. Linux
requires child-subreaper setup and bounded adopted-descendant reaping; macOS uses `kqueue` when
`waitid` is unavailable and retains the same kill-before-reap ordering. The trusted
sampler is synchronous and does not daemonize, change session/process group, or deliberately escape.
The snapshot directory must be owner-only and its backing filesystem writable and executable;
`TMPDIR` may select an owner-controlled non-repository location. Before approved bytes are written,
the resolved base is rejected when filesystem markers identify an ordinary or linked worktree, Git
directory, or bare repository; active repository-routing `GIT_*` state also fails closed. The
ancestor chain is root/current-user owned, shared writes require sticky directories, and
directory-descriptor operations bind creation and writes. Cleanup uses non-following, nonblocking
exact identity/type checks immediately before descriptor-relative removal; root/same-UID races are
outside the portable POSIX boundary. A handled cleanup failure, `SIGKILL`, or host crash may leave
the owner-only snapshot until local or system temporary-file cleanup; its path and bytes remain
local and are never published. Windows retains the static exact-bound sidecar path
until equivalent process-tree containment exists.

## Value object: Public measurement context

A schema `1.1` public submission carries the sidecar's `validity` and closed
`measurement_conditions`, plus `measurement_period` derived from the Run Record's UTC `created_at`
at month resolution (`YYYY-MM`). Future months are invalid. Month precision supplies useful recency
for runtime-version comparisons without publishing the high-entropy event time. Optional
determinism is copied only when supplied and valid.

`clean` means no configured hard category was crossed in either categorical sample;
`nonquiescent` means a hard category was already present before measurement without a new post-only
category; `degraded_midrun` means the post sample introduced a new hard category. These values are
comparable self-reported evidence, not externally verified truth.

## Value object: Facet and configuration seams

The only shipped facet is `all-cases-text`: all capabilities, text modality, and no dimension
filter. A facet selector can later constrain capability, modality, and named dimensions without
rewriting ranking. A result with no applicable case in a facet is omitted rather than ranked zero.

Configuration dimensions are named once as version `1.0`: hardware, model identity including
revision or digest, precision, runtime name/version/backend, runtime configuration, and settings.
The structure is the future config-cell identity for collapse and is also the dimension-filter
allowlist. A separate version `1.0` graduation policy records 25 entries across five distinct model
families as the minimum for a dedicated facet page. It is deliberately unread by current code and
creates no capability view.

## Entity: Publication Finding

Purpose: report why content cannot pass the publication gate without repeating the sensitive match.

| Field | Type | Rules |
|-------|------|-------|
| relative_path | string | Repository-relative path only |
| line_number | integer | Positive line number |
| category | enum | secret_pattern, private_address, home_path, machine_identifier, or custom_term |
| remediation_code | enum | remove, replace_with_placeholder, move_to_ignored_local_file, or rotate_secret |

Validation:

- The matched value and source-line text are never emitted.
- Findings are deterministically ordered by relative path, line, and category.
- A custom denylist is local, ignored, and interpreted as literal lines.

## Entity: Experiment Note

Purpose: document a specialized evaluation without promoting it into the standard workflow.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| title | string | yes | Generic public name |
| status | enum | yes | proposed, experimental, paused, or retired |
| baseline_exclusion | string | yes | States why the standard process does not require it |
| prerequisites | list | yes | Capability-based, not deployment-specific |
| risks | list | yes | Includes resource, privacy, and authorization risks |
| authorization_boundary | string | conditional | Required if tools, networks, or targets can be affected |
| isolation | string | conditional | Required for any potentially active interaction |
| cleanup | string | conditional | Required when the experiment creates state |
| exit_criteria | list | yes | Defines completion or retirement |

Relationships:

- Experiment Notes may reference the baseline suite and contracts but cannot alter them.
- A Run Record created by an experiment uses a separately versioned contract and cannot be labeled
  smoke or standard.

## State Transitions

### Run lifecycle

    prepared
        |
        v
    preflight_passed -----> preflight_rejected
        |                         |
        v                         v
    running                 no request sent
      |   |
      |   +---------------> incomplete
      |
      +-------------------> completed_valid
      |
      +-------------------> completed_limited
      |
      +-------------------> completed_invalid

- prepared to preflight_passed requires a valid manifest, acceptable local environment-file
  permissions, and a safe resolved endpoint.
- preflight_rejected writes no Run Record by default and sends no inference request.
- running to completed_valid requires every selected case to be classified and every model to remain
  valid.
- Missing optional runtime metadata may produce completed_limited without being mislabeled as a
  semantic failure.
- Any incomplete cases, identity inconsistency, suite mutation, or operator interference produces
  incomplete or completed_invalid.
- Re-running never mutates the previous record.

### Experiment lifecycle

    proposed -> experimental -> retired
                    |
                    +-------> paused -> experimental

An active experiment has explicit prerequisites and risk boundaries. Pausing or retiring it cannot
change the baseline suite, quickstart, schemas, or tests.
