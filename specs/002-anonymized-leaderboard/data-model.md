# Data model: Anonymized benchmark leaderboard

**Feature**: [spec.md](spec.md)

**Normative contracts**:
[hardware-descriptor.schema.json](contracts/hardware-descriptor.schema.json),
[leaderboard-submission.schema.json](contracts/leaderboard-submission.schema.json), and
[leaderboard-dataset.schema.json](contracts/leaderboard-dataset.schema.json),
[leaderboard-index.schema.json](contracts/leaderboard-index.schema.json), and
[leaderboard-shard.schema.json](contracts/leaderboard-shard.schema.json)

The submission and projected-entry schema remain `1.0`. During the hybrid rollout, the existing
dataset contract continues to describe the bounded legacy monolith and its entry shape. The compact
index and shard schemas describe the separate closed `index_version: "1.0"` transport envelopes;
they do not migrate accepted submission content.

## Data boundary

The feature separates a private run report from the smaller record a contributor chooses to make
public. The exporter reads the private report and an ignored hardware descriptor locally. It writes
one public candidate per model. Accepted candidates are reviewed in pull requests and compiled into
the bounded committed leaderboard transport file: the legacy monolith while it fits, then the
constant-shape index. A trusted Pages build validates that file and always emits a temporary index
plus byte-bounded shard pages for browser delivery.

| Classification | May contain | Must not contain |
|----------------|-------------|------------------|
| Private run report | Existing minimized run evidence, local run ID, time, and local model selector | Raw prompt, completion, reasoning, tool arguments, endpoint, or credential |
| Local hardware descriptor | Exact CPU, memory, accelerator, execution, runtime product details, and optional runtime configuration intended for publication | Hostname, account, network, serial, inventory ID, device UUID, unused inventory, or notes |
| Public submission | Public model provenance, settings, structured hardware and runtime, optional runtime configuration, categorical cases, and rounded aggregate observations | Source run ID or time, local model selector, manifest digest, contributor field, or raw model content |
| Committed leaderboard index | Index version, submission schema version, total entry count, and shard count | Accepted row payloads, arbitrary paths or URLs, contributor identity, or unpublished local data |
| Temporary leaderboard shard | Accepted submission fields, derived quality percentages, and quality rank for one bounded page | Per-case text, contributor identity, arbitrary fetch targets, or unpublished local data |

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

Purpose: hold the smallest accepted evidence for one model artifact and one standard-suite run.

| Field | Type | Rules |
|-------|------|-------|
| schema_version | string | Must be `1.0` |
| submission_id | string | Lowercase SHA-256 digest of canonical content without this field |
| suite_version | string | Must be `1.0` for the first leaderboard |
| profile | string | Must be `standard` |
| hardware | object | Hardware portion of the validated public descriptor |
| runtime | object | Runtime portion of the validated public descriptor |
| runtime_configuration | object, optional | Closed configuration when the descriptor supplied it |
| model | object | Bounded public provenance with exactly one revision or digest |
| settings | object | Bounded generation controls, with an optional closed reasoning-effort enum |
| cases | list | The five standard cases in suite order |
| metrics | object | Counts plus rounded mean latency and weighted throughput |

Eligibility:

- The source report passes the existing closed validator.
- The report and selected model are `valid`, the profile is `standard`, preflight is `verified`, and
  runtime identity matches.
- All five standard cases are present and scored.
- Case counts agree with categorical outcomes. Unsafe mutation cannot count as a semantic pass.
- A throughput value is present only when usage covers every case.

The exporter creates a separate record for each selected model. It does not retain a grouping value
that would reveal which models were tested together.

### Value object: Public model provenance

Contains `display_name`, `source`, exactly one of `revision` or `digest`, `precision`, and
`declared_context_tokens`. `display_name` is 1–160 ASCII characters, `source` is 1–240 ASCII
characters, and `precision` is 1–80 ASCII characters. These three fields reject the same
descriptor-grade UUID, serial/inventory-label, network, URL, and email shapes used to prevent
private inventory from entering public descriptors, plus reviewer mentions, role prefixes, and
imperative instruction-injection shapes. ASCII-only validation prevents bidi and homoglyph ambiguity
in reviewer-visible model labels. `source` is a public registry/publisher/artifact-source label, not
a URL. The object does not contain the source report's local `model_id`.

These tighter rules apply only to the three model fields. The public environment descriptor keeps
its existing character set and validation behavior.

The portable JSON Schema records the field-specific ASCII and length boundaries. The Python and
browser validators are authoritative for descriptor-grade and reviewer-pattern rejection that is
not duplicated as a non-portable schema regular expression. Shared behavioral fixtures exercise the
same corpus through both implementations.

### Value object: Public case result

Contains only `case_id`, `outcome`, `route`, and `termination`. Semantic and exact-format counts are
derived from the categorical outcome. Per-case latency, token counts, reasoning presence, prompts,
completions, and tool arguments are not retained.

### Value object: Public metrics

Contains `case_count`, `semantic_pass_count`, `exact_format_pass_count`, `scored_case_count`,
`usage_coverage_cases`, `latency_ms_mean`, and `completion_tokens_per_second`. Performance values are
rounded to one decimal place. Throughput may be `null`.

Before hashing, the exporter normalizes public fields whose contract type is `number`. Equivalent
spellings such as `1`, `1.0`, and negative zero therefore produce the same canonical content ID for
those fields. Integer-only fields still reject decimal spellings. One-decimal performance and memory
precision is enforced by the Python validator rather than a fractional JSON Schema `multipleOf`,
which is not portable across binary floating-point validators.

The submission identifier establishes integrity of the canonical public content and identifies exact
duplicates. It does not establish provenance, attest that a benchmark ran, verify who performed it,
or validate the truth of self-reported measurements.

## Entity: Leaderboard publication bundle

Purpose: represent every accepted submission through a bounded committed transport file and a
temporary index plus zero or more bounded shard pages generated for every Pages deployment. This is
a transport decomposition, not a submission migration: accepted submission records remain schema
`1.0` and byte-for-byte retained.

### Value object: Committed leaderboard index

The deterministic `site/data/leaderboard.json` file is the only generated leaderboard artifact
committed to the repository after sharding activates.

| Field | Type | Rules |
|-------|------|-------|
| index_version | string | Must be `1.0` for this transport increment |
| schema_version | string | Must be `1.0`, shared by the projected entries |
| entry_count | integer | Total number of accepted entries across all shards |
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

For a safe code-only rollout, readers and builders also accept the existing bounded legacy monolith
shape `{schema_version, entry_count, entries}`. The current six-entry monolith stays byte-identical in
the mixed code change. While a deterministic rebuild remains within the legacy cap, it may remain
the canonical committed output. The first build that would cross that cap switches the committed
file to the constant-shape index; it never drops rows to preserve the monolith. A maintainer may
not perform a leaderboard-only early migration under this stage's protected boundary. Pages always
emits the index and shards in its temporary artifact, including while the committed source remains
the legacy monolith.

### Value object: Temporary leaderboard shard

A shard is a deterministic same-origin JSON page containing a bounded subset of derived leaderboard
entries. Each entry keeps submission ID, suite, profile, hardware, runtime, optional runtime
configuration, model, settings, and aggregate metrics. It adds `semantic_score_percent`,
`exact_format_score_percent`, and `rank`.

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
data cannot provide a path or URL. Search, hardware filtering, and alternate sorting operate only on
loaded rows until all pages are present. The site labels that scope and distinguishes no loaded match
from no published match.

### Pagination

Accepted rows first receive their deterministic global rank order. That ordered sequence is greedily
split at deterministic entry boundaries according to the exact UTF-8 byte length of the rendered
canonical shard JSON. Growth therefore adds contiguous numbered pages without relying on
platform-specific string length.

Every accepted `site/data/submissions/<submission_id>.json` remains retained and addressable by its
digest. The union of shard entry IDs must equal the accepted submission IDs exactly: no missing,
duplicate, or extra record is allowed. Pagination is never pruning. Malformed source records,
duplicate digests, inconsistent counts or IDs, and individually oversized inputs still fail closed;
only valid aggregate corpus growth selects more pages instead of failing.

Ranking uses descending semantic percentage, then descending exact-format percentage. Equal quality
pairs share a dense rank. Source, display name, and submission ID provide deterministic display order
inside a tie. Latency and throughput never affect rank.

## State transitions

1. A valid standard report plus a valid local descriptor becomes a prepared candidate.
2. The contributor reviews the complete candidate and chooses whether to publish it.
3. The candidate becomes proposed when it is added to a public pull request.
4. Continuous integration validates the closed contract, digest, filename, privacy rules, and
   deterministic committed leaderboard transport file.
5. Maintainer review and merge make the candidate accepted.
6. The default-branch Pages workflow byte-checks the canonical committed transport file, generates a
   deterministic index and bounded shards in a temporary site artifact, and deploys that artifact.

Accepted files are append-only. A correction creates a new candidate and uses normal review instead
of silently replacing published evidence.

Every public presentation labels the records self-reported and unverified. Repository validation can
establish contract conformance, privacy-boundary compliance, and content integrity; none of those
controls turns an anonymous report into attested benchmark provenance.
