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
Keep private load logs and machine inventory out of the repository. Public hardware/runtime labels
and model artifact identity values must be compact visible-ASCII product or revision labels; URLs,
network/host shapes, identifiers, and reviewer-directed prose are rejected.

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

Before public schema `1.1` preparation, obtain categorical pre/post measurement evidence from a
compatible local sampler or adapter. On POSIX, non-interactive single-command save/PR uses
`--measurement-sampler <executable>`. The CLI allocates the run ID before endpoint access, invokes
the adapter synchronously before the run and, only when that pre-sample and the complete benchmark
both return successfully, after the run. If benchmark execution raises, no post-sample or public
export is attempted. The CLI verifies the echoed run/model/phase
binding, and atomically retains the closed sidecar at `--measurement-evidence`. The executable must
be at most 16 MiB, regular, non-symlinked, and not group- or world-writable. Its approved bytes are
copied into a private non-writable snapshot for execution while the source identity/content are
rechecked for every launch. Adapter stdout is bounded strict JSON; stderr and inherited
credentials are not captured or forwarded. A dedicated standard-library supervisor keeps the
sampler process launched from the snapshot and its descendants in one process group, kills that
group before reaping its leader, and on Linux fails closed unless child-subreaper setup succeeds,
then adopts and boundedly reaps descendants. The sampler must remain synchronous: it must not daemonize,
call `setsid`/`setpgid`, or otherwise deliberately escape the process group. Snapshot creation uses
an owner-only directory under the system temporary location; on a host where its filesystem is
mounted `noexec`, set `TMPDIR` to an owner-controlled, non-repository directory on a writable
filesystem that permits execution. Do not relocate snapshots into a tracked or shared repository
directory; the CLI resolves the selected temporary base and rejects ordinary worktrees, linked
worktrees, Git directories, bare repositories, and repository-routing `GIT_*` state before writing
the approved bytes. Every resolved ancestor must be owned by root or the current user, and any
shared-writable ancestor must use the sticky bit. Creation and writes use open directory descriptors
so an untrusted different-UID path swap cannot redirect sampler bytes into a repository. Cleanup performs
non-following, nonblocking exact-identity checks immediately before descriptor-relative removal.
Root and same-UID adversaries are outside this boundary; portable POSIX cannot make final pathname
removal identity-conditional, and those processes can already access the approved bytes. A handled
cleanup failure, `SIGKILL`, or a host crash can leave the owner-only private snapshot until local or
system temporary-file cleanup. The snapshot path and bytes remain local and are never published.
Windows uses the separate exact-bound sidecar plus `prepare-submission` until equivalent safe
process-tree containment is available.

The retained file is ignored and owner-only, carries the exact report `run_id`, and contains one
unique row for every exported model with only threshold outcomes and the closed categories for
memory pressure, thermal state, sustained load, swap, and resident models. Use `--submission-model`
or the two-step command's `--model` to export fewer rows. Raw readings, process names, inventory,
paths, additional timestamps, and free text stay local. A missing, stale-run, oversized, unsafe, or
incomplete sampler result blocks export without invalidating the private report. A static sidecar
from another compatible sampler remains valid for two-step `prepare-submission`; the tracked example
is deliberately nonquiescent and is never a clean-run template. The binding ID is validation-only
and absent from public JSON.

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

## 10. Understand public leaderboard retention and delivery

An accepted public submission is append-only source evidence. It stays under
`site/data/submissions/<submission_id>.json` and remains addressable by its canonical content digest.
New proposals use submission schema `1.1`. The accepted `1.0` corpus remains byte-for-byte legacy
evidence; open or locally saved `1.0` candidates must be regenerated, never hand-migrated. Corpus
growth never authorizes deleting, rewriting, sampling, or silently dropping an accepted record.
Corrections create a new reviewed submission.

The repository deliberately separates that retention policy from browser delivery:

- Once sharding is active, `site/data/leaderboard.json` is a constant-shape bounded deterministic
  index containing exactly `index_version`, `schema_version`, `entry_count`, and `shard_count`. It is
  the only generated leaderboard artifact committed to the repository.
- A benchmark pull request still contains exactly one added digest-named submission plus the
  regenerated canonical leaderboard transport file. Do not add generated shard files.
- Pull-request checks rebuild that committed file and compare its bytes. On `main`, Pages repeats the
  check before copying only the allowlisted static site files and generating the exact-key index and
  shard pages in a temporary deployment artifact. The growing source-submission directory is not
  duplicated into the Pages artifact.
- The browser loads the index first and fetches bounded pages on demand. It derives only contiguous
  one-based IDs from `000001` through the declared shard count and constructs only
  `data/leaderboard-NNNNNN.json`; public JSON never supplies a URL or arbitrary path. Each closed
  shard contains exactly `index_version`, `schema_version`, `shard_id`, `entry_count`, and `entries`.
  The legacy monolith, index, and every shard pass through fatal UTF-8 decoding with byte-order-mark
  rejection and the same strict duplicate-member-rejecting JSON parser before shape validation.
  Until every page is loaded, search, hardware filters, and alternate sorting are explicitly scoped
  to loaded results, and an empty filtered view does not claim that no matching published row exists.

The current six-entry all-legacy leaderboard monolith remains byte-identical until the first
accepted schema `1.1` submission creates a mixed projection. In that projection, legacy rows are
explicitly `legacy_unreported` with no synthesized month or condition evidence. The browser and
builder accept both closed transport forms. When a deterministic rebuild would cross the monolith
cap, the committed output switches to the constant-shape index and the Pages artifact receives
shards. Pages always deploys the generated index and shards. The transport `index_version` stays
`1.0`; it is independent of projected entry schema `1.1`.

Global rank order and page order are deterministic. The publisher greedily splits that sequence at
stable row boundaries according to the exact UTF-8 byte size of each rendered JSON page. It does not
estimate from character counts or discard older rows. The union of all pages must contain every
accepted submission digest exactly once.

Hard caps remain on each submission, the committed transport file, and every fetched shard. The
removed cap is the aggregate-corpus failure that would eventually prevent all later contributions.
Valid growth creates more bounded pages; corrupt, duplicate, inconsistent, privacy-unsafe, or
individually oversized records still fail closed. Temporary shards are disposable transport
artifacts and are rebuilt from accepted submissions on each Pages deployment.

The public suite registry currently contains only `standard` / `1.0`; all five cases are text and
carry capability metadata for future expansion. The only shipped facet is `all-cases-text`.
An inapplicable case records `not_applicable` as its outcome, route, and termination and is excluded
from denominators. A whole-suite all-not-applicable result remains valid private evidence but cannot
be published because every public candidate needs at least one scored case.
Configuration dimensions are fixed as version `1.0`: hardware, model identity including revision or
digest, precision, runtime name/version/backend, runtime configuration, and settings. A documented
but intentionally unused graduation policy requires at least 25 entries across five distinct model
families before a facet earns a dedicated page. No capability view or score exists yet.

The site displays schema `1.1` periods as an “as of” month and supports month filtering and recency
sorting. These controls, like other browser filters and sorts, apply only to loaded rows until every
shard has been fetched.
