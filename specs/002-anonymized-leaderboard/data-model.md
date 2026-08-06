# Data model: Anonymized benchmark leaderboard

**Feature**: [spec.md](spec.md)

**Normative contracts**:
[hardware-descriptor.schema.json](contracts/hardware-descriptor.schema.json),
[measurement-evidence.schema.json](contracts/measurement-evidence.schema.json),
[leaderboard-submission.schema.json](contracts/leaderboard-submission.schema.json),
[leaderboard-dataset.schema.json](contracts/leaderboard-dataset.schema.json),
[leaderboard-index.schema.json](contracts/leaderboard-index.schema.json), and
[leaderboard-shard.schema.json](contracts/leaderboard-shard.schema.json)

New submissions and projected entries use schema `1.1`. Accepted schema `1.0` submissions remain
byte-for-byte retained as legacy evidence. During migration, the existing dataset contract continues
to describe the bounded all-legacy monolith and its entry shape. The compact index and shard schemas
retain the separate closed `index_version: "1.0"` transport envelopes; a transport version is not a
submission schema version and does not rewrite accepted content.

## Data boundary

The feature separates a private run report from the smaller record a contributor chooses to make
public. The exporter reads the private report, an ignored hardware descriptor, and an ignored
categorical measurement-evidence sidecar locally. It writes one public candidate per model. Accepted
candidates are reviewed in pull requests and compiled into
the bounded committed leaderboard transport file: the legacy monolith while it fits, then the
constant-shape index. A trusted Pages build validates that file and always emits a temporary index
plus byte-bounded shard pages for browser delivery.

| Classification | May contain | Must not contain |
|----------------|-------------|------------------|
| Private run report | Existing minimized run evidence, local run ID, time, and local model selector | Raw prompt, completion, reasoning, tool arguments, endpoint, or credential |
| Local hardware descriptor | Exact CPU, memory, accelerator, execution, runtime product details, and optional runtime configuration intended for publication | Hostname, account, network, serial, inventory ID, device UUID, unused inventory, or notes |
| Local measurement sidecar | Exact source run ID binding; 1–1000 per-model pre/post threshold outcomes and closed categories; optional aggregate determinism | Raw host values, additional timestamps, paths, process names, inventory, free text, or inferred clean state |
| Public submission | Public model provenance, settings, structured hardware and runtime, optional runtime configuration, categorical cases, measurement month/conditions, and rounded aggregate observations | Source run ID or precise time, local model selector, manifest digest, contributor field, or raw model content |
| Committed leaderboard index | Index version, submission schema version, total entry count, and shard count | Accepted row payloads, arbitrary paths or URLs, contributor identity, or unpublished local data |
| Temporary leaderboard shard | Bounded configuration cells, representative counts/Wilson bands, corroboration, performance spread, and plausibility | Per-case text, contributor identity, unbounded source-ID/month arrays, arbitrary fetch targets, or unpublished local data |

Hardware and performance can weakly characterize a setup. The exporter removes direct machine
identifiers, but the operator still reviews the candidate before opening a public pull request.

## Entity: Public environment descriptor

Purpose: state the exact hardware used for inference and the runtime that served the model without
collecting general machine inventory.

| Field | Type | Rules |
|-------|------|-------|
| schema_version | string | Must be `1.0` |
| hardware.cpu.model | string | Public product name, 1 to 200 characters |
| hardware.cpu.logical_cores | integer | 1 to 4096 |
| hardware.memory.system_gb | number | 0.1 to 1,000,000 GB, one decimal place |
| hardware.memory.architecture | enum | `shared`, `discrete`, `mixed`, or `unknown` |
| hardware.accelerators | list | Zero to eight accelerator descriptions used for inference |
| hardware.execution_mode | enum | `cpu_only`, `accelerator_only`, `hybrid`, or `unknown` |
| runtime.name | string | Public runtime name, 1 to 100 characters |
| runtime.version | string | Public runtime version, 1 to 100 characters |
| runtime.backend | string | Public compute backend, 1 to 100 characters |
| runtime_configuration | object, optional | Closed snapshot; if present, all four fields below are required |
| runtime_configuration.context_window_tokens | integer or null | 1 to 9,007,199,254,740,991; `null` means not known |
| runtime_configuration.concurrent_requests | integer or null | 1 to 4096; `null` means not known |
| runtime_configuration.speculative_decoding | enum | `enabled`, `disabled`, or `unknown` |
| runtime_configuration.offload_mode | enum | `none`, `partial`, `maximum`, `not_applicable`, or `unknown` |

The optional object is carried only when the operator supplies it; validators never synthesize
defaults. When `context_window_tokens` is known, it cannot be smaller than the submitted
`settings.max_output_tokens` value.

Each accelerator description has a `kind`, product `model`, positive `count`, and `memory_gb`.
`count` groups identical devices used for inference. `null` means that separately scoped accelerator
memory is not being claimed. A shared-memory descriptor requires `null` for every row, while a
discrete-memory descriptor gives memory for every row. Mixed and unknown architectures may contain
either representation. Exact duplicate accelerator rows are not allowed.

Validation:

- The descriptor is a regular, non-symlink file that is ignored by Git.
- On systems with POSIX modes, the descriptor is owner-readable and owner-writable only.
- `cpu_only` has no accelerators. `accelerator_only` and `hybrid` have at least one.
- The object is closed. There is no field for a host label, device identifier, network value, or
  free-form note.
- The existing public-data walker rejects prohibited local data in every string.

## Entity: Leaderboard submission

Purpose: hold the smallest accepted evidence for one model artifact and one registered public-suite
run.

| Field | Type | Rules |
|-------|------|-------|
| schema_version | string | Must be `1.1` for a new submission; retained `1.0` files are legacy only |
| submission_id | string | Lowercase SHA-256 digest of canonical content without this field |
| suite_version | string | Resolved with profile through the public suite registry; currently `1.0` |
| profile | string | Public registry member; currently `standard` |
| measurement_period | string | Required UTC month `YYYY-MM`; future months rejected |
| validity | enum | `clean`, `nonquiescent`, or `degraded_midrun` |
| measurement_conditions | object | Required closed pre/post categorical evidence |
| determinism | object, optional | Closed 3–5-run aggregate stability evidence |
| hardware | object | Hardware portion of the validated public descriptor |
| runtime | object | Runtime portion of the validated public descriptor |
| runtime_configuration | object, optional | Closed configuration when the descriptor supplied it |
| model | object | Bounded public provenance with exactly one revision or digest |
| settings | object | Bounded generation controls, with an optional closed reasoning-effort enum |
| cases | list | Complete ordered case list from the resolved suite registry |
| metrics | object | Counts plus rounded mean latency and weighted throughput |

Eligibility:

- The source report passes the existing closed validator.
- The report and selected model have `valid` execution status, preflight is `verified`, runtime
  identity matches, and profile/suite membership resolves through the public suite registry.
- Every resolved case is represented; `scored_case_count` plus `not_applicable` positions equals
  suite length, and at least one case is scored. An attempted `not_scored` case and a whole-suite
  all-not-applicable result are not submission-eligible.
- Case counts agree with categorical outcomes. Unsafe mutation cannot count as a semantic pass.
- A throughput value is present only when usage covers every applicable case.
- The measurement sidecar is owner-only, ignored, categorical, exact-matched to the source run, and
  supplies 1–1000 unique model rows with an exact per-model match. Its absence, stale binding,
  excess size, or inconsistency blocks export; execution validity cannot synthesize measurement
  validity, and the run binding cannot enter public output.

The exporter creates a separate record for each selected model. It does not retain a grouping value
that would reveal which models were tested together.

### Value object: Public model provenance

Contains `display_name`, `source`, exactly one of `revision` or `digest`, `precision`,
`declared_context_tokens`, and the closed `parameter_scale` object. `parameter_scale` contains
nullable `total_billions` and `active_billions`; known values are positive, at most 1,000,000, and
have at most three decimal places, active cannot exceed total, and active must be null when total is
null. A compatible older manifest may omit this provenance, but schema `1.1` export writes explicit
nulls rather than parsing a display/source label. `display_name` is 1–160 ASCII characters, `source` is 1–240 ASCII
characters, and `precision` is 1–80 ASCII characters. These values and the revision/digest reject
descriptor-grade UUID, serial/inventory-label, network, URL, email, private-host, reviewer mention,
role-prefix, and instruction-injection shapes. The public hardware and runtime labels use the same
visible-ASCII, reviewer-neutral rule. This prevents cross-engine Unicode, bidi, homoglyph, and
punctuation-boundary ambiguity. `source` is a public registry/publisher/artifact-source label, not a
URL. The object does not contain the source report's local `model_id`.

The portable JSON Schema records the field-specific ASCII and length boundaries. The Python and
browser validators are authoritative for descriptor-grade and reviewer-pattern rejection that is
not duplicated as a non-portable schema regular expression. Shared behavioral fixtures exercise the
same corpus through both implementations.

### Value object: Public case result

Contains only `case_id`, `capability`, `modality`, `outcome`, `route`, and `termination`.
`capability` is one of `structured_output`, `coding`, `agent_tool_use`, `cyber_triage`, or
`safety_boundary`; `modality` is `text` or `vision`. Both must match the resolved suite registry.
All current standard cases are text. Semantic and exact-format counts are derived from the
categorical outcome. `not_applicable` means the model or runtime cannot attempt the case and is
excluded from every denominator; `not_scored` remains an attempted or transport/classification
failure. An inapplicable case uses `not_applicable` for outcome, route, and termination; the route and
termination sentinel is invalid for every other outcome. Per-case latency, token counts, reasoning
presence, prompts, completions, and tool arguments are not retained. No capability aggregation or
display is introduced in schema `1.1`.

### Value object: Public measurement evidence

`measurement_conditions` has exactly `pre`, `post`, and `hard_threshold_crossed`. Each sample has an
`outcome` of `within_thresholds` or `threshold_crossed` and a unique canonical-order subset of
`memory_pressure`, `thermal`, `sustained_load`, `swap`, and `resident_models`. The boolean is true
exactly when either sample contains a category. `clean`, `nonquiescent`, and `degraded_midrun` are
derived consistently from those categories.

The optional determinism object records `n_runs` from 3 through 5, `semantic_pass_rate`, booleans for
envelope-class, finish-reason, and fingerprint stability, and a consistent verdict of `stable`,
`warning`, or `blocking_instability`. The pass rate must be within half of one six-decimal unit of an
integer pass count divided by `n_runs`, accepting both exact fractional JSON values and their
six-decimal forms. It contains no response fingerprint or content. The required
`measurement_period` is derived from the source report's UTC creation month. Month resolution was
chosen to surface runtime aging without publishing a precise, high-entropy event time.

The local sidecar also carries `source_run_id`, which must exactly equal the source Run Record's
`run_id`, and its unique `models` list is bounded to 1–1000 entries. This binding prevents stale
categorical evidence from being attached to another report. It is validation-only: neither run ID
appears in the public submission or any leaderboard projection.

### Value object: Public metrics

Contains `case_count`, `semantic_pass_count`, `exact_format_pass_count`, `scored_case_count`,
`usage_coverage_cases`, `latency_ms_mean`, and `completion_tokens_per_second`. Performance values are
rounded to one decimal place. Score percentages use exact integer-ratio, half-up rounding to one
decimal so Python and browser validation agree at ties. Throughput may be `null`.

Before hashing, the exporter normalizes public fields whose contract type is `number`. Equivalent
spellings such as `1`, `1.0`, and negative zero therefore produce the same canonical content ID for
those fields. Integer-only fields still reject decimal spellings. One-decimal performance and memory
precision is enforced by the Python validator rather than a fractional JSON Schema `multipleOf`,
which is not portable across binary floating-point validators.

The submission identifier establishes integrity of the canonical public content and identifies exact
duplicates. It does not establish provenance, attest that a benchmark ran, verify who performed it,
or validate the truth of self-reported measurements.

The Pages picker parses raw candidate text strictly, including duplicate decoded member-name
rejection, runs the parallel closed validator, and recomputes this payload-minus-ID digest before a
successful preview. It remains a convenience check; Python and pull-request validation are the
authoritative publication boundary.

## Entity: Leaderboard publication bundle

Purpose: represent deterministic configuration-cell aggregates through a bounded committed
transport file and a temporary index plus zero or more bounded shard pages generated for every Pages
deployment. This is a transport decomposition, not a destructive submission migration: every source
submission remains digest-addressable, accepted `1.0` records remain byte-for-byte retained, and new
records use `1.1`.

### Value object: Committed leaderboard index

The deterministic `site/data/leaderboard.json` file is the only generated leaderboard artifact
committed to the repository after sharding activates.

| Field | Type | Rules |
|-------|------|-------|
| index_version | string | Must be `1.0` for this transport increment |
| schema_version | string | Projected-entry schema: `1.0` for the unchanged all-legacy monolith, otherwise `1.1` |
| entry_count | integer | Total number of projected configuration cells across all shards |
| shard_count | integer | Number of contiguous ordinal shards |

This constant-shape index contains no row payload, path, URL, or attacker-selected identifier. Shard
IDs are the one-based contiguous decimal range from one through `shard_count`, zero-padded to a
minimum width of six digits.

The index is derived from every validated submission and written in canonical deterministic JSON.
When it is the committed canonical form, pull-request CI and the Pages workflow rebuild it
independently and require a byte-for-byte match. During legacy-monolith retention, they apply that
same byte check to the monolith before Pages generates the temporary index. The exact benchmark
pull-request boundary remains one added digest-named submission blob plus the one modified
leaderboard transport file; shard files are rejected as pull-request changes.

The index has an individual hard byte cap. Its constant-shape representation prevents valid corpus
volume from growing the file beyond that bound. Corpus row volume is not measured against the old
aggregate dataset cap.

Readers and builders accept the existing bounded legacy monolith shape
`{schema_version, entry_count, entries}`. The current six-entry all-legacy monolith stays
byte-identical until a schema `1.1` submission is accepted. Once current-schema evidence exists, the
deterministic projection is `1.1`; each row records its source submission schema, and retained
legacy rows use `validity: legacy_unreported` with null period and conditions. Those nulls say the
properties were never measured; they are not defaults. The transport still switches to the
constant-shape index when its monolith cap requires it and never drops rows. Pages always emits the
index and shards in its temporary artifact.

### Value object: Temporary leaderboard shard

A shard is a deterministic same-origin JSON page containing a bounded subset of derived
configuration cells. Each current cell keeps one score-neutral representative's submission ID,
source schema, suite, profile, measurement period/validity/conditions, hardware, runtime, optional
runtime configuration, model, settings, and aggregate metrics. It adds the facet ID, config-cell
identity, fixed corroboration summary, representative Wilson intervals, performance distributions,
non-authoritative plausibility annotation, and dense rank band. Legacy representatives retain their
explicit missing-evidence annotation.

| Field | Type | Rules |
|-------|------|-------|
| index_version | string | Must be `1.0` and match the committed or temporary index |
| schema_version | string | Must match the index's projected-entry schema version |
| shard_id | string | One-based contiguous ordinal, zero-padded to a minimum width of six digits |
| entry_count | integer | Must equal the number of entries in this shard |
| entries | list | Derived leaderboard rows in deterministic global rank order |

Each shard is emitted only after the canonical committed transport file passes its byte check, into
the temporary static-site directory uploaded as the Pages artifact. Shards are never committed, and
the temporary output is discarded after deployment. Each shard has its own hard byte cap. The
browser derives a one-based ID padded to at least six digits from the validated index, synthesizes
`data/leaderboard-NNNNNN.json`, verifies bounded shape and size, and fetches pages on demand; public
data cannot provide a path or URL. The monolith, index, and shards are decoded with fatal UTF-8,
reject byte-order marks, and use the strict duplicate-member-rejecting parser before their closed
shapes are validated. Search, hardware filtering, and alternate sorting operate only on loaded rows
until all pages are present. The site labels that scope and distinguishes no loaded match from no
published match.

### Pagination

Accepted rows first receive their deterministic global rank order. That ordered sequence is greedily
split at deterministic entry boundaries according to the exact UTF-8 byte length of the rendered
canonical shard JSON. Growth therefore adds contiguous numbered pages without relying on
platform-specific string length.

Every accepted `site/data/submissions/<submission_id>.json` remains retained and addressable by its
digest. Each validated source record must contribute exactly once to one configuration cell's
corroboration count, but only the deterministic representative digest appears in the bounded shard.
Pagination is never pruning. Malformed source records, duplicate digests, inconsistent counts or
cells, and individually oversized inputs still fail closed; only valid aggregate corpus growth
selects more pages instead of failing.

Ranking uses outward-rounded 95% Wilson intervals from the representative raw pass counts. Repeated
anonymous records never pool the quality denominator. Semantic interval connected components are
primary and exact-format connected components inside each semantic component are secondary; the
result is a dense transitive rank band. Submission ID is the neutral final tiebreak inside a band.
Source/display names, latency, throughput, corroboration, and plausibility never affect rank.

### Value object: Facet selector and configuration dimensions

The only shipped facet is `all-cases-text`, selecting every capability, text modality, and no
dimension filters. Ranking accepts a facet selector so later capability or modality views are
additive. A row with no applicable case in the selected facet is omitted rather than ranked zero.
Every accepted public candidate must still contain at least one scored case across its complete
suite, preserving the append-only candidate-plus-generated-data boundary. Dataset validation accepts
registry-bounded subset counts even though no additional facet is rendered in this release.
Accepted records contain only full-suite aggregate performance, not per-case timing or usage. A
strict subset facet therefore sets latency and throughput to `null` and usage coverage to zero;
consumers must not interpret the source suite's aggregate performance as a facet measurement.
A strict subset projection uses logical leaderboard schema `1.1` even when every retained source is
legacy `1.0`, so those null semantics and explicit `legacy_unreported` annotations remain valid. The
shipped default all-legacy full-suite projection alone preserves the byte-identical `1.0` monolith.

Configuration-dimension structure `1.0` names hardware, model identity including revision or digest
and parameter scale, precision, runtime name/version/backend, runtime configuration, and settings.
The builder canonicalizes these named dimensions and groups them only inside the same facet, profile,
and suite. An absent runtime configuration is null. The cell publishes the config digest and fixed
key/selection versions. Representative selection prefers clean, nonquiescent, degraded-midrun, then
legacy; newest period and lowest digest break remaining ties. Fixed validity summaries publish
counts and earliest/latest periods without an unbounded observation list.

Each cell also publishes sample-count/median/minimum/maximum distributions for available latency and
throughput. A versioned caution-only plausibility result combines the existing coarse hardware class
with the explicit active-or-total parameter bucket; any outlier flags the cell, unknown inputs are
`not_evaluated`, and the annotation never gates or ranks.

This named structure
is the dimension-filter allowlist and config-cell identity. Facet
graduation policy `1.0` records a minimum of 25 entries across five distinct model families. Nothing
reads that policy in this release; it creates no view, score, or page.

### Value object: Derived configuration-cell evidence

Projected schema `1.1` entries add these exact closed objects to the representative fields:

| Field | Type | Rules |
|-------|------|-------|
| facet_id | string | `all-cases-text` for the shipped projection |
| config_cell | object | Exact `key_version`, `selection_version`, and canonical config `digest`; both versions are `1.0` |
| corroboration.accepted_record_count | integer | At least one; sum of the four validity counts |
| corroboration.by_validity | object | Exact `clean`, `nonquiescent`, `degraded_midrun`, and `legacy_unreported` summaries |
| score_intervals.method | string | `wilson_95` |
| score_intervals.semantic | interval | Integer outward-rounded bounds from representative semantic passes/scored cases |
| score_intervals.exact_format | interval | Integer outward-rounded bounds from representative exact-format passes/scored cases |
| performance_distribution | object | Exact latency and throughput distribution objects |
| plausibility | object | Versioned closed caution-only annotation |

Each validity summary has `count`, `earliest_period`, and `latest_period`. Zero count requires null
periods. Legacy periods are always null. A current nonzero count requires two valid months with
earliest no later than latest.

Each distribution has `sample_count`, `median`, `minimum`, and `maximum`. Zero samples require three
null values. Nonzero samples require finite nonnegative values at no more than two decimal places,
with minimum no greater than median and median no greater than maximum. Latency includes only
available full-facet mean-latency observations; throughput excludes nulls.

The plausibility object has `policy_version: "1.0"`, a status of `within_envelope`, `caution`, or
`not_evaluated`, a closed basis containing hardware class, size bucket, and whether active or total
billions were used, evaluated/outside record counts, and a canonical unique signal subset of
`latency_below_envelope` and `throughput_above_envelope`. Zero evaluated records is exactly
`not_evaluated`; any outside record is exactly `caution`; otherwise the status is
`within_envelope`.

## State transitions

1. A valid registered-suite execution report plus a valid local descriptor and owner-only
   categorical measurement sidecar bound to that exact run becomes a schema `1.1` prepared
   candidate; the binding itself is discarded from public bytes.
2. The contributor reviews the complete candidate and chooses whether to publish it.
3. The candidate becomes proposed when it is added to a public pull request.
4. Continuous integration validates the closed contract, digest, filename, privacy rules, and
   deterministic committed leaderboard transport file.
5. Maintainer review and merge make the candidate accepted.
6. The default-branch Pages workflow byte-checks the canonical committed transport file, generates a
   deterministic index and bounded shards in a temporary site artifact, and deploys that artifact.

Accepted schema `1.0` files remain in state 5 indefinitely. They are never promoted to `1.1` by
inference; only their mixed leaderboard projection receives an explicit legacy annotation. A new
`1.0` proposal is rejected at state 3 and must be regenerated.

Accepted files are append-only. A correction creates a new candidate and uses normal review instead
of silently replacing published evidence.

Every public presentation labels the records self-reported and unverified. Repository validation can
establish contract conformance, privacy-boundary compliance, and content integrity; none of those
controls turns an anonymous report into attested benchmark provenance.
