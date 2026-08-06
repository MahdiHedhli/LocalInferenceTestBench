# Submitting a benchmark

The public leaderboard accepts identifier-minimized schema `1.1` results from the registered public
suite. The sole current member is `standard` / `1.0`. Each record covers one model and includes the
exact hardware and runtime name and version used for inference. It can also include a closed
runtime-configuration snapshot. The record
does not include a contributor field, but the GitHub account and pull request used to submit it are
public.

Hardware and performance can make a setup recognizable even after direct machine identifiers are
removed. Read the complete prepared file before you publish it.

## Fast path: decide when the run finishes

A valid interactive `standard` run ends with a safe-default prompt:

```text
Share this result? [Enter] keep private, [s] save minimized JSON, [p] open public PR:
```

`Enter` keeps the report private. `s` creates owner-only identifier-minimized JSON under
`.local/leaderboard-submissions`. `p` saves the same JSON, displays the complete proposed public
record, identifies the GitHub account that will be visible, and requires `PUBLISH` before creating a
branch and pull request. A failed export or GitHub step never removes the private report.

Save and PR preparation require `.local/measurement-evidence.json` by default. A valid execution
report alone does not establish clean measurement conditions. If the ignored owner-only categorical
sidecar is absent or invalid, preparation stops while the private report remains saved.

For a non-interactive single-command POSIX run, also provide an explicitly trusted sampler executable.
The CLI invokes it immediately before the run and, only after a successful pre sample and successful
benchmark return, immediately after the run, then writes its exact-bound closed output to the
evidence path. Without that integration, use the two-step `prepare-submission` path;
the CLI will not race an external process or relabel a pre-existing sidecar after inference.

For scripts or unattended runs, choose the action explicitly:

```sh
# Local JSON only; no GitHub command or network write.
litb run <run-options> \
  --profile standard \
  --hardware .local/hardware.json \
  --measurement-sampler .local/bin/measurement-sampler \
  --measurement-evidence .local/measurement-evidence.json \
  --submission save

# Public branch and pull request. This never writes directly to main.
litb run <run-options> \
  --profile standard \
  --hardware .local/hardware.json \
  --measurement-sampler .local/bin/measurement-sampler \
  --measurement-evidence .local/measurement-evidence.json \
  --submission pr \
  --submission-model <report-model-id> \
  --confirm-public
```

The PR path requires an authenticated [GitHub CLI](https://cli.github.com/) for `github.com`,
Gitleaks 8.30.1 or newer, and a populated owner-only ignored `.local/privacy-denylist.txt`. If the
account cannot create a branch in the canonical repository, the tool creates or reuses that
account's public fork. It then opens a PR against the canonical `main` branch.

## Retry a saved candidate without rerunning inference

The local minimized JSON is reusable when you cancel at the disclosure prompt or publication fails:

```sh
litb publish-submission \
  --candidate .local/leaderboard-submissions/<submission-id>.json
```

The command accepts only an owner-only regular file that is Git-ignored when it is inside a
worktree, and whose filename, content digest, contract, and canonical bytes all match. A secure
candidate saved outside a worktree remains reusable. It displays the full JSON and authenticated GitHub
identity, destination, visibility, and branch/PR action before asking for literal `PUBLISH`. A
decline performs no mutating GitHub action. For an unattended retry, add `--confirm-public`; without
that flag, non-interactive publication stops before GitHub preflight.

## Before you start

You need:

- a valid report from the current `standard` profile;
- verified model preflight and a matching runtime identity;
- ignored owner-only categorical measurement evidence for every selected model;
- Python 3.11 or newer;
- the repository hooks and local privacy denylist configured; and
- Gitleaks 8.30.1 or newer.

GitHub CLI is needed only for the automated public-PR option. Saving minimized JSON remains entirely
local.

Do not use a smoke, limited, invalid, partial, or hand-edited source report. The exporter rejects
these records.

Use short visible-ASCII product and revision labels in the public descriptor and model provenance.
URLs, network/private-host shapes, machine identifiers, and reviewer-directed prose are rejected in
both the Python and browser validators.

## Describe the environment you want to publish

Create the descriptor in the ignored local directory:

```sh
cp config/hardware.example.json .local/hardware.json
chmod 600 .local/hardware.json
```

Edit the file with the exact public details for the run:

- CPU model and logical core count;
- system memory in GB and whether memory is shared, discrete, mixed, or unknown;
- each accelerator used for inference, including its kind, model, count, and memory when discrete;
- whether inference used the CPU, accelerator, both, or an unknown path; and
- serving runtime name, version, and compute backend;
- when known, the configured context window, concurrent-request count, speculative-decoding state,
  and offload mode.

The `runtime_configuration` object is optional for compatibility with earlier records. When it is
present, all four fields are explicit: use `null` for an unknown context window or concurrent-request
count, and `unknown` for an unknown categorical state. Do not guess defaults from the runtime or
hardware. A known configured context window must be at least the model's `max_output_tokens` value.

List only devices that participated in inference. Do not add a hostname, username, account, IP
address, private domain, serial number, inventory tag, MAC address, device UUID, local service name,
or free-form note. The closed contract has no place for those values.

The descriptor must remain ignored by Git and owner-only. The exporter fails closed if the file is a
symlink, tracked, not ignored, or broadly readable.

## Supply categorical measurement evidence

Copy the closed example, then replace its example row with output from a compatible local sampler or
adapter and restrict the file:

```sh
cp config/measurement-evidence.example.json .local/measurement-evidence.json
chmod 600 .local/measurement-evidence.json
```

The example is deliberately nonquiescent so copying it cannot accidentally create a clean claim.
Replace its top-level `source_run_id` with the exact `run_id` from the report being prepared.

The sidecar is separate from the run report because the report's execution validity describes
endpoint, identity, request, and scoring integrity—not host quiescence. Each selected model needs an
exact model-ID match with pre/post outcomes and only these closed threshold categories: memory
pressure, thermal state, sustained load, swap, and resident models. An optional determinism block
may retain only 3–5-run aggregate rates and stability booleans. The sidecar must contain 1–1000
unique model rows; a stale `source_run_id` or an oversized model list is rejected before export.

Do not hand-assert that a run was clean. Do not include raw readings, process names, inventory,
paths, precise timestamps, or free text. The file must be ignored, owner-only, regular, and
non-symlinked. Missing, mismatched, unsafe, or inconsistent evidence blocks candidate preparation and
is never uploaded. The top-level source binding is used only for local validation and is stripped
with the report's run ID from every public candidate. The normative shape is
[`measurement-evidence.schema.json`](../specs/002-anonymized-leaderboard/contracts/measurement-evidence.schema.json).

### Single-command sampler adapter

`--measurement-sampler` names one explicitly trusted local POSIX executable, not a shell command or
an argument string. It must be at most 16 MiB, regular, non-symlinked, and not writable by the group
or world. Its approved file identity and content are rechecked before each launch, and the CLI
executes only a private non-writable snapshot of those approved bytes. The CLI
invokes `pre` with a 30-second bound immediately before the complete benchmark run and invokes
`post` immediately afterward only if `pre` succeeded and the complete benchmark returned
successfully. If benchmark execution raises, no post sample is collected and no export is attempted.
The adapter receives one compact JSON object on standard input. The `"schema_version": "1.0"`
shown here versions the private sampler/evidence protocol; it is independent of the public
leaderboard candidate schema `1.1`:

```json
{
  "model_ids": ["public-model-id"],
  "phase": "pre",
  "schema_version": "1.0",
  "source_run_id": "<generated-run-id>"
}
```

It must synchronously sample the current host conditions and return exactly this closed shape on
standard output, echoing all binding fields unchanged:

```json
{
  "model_ids": ["public-model-id"],
  "phase": "pre",
  "sample": {
    "categories": [],
    "outcome": "within_thresholds"
  },
  "schema_version": "1.0",
  "source_run_id": "<generated-run-id>"
}
```

The `post` call uses the same shape with `phase` set to `post`. The adapter must not cache an older
sample. Only `within_thresholds` or `threshold_crossed` and the five closed category names are legal;
there is no field for raw readings, device inventory, process names, paths, timestamps, or free text.
The CLI derives the public validity and hard-threshold boolean from those two samples, creates one
row per report model, validates the ordinary sidecar contract, and atomically writes it owner-only
to `--measurement-evidence`. A model subset may then be selected with `--submission-model`.

The adapter receives an allowlisted environment without credential variables. Its stderr is
discarded and its stdout is read through a 256 KiB in-flight cap, so diagnostics must remain local.
A dedicated standard-library supervisor starts the approved snapshot in an isolated process group
while passing its standard input and output directly through the existing bounded channels. Cleanup
observes leader exit without reaping it and signals the group before the reap, so the numeric PGID
cannot be reused between those operations. It uses `waitid` where available and `kqueue` on older
supported macOS Python. On Linux the supervisor fails closed unless it can become a child subreaper, then
boundedly reaps adopted descendants after the direct child exits. macOS uses the same
kill-before-reap ordering and relies on the host init process for orphan reaping.

The sampler is a trusted synchronous adapter. It must not daemonize, call `setsid` or `setpgid`, or
otherwise intentionally escape the inherited process group; portable POSIX process management
cannot contain a process that deliberately leaves that boundary without a separate OS sandbox or
cgroup. An uninterruptible kernel task may outlive any signal, so the bridge reports a bounded
categorical cleanup failure rather than waiting indefinitely. Snapshot creation uses an owner-only
directory under the system temporary location. If its filesystem is mounted `noexec`, set `TMPDIR`
to an owner-controlled, non-repository directory on a writable filesystem that permits execution.
The CLI resolves that base and rejects ordinary worktrees, linked worktrees, Git directories, and
bare repositories, plus repository-routing `GIT_*` state, before writing approved sampler bytes.
All resolved ancestors must be root/current-user owned, with the sticky bit required for shared
writes. Creation and writes are anchored to open directory descriptors. Cleanup uses non-following,
nonblocking exact-identity checks immediately before descriptor-relative removal. Root and same-UID
processes are outside this portable POSIX containment boundary and can already access the bytes.

Timeout, nonzero exit, malformed/duplicate JSON, extra fields, mismatched bindings, file replacement,
or incomplete samples fail closed after the private run report is saved. The owner-only sidecar is
bounded at 2 MiB so every valid 1–1000-row evidence document remains representable.

The single-command sampler fails closed on Windows until equivalent process-tree containment is
available. Windows users can run the benchmark privately, create an exact-bound categorical sidecar
with a compatible local collector, and use the separate `prepare-submission` command.

## Manual path: prepare the minimized record

For a single-model report:

```sh
litb prepare-submission \
  --report artifacts/<run-record>.json \
  --hardware .local/hardware.json \
  --measurement-evidence .local/measurement-evidence.json
```

For a report containing several models, choose one or repeat the option:

```sh
litb prepare-submission \
  --report artifacts/<run-record>.json \
  --hardware .local/hardware.json \
  --measurement-evidence .local/measurement-evidence.json \
  --model <report-model-id>
```

The default destination is `.local/leaderboard-submissions`. Each model gets its own owner-only JSON
file. Its filename is a SHA-256 digest of the canonical minimized content. The digest catches content
changes and exact duplicates. It does not prove that the run took place.

## Read the candidate

Check every value before it enters a public branch. A candidate contains:

- public schema `1.1`, plus registered suite and profile versions;
- a UTC month-resolution measurement period, measurement validity, closed pre/post condition
  categories, and optional aggregate determinism;
- public model provenance and generation settings;
- the exact public hardware and runtime descriptor, including the optional reported runtime
  configuration;
- one categorical outcome, route, and termination for each standard case; and
- aggregate quality counts, mean latency, usage coverage, and optional weighted throughput.

It does not contain the source run ID or precise time, manifest digest, local model selector, endpoint,
credential, environment content, contributor, hostname, account, network data, device identifier,
raw prompt, completion, reasoning, tool argument, or per-case performance trace.

Every case also records its registry-defined task capability and modality. All five current cases are
text; these tags are validation seams and do not create a capability score or view.

You can select the file on the
[Pages site](https://mahdihedhli.github.io/LocalInferenceTestBench/#submit) to parse its strict public
JSON with fatal UTF-8/BOM rejection, reject duplicate member names, validate the closed schema,
recompute the canonical content digest, and preview the model and hardware details. The file stays in
your browser. This convenience check does not replace the authoritative Python, privacy,
pull-request, and hosted validation gates.

## Add the candidate to a branch

For the automated review and merge lane, create the deterministic branch whose suffix is the
candidate's submission ID:

```sh
litb_submission_id="replace-with-the-64-character-submission-id"
git switch -c "litb/submission-${litb_submission_id}"
```

The digest in the branch name must match the one added JSON filename and its canonical content ID.
Another branch name can still be reviewed manually, but it is ineligible for automated approval and
merge.

Copy the file without renaming it:

```sh
cp .local/leaderboard-submissions/<submission-id>.json \
  site/data/submissions/<submission-id>.json

python3 scripts/build_leaderboard.py
python3 scripts/build_leaderboard.py --check
```

Commit the candidate and the regenerated `site/data/leaderboard.json`. Do not edit the generated
leaderboard by hand.

New pull requests must add schema `1.1`. Accepted `1.0` files stay unchanged under their original
digests, while open or locally saved `1.0` candidates must be regenerated from the source report,
descriptor, and measurement evidence. Do not edit a historical file to add missing fields.

The committed generated file remains the canonical monolith while it fits the public per-file cap.
When the corpus crosses that cap, the same command switches it deterministically to a compact index.
Leaderboard shards are generated only in the trusted GitHub Pages artifact; contributors never add
or commit shard files. Every accepted digest-named submission remains addressable in the repository.

The automated PR path performs these steps in a private temporary directory cloned from the fixed
canonical upstream. It stages only one new digest-named submission and the regenerated leaderboard,
runs the same contract, deterministic-build, privacy, unit, and redacted secret checks, and uploads
only those two public files. It never stages or transmits the source report, endpoint, environment
file, hardware descriptor, measurement sidecar, privacy denylist, or artifact directory.

## Run the release checks

```sh
python3 -m unittest discover -s tests -v
./scripts/public-check --full-tree --strict
```

The tests validate the closed fields, content ID, filename, case arithmetic, rank, and deterministic
dataset. The publication gate scans tracked content and history without printing matched values.

## Open the pull request

Use the benchmark submission template. Confirm that you read the JSON, that the hardware describes
only the inference path, and that you accept public display of the hardware, performance figures,
pull request, and GitHub account.

Trusted base code validates the exact two-file shape, ordinary file modes, schema, canonical digest,
duplicate status, and byte-exact generated leaderboard before posting one fixed GitHub Actions audit
marker bound to the full base and head SHAs. After that marker job succeeds, it directly invokes a
local reusable workflow from the same trusted caller commit with the exact pull request number, full
base SHA, full head SHA, and marker comment ID. The reusable workflow retrieves the exact live,
unedited marker, verifies GitHub Actions user ID `41898282` and App ID `15368`, and independently
repeats the complete content and repository-state validation before it may arm native squash
auto-merge and add an exact-head approval from the configured reviewer account. The marker is audit
evidence, not authorization by itself.

The required `Trusted benchmark boundary` status is a final aggregator. It stays pending until the
marker and reusable automation jobs complete successfully, so an interrupted partial run cannot
leave an early green boundary that later combines with an unrelated approval. The
`litb/submission-<submission-id>` namespace is reserved; a branch using it fails the boundary if its
diff becomes general, mixed, or otherwise ineligible for the exact submission lane.

Codex and CodeRabbit may review on a best-effort advisory basis, but automation does not wait for
either service. A clean, absent, failed, skipped, or rate-limited response is not a merge signal.
Repository-`GITHUB_TOKEN` comments do not start downstream `issue_comment` workflows, so a clean
Codex comment is no longer the gate. Any finding expressed as a review thread or changes request in
time for the final live revalidation, stale base/head, malformed record, or failed required check
leaves the pull request open for a maintainer.

GitHub may briefly report unknown mergeability; the workflow retries that state only for a bounded
interval and otherwise leaves the PR open. An established `unstable` state may continue to native
auto-merge, but it is not treated as a passed check. GitHub still waits for every configured required
check. Administration-only protection settings are mandatory repository-operator prerequisites and
are not claimed as per-run evidence by the read-only workflow. The trusted caller explicitly maps
repository secret `ERNEST_REVIEW_TOKEN` to the reusable workflow's `reviewer_token`; it never
inherits secrets, and only the final mutation step binds that credential.

Retries remain exact-head operations. If a partial automation run already left the configured
reviewer approval on the current head, the workflow may reuse that approval and re-arm missing native
auto-merge only after every authorization check runs again and while the final required boundary
remains pending. That pending context prevents the retry from becoming an already-clean approved PR.
A dismissed approval, change request, or approval for another head cannot be reused.

Published entries remain self-reported, schema-validated, and not independently reproduced. Bot
review, the Actions audit marker, automated reviewer-account approval, and a content digest are
publication-policy evidence—not evidence that a benchmark run occurred or an independent
substantive reproduction. Deterministic validation proves schema conformance and integrity of the
published bytes, not provenance. Quality is displayed as representative pass counts plus 95% Wilson
intervals. Transitive semantic/exact overlap produces an explicit rank band. Latency and throughput
are shown with their hardware context but never affect rank.

Records with the same versioned hardware/model/runtime/settings configuration collapse to one
bounded cell. Accepted hashes increase the corroboration count and performance spread, but are not
treated as independent people or pooled to narrow the quality interval. The cell uses a documented
score-neutral representative and keeps every original digest-named record in the repository. A
visible plausibility caution is only an outlier-review hint; it never verifies, drops, gates, or
ranks the result.

The site defaults to clean self-reported measurement evidence. Users can deliberately include
nonquiescent, degraded-midrun, or `legacy_unreported` rows; the filter does not verify any claim.
Legacy rows have no synthesized period or condition evidence.

Automated benchmark PRs are restricted to exactly one append-only submission JSON file plus the
deterministically regenerated leaderboard. Mixed code-and-data PRs, rewrites, deletes, renames, and
extra files are rejected by continuous integration.

Auto-merge never uses the contributor-editable pull-request title or body as the squash commit
message. It uses fixed bounded text that labels the record self-reported and the run unverified,
plus the validated submission digest, and never bypasses branch protection or pushes directly to
`main`.
