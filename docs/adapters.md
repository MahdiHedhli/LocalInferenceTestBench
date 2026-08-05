# Runtime adapters

The baseline speaks the OpenAI-compatible model-list and chat-completions contracts. This covers many
local runtimes without embedding their lifecycle APIs or hardware assumptions in the core project.

An adapter may provide:

- model loading, unloading, and applied-context confirmation;
- runtime-specific reasoning or prompt-template controls;
- time-to-first-token and resource telemetry;
- tokenization for more precise long-context targets; or
- translation from another local inference protocol.

Adapters must preserve these boundaries:

- lifecycle mutations are explicit and separately confirmed;
- only instances created by an adapter may be automatically released;
- endpoints still resolve exclusively to local/private addresses;
- raw model or telemetry payloads are not persisted by default;
- secrets never enter command-line values or reports;
- runtime-specific fields live in namespaced, aggregate-safe metadata; and
- the baseline suite remains runnable without the adapter.

Document each adapter's supported runtime versions, state changes, rollback behavior, missing metrics,
and tests. Do not infer that two runtime aliases identify the same artifact.
