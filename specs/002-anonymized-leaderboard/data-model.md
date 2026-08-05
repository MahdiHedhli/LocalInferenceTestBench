# Data model: Anonymized benchmark leaderboard

**Feature**: [spec.md](spec.md)

**Normative contracts**:
[hardware-descriptor.schema.json](contracts/hardware-descriptor.schema.json),
[leaderboard-submission.schema.json](contracts/leaderboard-submission.schema.json), and
[leaderboard-dataset.schema.json](contracts/leaderboard-dataset.schema.json)

## Data boundary

The feature separates a private run report from the smaller record a contributor chooses to make
public. The exporter reads the private report and an ignored hardware descriptor locally. It writes
one public candidate per model. Accepted candidates are reviewed in pull requests and compiled into
the static Pages dataset.

| Classification | May contain | Must not contain |
|----------------|-------------|------------------|
| Private run report | Existing minimized run evidence, local run ID, time, and local model selector | Raw prompt, completion, reasoning, tool arguments, endpoint, or credential |
| Local hardware descriptor | Exact CPU, memory, accelerator, execution, and runtime product details intended for publication | Hostname, account, network, serial, inventory ID, device UUID, unused inventory, or notes |
| Public submission | Public model provenance, settings, structured hardware and runtime, categorical cases, and rounded aggregate observations | Source run ID or time, local model selector, manifest digest, contributor field, or raw model content |
| Generated dataset | Accepted submission fields, derived quality percentages, and quality rank | Per-case text, contributor identity, or unpublished local data |

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
| model | object | Public provenance with exactly one revision or digest |
| settings | object | Temperature and top-p use at most six fractional digits; output limit and optional seed are integers |
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
`declared_context_tokens`. It does not contain the source report's local `model_id`.

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

## Entity: Leaderboard dataset

Purpose: provide one deterministic, browser-readable file built from all accepted submissions.

| Field | Type | Rules |
|-------|------|-------|
| schema_version | string | Must be `1.0` |
| entry_count | integer | Must equal the number of entries |
| entries | list | Valid accepted records with cases removed and derived rank fields added |

Each entry keeps submission ID, suite, profile, hardware, runtime, model, settings, and aggregate
metrics. It adds `semantic_score_percent`, `exact_format_score_percent`, and `rank`.

Ranking uses descending semantic percentage, then descending exact-format percentage. Equal quality
pairs share a dense rank. Source, display name, and submission ID provide deterministic display order
inside a tie. Latency and throughput never affect rank.

## State transitions

1. A valid standard report plus a valid local descriptor becomes a prepared candidate.
2. The contributor reviews the complete candidate and chooses whether to publish it.
3. The candidate becomes proposed when it is added to a public pull request.
4. Continuous integration validates the closed contract, digest, filename, privacy rules, and
   deterministic dataset.
5. Maintainer review and merge make the candidate accepted.
6. The default-branch Pages workflow rebuilds and deploys the dataset.

Accepted files are append-only. A correction creates a new candidate and uses normal review instead
of silently replacing published evidence.
