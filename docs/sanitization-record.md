# Sanitization record

This repository is a clean public rewrite of a private local-inference evaluation process. No source
tree, Git history, runtime artifact, or operational handoff was copied wholesale.

## Concepts retained

- artifact-level model identity and provenance;
- smoke, standard, and explicit expensive-test staging;
- synthetic cases and inert tool contracts;
- static-only evaluation of generated code;
- semantic and exact-envelope scoring as separate dimensions;
- distinct context, output-budget, reasoning-route, and safe-error classifications;
- sequential testing and run-validity review;
- aggregate-only reporting and a separate deployment-approval gate; and
- local pre-publication checks backed by hosted secret scanning.

## Material intentionally excluded

- machine, account, network, and service identifiers;
- hardware capacity and operating-system-specific collectors;
- private endpoints, credential locations, and observability configuration;
- real model inventory, aliases, results, timestamps, and performance figures;
- production-agent names, provider configuration, and operational runbooks;
- screenshots, logs, traces, prompt/response data, and generated artifacts; and
- private pattern lists used by the source environment.

Specialized ideas were rewritten as optional experiments with only public upstream references and
general safety requirements. They are not part of the baseline guide or runner.
