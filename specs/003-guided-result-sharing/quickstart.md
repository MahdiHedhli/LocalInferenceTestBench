# Quickstart: Guided result sharing

Create the public hardware descriptor once and keep it owner-only and ignored:

```sh
cp config/hardware.example.json .local/hardware.json
chmod 600 .local/hardware.json
```

### Two-step static-sidecar flow

After a private benchmark has completed, place the categorical output of a separately run compatible
local sampler or adapter at `.local/measurement-evidence.json` and restrict it too:

```sh
cp config/measurement-evidence.example.json .local/measurement-evidence.json
chmod 600 .local/measurement-evidence.json
```

The tracked example is deliberately `nonquiescent`. Replace its example row with actual categorical
sampler or adapter output, and only then replace `source_run_id` with the completed source report's
exact `run_id`; do not use the example as evidence that a run was clean. The sidecar accepts 1–1000
unique model rows. Its
run binding is validated locally and never enters the saved candidate or public pull request.

Besides its private source-run binding, the sidecar contains closed pre/post threshold outcomes,
category names, and optional aggregate determinism only. Do not hand-label an execution-valid run as
clean, and do not put raw memory, thermal, load, swap, process, inventory, path, or additional
timestamp values in the file. If the evidence file is absent or unsafe, local candidate save and
public PR preparation stop; the private benchmark report remains saved.

Use that static file with the separate `litb prepare-submission` command. Do not prepopulate it for
the single-command flow below: `litb run --measurement-sampler` allocates and owns the exact run
binding, then atomically creates or replaces `--measurement-evidence` only after successful pre/run/post
collection.

### Single-command sampler flow

Install hooks, populate `.local/privacy-denylist.txt`, and install Gitleaks 8.30.1 or newer. Saving a
local candidate does not require GitHub CLI:

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile standard \
  --hardware .local/hardware.json \
  --measurement-sampler .local/bin/measurement-sampler \
  --measurement-evidence .local/measurement-evidence.json \
  --submission save
```

For an interactive terminal, omit `--submission`; the prompt appears after an eligible run and Enter
keeps it private.

For a reviewed public PR, authenticate GitHub CLI to `github.com` and run:

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --model <one-public-manifest-id> \
  --profile standard \
  --hardware .local/hardware.json \
  --measurement-sampler .local/bin/measurement-sampler \
  --measurement-evidence .local/measurement-evidence.json \
  --submission pr
```

The sampler is one explicitly trusted POSIX regular non-symlink executable of at most 16 MiB that
produces synchronous closed categorical pre/post samples. It must not be group- or world-writable;
only a private non-writable snapshot of its approved bytes executes. These single-command
run-and-export examples require it. It must stay synchronous and inside its inherited
session/process group. If the system temporary location is `noexec`, select an owner-controlled,
non-repository directory on a writable filesystem that permits execution with `TMPDIR`. A
post sample is collected only after both pre sampling and benchmark execution return successfully.
The resolved temp base is rejected before approved bytes are written when it belongs to an ordinary
or linked worktree, a Git directory, or a bare repository, or repository-routing `GIT_*` state is
active. Its ancestors must be root/current-user owned, shared-writable directories require the
sticky bit, and descriptor-anchored creation/writes resist path swaps. Cleanup performs exact
identity/type checks immediately before descriptor-relative removal; root and same-UID races remain
outside the portable POSIX boundary. Windows and static-sidecar flows use the
separate `prepare-submission` command.

Read the complete JSON and disclosure, then type `PUBLISH`. In a non-interactive environment, add
`--submission-model <report-model-id> --confirm-public`. A successful command prints the PR URL. A
failure leaves the private report and minimized JSON available for retry.

Retry the saved file without loading the model or rerunning inference:

```sh
litb publish-submission \
  --candidate .local/leaderboard-submissions/<submission-id>.json
```

The retry repeats validation and disclosure. It requires literal `PUBLISH` interactively or
`--confirm-public` non-interactively.
