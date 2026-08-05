# Experimental evaluations

These notes are optional research directions. They are not required by the standard guide, are not
enabled by the reference profiles, and should not be treated as universal promotion criteria.

## Long-context retrieval

Generate deterministic filler with a marker placed away from both ends, derive the target from the
declared context limit, reserve generation headroom, and require measured input-token usage before
calling the test near-full-context. Run one model at a time with a time limit.

## Bounded repeatability

Repeat a designated case three to five times with identical settings. Compare semantic status,
envelope class, finish reason, and a transient response fingerprint. Persist only whether the
fingerprint was stable, never the individual fingerprints. Fingerprint drift alone is a warning;
semantic, envelope, or finish-reason drift can block promotion for strict consumers.

## PolyRange-style dynamic agent evaluation

[PolyRange](https://github.com/orlyjamie/polyrange) illustrates contamination-resistant evaluation
against randomized, deliberately vulnerable web targets. A future adapter could measure a bare model
and an orchestration layer against operator-owned, per-run targets with an explicit success oracle.

Such work requires more than the baseline harness:

- written authorization limited to operator-owned targets;
- isolated, non-production, loopback-bound or equivalently contained deployments;
- a generator model distinct from the evaluated model;
- validation that randomization and defenses actually discriminate capability;
- no third-party targeting, uncontrolled scanning, or standing credentials; and
- deterministic teardown and evidence-minimization rules.

The reference runner does not deploy targets, execute model actions, or provide offensive tooling.

## Opik metadata-only observability

[Opik](https://github.com/comet-ml/opik) can be evaluated as an optional observability sink. A safe
exporter would emit one trace per model with empty input and output fields and explicit false capture
flags. Only aggregate quality, latency, token metrics, suite version, and public model identity may
leave the runner. Endpoint health must be checked separately, export must require an explicit flag,
and export failure must not broaden network access or invalidate an otherwise local result.

This experiment must use operator-supplied local configuration, retain no Opik project or endpoint
default in the public repository, and include a contract test proving that prompts, completions,
reasoning, credentials, and tool payloads are absent from every emitted object.

## Cross-runtime equivalence

Serve the same pinned artifact through two runtimes and compare semantics, envelopes, token accounting,
reasoning routing, and performance. Treat differing templates or tokenizers as different configurations
even if the weights are identical.
