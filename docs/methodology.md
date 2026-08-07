# Evaluation methodology

LITB answers a narrow question: does a particular model artifact, served with a
particular configuration, satisfy the contracts of an intended workload at an acceptable cost?

It does not try to produce a universal model ranking. Quality results can often travel across systems;
latency, throughput, memory pressure, and thermals generally cannot.

## The evaluation unit

Treat the following tuple as one candidate. If any element changes, record a new result instead of
overwriting the old one:

- model source and exact revision, weight digest, or documented composite checksum-manifest digest;
- artifact format and quantization or precision;
- runtime and runtime version;
- context limit and generation settings;
- prompt-template or reasoning-mode settings, when exposed;
- benchmark-suite version; and
- a non-identifying environment profile used only to group performance results.

A display name is not an identity. Two files with the same friendly name may have different weights,
templates, quantization, or runtime behavior.

The public taxonomy separates tasks from dimensions:

- **Tasks** say what is measured: `structured_output`, `coding`, `agent_tool_use`, `cyber_triage`,
  and `safety_boundary`.
- **Dimensions** say under what conditions it is measured: modality, context length, quantization,
  runtime, and hardware.

Modality crosses the task axis; it is not another capability. A future vision agent case would still
be `agent_tool_use`. Every current case is text. Image and video generation remain outside this
project because they require a different runtime and similarity or preference scoring.

The current mapping is `structured-json` → `structured_output`, `python-ast` → `coding`,
`defensive-triage` → `cyber_triage`, `read-only-tool` → `agent_tool_use`, and
`unapproved-change-boundary` → `safety_boundary`.

## Staged process

### 1. Define the decision

Write down the workloads, required output envelopes, latency tolerance, context needs, and failure
conditions before testing. Avoid selecting metrics after seeing results.

### 2. Freeze the case and candidate manifests

Pin the suite version and record public provenance for every candidate. For multi-shard artifacts,
the operator guide defines the path-free `sha256-manifest-v1` checksum-manifest scheme; record its
derivation evidence privately and do not present it as an independent rehash of the weights. Keep
runtime selectors in a local ignored manifest if they reveal internal naming.

### 3. Establish a valid comparison window

- Load and configure models outside the baseline harness.
- Test one resource-intensive model at a time.
- Stop unrelated local inference clients and record whether the environment was stable.
- Pin the runtime/backend version; verify context, concurrency, speculation, and offload settings.
- Use the same verified runtime settings for models in the same performance comparison.
- Record an explicit reasoning effort when used; omission means unreported/runtime behavior, not an
  inferred effort level.
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

The standard suite's five binary cases are a compatibility floor and screen, not a statistically
discriminating ranking instrument. A perfect five-of-five result still carries wide uncertainty.
Resolution should come from expanding a reviewed suite, not from printing extra decimal places or
inventing capability scores from roughly one case per task. The suite registry therefore records
capability and modality now, while the site deliberately exposes no capability-specific score,
column, view, or page.

The public board renders each representative result as `passes/scored` plus a 95% Wilson interval.
Lower bounds are rounded down and upper bounds up to whole percentages, so five passes in five cases
appears as `5/5 (56–100%)`. Semantic overlap components are ranked first; exact-format overlap
components partition them secondarily. Overlap is transitive, and every member of a component shares
an explicit rank band. Model/source names and speed do not order a band; the content digest is the
neutral final tiebreak.

Accepted hashes are anonymous observations, not proven independent samples. Repeats for one exact
configuration therefore do not pool pass-count denominators or narrow the Wilson interval. They add
only a corroboration count and latency/throughput median and spread. This is deliberately resistant
to false precision from submission flooding.

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
| Execution validity | Valid, limited, or invalid | Did endpoint, identity, request, and classification complete coherently? |
| Measurement validity | Clean, nonquiescent, or degraded mid-run | What coarse self-reported host conditions surrounded the measurement? |

## Comparison rules

- Compare semantic and envelope results across hardware only when the suite and model identity match.
- Compare latency and throughput only within the same non-identifying environment profile.
- Do not mix cold-start latency with warmed generation latency.
- Treat missing usage data as missing, not zero.
- Treat `not_applicable` as absence from the applicable denominator, not a failed case. It is distinct
  from `not_scored`, which means a case was attempted or reached but could not be scored and therefore
  is not eligible for a public comparison row. An inapplicable case uses `not_applicable` consistently
  for outcome, route, and termination; mixed sentinels are invalid.
- Do not infer clean measurement conditions from valid execution. Public preparation requires a
  separate categorical sidecar, and missing evidence is not a clean run.
- Treat a plausibility caution only as an outlier-review hint. The broad versioned envelope uses the
  declared coarse hardware class and explicit active-or-total parameter scale; unknown scale is
  `not_evaluated`, and no plausibility state establishes that a run occurred.
- A fenced but correct JSON object can pass semantics while failing exact-envelope adherence.
- A response that consumes its output budget is not automatically a context-window failure.
- A reasoning-only response at the configured output ceiling must be rerun with a justified larger
  budget before it is treated as a model-quality result.
- Reasoning text without a usable final message or tool call is not a successful consumer response.
- Retain failed and invalid runs; do not silently replace inconvenient evidence.
