# Quickstart Validation: Local Inference Test Bench

This guide proves the baseline end to end against any compatible local inference runtime. It does
not install, start, load, unload, or reconfigure that runtime.

## What this validates

- A collection manifest matches the published contract.
- The supplied endpoint passes the local-address gate before any inference request.
- Smoke and standard cases run sequentially.
- Semantic success and exact-format adherence remain separate.
- The written Run Record contains only fields allowed by the closed contract.
- Local tests and the publication gate reject unsafe tracked content.

The manifest and result shapes are defined in
[manifest.schema.json](contracts/manifest.schema.json) and
[run-record.schema.json](contracts/run-record.schema.json). Entity rules and validity states are in
[data-model.md](data-model.md).

## Prerequisites

- Python 3.11 or newer
- Git
- A separately managed local runtime that exposes an OpenAI-compatible chat-completions interface
- Gitleaks 8.30.1 or newer for the local scripts/public-check gate
- A shell with the local endpoint available to it

The baseline has no accelerator, model family, operating-system, memory-capacity, or inference
application requirement.

## 1. Install in an isolated environment

From the repository root:

    python3 -m venv .venv

Activate the environment with the command for your shell.

POSIX shells:

    . .venv/bin/activate

PowerShell:

    .\.venv\Scripts\Activate.ps1

Install the editable package:

    python -m pip install --upgrade pip
    python -m pip install -e .

Expected outcome: the litb console command and python -m local_inference_test_bench entry point are
available.

## 2. Create ignored local configuration

Copy the public example; do not edit the tracked example with local values.

POSIX shells:

    cp config/models.example.json config/models.local.json
    chmod 600 config/models.local.json

PowerShell:

    Copy-Item config/models.example.json config/models.local.json

Edit config/models.local.json:

- Keep schema_version and suite_version at the supported values.
- Give every entry a public-safe unique id.
- Record a public display name, source, exactly one revision or digest, precision, and declared
  context capacity.
- Set runtime_model to the selector accepted by the already-running local endpoint.
- Choose non-secret generation settings.
- Remove credential_env when the runtime needs no credential. Otherwise set it to an
  environment-variable name only and populate that variable outside the manifest. Never place the
  credential value in JSON or a command option.

The local file must remain ignored. Before continuing, inspect its Git status:

    git status --short --ignored config/models.local.json

Expected outcome: the local manifest is reported as ignored and is not staged.

## 3. Capture the endpoint without writing it to a tracked file

Use an interactive shell prompt so this guide does not prescribe or persist an endpoint value.

POSIX shells:

    read -r -p "Local endpoint URL: " LITB_ENDPOINT
    export LITB_ENDPOINT

PowerShell:

    $env:LITB_ENDPOINT = Read-Host "Local endpoint URL"

If the manifest names a credential variable, populate that variable through your shell prompt or
normal local secret store. Do not pass the credential value as an argument. An optional ignored
environment file may be selected with --env-file, but the file must meet the documented local
permission gate.

## 4. Run preflight only

Using the console command:

    litb check \
      --manifest config/models.local.json \
      --endpoint "$LITB_ENDPOINT"

Equivalent module invocation:

    python -m local_inference_test_bench check \
      --manifest config/models.local.json \
      --endpoint "$LITB_ENDPOINT"

PowerShell:

    litb check --manifest config/models.local.json --endpoint $env:LITB_ENDPOINT

Expected outcome:

- The manifest collection is accepted and contains at least one model.
- The endpoint parses, resolves only to allowed local addresses, and contains no credentials, query,
  or fragment.
- The named credential variable is present when required.
- Available runtime model metadata is checked without printing the endpoint, selector, credential, or
  returned identity.
- No benchmark case is sent by check.

If preflight fails, stop and correct the local configuration. Do not bypass the gate.

## 5. Run the smoke profile

    litb run \
      --manifest config/models.local.json \
      --endpoint "$LITB_ENDPOINT" \
      --profile smoke \
      --artifacts-dir artifacts

Expected outcome:

- Entries execute one at a time using synthetic baseline cases.
- No generated code or selected tool is executed.
- One minimized JSON record is written under the ignored artifacts directory.
- The record sets deployment_authorization to false even when every case passes.
- Semantic and exact-format counts can differ without either value being overwritten.

The standard profile uses the same command with --profile standard. Run it only after smoke passes:

    litb run \
      --manifest config/models.local.json \
      --endpoint "$LITB_ENDPOINT" \
      --profile standard \
      --artifacts-dir artifacts

PowerShell smoke invocation:

    litb run --manifest config/models.local.json --endpoint $env:LITB_ENDPOINT --profile smoke --artifacts-dir artifacts

## 6. Inspect a result safely

Review keys and categorical values, not model content. A conforming record contains:

- schema and suite versions, run ID, UTC creation time, selected profile, and public-manifest digest;
- valid, limited, or invalid run and model validity;
- public provenance and non-secret generation settings for each model;
- verified or metadata_unavailable preflight status plus an identity-match boolean;
- per-case semantic, exact-format, outcome, categorical route, reasoning-presence, latency, optional
  completion throughput, usage, and termination fields;
- aggregate counts and metrics; and
- deployment_authorization set to false.

It contains no prompt, completion, response fingerprint, reasoning, tool argument, endpoint,
credential, environment, machine, raw identity, or free-form error field. Do not publish the record
merely because it conforms; generated artifacts remain local until deliberately sanitized and
rescanned.

## 7. Run repository validation

Install the version-controlled hooks once per clone:

    ./scripts/install-hooks

From PowerShell:

    sh scripts/install-hooks

Replace the commented shapes in `.local/privacy-denylist.txt` with at least one private, non-secret
literal from your environment. Keep the file ignored and, on POSIX systems, mode 600. Strict checks
fail closed when this local environment gate is missing, empty, tracked, not ignored, or broadly
readable.

Run the standard-library tests:

    python -m unittest discover -s tests -v

Run the full publication gate:

    ./scripts/public-check --full-tree --strict

From PowerShell with the shell distributed by Git:

    sh scripts/public-check --full-tree --strict

Expected outcome: unit and integration tests, the full-content privacy scan, and the required external
secret scanner all pass. Scanner unavailability is a failed publication check.

For focused diagnostics, use the same scanner modes called by the hooks:

    python3 scripts/public_safety.py --staged
    python3 scripts/public_safety.py --full-tree
    python3 scripts/public_safety.py --history
    ./scripts/public-check --staged

Expected outcome: Git uses .githooks/pre-commit and .githooks/pre-push, and each hook invokes the
appropriate fail-closed checks before publication.

## Negative validation scenarios

These scenarios should fail safely and are covered by automated tests:

1. Supply a public, unresolved, credential-bearing, query-bearing, or mixed-resolution endpoint.
   check exits nonzero before an inference request and does not echo the value.
2. Add an unknown manifest field, duplicate a model ID, omit all models, include both revision and
   digest, or include neither. Manifest validation exits nonzero.
3. Name a missing credential variable. Preflight exits nonzero without printing its value.
4. Point --env-file at a tracked or overly permissive file. The local environment gate rejects it.
5. Seed a temporary test repository with a secret-like value, private address, home path, machine
   identifier, or literal custom denied term. The publication gate reports only a relative path,
   line number, category, and remediation.
6. Classify a semantically correct response with the wrong envelope. The semantic result remains true
   while exact format is false.
7. Return an output-budget termination. It is not relabeled as a context-window event.
8. Return reasoning without a usable final response. Termination is reasoning_only and no reasoning
   content is persisted.
9. Select an unsafe mutation or an unexpected tool. Routing fails and the harness invokes nothing;
   only an exact safe refusal or the correct inert read-only lookup satisfies the change boundary.

## Experiments are not part of this quickstart

Long-context, repeatability, model-template, metadata-only observability, dynamic-agent,
multi-runtime, and orchestration work is intentionally excluded. Each proposal belongs under
docs/experiments with an Experimental label, prerequisites, risks, authorization boundary where
needed, cleanup conditions, and a statement that the smoke and standard baseline does not depend on
it.
