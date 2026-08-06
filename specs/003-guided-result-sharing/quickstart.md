# Quickstart: Guided result sharing

Create the public hardware descriptor once and keep it owner-only and ignored:

```sh
cp config/hardware.example.json .local/hardware.json
chmod 600 .local/hardware.json
```

Install hooks, populate `.local/privacy-denylist.txt`, and install Gitleaks 8.30.1 or newer. Saving a
local candidate does not require GitHub CLI:

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile standard \
  --hardware .local/hardware.json \
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
