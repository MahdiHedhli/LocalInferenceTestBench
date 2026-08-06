# Quickstart: Prepare a leaderboard submission

This walkthrough uses only synthetic paths and the sanitized hardware example. A real submission is
public, including its hardware and runtime details and the GitHub account that opens the pull
request.

## 1. Finish a standard run

Run smoke first, then create a valid standard report with the normal operator workflow:

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile standard
```

The exporter refuses smoke, limited, invalid, incomplete, or identity-unverified results.

## 2. Describe the hardware used

Copy the example into the ignored local area and restrict its permissions:

```sh
cp config/hardware.example.json .local/hardware.json
chmod 600 .local/hardware.json
```

Edit `.local/hardware.json` with the exact public CPU, memory, accelerator, execution-mode, and
runtime details for the run. List only accelerators that took part in inference. Do not include a
hostname, username, IP address, serial number, inventory ID, device UUID, internal label, or note.

## 3. Prepare one public candidate

First place the categorical output of a compatible local measurement sampler or adapter in the
ignored owner-only `.local/measurement-evidence.json`. Besides its private source-run binding, it may
contain only closed pre/post threshold categories and optional aggregate determinism; do not infer
clean from a valid execution report.

```sh
cp config/measurement-evidence.example.json .local/measurement-evidence.json
chmod 600 .local/measurement-evidence.json
```

The tracked example is deliberately `nonquiescent`, so copying it unchanged cannot claim that a run
was clean. Replace `source_run_id` with the source report's exact `run_id` and replace its example row
with the sampler or adapter output for the selected report model. The file accepts 1–1000 unique
model rows; the run binding is checked locally and does not enter the prepared public candidate.

```sh
litb prepare-submission \
  --report artifacts/<run-record>.json \
  --hardware .local/hardware.json \
  --measurement-evidence .local/measurement-evidence.json \
  --model <report-model-id>
```

The default destination is `.local/leaderboard-submissions`. The command creates a schema `1.1`
owner-only file
whose name is its content digest. A report with one model does not need `--model`. Repeat `--model`
to export several models as separate, unlinked files.

## 4. Review before publishing

Open the prepared file and verify every hardware, runtime, model, setting, case, and metric value.
The file should not contain the source run ID, precise run time, local model selector, manifest digest,
endpoint, account, machine identifier, raw prompt, completion, reasoning, or tool argument.

It does contain a UTC measurement month and categorical measurement conditions. Accepted schema
`1.0` source files remain unchanged, but every new pull request must use `1.1`.

You may select the file on the Pages site for a browser-only fatal UTF-8/BOM, strict JSON,
duplicate-member, closed-schema, and canonical-digest check plus preview. The check does not upload
the file, but it remains a convenience. The Python validator and pull-request gates in continuous
integration are authoritative.

## 5. Propose the record

Copy the reviewed candidate to `site/data/submissions/<submission_id>.json` in a branch, then run:

```sh
python3 scripts/build_leaderboard.py
python3 scripts/build_leaderboard.py --check
python3 -m unittest discover -s tests -v
./scripts/public-check --full-tree --strict
```

Commit both the accepted record and the regenerated `site/data/leaderboard.json`, then open a pull
request using the benchmark submission template. The pull request and your GitHub account are public
before checks finish. The JSON record has no contributor field.

## Expected result

After validation, review, and merge, the Pages workflow rebuilds the same dataset and publishes the
entry. The entry receives a quality rank based only on semantic and exact-format scores. Observed
latency and throughput appear with the submitted hardware and runtime but do not change rank.
