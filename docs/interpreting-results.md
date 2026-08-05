# Interpreting results

Read validity and identity before reading scores. A fast result from a disturbed run or a differently
configured artifact is not a useful comparison.

## Result layers

1. **Run validity**: Was the endpoint local, the configuration declared, and the comparison window
   acceptable? Invalid runs remain evidence of what happened but should not rank candidates.
2. **Semantic result**: Did the response satisfy the task contract?
3. **Envelope result**: Did the answer arrive as direct JSON, source, or a schema-valid tool call?
4. **Reliability result**: Was there a refusal, malformed tool call, missing final message, timeout,
   output-budget exhaustion, or likely context failure?
5. **Performance result**: What latency and token usage did the compatible API report?

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

Routes such as `safe_refusal`, `read_only_tool`, and `unsafe_mutation` are reported separately from
termination, so a safe policy decision is not confused with a transport or generation stop.

## Promotion checklist

- Exact artifact identity and suite/settings version are present.
- All required workload cases pass semantically.
- Exact-envelope performance meets the actual consumer's needs.
- No unresolved reasoning-only, truncation, or tool-schema behavior remains.
- Performance was measured in a comparable environment and is acceptable at the intended concurrency.
- Any required context experiment passed with measured input usage.
- The report passed publication review if it will leave the local machine.
- A separate owner-approved deployment and rollback plan exists.

Do not collapse quality into one number. A slower model with reliable direct tool calls may be better
for automation; a faster model with fenced JSON may be perfectly good for an interactive workflow.
