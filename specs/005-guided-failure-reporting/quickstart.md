# Quickstart: Guided benchmark failure reporting

Run the benchmark normally. Interactive execution defaults to the opt-in failure prompt:

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile standard
```

If an actionable execution category is detected, the CLI:

1. preserves any completed private report;
2. prints the complete closed failure draft;
3. explains that opening the URL sends those fields to GitHub and may retain them in browser or
   network history;
4. asks `Open this sanitized draft in GitHub? [y/N]`;
5. opens the fixed issue composer only for one ASCII `y` or `Y`, with surrounding ASCII whitespace
   allowed.

Review the issue again in GitHub. Clicking Submit creates the public issue. Do not add logs,
tracebacks, prompts, completions, endpoints, credentials, paths, hostnames, or raw hardware
inventory in the browser editor.

To suppress the prompt:

```sh
litb run \
  --manifest .local/models.json \
  --endpoint http://127.0.0.1:1234/v1 \
  --profile standard \
  --failure-report none
```

Non-interactive runs never open a browser, including when `--failure-report ask` is explicit.
Failure reporting does not alter the benchmark's exit status; Ctrl-C while the optional prompt is
active declines that prompt and returns the original status.
