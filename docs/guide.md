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
- exactly one upstream revision, weight-file digest, or documented checksum-manifest digest;
- quantization or precision;
- the declared context limit;
- the exact selector understood by the local runtime; and
- temperature, top-p, output budget, and seed when supported; and
- optional `reasoning_effort` (`none`, `minimal`, `low`, `medium`, `high`, or `xhigh`) only when the
  runtime implements that OpenAI-compatible request field.

The runner sends `reasoning_effort` only when it is explicitly present. Omitting it preserves the
runtime's behavior; no default is inferred.

The example starts with a 4,096-token output budget. Treat that budget as part of the candidate, not
as a harmless transport limit: a reasoning model can consume a smaller budget before producing its
final response. If a case ends as `reasoning_only` or exhausts exactly the configured budget, correct
the manifest and repeat preflight, smoke, and standard before publishing. Do not reinterpret a
truncated response as a model-quality failure.

The runtime selector is local input and is not copied into the public result record. Do not put an
endpoint or credential value in the manifest.

For an installed multi-shard artifact whose provider records a SHA-256 for every completed weight
download, `sha256-manifest-v1:<hex>` is an accepted composite identity. Compute `<hex>` over the
UTF-8 bytes of one `basename<TAB>provider-sha256<LF>` line per `.gguf` or `.safetensors` weight file,
sorted bytewise by basename. Use it only when every expected shard is present, basenames are unique,
and local file sizes match the completed-download metadata. This identifies the checksum manifest;
it does not claim that the full weights were independently rehashed. Never include local paths.

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
configuration. The baseline runner intentionally has no model-state API. Before each comparable run:

- pin and record the exact serving runtime and backend version;
- load only the model being measured;
- set and verify the applied context window;
- use one concurrent request;
- disable speculative decoding unless it is the deliberate comparison variable; and
- record the offload policy without inferring the actual execution path.

Put the public values in the owner-only hardware descriptor's `runtime` and optional
`runtime_configuration` objects. Use `null` or `unknown` when the runtime cannot verify a setting.
Keep private load logs and machine inventory out of the repository.

For large candidates, test sequentially. Release a model through the same runtime control you used to
load it. A runtime load error or HTTP 500 can be a backend/model compatibility failure; verify the
selected backend version before declaring the model unusable, then restart at preflight after any
runtime change.

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

The default per-request timeout is 300 seconds so slower local reasoning models can finish. Override
it explicitly when your evaluation requires a different limit, and keep it equal across models in a
performance comparison.

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
a different response subset. A valid smoke report proves the transport and scoring path worked; it
does not mean every semantic or exact-format check passed.

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

Repeat `check` → `smoke` → `standard` whenever the model artifact, runtime/backend version, context,
generation settings, reasoning mode, concurrency, speculation, or offload policy changes. Each such
change describes a different candidate result.

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
