# LocalInferenceTestBench

A hardware-agnostic, privacy-conscious process and reference runner for evaluating language models on
your own inference endpoint.

The project focuses on the part that is usually hardest to reproduce: model identity, staged test
profiles, safe synthetic cases, semantic-versus-format scoring, validity, and evidence handling. It
does not assume a GPU vendor, memory capacity, operating system, model family, or inference app.

## What you get

- a small Python reference runner for local OpenAI-compatible endpoints;
- smoke and standard profiles covering structured output, static-only coding, defensive analysis,
  inert read-only tool selection, and an unapproved-change boundary;
- versioned example manifests and JSON contracts for aggregate-only results;
- a guide for comparable performance and quality testing across different systems;
- optional experiments kept separate from the standard process;
- a fail-closed local privacy gate, Git hooks, Gitleaks, and matching CI checks; and
- a complete Spec Kit constitution, specification, plan, contracts, checklist, and task history.

The runner never loads or unloads a model, executes generated code, invokes a model-selected tool,
or persists raw prompts, responses, reasoning, tool arguments, credentials, endpoint values, or
machine inventory.

## Quick start

Requirements: Python 3.11 or newer, Git, and a model already served through a local
OpenAI-compatible endpoint.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

mkdir -p .local
cp config/models.example.json .local/models.json
```

Edit `.local/models.json` with the model's public provenance and the selector reported by your local
runtime. Remove `credential_env` if the endpoint does not require a token; otherwise set that named
environment variable without putting its value on the command line.

```sh
export LOCAL_INFERENCE_API_KEY="<set-locally>"

litb check \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1

litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile smoke
```

Use `--profile standard` after smoke passes. Run artifacts stay ignored under `artifacts/` and are
restricted to aggregate-safe fields.

See the full [operator guide](docs/guide.md) before comparing multiple models.

## Method at a glance

1. Define the workload decision and success conditions.
2. Pin model artifact identity, suite version, and generation settings.
3. Establish a stable comparison window and load models outside the harness.
4. Run `litb check`, then smoke, then standard.
5. Add an explicit experiment only when the decision needs it.
6. Interpret validity, semantics, envelope adherence, reliability, and performance separately.
7. Treat promotion or provider changes as a separate reviewed decision.

The complete rationale is in [evaluation methodology](docs/methodology.md) and
[interpreting results](docs/interpreting-results.md).

## Privacy before publication

Install the tracked hooks once per clone:

```sh
scripts/install-hooks
```

Replace the commented denylist shapes in the generated `.local/privacy-denylist.txt` with at least
one private, non-secret literal from your environment. Keep the file ignored and owner-only. The
publication gate requires Gitleaks 8.30.1 or newer; then run:

```sh
./scripts/public-check --full-tree --strict
```

The gate reports only a rule ID, file, and line—not the matched value. CI repeats generic privacy and
secret scans, while GitHub secret scanning and push protection provide a remote backstop. Read
[security and privacy](docs/security-and-privacy.md) before publishing results.

## Standard versus experimental

The standard guide is intentionally small and portable. Long-context stress, repeatability,
observability export, dynamic agent environments, and cross-runtime equivalence live only in the
[experimental notes](docs/experiments/README.md). Removing that directory does not affect the runner
or quick start.

## Specification

This repository was built with [GitHub Spec Kit](https://github.com/github/spec-kit) v0.16.0. The
governing source of truth is the [project constitution](.specify/memory/constitution.md), followed by
the [active feature specification](specs/001-local-inference-testbench/spec.md) and its plan,
contracts, validation guide, and tasks.

## License

Project code and documentation are available under the [MIT License](LICENSE). Copied Spec Kit
materials retain their original notice in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
