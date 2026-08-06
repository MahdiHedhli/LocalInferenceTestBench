# Quickstart: Guided result sharing

Create the public hardware descriptor once and keep it owner-only and ignored:

```sh
cp config/hardware.example.json .local/hardware.json
chmod 600 .local/hardware.json
```

Before preparing a schema `1.1` public candidate, place the categorical output of a compatible local
measurement sampler or adapter at `.local/measurement-evidence.json` and restrict it too:

```sh
cp config/measurement-evidence.example.json .local/measurement-evidence.json
chmod 600 .local/measurement-evidence.json
```

The tracked example is deliberately `nonquiescent`. Replace its example row with actual categorical
sampler or adapter output, and replace `source_run_id` with the source report's exact `run_id`; do not
use the example as evidence that a run was clean. The sidecar accepts 1–1000 unique model rows. Its
run binding is validated locally and never enters the saved candidate or public pull request.

Besides its private source-run binding, the sidecar contains closed pre/post threshold outcomes,
category names, and optional aggregate determinism only. Do not hand-label an execution-valid run as
clean, and do not put raw memory, thermal, load, swap, process, inventory, path, or additional
timestamp values in the file. If the evidence file is absent or unsafe, local candidate save and
public PR preparation stop; the private benchmark report remains saved.

Install hooks, populate `.local/privacy-denylist.txt`, and install Gitleaks 8.30.1 or newer. Saving a
local candidate does not require GitHub CLI:

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile standard \
  --hardware .local/hardware.json \
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
  --measurement-evidence .local/measurement-evidence.json \
  --submission pr
```

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
