# Submitting a benchmark

The public leaderboard accepts identifier-minimized results from the current standard suite. Each
record covers one model and includes the exact hardware and runtime name and version used for
inference. It can also include a closed runtime-configuration snapshot. The record
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
branch and reviewed pull request. A failed export or GitHub step never removes the private report.

For scripts or unattended runs, choose the action explicitly:

```sh
# Local JSON only; no GitHub command or network write.
litb run <run-options> \
  --profile standard \
  --hardware .local/hardware.json \
  --submission save

# Public branch and pull request. This never writes directly to main.
litb run <run-options> \
  --profile standard \
  --hardware .local/hardware.json \
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
- Python 3.11 or newer;
- the repository hooks and local privacy denylist configured; and
- Gitleaks 8.30.1 or newer.

GitHub CLI is needed only for the automated public-PR option. Saving minimized JSON remains entirely
local.

Do not use a smoke, limited, invalid, partial, or hand-edited source report. The exporter rejects
these records.

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

## Manual path: prepare the minimized record

For a single-model report:

```sh
litb prepare-submission \
  --report artifacts/<run-record>.json \
  --hardware .local/hardware.json
```

For a report containing several models, choose one or repeat the option:

```sh
litb prepare-submission \
  --report artifacts/<run-record>.json \
  --hardware .local/hardware.json \
  --model <report-model-id>
```

The default destination is `.local/leaderboard-submissions`. Each model gets its own owner-only JSON
file. Its filename is a SHA-256 digest of the canonical minimized content. The digest catches content
changes and exact duplicates. It does not prove that the run took place.

## Read the candidate

Check every value before it enters a public branch. A candidate contains:

- suite and standard-profile versions;
- public model provenance and generation settings;
- the exact public hardware and runtime descriptor, including the optional reported runtime
  configuration;
- one categorical outcome, route, and termination for each standard case; and
- aggregate quality counts, mean latency, usage coverage, and optional weighted throughput.

It does not contain the source run ID or time, manifest digest, local model selector, endpoint,
credential, environment content, contributor, hostname, account, network data, device identifier,
raw prompt, completion, reasoning, tool argument, or per-case performance trace.

You can select the file on the
[Pages site](https://mahdihedhli.github.io/LocalInferenceTestBench/#submit) to check its basic public
shape and preview the model and hardware details. The file stays in your browser. This convenience
check does not verify the content digest or replace local and hosted validation.

## Add the candidate to a branch

Copy the file without renaming it:

```sh
cp .local/leaderboard-submissions/<submission-id>.json \
  site/data/submissions/<submission-id>.json

python3 scripts/build_leaderboard.py
python3 scripts/build_leaderboard.py --check
```

Commit the candidate and the regenerated `site/data/leaderboard.json`. Do not edit the generated
leaderboard by hand.

The automated PR path performs these steps in a private temporary directory cloned from the fixed
canonical upstream. It stages only one new digest-named submission and the regenerated leaderboard,
runs the same contract, deterministic-build, privacy, unit, and redacted secret checks, and uploads
only those two public files. It never stages or transmits the source report, endpoint, environment
file, hardware descriptor, privacy denylist, or artifact directory.

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

Maintainers review the record and automated checks before merge. Published entries are
self-reported, schema-validated, maintainer-reviewed, and not independently reproduced. Quality rank
uses semantic score first and exact-format score second. Latency and throughput are shown with their
hardware context but never affect rank.

Automated benchmark PRs are restricted to exactly one append-only submission JSON file plus the
deterministically regenerated leaderboard. Mixed code-and-data PRs, rewrites, deletes, renames, and
extra files are rejected by continuous integration.
