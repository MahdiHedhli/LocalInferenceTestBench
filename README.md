# Local Inference Test Bench

A hardware-agnostic, privacy-conscious process and reference runner for evaluating language models on
your own inference endpoint.

The project focuses on the part that is usually hardest to reproduce: model identity, staged test
profiles, safe synthetic cases, semantic-versus-format scoring, validity, and evidence handling. It
does not assume a GPU vendor, memory capacity, operating system, model family, or inference app.

## Why I built this

I built LocalInferenceTestBench to answer a practical question: how well do local models run on my
own hardware when I give them the same set of tasks? Tokens per second matter, but they are only part
of the answer. I also want to know whether a model returns clean structured data, writes code that
holds up to static checks, handles a defensive analysis prompt, and respects a safe tool boundary.
Running the same cases each time gives me a fairer picture of which model fits the work.

## What you get

- a small Python reference runner for local OpenAI-compatible endpoints;
- smoke and standard profiles covering structured output, static-only coding, defensive analysis,
  inert read-only tool selection, and an unapproved-change boundary;
- versioned example manifests and JSON contracts for aggregate-only results;
- a guide for comparable performance and quality testing across different systems;
- a public, quality-ranked leaderboard with exact hardware and runtime context;
- an identifier-minimized export path for reviewed community submissions;
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

At the end of a valid interactive standard run, the bench now offers three choices: keep the report
private, save identifier-minimized JSON, or open a reviewed public pull request. Enter keeps the
result private. Nothing is uploaded merely because a run finished.

For a scripted local export:

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile standard \
  --hardware .local/hardware.json \
  --submission save
```

To automate the public contribution path, use `--submission pr`. The tool saves and displays the
complete minimized record, runs the privacy and secret gates in an isolated clone, then creates a
feature branch and pull request through an authenticated GitHub CLI. It never pushes directly to
`main`. Non-interactive publication also requires `--confirm-public`.

If publication is cancelled or a GitHub step fails, retry from the saved minimized file without
rerunning inference:

```sh
litb publish-submission \
  --candidate .local/leaderboard-submissions/<submission-id>.json
```

The retry revalidates the file, repeats the complete disclosure, and requires literal `PUBLISH` in
an interactive terminal. Add `--confirm-public` only for an intentional non-interactive retry.

See the full [operator guide](docs/guide.md) before comparing multiple models.

## Public leaderboard

The [GitHub Pages leaderboard](https://mahdihedhli.github.io/LocalInferenceTestBench/) puts the
community results first. Quality rank uses semantic score, then exact-format score. Latency and
throughput are shown with the hardware and runtime reported for them, but speed does not affect rank.
Every entry is self-reported and unverified. Its content hash establishes that the accepted JSON has
not changed; it does not prove who produced it, that a benchmark run occurred, or that the reported
measurements are true.

Leaderboard records include exact CPU, memory, accelerator, execution-mode, runtime name and
version, and—when supplied—the configured context window, concurrency, speculative-decoding state,
and offload mode because performance without that context is not useful. Unknown numeric values are
reported as `null`; categorical uncertainty is reported as `unknown`, never inferred. Records omit
direct machine identifiers, source run IDs, timestamps, local model selectors, raw prompts,
completions, reasoning, and tool arguments. Hardware plus performance can still make a setup
recognizable, and the GitHub account used to open a submission pull request is public.

To prepare a result from a valid standard run:

```sh
cp config/hardware.example.json .local/hardware.json
chmod 600 .local/hardware.json

litb prepare-submission \
  --report artifacts/<run-record>.json \
  --hardware .local/hardware.json \
  --model <report-model-id>
```

Review the generated file before sharing it. The complete process is in
[submitting a benchmark](docs/submitting-benchmarks.md).

The same preparation and review happen automatically after `litb run --profile standard` when you
choose the save or public-PR option. “Identifier-minimized” is deliberate: exact hardware,
performance, the public pull request, and its GitHub account can still link a result to its source.

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

The gate reports only a rule ID, file, and line. It never prints the matched value. CI repeats generic
privacy and secret scans, while GitHub secret scanning and push protection provide a remote backstop. Read
[security and privacy](docs/security-and-privacy.md) before publishing results.

## Standard versus experimental

The standard guide is intentionally small and portable. Long-context stress, repeatability,
observability export, dynamic agent environments, and cross-runtime equivalence live only in the
[experimental notes](docs/experiments/README.md). Removing that directory does not affect the runner
or quick start.

Image and video generation are explicitly out of scope. Scoring generated media generally requires
a similarity model or human preference, which conflicts with this project's judge-free,
rule-based design, and generation uses a different runtime stack. A separate generation benchmark
may reuse this project's submission pipeline, privacy gate, and validity model.

## Specification

This repository was built with [GitHub Spec Kit](https://github.com/github/spec-kit) v0.16.0. The
governing source of truth is the [project constitution](.specify/memory/constitution.md), followed by
the [baseline specification](specs/001-local-inference-testbench/spec.md) and the
[leaderboard specification](specs/002-anonymized-leaderboard/spec.md), with their plans, contracts,
validation guides, and tasks.

## License

Project code and documentation are available under the [MIT License](LICENSE). Copied Spec Kit
materials retain their original notice in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
