# Interpreting results

Read validity and identity before reading scores. A fast result from a disturbed run or a differently
configured artifact is not a useful comparison.

## Result layers

1. **Execution validity**: Did local endpoint checks, runtime identity, requests, and classification
   complete coherently? The private report uses `valid`, `limited`, or `invalid`. This does not
   describe host quiescence.
2. **Measurement validity**: Did the categorical pre/post evidence remain `clean`, begin
   `nonquiescent`, or become `degraded_midrun`? This public field is supplied separately and remains
   self-reported rather than verified.
3. **Semantic result**: Did the response satisfy the task contract?
4. **Envelope result**: Did the answer arrive as direct JSON, source, or a schema-valid tool call?
5. **Reliability result**: Was there a refusal, malformed tool call, missing final message, timeout,
   output-budget exhaustion, or likely context failure?
6. **Performance result**: What latency and token usage did the compatible API report?

The public leaderboard defaults to `clean` rows. Selecting nonquiescent, degraded-midrun, or
`legacy_unreported` rows broadens the comparison; it does not make any category verifiable. Accepted
schema `1.0` entries show legacy-unreported conditions and no measurement month because those values
were never collected. They are not silently assigned defaults.

Schema `1.1` rows display their UTC month as “as of” and can be filtered or sorted by recency. Month
is deliberately coarse: it helps identify aging runtime evidence without publishing an event time.
On a paginated board, controls describe loaded rows until all pages have been fetched.

## Configuration cells and rank bands

The board projects one cell for each exact facet/profile/suite/configuration key. If several accepted
records share that key, one score-neutral representative is selected: clean before nonquiescent,
then degraded-midrun, then legacy-unreported; newest month and content digest break remaining ties.
Validity/month filters apply to that representative. The cell separately shows fixed counts and
month ranges for every retained validity class, so the representative is not presented as the only
evidence. Every original record remains addressable by its digest in the repository.

Quality is shown as a pass count with a 95% Wilson interval. Overlapping evidence shares a transitive
rank band; it is not a strict point-estimate ordering. Repeated anonymous hashes increase the cell's
corroboration and performance sample range but do not narrow its quality interval, because neither
the hash nor repository acceptance proves independent operators or runs.

`Caution` means at least one retained performance observation fell outside a deliberately broad,
versioned envelope for the declared coarse hardware class and explicit model-size bucket.
`Within envelope` means no automatic flag fired, not that a result is verified. `Not evaluated`
means the model scale, hardware class, or facet performance was unavailable. Plausibility never
drops, gates, or changes a rank band.

## Common classifications

| Classification | Meaning | Next question |
|---|---|---|
| `completed` | A usable final response completed. | Did semantics and format pass? |
| `output_budget` | Generation reached its configured output limit. | Is the budget realistic for the workload? |
| `context_window` | The request and output likely exceeded the available window. | Was the applied context actually confirmed? |
| `reasoning_only` | Reasoning was present but no usable final response was routed. | Is the runtime template compatible? |
| `tool_call` | Generation ended with one or more tool calls. | Did the route and argument checks pass? |
| `length_unknown` | The runtime reported a length stop without enough usage evidence to attribute it. | Is complete usage reporting available? |
| Error categories | The harness retained a category such as `timeout` or `network_error`, not raw error content. | Can private runtime logs explain it locally? |
| `not_applicable` | The model or runtime could not attempt the case. | Should this result be absent from the selected facet? A public candidate still needs at least one scored case across its complete suite. |

Routes such as `safe_refusal`, `read_only_tool`, and `unsafe_mutation` are reported separately from
termination, so a safe policy decision is not confused with a transport or generation stop.
For an inapplicable case, outcome, route, and termination all use the `not_applicable` sentinel so
the record cannot imply that an unattempted case completed through an ordinary response route.
`not_applicable` is excluded from score denominators; `not_scored` remains a reached but unscored case.

### Execution-failure issue signals are not scores

The optional GitHub failure draft is generated only from closed runtime, transport, or harness
compatibility categories such as timeout, invalid protocol JSON, response bounds, or a runtime
request rejection. It is a self-reported diagnostic signal, not a benchmark result, rank input,
attestation, or proof that the harness is defective.

Semantic or exact-format failure, refusal, reasoning-only output, context/output limits,
`not_applicable`, and nonquiescent or degraded measurement conditions remain ordinary benchmark
evidence and never trigger the issue prompt. Configuration, endpoint safety, authentication,
rate-limit, sampler, submission, and publication failures retain their existing local remediation
paths.

## Promotion checklist

- Exact artifact identity and suite/settings version are present.
- All required workload cases pass semantically.
- Exact-envelope performance meets the actual consumer's needs.
- Facet latency and throughput are shown only when the selector covers the complete suite. A future
  strict subset facet reports those performance values as unavailable because public records do not
  retain per-case timing or usage from which an honest subset aggregate could be reconstructed.
- No unresolved reasoning-only, truncation, or tool-schema behavior remains.
- Performance was measured in a comparable environment and is acceptable at the intended concurrency.
- Any required context experiment passed with measured input usage.
- The report passed publication review if it will leave the local machine.
- A separate owner-approved deployment and rollback plan exists.

Do not collapse quality into one number. A slower model with reliable direct tool calls may be better
for automation; a faster model with fenced JSON may be perfectly good for an interactive workflow.
