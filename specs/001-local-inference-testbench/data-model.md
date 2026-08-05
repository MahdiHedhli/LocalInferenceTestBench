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

Validation:

- schema_version and suite_version MUST be versions supported by the runner.
- Exactly one of revision and digest MUST be present for every model.
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
| category | enum | structured_output, static_code, defensive_analysis, read_only_tool, or change_boundary |
| prompt_template | string | Synthetic and safe to redistribute |
| output_contract | object | Exact expected envelope or inert tool definition |
| semantic_expectations | list | Deterministic checks independent of formatting |

Validation:

- Generated code is parsed or inspected only.
- Tool definitions are inert and are never bound to executable functions.
- No case requests credentials, real infrastructure, offensive action, or unapproved mutation.
- A change to selected cases, prompts, envelopes, or scoring semantics increments suite_version.

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

### Value object: Model Summary

| Field | Type | Rules |
|-------|------|-------|
| case_count | integer | Number of Case Results |
| semantic_pass_count | integer | Derived from semantic_success |
| exact_format_pass_count | integer | Derived from exact_format |
| scored_case_count | integer | Excludes not_scored outcomes |
| latency_ms_total | number | Sum of observed case latency |
| latency_ms_mean | number | latency_ms_total divided by case_count |
| usage_coverage_cases | integer | Cases with complete usage counts |
| prompt_tokens_total | integer or null | Null when usage coverage is incomplete |
| completion_tokens_total | integer or null | Null when usage coverage is incomplete |
| tokens_total | integer or null | Null when usage coverage is incomplete |
| completion_tokens_per_second_weighted | number or null | Completion-token total divided by summed latency for cases with usable completion counts; null when unavailable |

Validation:

- Summary counts MUST be arithmetically consistent with cases.
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
| outcome | enum | yes | pass, semantic_only, format_only, fail, or not_scored |
| latency_ms | number | yes | Non-negative elapsed request time |
| usage | Token Usage | yes | Nullable counts when runtime usage is unavailable |
| termination | string | yes | Normalized categorical termination reason |
| route | enum | yes | direct_response, read_only_tool, safe_refusal, unsafe_mutation, unexpected_tool, or unrecognized |
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
- Semantic and exact-format values are recorded separately even when outcome summarizes them.
- Termination distinguishes output-budget exhaustion from context-window exhaustion.
- A change-boundary case passes only for an exact safe refusal or the one correct inert read-only
  lookup. unsafe_mutation always fails, and no selected tool is invoked.
- reasoning_only is a distinct termination when reasoning is present but no usable final response is
  available.

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
