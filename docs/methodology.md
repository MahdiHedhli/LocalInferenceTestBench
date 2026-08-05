# Evaluation methodology

LocalInferenceTestBench answers a narrow question: does a particular model artifact, served with a
particular configuration, satisfy the contracts of an intended workload at an acceptable cost?

It does not try to produce a universal model ranking. Quality results can often travel across systems;
latency, throughput, memory pressure, and thermals generally cannot.

## The evaluation unit

Treat the following tuple as one candidate. If any element changes, record a new result instead of
overwriting the old one:

- model source and exact revision or digest;
- artifact format and quantization or precision;
- runtime and runtime version;
- context limit and generation settings;
- prompt-template or reasoning-mode settings, when exposed;
- benchmark-suite version; and
- a non-identifying environment profile used only to group performance results.

A display name is not an identity. Two files with the same friendly name may have different weights,
templates, quantization, or runtime behavior.

## Staged process

### 1. Define the decision

Write down the workloads, required output envelopes, latency tolerance, context needs, and failure
conditions before testing. Avoid selecting metrics after seeing results.

### 2. Freeze the case and candidate manifests

Pin the suite version and record public provenance for every candidate. Keep runtime selectors in a
local ignored manifest if they reveal internal naming.

### 3. Establish a valid comparison window

- Load and configure models outside the baseline harness.
- Test one resource-intensive model at a time.
- Stop unrelated local inference clients and record whether the environment was stable.
- Use the same runtime settings for models in the same performance comparison.
- Warm up consistently, or label cold-start and warm measurements separately.

The reference runner does not collect machine inventory. If an adapter collects resource data, keep
the raw inventory local and export only coarse, non-identifying categories.

### 4. Run preflight

Preflight validates the manifest, confirms that the endpoint resolves only to a local/private address,
checks the advertised model list, and validates credential handling. It does not generate text or
change model state.

### 5. Run the smoke profile

Smoke uses three synthetic cases:

- exact structured output;
- Python source inspected with the abstract syntax tree and never executed; and
- bounded defensive analysis of synthetic findings.

Smoke is the fast compatibility gate. A failure here should be explained before expensive testing.

### 6. Run the standard profile

Standard adds two inert tool-contract cases:

- select a read-only lookup tool with schema-valid arguments; and
- refuse or remain read-only when asked for an unapproved change.

The model may emit a tool-call object, but the harness never executes it.

### 7. Add experiments only when the decision needs them

Long-context retrieval, bounded repeatability, reasoning-template analysis, dynamic agent tasks,
telemetry export, and multi-runtime comparisons are deliberately outside the baseline. See
[`experiments/README.md`](experiments/README.md).

### 8. Review before promotion

A passing report is evidence, not deployment authorization. Confirm identity, semantic and format
results, validity, failures, and intended-workload fit. Provider changes, agent permissions, network
changes, and rollback planning belong to a separate reviewed change.

## What to measure

| Dimension | Record | Interpretation |
|---|---|---|
| Semantic quality | Contract checks and pass rate | Did the answer do the required task? |
| Envelope quality | Direct JSON/source/tool-call adherence | Can the consumer parse it without repair? |
| Reliability | Termination, refusal, empty-final, tool-route categories | How did failures present? |
| Performance | End-to-end latency and API-reported token rate | Compare only within a normalized environment. |
| Context | Declared target, measured input tokens, retrieval outcome | Keep output-budget and context failures distinct. |
| Validity | Valid, limited, or invalid | Are quality and performance claims usable? |

## Comparison rules

- Compare semantic and envelope results across hardware only when the suite and model identity match.
- Compare latency and throughput only within the same non-identifying environment profile.
- Do not mix cold-start latency with warmed generation latency.
- Treat missing usage data as missing, not zero.
- A fenced but correct JSON object can pass semantics while failing exact-envelope adherence.
- A response that consumes its output budget is not automatically a context-window failure.
- Reasoning text without a usable final message or tool call is not a successful consumer response.
- Retain failed and invalid runs; do not silently replace inconvenient evidence.
