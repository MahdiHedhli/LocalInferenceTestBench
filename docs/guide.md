# Operator guide

This guide walks through a comparable local inference evaluation without assuming particular
hardware or runtime lifecycle commands.

## 1. Prepare the repository

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
mkdir -p .local
cp config/models.example.json .local/models.json
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`; the `litb` commands are otherwise
the same.

The editable install has no runtime dependencies beyond Python's standard library.

## 2. Describe candidates

The example manifest is a collection so the runner can test candidates sequentially. For each model,
record:

- a portable local entry ID and display name;
- public source repository or artifact label;
- exactly one upstream revision or file digest;
- quantization or precision;
- the declared context limit;
- the exact selector understood by the local runtime; and
- temperature, top-p, output budget, and seed when supported.

The runtime selector is local input and is not copied into the public result record. Do not put an
endpoint or credential value in the manifest.

If authentication is required, declare only the environment variable name in `credential_env`:

```sh
export LOCAL_INFERENCE_API_KEY="<set-locally>"
```

For an env file, keep it ignored and owner-only:

```sh
chmod 600 .local/inference.env
litb check --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --env-file .local/inference.env
```

The runner rejects a symlinked, group/world-readable, wrong-owner, or tracked credential file on
platforms where those checks are available.

## 3. Load the model outside the harness

Use the runtime's normal controls to load one candidate at the desired context and generation
configuration. The baseline runner intentionally has no model-state API. Record runtime-specific load
confirmation in private operator notes or an adapter; do not add machine inventory to the manifest.

For large candidates, test sequentially. Release a model through the same runtime control you used to
load it.

## 4. Preflight without inference

```sh
litb check \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1
```

Preflight fails closed when:

- the manifest is malformed, ambiguous, or contains unsupported fields;
- the endpoint contains credentials, a query, a fragment, or an unsupported path;
- any resolved endpoint address is outside explicit loopback/private/link-local ranges;
- a required credential is absent or its env file is unsafe; or
- a manifest selector is absent from the runtime's model list.

Endpoint and credential values are not echoed.

## 5. Run smoke

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile smoke
```

Smoke sends three synthetic cases and runs them sequentially. Generated Python is parsed with `ast`
and is never imported or executed. Review the resulting validity, semantic checks, exact-envelope
checks, latency, usage, and termination classifications.

If a case fails, explain the route before escalating. Common causes include fenced output, output
budget exhaustion, a prompt-template mismatch, unavailable usage fields, or a runtime that implements
a different response subset.

## 6. Run standard

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile standard
```

Standard adds inert function definitions. One case requires the correct read-only lookup; the other
allows a safe refusal or read-only route but rejects an unapproved change request. The runner scores
tool objects and their schemas without invoking them.

## 7. Compare results responsibly

- Compare semantic and envelope behavior using the same suite and generation settings.
- Compare latency and throughput only across runs from the same normalized environment profile.
- Keep cold-start and warmed measurements separate.
- Do not rank invalid runs.
- Preserve model provenance; do not group by display name alone.
- Keep missing usage values null rather than converting them to zero.

See [interpreting results](interpreting-results.md) for the promotion checklist.

## 8. Add an experiment deliberately

Use [experimental notes](experiments/README.md) only after the baseline is understood. Each experiment
needs a question, prerequisites, risk boundary, time limit, evidence fields, and cleanup condition.
It must remain removable from the standard workflow.

## 9. Keep artifacts private by default

The `artifacts/` directory is ignored except for its placeholder. Do not force-add real run records.
If sharing a result is necessary, follow the deliberate export review in
[security and privacy](security-and-privacy.md).
